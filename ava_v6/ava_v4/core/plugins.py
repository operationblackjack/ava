"""
plugins.py — AVA's plugin system
Any .py file placed in the plugins/ folder that defines a register() function
will be auto-loaded at startup. This is how you add new features to AVA
without touching any existing code.

---- How to write a plugin ----

Create a file in plugins/, e.g. plugins/weather.py

It must define a register() function that returns a dict like this:

    def register():
        return {
            "commands": {
                "weather": handle_weather,      # /weather → calls handle_weather(rest, mem)
                "forecast": handle_forecast,    # /forecast → calls handle_forecast(rest, mem)
            },
            "description": "Weather lookups for your area",   # shown in /help
        }

    def handle_weather(rest: str, mem: dict) -> str:
        return "It's sunny! ☀️"

That's it. Drop the file in, restart AVA, and /weather works.

The handler signature is always: func(rest: str, mem: dict) -> str
  - rest  = everything the user typed after the command name
  - mem   = AVA's current memory dict (you can read and write to it)
  - return a string — this is what AVA prints to the user
"""

import importlib.util
import sys
from pathlib import Path

_PLUGINS_DIR = Path(__file__).parent.parent / "plugins"


def load_all() -> dict[str, dict]:
    """
    Scan the plugins/ folder and load every valid plugin.
    Returns a dict: { command_name: {"handler": fn, "source": plugin_name} }
    """
    loaded: dict[str, dict] = {}

    if not _PLUGINS_DIR.exists():
        return loaded

    for path in sorted(_PLUGINS_DIR.glob("*.py")):
        if path.stem.startswith("_"):
            continue
        try:
            spec   = importlib.util.spec_from_file_location(f"plugins.{path.stem}", path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[f"plugins.{path.stem}"] = module
            spec.loader.exec_module(module)

            if not hasattr(module, "register"):
                continue

            registration = module.register()
            commands = registration.get("commands", {})
            desc     = registration.get("description", "")

            for cmd_name, handler in commands.items():
                loaded[cmd_name.lower()] = {
                    "handler":     handler,
                    "description": desc,
                    "source":      path.stem,
                }

            print(f"  [plugin loaded: {path.stem} → /{', /'.join(commands.keys())}]")

        except Exception as e:
            print(f"  [plugin error: {path.name} — {e}]")

    return loaded
