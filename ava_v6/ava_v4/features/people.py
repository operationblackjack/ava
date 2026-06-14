"""
people.py — Relationship memory for AVA
Commands: /people  /person <name>  /met <name> | <role> | <note>  /forget <name>

AVA tracks people you mention — who they are, your relationship,
and what you've said about them. She uses this to know that "Kerdeesha"
is a friend, not a topic keyword.
"""

import time
import core.memory as memory
import core.vault  as vault
from core.config import NOTES_DIR
from pathlib import Path


def cmd_people(rest: str, mem: dict) -> str:
    """
    /people — show everyone AVA knows about
    """
    people = mem.get("people", {})
    if not people:
        return (
            "I don't know anyone yet. Tell me about people in your life and I'll remember them.\n\n"
            "Or use `/met <name> | <role> | <note>` to introduce someone directly."
        )

    now   = time.time()
    lines = [f"## People AVA knows ({len(people)})\n"]

    # sort by last mentioned
    sorted_people = sorted(
        people.values(),
        key=lambda p: p.get("last_mentioned", 0),
        reverse=True
    )

    for p in sorted_people:
        name  = p.get("name", "?")
        role  = p.get("role", "")
        notes = p.get("notes", [])
        days  = int((now - p.get("last_mentioned", now)) / 86400)

        header = f"**{name}**"
        if role:
            header += f" — {role}"
        if days > 0:
            header += f" *(mentioned {days}d ago)*"

        lines.append(header)
        for n in notes[-2:]:   # show last 2 notes
            lines.append(f"  · {n}")
        lines.append("")

    return "\n".join(lines)


def cmd_person(rest: str, mem: dict) -> str:
    """
    /person <name> — show everything AVA knows about one person
    """
    name = rest.strip()
    if not name:
        return "Who? `/person <name>`"

    p = memory.get_person(mem, name)
    if not p:
        return (
            f"I don't know anyone called **{name}** yet.\n\n"
            f"Use `/met {name} | <their role> | <a note about them>` to introduce them."
        )

    lines = [f"## {p['name']}\n"]
    if p.get("role"):
        lines.append(f"**Role:** {p['role']}\n")

    days = int((time.time() - p.get("last_mentioned", time.time())) / 86400)
    lines.append(f"**Last mentioned:** {'today' if days == 0 else f'{days} days ago'}\n")

    notes = p.get("notes", [])
    if notes:
        lines.append("**Notes:**")
        for n in notes:
            lines.append(f"- {n}")
    else:
        lines.append("*No notes yet.*")

    return "\n".join(lines)


def cmd_met(rest: str, mem: dict) -> str:
    """
    /met <name> | <role> | <note>
    Introduce someone to AVA, or add a note about them.

    Examples:
      /met Kerdeesha | close friend | we went to school together
      /met Maddie | friend | loves horror movies
    """
    parts = [p.strip() for p in rest.split("|")]
    if not parts or not parts[0]:
        return "Format: `/met <name> | <role> | <note about them>`"

    name = parts[0].strip()
    role = parts[1].strip() if len(parts) > 1 else ""
    note = parts[2].strip() if len(parts) > 2 else ""

    memory.upsert_person(mem, name, role=role, note=note)

    lines = [f"✦ Remembered **{name}**"]
    if role:
        lines.append(f"as: {role}")
    if note:
        lines.append(f"note: {note}")
    return " — ".join(lines)


def cmd_note_person(rest: str, mem: dict) -> str:
    """
    /pnote <name> | <note>
    Add a note to an existing person without changing their role.
    """
    parts = [p.strip() for p in rest.split("|", 1)]
    if len(parts) < 2:
        return "Format: `/pnote <name> | <note>`"

    name, note = parts[0], parts[1]
    p = memory.get_person(mem, name)
    if not p:
        return f"I don't know **{name}** yet. Use `/met` to introduce them first."

    memory.upsert_person(mem, name, note=note)
    return f"✦ Note added to **{name}**: {note}"


def cmd_forget(rest: str, mem: dict) -> str:
    """
    /forget <name> — remove a person from AVA's memory
    """
    name = rest.strip()
    if not name:
        return "Who should I forget? `/forget <name>`"

    people = mem.get("people", {})
    key    = name.lower()
    if key not in people:
        return f"I don't have anyone called **{name}** in memory."

    # ask confirmation
    real_name = people[key].get("name", name)
    print(f"  Forget {real_name}? This removes all notes about them. [y/N] ", end="")
    try:
        ans = input().strip().lower()
    except EOFError:
        ans = "n"

    if ans != "y":
        return "Cancelled."

    del people[key]
    return f"✦ Forgot **{real_name}**."


def register():
    return {
        "commands": {
            "people": cmd_people,
            "person": cmd_person,
            "met":    cmd_met,
            "pnote":  cmd_note_person,
            "forget": cmd_forget,
        },
        "description": "Relationship memory — /people /person /met /pnote /forget",
    }
