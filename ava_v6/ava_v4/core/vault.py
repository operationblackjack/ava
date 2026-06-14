"""
vault.py — All Obsidian vault read / write operations

Key rules:
  1. UNIFORM FILE STRUCTURE — frontmatter / title / body / History / Related.
  2. TOPIC-SCOPED LINKING — notes only link within the same folder.
  3. NO SILENT WRITES — create_note / create_idea return a PENDING action dict
     instead of writing immediately. main.py shows the user a confirmation
     prompt and only calls commit_pending() on approval.
"""

import re
from datetime import date
from pathlib import Path
from core.config import (
    VAULT, NOTES_DIR, IDEAS_DIR, SKILLS_DIR, PROJECTS_DIR,
    SESSIONS_DIR, JOURNAL_DIR, TEMPLATES_DIR, TASTES_DIR,
    ABOUT_FILE, SESSIONS_INDEX, PROTECTED,
)

# ── Cache ──────────────────────────────────────────────────────────────────────
_stems_cache: set[str] | None = None
_about_cache: str | None = None


def invalidate():
    global _stems_cache, _about_cache
    _stems_cache = None
    _about_cache = None


def stems() -> set[str]:
    global _stems_cache
    if _stems_cache is None:
        _stems_cache = {f.stem for f in VAULT.rglob("*.md")}
    return _stems_cache


def about() -> str:
    global _about_cache
    if _about_cache is None:
        _about_cache = read_file(ABOUT_FILE) or "No About Me file found yet."
    return _about_cache


def ensure_dirs():
    for d in [NOTES_DIR, IDEAS_DIR, SKILLS_DIR, PROJECTS_DIR,
              SESSIONS_DIR, JOURNAL_DIR, TEMPLATES_DIR, TASTES_DIR]:
        d.mkdir(parents=True, exist_ok=True)


# ── Low-level I/O ──────────────────────────────────────────────────────────────
def write_file(path: Path, text: str) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        invalidate()
        return True
    except Exception as e:
        print(f"  [vault write error: {e}]")
        return False


def read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def safe_name(title: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "-", title).strip()


def parse_frontmatter(content: str) -> tuple[dict, str]:
    if not content.startswith("---"):
        return {}, content
    end = content.find("---", 3)
    if end == -1:
        return {}, content
    fm_block = content[3:end].strip()
    body = content[end + 3:].lstrip()
    fm: dict = {}
    for line in fm_block.splitlines():
        if ":" in line and not line.startswith(" ") and not line.startswith("-"):
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
        elif line.startswith("  - ") and fm:
            last_key = list(fm.keys())[-1]
            if isinstance(fm[last_key], list):
                fm[last_key].append(line[4:].strip())
            else:
                fm[last_key] = [line[4:].strip()]
    return fm, body


def build_frontmatter(tags: list[str], extra: dict | None = None) -> str:
    today = date.today().isoformat()
    tag_lines = "\n".join(f"  - {t}" for t in tags)
    fm = f"---\ntags:\n{tag_lines}\ndate: {today}"
    if extra:
        for k, v in extra.items():
            fm += f"\n{k}: {v}"
    return fm + "\n---\n\n"


def strip_frontmatter(content: str) -> str:
    _, body = parse_frontmatter(content)
    return body


# ── Section parser ─────────────────────────────────────────────────────────────
def _split_sections(body: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current_key = ""
    current_lines: list[str] = []
    for line in body.splitlines(keepends=True):
        m = re.match(r"^(#{1,3})\s+(.+)", line)
        if m:
            sections[current_key] = "".join(current_lines)
            current_key = m.group(2).strip()
            current_lines = [line]
        else:
            current_lines.append(line)
    sections[current_key] = "".join(current_lines)
    return sections


_MANAGED_SECTIONS = {"history", "related"}


def _build_note(title: str, body: str, tags: list[str],
                history: list[str], related: list[str],
                extra_fm: dict | None = None) -> str:
    fm = build_frontmatter(tags, extra_fm)
    parts = [fm, f"# {title}\n\n", body.rstrip()]
    if history:
        parts.append("\n\n## History\n" + "\n".join(f"- {h}" for h in history))
    if related:
        parts.append("\n\n## Related\n" + "\n".join(f"- [[{r}]]" for r in related))
    parts.append("\n")
    return "".join(parts)


def _extract_body(full_content: str) -> tuple[str, list[str], list[str]]:
    _, raw_body = parse_frontmatter(full_content)
    lines = raw_body.splitlines(keepends=True)
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    raw_body = "".join(lines).lstrip("\n")
    sections = _split_sections(raw_body)
    history: list[str] = []
    related: list[str] = []
    body_parts: list[str] = []
    for heading, text in sections.items():
        h = heading.lower()
        if h == "history":
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("- "):
                    history.append(line[2:])
        elif h == "related":
            for link in re.findall(r"\[\[(.+?)\]\]", text):
                related.append(link.strip())
        elif heading not in _MANAGED_SECTIONS:
            body_parts.append(text)
    body = "".join(body_parts).strip()
    return body, history, related


# ── Topic-scoped linking ───────────────────────────────────────────────────────
def smart_related(content: str, exclude_stem: str = "",
                  folder: Path | None = None,
                  max_links: int = 4, min_overlap: int = 3) -> list[str]:
    STOP = {
        "this", "that", "with", "from", "have", "will", "your", "they",
        "been", "what", "when", "were", "their", "there", "about", "which",
        "some", "more", "also", "into", "note", "file", "update", "added",
        "tags", "date", "related", "notes", "ideas", "vault", "just",
    }
    search_folder = folder or NOTES_DIR
    words = {w for w in re.findall(r"\b[a-zA-Z]{4,}\b", content.lower()) if w not in STOP}
    if not words:
        return []
    scores: dict[str, int] = {}
    try:
        candidates = list(search_folder.glob("*.md"))
    except Exception:
        return []
    for f in candidates:
        if f.stem == exclude_stem:
            continue
        try:
            note_words = {w for w in re.findall(r"\b[a-zA-Z]{4,}\b",
                          f.read_text(encoding="utf-8").lower()) if w not in STOP}
            overlap = len(words & note_words)
            if overlap >= min_overlap:
                scores[f.stem] = overlap
        except Exception:
            continue
    top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:max_links]
    return [stem for stem, _ in top]


def find_orphans(limit: int = 10) -> list[Path]:
    all_files = list(VAULT.rglob("*.md"))
    linked: set[str] = set()
    for f in all_files:
        try:
            for link in re.findall(r"\[\[(.+?)(?:\|.+?)?\]\]", f.read_text(encoding="utf-8")):
                linked.add(link.strip())
        except Exception:
            continue
    orphans = [f for f in all_files if f.stem not in linked]
    return orphans[:limit]


# ── Exact-match resolution ─────────────────────────────────────────────────────
def find_file(name: str) -> Path | None:
    """Find a .md file anywhere in the vault by stem, case-insensitive."""
    name_lower = name.lower()
    for f in VAULT.rglob("*.md"):
        if f.stem.lower() == name_lower:
            return f
    return None


def find_closest_file(title: str) -> Path | None:
    """
    Given a title AVA wants to write, find an existing file that is
    clearly the same thing — exact stem match or very close fuzzy match.
    Returns None if nothing is close enough (meaning: create new).
    """
    fname = safe_name(title).lower()
    # 1. exact stem match
    exact = find_file(fname)
    if exact:
        return exact
    # 2. one is a substring of the other (catches "About Me" vs "About Me Friends")
    for f in VAULT.rglob("*.md"):
        fs = f.stem.lower()
        if fs in fname or fname in fs:
            return f
    return None


# ── Pending action system ──────────────────────────────────────────────────────
# Instead of writing files immediately, AVA stages a list of pending actions.
# main.py shows a confirmation prompt, then calls commit() or discard().

class PendingAction:
    """A file write that hasn't been confirmed by the user yet."""
    def __init__(self, action_type: str, title: str, content: str,
                 tags: list[str], folder: Path, is_update: bool,
                 existing_path: Path | None, suggested_links: list[str]):
        self.action_type    = action_type       # "note" | "idea" | "about"
        self.title          = title
        self.content        = content
        self.tags           = tags
        self.folder         = folder
        self.is_update      = is_update         # True = updating existing file
        self.existing_path  = existing_path     # path of file being updated
        self.suggested_links = suggested_links  # auto-detected related files

    def describe(self) -> str:
        verb   = "Update" if self.is_update else "Create"
        target = self.existing_path.name if self.existing_path else f"{safe_name(self.title)}.md"
        loc    = str(self.folder).split("/")[-1] if "/" in str(self.folder) else str(self.folder).split("\\")[-1]
        lines  = [f"{verb} **{target}** in {loc}/"]
        if self.suggested_links:
            lines.append(f"  Link to: {', '.join(f'[[{l}]]' for l in self.suggested_links)}")
        return "\n".join(lines)

    def commit(self, approved_links: list[str] | None = None) -> tuple[str, str]:
        """Execute the write. Returns (status, filename_stem)."""
        today   = date.today().isoformat()
        related = approved_links if approved_links is not None else self.suggested_links
        fname   = safe_name(self.title)

        if self.action_type == "about":
            _commit_about(self.content)
            return "updated", "About Me"

        path = self.existing_path or (self.folder / f"{fname}.md")

        if self.is_update and path.exists():
            existing = read_file(path)
            body, history, _ = _extract_body(existing)
            new_paragraphs = [
                p.strip() for p in self.content.split("\n\n")
                if p.strip() and p.strip().lower() not in body.lower()
            ]
            if new_paragraphs:
                body = body.rstrip() + "\n\n" + "\n\n".join(new_paragraphs)
            history.insert(0, f"{today}: updated")
            fm, _ = parse_frontmatter(existing)
            orig_tags = fm.get("tags", self.tags)
            if isinstance(orig_tags, str):
                orig_tags = [orig_tags]
            note_str = _build_note(self.title, body, orig_tags, history, related,
                                   extra_fm={"updated": today})
            write_file(path, note_str)
            return "updated", path.stem
        else:
            history  = [f"{today}: created"]
            note_str = _build_note(self.title, self.content.strip(),
                                   self.tags, history, related)
            write_file(path, note_str)
            return "created", fname


def _commit_about(new_note: str):
    today   = date.today().isoformat()
    content = read_file(ABOUT_FILE)
    if not content:
        content = (
            "---\ntags:\n  - about\ndate: " + today + "\n---\n\n"
            "# About Me\n\nAVA's running record of who you are.\n\n## Notes\n\n"
        )
    if "## Notes" in content:
        content = content.rstrip() + f"\n- **{today}:** {new_note}\n"
    else:
        content = content.rstrip() + f"\n\n## Notes\n\n- **{today}:** {new_note}\n"
    write_file(ABOUT_FILE, content)
    invalidate()


# ── Public staging API ─────────────────────────────────────────────────────────
def stage_note(title: str, content: str,
               tags: list[str] | None = None,
               folder: Path | None = None) -> PendingAction:
    """
    Prepare a note write without executing it.
    Detects whether this should be a create or update by looking for
    an existing file with a matching (or very similar) title.
    """
    tags   = tags or ["note"]
    folder = folder or NOTES_DIR
    fname  = safe_name(title)

    # Smart resolution: don't create a new file if a close match exists
    existing_path = find_closest_file(title)
    is_update     = existing_path is not None
    # if it resolved to an existing file, use its stem as the title
    resolved_title = existing_path.stem if is_update else title

    related = smart_related(content, exclude_stem=fname, folder=folder)

    return PendingAction(
        action_type="note",
        title=resolved_title,
        content=content,
        tags=tags,
        folder=existing_path.parent if is_update else folder,
        is_update=is_update,
        existing_path=existing_path,
        suggested_links=related,
    )


def stage_idea(title: str, body: str) -> PendingAction:
    fname = safe_name(title)
    path  = IDEAS_DIR / f"{fname}.md"
    related = smart_related(body, exclude_stem=fname, folder=IDEAS_DIR)
    return PendingAction(
        action_type="idea",
        title=title,
        content=body,
        tags=["idea"],
        folder=IDEAS_DIR,
        is_update=path.exists(),
        existing_path=path if path.exists() else None,
        suggested_links=related,
    )


def stage_about(note: str) -> PendingAction:
    return PendingAction(
        action_type="about",
        title="About Me",
        content=note,
        tags=["about"],
        folder=VAULT,
        is_update=True,
        existing_path=ABOUT_FILE,
        suggested_links=[],
    )


# ── Direct write (used by commands, sessions, journal — not AI) ───────────────
def create_note(title: str, content: str,
                tags: list[str] | None = None,
                folder: Path | None = None) -> tuple[str, str]:
    """Direct write — used by /note command and internal features only."""
    action = stage_note(title, content, tags, folder)
    return action.commit()


def create_idea(title: str, body: str) -> tuple[str, str]:
    action = stage_idea(title, body)
    return action.commit()


def update_about(new_note: str):
    _commit_about(new_note)


def delete_file(name: str) -> tuple[str, str]:
    if name in PROTECTED:
        return "protected", name
    path = find_file(name)
    if not path:
        return "not_found", name
    try:
        path.unlink()
        invalidate()
        return "deleted", name
    except Exception as e:
        return "error", str(e)


def search(query: str, max_results: int = 10) -> list[str]:
    query_lower = query.lower()
    results = []
    for f in VAULT.rglob("*.md"):
        try:
            content = f.read_text(encoding="utf-8")
            if query_lower in content.lower():
                snippet = ""
                for line in content.splitlines():
                    if query_lower in line.lower():
                        snippet = line.strip()[:120]
                        break
                results.append(f"**{f.stem}** — {snippet}")
                if len(results) >= max_results:
                    break
        except Exception:
            continue
    return results


def stats() -> dict:
    counts = {}
    for label, folder in [
        ("notes", NOTES_DIR), ("ideas", IDEAS_DIR), ("skills", SKILLS_DIR),
        ("projects", PROJECTS_DIR), ("sessions", SESSIONS_DIR),
        ("journal", JOURNAL_DIR), ("tastes", TASTES_DIR),
    ]:
        try:
            counts[label] = len(list(folder.glob("*.md")))
        except Exception:
            counts[label] = 0
    return counts
