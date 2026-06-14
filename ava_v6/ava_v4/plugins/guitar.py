"""
guitar.py — Guitar practice tracker that actually grows

/practice <area> | <what you worked on>   — log a session, tagged by area
/practice <what you worked on>            — log a session (area auto-detected
                                              if it matches a known area, else "general")
/practices                                — recent sessions + pattern insights
/areas                                    — see all tracked practice areas and
                                              when each was last touched
/goal <description>                      — get a practice plan, saved to vault

Practice log lives at Notes/Guitar Practice Log.md as a uniform note with a
"## Sessions" list (date [area] — note). AVA notices neglected areas
(untouched 30+ days) and streaks (same area logged 3+ times in the last week).
"""

import re
from datetime import date, datetime, timedelta
import core.vault as vault
import core.llm as llm
from core.config import NOTES_DIR

PRACTICE_FILE = NOTES_DIR / "Guitar Practice Log.md"

# Common technique/area keywords used to auto-detect area if not given explicitly
_KNOWN_AREA_HINTS = {
    "fingerpicking": ["fingerpicking", "finger picking", "fingerstyle"],
    "open d":        ["open d", "drop d", "alt tuning", "alternate tuning"],
    "barre chords":  ["barre", "bar chord"],
    "scales":        ["scale", "scales", "modes", "mode"],
    "music theory":  ["theory", "chord progression", "harmony"],
    "strumming":     ["strumming", "rhythm"],
    "improv":        ["improv", "improvisation", "soloing", "lead"],
    "songs":         ["song", "cover", "tab"],
    "ear training":  ["ear training", "by ear", "transcrib"],
}

_NEGLECT_DAYS = 30
_STREAK_DAYS  = 7
_STREAK_MIN   = 3


def _detect_area(note: str) -> str:
    note_l = note.lower()
    for area, hints in _KNOWN_AREA_HINTS.items():
        if any(h in note_l for h in hints):
            return area
    return "general"


def _load_sessions() -> list[dict]:
    """Parse logged sessions from the practice file. Returns list of
    {date: date, area: str, note: str}."""
    if not PRACTICE_FILE.exists():
        return []
    content = vault.strip_frontmatter(vault.read_file(PRACTICE_FILE))
    sessions = []
    # lines look like: **2026-06-10** [fingerpicking] — worked on travis picking
    pattern = re.compile(r"\*\*(\d{4}-\d{2}-\d{2})\*\*\s*\[(.+?)\]\s*—\s*(.+)")
    for line in content.splitlines():
        m = pattern.match(line.strip())
        if m:
            try:
                d = datetime.strptime(m.group(1), "%Y-%m-%d").date()
            except ValueError:
                continue
            sessions.append({"date": d, "area": m.group(2).strip(), "note": m.group(3).strip()})
    return sessions


def _rebuild_file(sessions: list[dict]):
    """Rewrite the practice log file from a sessions list, sorted oldest-first."""
    sessions_sorted = sorted(sessions, key=lambda s: s["date"])
    lines = ["# Guitar Practice Log\n", "## Sessions\n"]
    for s in sessions_sorted:
        lines.append(f"**{s['date'].isoformat()}** [{s['area']}] — {s['note']}")
    body = "\n".join(lines) + "\n"
    vault.write_file(PRACTICE_FILE, body)


def handle_practice(rest: str, mem: dict) -> str:
    raw = rest.strip()
    if not raw:
        return "What did you work on? `/practice <description>` or `/practice <area> | <description>`"

    if "|" in raw:
        area, _, note = raw.partition("|")
        area, note = area.strip().lower(), note.strip()
        if not note:
            return "Format: `/practice <area> | <what you worked on>`"
    else:
        note = raw
        area = _detect_area(note)

    today = date.today()
    sessions = _load_sessions()
    sessions.append({"date": today, "area": area, "note": note})
    _rebuild_file(sessions)

    skills = mem.setdefault("skills", [])
    if "guitar" not in [s.lower() for s in skills]:
        skills.append("guitar")

    reply = f"✦ Practice logged: **[{area}]** {note}"

    # streak detection: same area logged 3+ times in last 7 days
    cutoff = today - timedelta(days=_STREAK_DAYS)
    recent_same_area = [s for s in sessions if s["area"] == area and s["date"] >= cutoff]
    if len(recent_same_area) >= _STREAK_MIN:
        reply += (
            f"\n\n*That's {len(recent_same_area)} sessions on **{area}** in the last "
            f"{_STREAK_DAYS} days — solid consistency. Keep it going.*"
        )

    # neglect check: any area not touched in 30+ days that used to be active
    all_areas = {s["area"] for s in sessions}
    neglected = []
    for a in all_areas:
        if a == area:
            continue
        a_sessions = [s for s in sessions if s["area"] == a]
        last_touched = max(s["date"] for s in a_sessions)
        days_since = (today - last_touched).days
        if days_since >= _NEGLECT_DAYS and len(a_sessions) >= 2:
            neglected.append((a, days_since))

    if neglected:
        neglected.sort(key=lambda x: x[1], reverse=True)
        a, days_since = neglected[0]
        reply += (
            f"\n\n*Side note: you haven't touched **{a}** in {days_since} days, "
            f"but you used to work on it regularly. Might be worth a revisit "
            f"sometime — or maybe you've moved on, which is fine too.*"
        )

    return reply


def handle_practices(rest: str, mem: dict) -> str:
    sessions = _load_sessions()
    if not sessions:
        return "No practice log yet. Start with `/practice <what you worked on>`"

    sessions_sorted = sorted(sessions, key=lambda s: s["date"], reverse=True)
    recent = sessions_sorted[:10]

    lines = ["## Recent Practice Sessions\n"]
    for s in recent:
        lines.append(f"- **{s['date'].isoformat()}** [{s['area']}] — {s['note']}")

    # pattern insight: most-practiced area in last 30 days
    today = date.today()
    cutoff = today - timedelta(days=30)
    last_30 = [s for s in sessions if s["date"] >= cutoff]
    if last_30:
        from collections import Counter
        counts = Counter(s["area"] for s in last_30)
        most_common = counts.most_common()
        lines.append("\n## Last 30 Days\n")
        for area, n in most_common:
            lines.append(f"- **{area}**: {n} session{'s' if n != 1 else ''}")

        # neglected areas (in history but not last 30 days)
        all_areas = {s["area"] for s in sessions}
        recent_areas = set(counts.keys())
        stale = all_areas - recent_areas
        if stale:
            lines.append(
                "\n*Areas you haven't touched in 30+ days: "
                + ", ".join(f"**{a}**" for a in sorted(stale)) + "*"
            )

    return "\n".join(lines)


def handle_areas(rest: str, mem: dict) -> str:
    sessions = _load_sessions()
    if not sessions:
        return "No practice log yet."

    today = date.today()
    by_area: dict[str, list] = {}
    for s in sessions:
        by_area.setdefault(s["area"], []).append(s)

    lines = ["## Practice Areas\n"]
    for area, slist in sorted(by_area.items(), key=lambda kv: max(s["date"] for s in kv[1]), reverse=True):
        last = max(s["date"] for s in slist)
        days_since = (today - last).days
        status = "🟢 active" if days_since < 14 else ("🟡 cooling" if days_since < 30 else "🔴 neglected")
        lines.append(f"- **{area}** — {len(slist)} sessions, last: {last.isoformat()} ({days_since}d ago) {status}")

    return "\n".join(lines)


def handle_goal(rest: str, mem: dict) -> str:
    goal = rest.strip()
    if not goal:
        return "What's the goal? /goal <description>"
    print("  Building practice plan...")
    plan = llm.call([{"role": "user", "content": (
        f"A guitarist wants to achieve: {goal}\n\n"
        f"Write a specific 2-week practice plan (5 bullet points). "
        f"Name real techniques, exercises, or songs. Be concrete."
    )}], max_tokens=400)
    vault.create_note(f"Guitar Goal — {goal}", plan, tags=["guitar", "goal"])
    return f"## Goal: {goal}\n\n{plan}\n\n✦ Saved to vault."


def register():
    return {
        "commands": {
            "practice":  handle_practice,
            "practices": handle_practices,
            "areas":     handle_areas,
            "goal":      handle_goal,
        },
        "description": "Guitar practice tracker — /practice /practices /areas /goal",
    }
