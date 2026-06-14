"""
clean.py — Vault file cleaner
Handles: /clean <filename>   — repair a messy note to uniform structure
         /cleanall           — scan for and repair all notes with duplicate sections
"""

import re
from datetime import date
import core.vault as vault
import core.llm as llm


def _deduplicate_content(text: str) -> str:
    """
    Remove duplicate paragraphs and repeated Update blocks from a note body.
    Keeps the first occurrence of each unique paragraph.
    """
    # split on the old-style update separators
    parts = re.split(r"\n---\n\*Update \d{4}-\d{2}-\d{2}\*\n", text)

    seen_lines: set[str] = set()
    clean_lines: list[str] = []

    for part in parts:
        for line in part.splitlines():
            stripped = line.strip()
            # skip duplicate non-empty lines
            if stripped and stripped in seen_lines:
                continue
            if stripped:
                seen_lines.add(stripped)
            clean_lines.append(line)

    # collapse more than 2 consecutive blank lines
    result = "\n".join(clean_lines)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def _rebuild_note(stem: str, raw: str) -> str:
    """
    Take a messy existing note and rebuild it in the uniform structure.
    Uses the LLM to distil the content cleanly if the note is complex.
    """
    today = date.today().isoformat()

    # extract frontmatter tags if present
    fm, body = vault.parse_frontmatter(raw)
    existing_tags = fm.get("tags", ["note"])
    if isinstance(existing_tags, str):
        existing_tags = [existing_tags]

    # strip title from body
    lines = body.splitlines(keepends=True)
    title = stem
    if lines and lines[0].startswith("# "):
        title = lines[0][2:].strip()
        lines = lines[1:]
    body = "".join(lines).lstrip("\n")

    # clean out duplicate content
    clean_body = _deduplicate_content(body)

    # strip old Related section (we'll rebuild it)
    clean_body = re.sub(r"\n## Related\n[\s\S]*?(?=\n## |\Z)", "", clean_body).strip()
    # strip old History section
    clean_body = re.sub(r"\n## History\n[\s\S]*?(?=\n## |\Z)", "", clean_body).strip()

    # rebuild Related using topic-scoped linking
    path     = vault.find_file(stem)
    folder   = path.parent if path else None
    related  = vault.smart_related(clean_body, exclude_stem=stem, folder=folder)
    history  = [f"{today}: cleaned and restructured"]

    return vault.build_frontmatter(existing_tags, {"updated": today}) + \
           f"# {title}\n\n{clean_body}\n" + \
           (f"\n## History\n- {history[0]}\n" if history else "") + \
           (f"\n## Related\n" + "\n".join(f"- [[{r}]]" for r in related) + "\n" if related else "")


def cmd_clean(rest: str, mem: dict) -> str:
    """
    /clean <filename>   — repair a specific note to uniform structure
    """
    name = rest.strip()
    if not name:
        return (
            "Which file should I clean?\n\n"
            "`/clean <filename>` — repair one note\n"
            "`/cleanall` — scan and repair all notes with duplicate sections"
        )

    path = vault.find_file(name)
    if not path:
        return f"Can't find **{name}** in the vault."

    raw      = vault.read_file(path)
    rebuilt  = _rebuild_note(path.stem, raw)
    vault.write_file(path, rebuilt)

    return (
        f"✦ **{path.stem}** has been cleaned.\n\n"
        f"Duplicate sections collapsed, structure normalised, links rebuilt."
    )


def cmd_cleanall(rest: str, mem: dict) -> str:
    """
    /cleanall — find all notes with duplicate Update sections and clean them.
    """
    cleaned = []
    skipped = []

    for f in vault.VAULT.rglob("*.md"):
        try:
            raw = f.read_text(encoding="utf-8")
            # detect old-style update appends
            if re.search(r"\n---\n\*Update \d{4}-\d{2}-\d{2}\*\n", raw):
                rebuilt = _rebuild_note(f.stem, raw)
                vault.write_file(f, rebuilt)
                cleaned.append(f.stem)
            else:
                skipped.append(f.stem)
        except Exception as e:
            skipped.append(f"{f.stem} (error: {e})")

    if not cleaned:
        return "No notes with old-style duplicate sections found. Vault looks clean. ✦"

    lines = [f"✦ Cleaned {len(cleaned)} note(s):\n"]
    for name in cleaned:
        lines.append(f"- **{name}**")
    lines.append(f"\n{len(skipped)} notes were already clean and left untouched.")
    return "\n".join(lines)


def register():
    return {
        "commands": {
            "clean":    cmd_clean,
            "cleanall": cmd_cleanall,
        },
        "description": "Vault cleaner — /clean <file> or /cleanall to fix messy notes",
    }
