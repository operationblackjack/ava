"""
reminders.py — Simple reminders
/remind <text>    — add a reminder
/reminders        — list active reminders
/done <number>    — mark a reminder complete
"""

from datetime import date


def handle_remind(rest: str, mem: dict) -> str:
    text = rest.strip()
    if not text:
        return "What should I remind you about? /remind <text>"
    mem.setdefault("reminders", []).append({
        "text": text, "date": date.today().isoformat(), "done": False
    })
    return f"✦ Reminder set: *{text}*"


def handle_reminders(rest: str, mem: dict) -> str:
    active = [r for r in mem.get("reminders", []) if not r.get("done")]
    if not active:
        return "No active reminders. Use /remind <text> to add one."
    lines = [f"## Reminders ({len(active)} active)\n"]
    for i, r in enumerate(active, 1):
        lines.append(f"**{i}.** {r['text']} *(added {r['date']})*")
    lines.append("\nUse `/done <number>` to mark one complete.")
    return "\n".join(lines)


def handle_done(rest: str, mem: dict) -> str:
    if not rest.strip().isdigit():
        return "Give me the reminder number. /done <number>"
    n      = int(rest.strip())
    active = [r for r in mem.get("reminders", []) if not r.get("done")]
    if n < 1 or n > len(active):
        return f"No reminder number {n}. Use /reminders to see the list."
    active[n - 1]["done"] = True
    return f"✦ Done: *{active[n - 1]['text']}*"


def register():
    return {
        "commands": {
            "remind":    handle_remind,
            "reminders": handle_reminders,
            "done":      handle_done,
        },
        "description": "Reminders — /remind /reminders /done",
    }
