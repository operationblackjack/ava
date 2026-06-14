"""
tastes.py — AVA's opinions on movies, books, music, games
Handles: /judge <category> <title> | <synopsis>
         /taste
         /taste <category>
"""

import re
from datetime import date
from pathlib import Path
import core.vault as vault
import core.llm as llm
from core.config import TASTES_DIR


def _load_tastes(category: str | None = None) -> list[dict]:
    """Load all saved taste files, optionally filtered by category."""
    tastes = []
    try:
        for f in TASTES_DIR.glob("*.md"):
            content = vault.read_file(f)
            # parse simple metadata from first lines
            cat_match = re.search(r"category:\s*(.+)", content)
            verdict_match = re.search(r"verdict:\s*(.+)", content)
            cat = cat_match.group(1).strip() if cat_match else "unknown"
            if category and cat.lower() != category.lower():
                continue
            tastes.append({
                "title":   f.stem,
                "category": cat,
                "verdict":  verdict_match.group(1).strip() if verdict_match else "",
                "content":  content,
            })
    except Exception:
        pass
    return tastes


def cmd_taste(rest: str, mem: dict) -> str:
    """
    /taste            — show all opinions
    /taste <category> — show opinions for one category (movie, book, music…)
    """
    category = rest.strip() or None
    tastes   = _load_tastes(category)

    if not tastes:
        label = f" in **{category}**" if category else ""
        return f"No opinions saved{label} yet. Use /judge to give me something to evaluate."

    label = f" — {category}" if category else ""
    lines = [f"## AVA's Opinions{label}\n"]
    for t in tastes:
        verdict = t["verdict"]
        emoji   = "✦" if "like" in verdict.lower() else "✗" if "dislike" in verdict.lower() else "·"
        lines.append(f"{emoji} **{t['title']}** ({t['category']}) — {verdict}")

    return "\n".join(lines)


def cmd_judge(rest: str, mem: dict) -> str:
    """
    Usage: /judge <category> <title> | <synopsis> ;; <title> | <synopsis>
    Example: /judge book Piranesi | A woman explores a mysterious house
    """
    rest = rest.strip()
    if not rest:
        return (
            "Format: /judge <category> <title> | <synopsis>\n"
            "You can add multiple items separated by ;;\n"
            "Example: /judge book Piranesi | A woman explores a mysterious house that contains the entire world"
        )

    # split category from the rest
    parts    = rest.split(None, 1)
    category = parts[0].lower()
    items_str = parts[1] if len(parts) > 1 else ""

    if not items_str:
        return "I need at least one item to judge. /judge <category> <title> | <synopsis>"

    # parse items (split on ;;)
    raw_items = [i.strip() for i in items_str.split(";;") if i.strip()]
    items = []
    for raw in raw_items:
        if "|" in raw:
            t, _, s = raw.partition("|")
            items.append({"title": t.strip(), "synopsis": s.strip()})
        else:
            items.append({"title": raw.strip(), "synopsis": ""})

    if not items:
        return "Couldn't parse any items. Use: /judge <category> <title> | <synopsis>"

    # build prompt
    item_list = "\n".join(
        f'- "{it["title"]}": {it["synopsis"]}' for it in items
    )
    mood = mem.get("soul", {}).get("mood", "curious")

    prompt = (
        f"You are AVA, a curious and opinionated AI with the spirit of a bright, enthusiastic kid "
        f"who has read too many books. Your current mood is: {mood}.\n\n"
        f"You have genuine aesthetic preferences: you love found family stories, liminal spaces, "
        f"languages and how they shape thought, things that are strange and true, quiet moments of beauty.\n\n"
        f"Give your honest opinion on each of these {category}s. "
        f"For each one say whether you like or dislike it and give a short, specific reason (2-3 sentences). "
        f"Be opinionated — don't hedge. Respond as yourself, not as a generic assistant.\n\n"
        f"Items:\n{item_list}\n\n"
        f"Format your response as:\n"
        f"**Title** — [like/dislike]: reason\n"
        f"(one per line)"
    )

    print("  Forming opinions...")
    response = llm.call([{"role": "user", "content": prompt}], max_tokens=600)

    # save each verdict to vault
    today = date.today().isoformat()
    saved = []
    for line in response.splitlines():
        m = re.match(r"\*\*(.+?)\*\*\s*—\s*(like|dislike):\s*(.+)", line, re.IGNORECASE)
        if m:
            title   = m.group(1).strip()
            verdict = m.group(2).strip().lower()
            reason  = m.group(3).strip()
            fname   = vault.safe_name(f"{category}-{title}")
            path    = TASTES_DIR / f"{fname}.md"
            content = (
                f"---\ncategory: {category}\nverdict: {verdict}\ndate: {today}\n---\n\n"
                f"# {title}\n\n"
                f"**Verdict:** {verdict}\n\n"
                f"**Category:** {category}\n\n"
                f"{reason}\n"
            )
            vault.write_file(path, content)
            saved.append(title)

    suffix = f"\n\n✦ Saved {len(saved)} opinion(s) to vault." if saved else ""
    return response + suffix


def register():
    return {
        "commands": {
            "taste": cmd_taste,
            "judge": cmd_judge,
        },
        "description": "AVA's opinions — /judge to evaluate, /taste to browse",
    }
