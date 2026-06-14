"""
morning.py — AVA's daily briefing
Command: /morning

Reads recent journal entries, pending reminders, active projects,
neglected notes, and gives a personalised start-of-day summary.
"""

from datetime import date, datetime, timedelta
from pathlib import Path
import core.vault as vault
import core.llm   as llm
import core.memory as memory
import core.rag as rag
from core.config import (
    JOURNAL_DIR, NOTES_DIR, IDEAS_DIR, SESSIONS_DIR
)
from features.journal import _negative_streak


def _user_mood_context(mem: dict) -> str:
    log = mem.get("user_mood_log", {})
    if not log:
        return "No mood data tracked yet."
    streak = _negative_streak(mem)
    today_key = date.today().isoformat()
    today_mood = log.get(today_key, "not logged yet")
    if streak >= 3:
        return (
            f"Today's inferred mood: {today_mood}. "
            f"User has logged a negative mood ({streak} days running) — "
            f"worth gently checking in on, without being heavy-handed."
        )
    return f"Today's inferred mood: {today_mood}."


def _recent_journal(days: int = 3) -> str:
    """Pull the last few days of journal entries."""
    lines = []
    for i in range(days):
        d    = (date.today() - timedelta(days=i)).isoformat()
        path = JOURNAL_DIR / f"{d}.md"
        if path.exists():
            content = vault.strip_frontmatter(vault.read_file(path)).strip()
            if content:
                lines.append(f"**{d}:**\n{content[:600]}")
    return "\n\n".join(lines) if lines else "No recent journal entries."


def _pending_reminders(mem: dict) -> str:
    """Pull active reminders from memory."""
    reminders = mem.get("reminders", [])
    if not reminders:
        return "No reminders set."
    today = date.today().isoformat()
    active = [r for r in reminders if not r.get("done") and r.get("date", "9999") <= today]
    upcoming = [r for r in reminders if not r.get("done") and r.get("date", "9999") > today]
    lines = []
    if active:
        lines.append("**Due now:**")
        for r in active[:5]:
            lines.append(f"  - {r['text']}")
    if upcoming:
        lines.append("**Upcoming:**")
        for r in upcoming[:5]:
            lines.append(f"  - {r['text']} ({r.get('date', '?')})")
    return "\n".join(lines) if lines else "No active reminders."


def _neglected_notes(days: int = 14, limit: int = 5) -> list[str]:
    """Find notes not touched in a while — worth revisiting."""
    import time
    cutoff = time.time() - (days * 86400)
    old    = []
    for f in NOTES_DIR.glob("*.md"):
        try:
            if f.stat().st_mtime < cutoff:
                old.append(f)
        except Exception:
            continue
    old.sort(key=lambda f: f.stat().st_mtime)
    return [f.stem for f in old[:limit]]


def _active_projects(mem: dict) -> str:
    """Pull active project names from memory."""
    projects = mem.get("active_projects", [])
    if not projects:
        return "No active projects tracked."
    return "\n".join(f"- {p}" for p in projects[:8])


def _recent_session_summary() -> str:
    """Get the most recent session summary."""
    try:
        sessions = sorted(SESSIONS_DIR.glob("*.md"), reverse=True)
        if not sessions:
            return ""
        content = vault.strip_frontmatter(vault.read_file(sessions[0])).strip()
        # extract summary section
        if "## Summary" in content:
            summary = content.split("## Summary", 1)[1].strip()
            return summary[:400]
        return content[:400]
    except Exception:
        return ""


def cmd_morning(rest: str, mem: dict) -> str:
    """
    /morning — personalised daily briefing from AVA
    """
    today    = date.today().strftime("%A, %B %d %Y")
    mood     = mem.get("soul", {}).get("mood", "curious")
    wm       = memory.working_memory_summary(mem)

    print("  Pulling your vault together…")

    journal      = _recent_journal(days=3)
    reminders    = _pending_reminders(mem)
    projects     = _active_projects(mem)
    neglected    = _neglected_notes()
    last_session = _recent_session_summary()
    surfaced     = rag.surface_stale_relevant(mem)
    mood_context = _user_mood_context(mem)

    neglected_str = (
        "Notes you haven't touched in a while: " + ", ".join(f"[[{n}]]" for n in neglected)
        if neglected else "All your notes seem active."
    )

    context = f"""Today is {today}.

Recent journal:
{journal}

Reminders:
{reminders}

Active projects:
{projects}

Last session summary:
{last_session or "No previous session."}

Neglected notes:
{neglected_str}

{surfaced or "Nothing stale-but-relevant to surface right now."}

User's recent mood (inferred from journal): {mood_context}

User's recent focus topics: {wm}"""

    prompt = (
        f"You are AVA, an AI second brain. Mood: {mood}.\n\n"
        f"Give a warm, personalised morning briefing based on this context. "
        f"Be specific — reference actual content from the journal and notes. "
        f"Include: what they've been thinking about lately, any reminders due, "
        f"one neglected note worth revisiting today (especially anything from "
        f"the 'Notes worth revisiting' section, which connects an old note to "
        f"a current focus topic — call this out explicitly if present), "
        f"and a single sharp question or thought to start their day. "
        f"If the user's mood context mentions a negative streak, weave in a "
        f"gentle, non-clinical check-in — don't make it the whole briefing, "
        f"just acknowledge it like a friend would. "
        f"Keep it to 200-250 words. "
        f"Feel like a thoughtful friend, not a productivity app.\n\n"
        f"Context:\n{context}"
    )

    briefing = llm.call([{"role": "user", "content": prompt}], max_tokens=400)
    return f"## Good morning ✦\n\n{briefing}"


def cmd_surface(rest: str, mem: dict) -> str:
    """
    /surface — show notes that connect to your current focus topics
    but haven't been touched in a while.
    """
    result = rag.surface_stale_relevant(mem, max_results=6)
    if not result:
        return (
            "Nothing stale-but-relevant to surface right now — either everything's "
            "fresh, or your working memory doesn't overlap with any older notes yet."
        )
    return result


def register():
    return {
        "commands": {"morning": cmd_morning, "surface": cmd_surface},
        "description": "Daily briefing — /morning for a personalised start to your day, /surface for notes worth revisiting",
    }
