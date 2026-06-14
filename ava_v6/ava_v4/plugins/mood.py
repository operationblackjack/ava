"""
mood.py — Personal mood tracker
/mood <how you feel>   — log a mood entry
/moods                 — view recent entries with pattern analysis
"""

from datetime import datetime
import core.vault as vault
import core.llm as llm
from core.config import JOURNAL_DIR

MOOD_FILE = JOURNAL_DIR / "Mood Log.md"


def handle_mood(rest: str, mem: dict) -> str:
    entry = rest.strip()
    if not entry:
        return "How are you feeling? /mood <description>"
    now       = datetime.now().strftime("%Y-%m-%d %H:%M")
    log_entry = f"\n**{now}** — {entry}"
    if MOOD_FILE.exists():
        vault.write_file(MOOD_FILE, vault.read_file(MOOD_FILE) + log_entry)
    else:
        vault.write_file(MOOD_FILE, f"# Mood Log\n{log_entry}")
    moods = mem.setdefault("mood_log", [])
    moods.append({"time": now, "entry": entry})
    if len(moods) > 50:
        mem["mood_log"] = moods[-50:]
    return f"✦ Logged: *{entry}*"


def handle_moods(rest: str, mem: dict) -> str:
    if not MOOD_FILE.exists():
        return "No mood entries yet. Start with /mood <how you feel>"
    lines   = [l for l in vault.read_file(MOOD_FILE).splitlines() if l.startswith("**")]
    recent  = lines[-20:] if len(lines) > 20 else lines
    if not recent:
        return "Mood log is empty."
    log_text = "\n".join(recent)
    print("  Looking for patterns...")
    reflection = llm.call([{"role": "user", "content": (
        f"Here are recent mood log entries:\n\n{log_text}\n\n"
        f"Notice 2-3 patterns or observations. Be gentle, specific, brief (3-4 sentences)."
    )}], max_tokens=300)
    return f"## Recent Moods\n\n{log_text}\n\n---\n\n**AVA notices:** {reflection}"


def register():
    return {
        "commands": {"mood": handle_mood, "moods": handle_moods},
        "description": "Mood tracker — /mood to log, /moods to review",
    }
