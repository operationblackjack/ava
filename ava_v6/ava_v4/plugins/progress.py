"""
progress.py — Weekly progress review
/progress   — what you've been focused on and priorities for the week
"""

import core.vault as vault
import core.llm as llm
from core.config import SESSIONS_DIR
from core.memory import working_memory_summary


def handle_progress(rest: str, mem: dict) -> str:
    try:
        session_files = sorted(SESSIONS_DIR.glob("*.md"), reverse=True)[:5]
    except Exception:
        session_files = []
    session_text = ""
    for f in session_files:
        body = vault.strip_frontmatter(vault.read_file(f)).strip()
        session_text += f"\n---\n{body[:600]}\n"
    interests = ", ".join(mem.get("interests", [])) or "nothing tracked"
    skills    = ", ".join(mem.get("skills", []))    or "nothing tracked"
    wm        = working_memory_summary(mem, top_n=15)
    count     = mem.get("session_count", 0)
    print("  Reviewing your progress...")
    response = llm.call([{"role": "user", "content": (
        f"You are AVA, an AI second brain. Review this person's recent activity.\n\n"
        f"Total sessions: {count}\nInterests: {interests}\nSkills: {skills}\n"
        f"Working memory: {wm}\n\nRecent sessions:\n{session_text or 'None yet.'}\n\n"
        f"Write a short review with three sections:\n"
        f"1. **What you've been focused on** (2-3 sentences)\n"
        f"2. **What might be going stale** (1-2 specific things)\n"
        f"3. **Three priorities for this week** (specific and actionable)\n\n"
        f"Be direct. Skip generic advice."
    )}], max_tokens=500)
    return f"## Your Weekly Review\n\n{response}"


def register():
    return {
        "commands": {"progress": handle_progress},
        "description": "Weekly review — /progress",
    }
