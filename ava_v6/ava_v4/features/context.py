"""
context.py — Conversation threading / file context
Commands: /context <filename>   — load a vault file into the current conversation
          /context              — show what's currently loaded
          /unload               — clear loaded context

When you load a file, AVA reads it and holds it in the conversation context.
You can then say "update the friends section" or "what does this say about X"
and she knows exactly which file you mean — no guessing.
"""

import core.vault as vault

# In-session context store (lives in memory during the session, not persisted)
_loaded: dict[str, str] = {}   # {stem: content}


def get_context_block() -> str:
    """
    Return a formatted block of all loaded files for injection
    into the system prompt. Returns "" if nothing loaded.
    """
    if not _loaded:
        return ""
    blocks = []
    for stem, content in _loaded.items():
        # cap each file at 1500 chars to be kind to the context window
        snippet = content[:1500]
        if len(content) > 1500:
            snippet += "\n… (truncated)"
        blocks.append(f"### [[{stem}]] (loaded)\n{snippet}")
    return "## Files you are currently working on\n\n" + "\n\n---\n\n".join(blocks)


def cmd_context(rest: str, mem: dict) -> str:
    """
    /context              — show what files are loaded
    /context <filename>  — load a file into this conversation
    """
    name = rest.strip()

    if not name:
        if not _loaded:
            return (
                "No files loaded into context.\n\n"
                "Use `/context <filename>` to load a vault file so AVA knows exactly what you're working on."
            )
        lines = ["## Currently loaded files\n"]
        for stem, content in _loaded.items():
            word_count = len(content.split())
            lines.append(f"- **[[{stem}]]** ({word_count} words)")
        lines.append("\nUse `/unload` to clear, or `/context <filename>` to add another.")
        return "\n".join(lines)

    path = vault.find_file(name)
    if not path:
        return f"Can't find **{name}** in the vault."

    content = vault.read_file(path)
    if not content:
        return f"**{path.stem}** is empty."

    _loaded[path.stem] = content
    word_count = len(content.split())
    return (
        f"✦ Loaded **[[{path.stem}]]** ({word_count} words) into context.\n\n"
        f"AVA can now see this file. You can say things like:\n"
        f"- *\"Add Maddie to the friends section\"*\n"
        f"- *\"What does this say about Diana?\"*\n"
        f"- *\"Rewrite the opening paragraph\"*"
    )


def cmd_unload(rest: str, mem: dict) -> str:
    """
    /unload              — clear all loaded context
    /unload <filename>  — unload a specific file
    """
    name = rest.strip()

    if not _loaded:
        return "Nothing is currently loaded."

    if name:
        key = name.lower()
        match = next((s for s in _loaded if s.lower() == key), None)
        if not match:
            return f"**{name}** isn't loaded. Loaded files: {', '.join(_loaded.keys())}"
        del _loaded[match]
        return f"✦ Unloaded **[[{match}]]**."

    count = len(_loaded)
    _loaded.clear()
    return f"✦ Cleared {count} loaded file(s) from context."


def register():
    return {
        "commands": {
            "context": cmd_context,
            "unload":  cmd_unload,
        },
        "description": "File context — /context <file> to load a note, /unload to clear",
    }
