"""
notes.py — Note management commands
Handles: /note  /idea  /read  /search  /delete  /recap  /garden
"""

import core.vault as vault
from core.config import PROTECTED


def cmd_note(rest: str, mem: dict) -> str:
    """Usage: /note <title> | <content>"""
    if "|" not in rest:
        return "Use the format: /note <title> | <content>"
    title, _, content = rest.partition("|")
    title   = title.strip()
    content = content.strip()
    if not title or not content:
        return "Both a title and content are needed. /note <title> | <content>"
    status, fname = vault.create_note(title, content)
    if status == "created":
        return f"✦ Note created: **{fname}**"
    return f"✦ Note updated: **{fname}**"


def cmd_idea(rest: str, mem: dict) -> str:
    """Usage: /idea <title> | <body>"""
    if "|" not in rest:
        return "Use the format: /idea <title> | <body>"
    title, _, body = rest.partition("|")
    title = title.strip()
    body  = body.strip()
    if not title or not body:
        return "Both a title and body are needed. /idea <title> | <body>"
    status, fname = vault.create_idea(title, body)
    if status == "duplicate":
        return f"That idea already exists: **{fname}**"
    return f"✦ Idea saved: **{fname}**"


def cmd_read(rest: str, mem: dict) -> str:
    """Usage: /read <filename>"""
    name = rest.strip()
    if not name:
        return "Tell me which file to read. /read <filename>"
    path = vault.find_file(name)
    if not path:
        return f"Couldn't find a file called **{name}** in the vault."
    content = vault.read_file(path)
    if not content:
        return f"**{name}** exists but is empty."
    return f"## {path.stem}\n\n{content}"


def cmd_search(rest: str, mem: dict) -> str:
    """Usage: /search <query>"""
    query = rest.strip()
    if not query:
        return "What should I search for? /search <query>"
    results = vault.search(query)
    if not results:
        return f'No notes found containing "{query}".'
    lines = [f"Found {len(results)} result(s) for **{query}**:\n"]
    lines.extend(f"- {r}" for r in results)
    return "\n".join(lines)


def cmd_delete(rest: str, mem: dict) -> str:
    """Usage: /delete <filename>"""
    name = rest.strip()
    if not name:
        return "Which file? /delete <filename>"
    if name in PROTECTED:
        return f"**{name}** is a protected file — I won't delete it."
    # simple confirmation: user must type /delete <name> confirm
    parts = name.split()
    if len(parts) >= 2 and parts[-1].lower() == "confirm":
        real_name = " ".join(parts[:-1])
        status, result = vault.delete_file(real_name)
        if status == "deleted":
            return f"✦ Deleted: **{result}**"
        if status == "protected":
            return f"**{result}** is protected — I won't delete it."
        if status == "not_found":
            return f"Couldn't find **{result}**."
        return f"Something went wrong: {result}"
    return (
        f"Are you sure you want to delete **{name}**?\n"
        f"Type `/delete {name} confirm` to go through with it."
    )


def cmd_recap(rest: str, mem: dict) -> str:
    """Show vault statistics."""
    s = vault.stats()
    lines = ["## Vault Stats\n"]
    for label, count in s.items():
        lines.append(f"- **{label.title()}:** {count}")
    total = sum(s.values())
    lines.append(f"\n**Total files:** {total}")
    return "\n".join(lines)


def cmd_garden(rest: str, mem: dict) -> str:
    """Find orphaned notes with no links."""
    orphans = vault.find_orphans()
    if not orphans:
        return "No orphaned notes — your vault is well connected. ✦"
    lines = [f"Found {len(orphans)} orphaned note(s) (no links to/from them):\n"]
    for p in orphans:
        lines.append(f"- [[{p.stem}]]")
    lines.append("\nAsk me to connect any of these to other notes.")
    return "\n".join(lines)


def register():
    return {
        "commands": {
            "note":   cmd_note,
            "idea":   cmd_idea,
            "read":   cmd_read,
            "search": cmd_search,
            "delete": cmd_delete,
            "recap":  cmd_recap,
            "garden": cmd_garden,
        },
        "description": "Core vault note management",
    }
