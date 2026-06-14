"""
journal.py — Daily journal commands
Handles: /journal  /journal <text>

Also tracks the user's inferred mood over time from journal entries —
simple keyword-based sentiment, stored per-day in memory so AVA can notice
streaks (e.g. tired/frustrated for 5 days straight) and gently check in.
"""

from datetime import date, datetime, timedelta
from pathlib import Path
import core.vault as vault
from core.config import JOURNAL_DIR


# ── Mood inference ───────────────────────────────────────────────────────────
_MOOD_KEYWORDS = {
    "tired":       {"tired", "exhausted", "drained", "sleepy", "burnt out", "burned out", "worn out"},
    "frustrated":  {"frustrated", "annoyed", "irritated", "fed up", "angry", "pissed"},
    "anxious":     {"anxious", "worried", "stressed", "nervous", "overwhelmed", "on edge"},
    "sad":         {"sad", "down", "low", "depressed", "blue", "lonely", "empty"},
    "happy":       {"happy", "great", "excited", "thrilled", "good day", "amazing", "grateful"},
    "calm":        {"calm", "peaceful", "relaxed", "content", "at ease"},
    "motivated":   {"motivated", "productive", "focused", "energised", "energized", "inspired"},
}

_NEGATIVE_MOODS = {"tired", "frustrated", "anxious", "sad"}


def _infer_mood(text: str) -> str | None:
    text_l = text.lower()
    scores: dict[str, int] = {}
    for mood, keywords in _MOOD_KEYWORDS.items():
        for kw in keywords:
            if kw in text_l:
                scores[mood] = scores.get(mood, 0) + 1
    if not scores:
        return None
    return max(scores.items(), key=lambda x: x[1])[0]


def _record_user_mood(mem: dict, mood: str):
    """Store today's inferred mood in a rolling log inside memory."""
    log = mem.setdefault("user_mood_log", {})
    today = date.today().isoformat()
    log[today] = mood
    # keep last 60 days
    if len(log) > 60:
        for k in sorted(log.keys())[:-60]:
            del log[k]


def _negative_streak(mem: dict) -> int:
    """How many consecutive days (ending today) have a negative mood logged."""
    log = mem.get("user_mood_log", {})
    streak = 0
    d = date.today()
    while True:
        key = d.isoformat()
        mood = log.get(key)
        if mood in _NEGATIVE_MOODS:
            streak += 1
            d -= timedelta(days=1)
        else:
            break
    return streak


def _today_path() -> Path:
    today = date.today().isoformat()
    return JOURNAL_DIR / f"{today}.md"


def cmd_journal(rest: str, mem: dict) -> str:
    """
    /journal         — show last 5 entries
    /journal <text>  — add an entry to today's journal
    """
    text = rest.strip()

    if not text:
        return _show_recent()

    # Add entry to today's file
    path  = _today_path()
    stamp = datetime.now().strftime("%H:%M")
    entry = f"\n**{stamp}** — {text}"

    if path.exists():
        existing = vault.read_file(path)
        vault.write_file(path, existing + entry)
    else:
        header = f"# Journal — {date.today().isoformat()}\n"
        vault.write_file(path, header + entry)

    # infer mood from this entry and record it
    inferred = _infer_mood(text)
    note = f"✦ Journal entry saved ({stamp})"
    if inferred:
        _record_user_mood(mem, inferred)
        if inferred in _NEGATIVE_MOODS:
            streak = _negative_streak(mem)
            if streak >= 5:
                note += (
                    f"\n\n*(I've noticed you've sounded {inferred} for {streak} days "
                    f"in a row now — no pressure, just didn't want to pretend I hadn't "
                    f"noticed. How are you actually doing?)*"
                )
    return note


def _show_recent(n: int = 5) -> str:
    try:
        files = sorted(JOURNAL_DIR.glob("*.md"), reverse=True)[:n]
    except Exception:
        return "No journal entries yet."

    if not files:
        return "No journal entries yet."

    lines = [f"## Last {min(n, len(files))} Journal Entries\n"]
    for f in files:
        content = vault.read_file(f)
        body = vault.strip_frontmatter(content).strip()
        lines.append(f"### {f.stem}\n{body}\n")

    return "\n".join(lines)


def register():
    return {
        "commands": {
            "journal": cmd_journal,
        },
        "description": "Daily journal — /journal to view, /journal <text> to add",
    }
