"""
example_plugin.py — A simple example plugin for AVA

This file shows you exactly how to write a plugin.
When you're ready to use it, rename it (remove "example_") and
fill in your own logic.

Drop any .py file with a register() function into this plugins/ folder
and AVA will load it automatically on startup.
"""


def handle_hello(rest: str, mem: dict) -> str:
    """
    A trivial example command: /hello
    rest = anything the user typed after /hello
    mem  = AVA's memory dict (you can read or write to it)
    """
    name = rest.strip() or "world"
    mood = mem.get("soul", {}).get("mood", "curious")
    return f"Hello, {name}! (AVA is feeling {mood} right now.)"


def register():
    """
    Every plugin must have a register() function.
    It returns a dict with:
      - commands: { "command_name": handler_function, ... }
      - description: a short string shown in /help
    """
    return {
        "commands": {
            "hello": handle_hello,
        },
        "description": "Example plugin — /hello <name>",
    }
