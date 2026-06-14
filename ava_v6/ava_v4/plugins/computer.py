"""
computer.py — AVA Computer Control Plugin
Lets AVA open apps, open the browser, and search the web on your behalf.

Commands:
  /open <app or file>     — open an application, file, or folder
  /browser <url>          — open a URL in your default browser
  /search <query>         — web search; AVA reads the results and summarises
  /run <command>          — run a shell command (requires confirmation)

Requirements: pip install httpx beautifulsoup4 lxml   (already in AVA's stack)
"""

import os
import re
import subprocess
import sys
import webbrowser
from pathlib import Path

import httpx
import core.llm as llm

# ── helpers ───────────────────────────────────────────────────────────────────

# Common Windows app aliases so users can say "open spotify" etc.
_APP_ALIASES: dict[str, str] = {
    "notepad":     "notepad.exe",
    "explorer":    "explorer.exe",
    "calculator":  "calc.exe",
    "cmd":         "cmd.exe",
    "powershell":  "powershell.exe",
    "paint":       "mspaint.exe",
    "wordpad":     "wordpad.exe",
    "chrome":      r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "firefox":     r"C:\Program Files\Mozilla Firefox\firefox.exe",
    "edge":        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "spotify":     str(Path.home() / "AppData\\Roaming\\Spotify\\Spotify.exe"),
    "discord":     str(Path.home() / "AppData\\Local\\Discord\\Update.exe --processStart Discord.exe"),
    "vscode":      r"C:\Program Files\Microsoft VS Code\Code.exe",
    "obsidian":    str(Path.home() / "AppData\\Local\\Obsidian\\Obsidian.exe"),
    "terminal":    "wt.exe",          # Windows Terminal
    "files":       "explorer.exe",
    "file explorer": "explorer.exe",
}


def _open_target(target: str) -> str:
    """Open an app, file, or folder. Returns a status message."""
    target = target.strip()
    if not target:
        return "Open what? Give me an app name or file path."

    lower = target.lower()

    # check aliases first
    if lower in _APP_ALIASES:
        exe = _APP_ALIASES[lower]
        try:
            if sys.platform == "win32":
                os.startfile(exe)
            else:
                subprocess.Popen(["xdg-open", exe])
            return f"✦ Opened **{target}**."
        except Exception as e:
            return f"Couldn't open {target}: {e}"

    # try as a path
    path = Path(target)
    if path.exists():
        try:
            if sys.platform == "win32":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
            return f"✦ Opened **{path.name}**."
        except Exception as e:
            return f"Couldn't open that path: {e}"

    # last resort: try running it directly
    try:
        if sys.platform == "win32":
            subprocess.Popen(target, shell=True)
        else:
            subprocess.Popen(target.split())
        return f"✦ Launched: `{target}`"
    except Exception as e:
        return (
            f"I couldn't find or open **{target}**.\n\n"
            f"Error: {e}\n\n"
            "Try the full path, or add it to the `_APP_ALIASES` table in `plugins/computer.py`."
        )


def cmd_open(rest: str, mem: dict) -> str:
    return _open_target(rest)


def cmd_browser(rest: str, mem: dict) -> str:
    url = rest.strip()
    if not url:
        return "Give me a URL. `/browser https://example.com`"
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        webbrowser.open(url)
        return f"✦ Opened **{url}** in your browser."
    except Exception as e:
        return f"Couldn't open browser: {e}"


# ── Web search with LLM summarisation ─────────────────────────────────────────

_SEARCH_URL = "https://html.duckduckgo.com/html/"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def _ddg_search(query: str, max_results: int = 6) -> list[dict]:
    """Search DuckDuckGo HTML and return [{title, url, snippet}]."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    try:
        resp = httpx.post(
            _SEARCH_URL,
            data={"q": query, "b": "", "kl": ""},
            headers=_HEADERS,
            timeout=15,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except Exception:
        return []

    soup    = BeautifulSoup(resp.text, "lxml")
    results = []
    for r in soup.select(".result__body")[:max_results]:
        title_el   = r.select_one(".result__title")
        url_el     = r.select_one(".result__url")
        snippet_el = r.select_one(".result__snippet")
        title   = title_el.get_text(strip=True)   if title_el   else ""
        url     = url_el.get_text(strip=True)     if url_el     else ""
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""
        if title:
            results.append({"title": title, "url": url, "snippet": snippet})
    return results


def cmd_search(rest: str, mem: dict) -> str:
    query = rest.strip()
    if not query:
        return "What should I search for? `/search <query>`"

    results = _ddg_search(query)
    if not results:
        return (
            f"I couldn't pull search results for **{query}** right now.\n"
            "Check your internet connection or try `/browser https://duckduckgo.com`."
        )

    # build a compact context for the LLM to summarise
    ctx_lines = [f"Web search results for: {query}\n"]
    for i, r in enumerate(results, 1):
        ctx_lines.append(f"{i}. {r['title']}\n   {r['url']}\n   {r['snippet']}\n")
    context = "\n".join(ctx_lines)

    try:
        summary = llm.call(
            [{
                "role": "user",
                "content": (
                    "You are AVA, a smart second brain. Based on these web search results, "
                    "give a helpful, direct answer in 3-5 sentences. "
                    "If the results don't clearly answer the question, say so and offer what you can.\n\n"
                    + context
                ),
            }],
            max_tokens=400,
        )
    except Exception as e:
        summary = f"(Couldn't summarise results: {e})"

    sources = "\n".join(
        f"- [{r['title']}]({r['url']})" if r["url"].startswith("http") else f"- {r['title']} — {r['url']}"
        for r in results[:4]
    )
    return f"## Search: {query}\n\n{summary}\n\n**Sources**\n{sources}"


def cmd_run(rest: str, mem: dict) -> str:
    """
    /run <shell command>
    Runs a shell command after asking for confirmation in the terminal.
    The output is returned to the user.
    """
    cmd = rest.strip()
    if not cmd:
        return "What command should I run? `/run <command>`"

    print(f"\n  [AVA wants to run: {cmd}]")
    confirm = input("  Allow? (yes/no): ").strip().lower()
    if confirm not in ("yes", "y"):
        return "Command cancelled."

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        parts = []
        if out:
            parts.append(f"**Output:**\n```\n{out[:2000]}\n```")
        if err:
            parts.append(f"**Stderr:**\n```\n{err[:500]}\n```")
        if not parts:
            parts.append(f"Command exited with code {result.returncode} (no output).")
        return "\n\n".join(parts)
    except subprocess.TimeoutExpired:
        return "Command timed out after 30 seconds."
    except Exception as e:
        return f"Error running command: {e}"


def register():
    return {
        "commands": {
            "open":    cmd_open,
            "browser": cmd_browser,
            "search":  cmd_search,
            "run":     cmd_run,
        },
        "description": "Computer control — /open /browser /search /run",
    }
