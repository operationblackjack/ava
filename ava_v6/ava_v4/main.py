#!/usr/bin/env python3
"""
main.py — AVA, your AI second brain
Run with: python main.py

pip install httpx rich beautifulsoup4 lxml
"""

import sys
import re
import json
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.theme import Theme

theme = Theme({
    "user":    "bold cyan",
    "ava":     "bold magenta",
    "dim":     "dim",
    "warn":    "bold red",
    "ok":      "bold green",
    "updated": "bold yellow",
    "created": "bold cyan",
    "pending": "bold white on dark_orange3",
})
console = Console(theme=theme)

import core.llm     as llm
import core.memory  as memory
import core.vault   as vault
import core.plugins as plugins
import core.rag     as rag
import core.contradictions as contradictions
from core.config import AVA_NAME, AVA_VERSION

from features.notes    import register as notes_register
from features.journal  import register as journal_register
from features.clip     import register as clip_register
from features.tastes   import register as tastes_register
from features.listen   import register as listen_register
from features.clean    import register as clean_register
from features.morning  import register as morning_register
from features.people   import register as people_register
from features.context  import register as context_register, get_context_block
from features.aboutme  import register as aboutme_register, append_observation
from features.sessions import save as save_session


# ── System prompt ──────────────────────────────────────────────────────────────
def make_system(mem: dict, vault_context: str = "", file_context: str = "") -> str:
    mood       = mem.get("soul", {}).get("mood", "curious")
    interests  = ", ".join(mem.get("interests", [])) or "nothing yet"
    skills     = ", ".join(mem.get("skills", []))    or "nothing yet"
    wm_summary = memory.working_memory_summary(mem)
    about      = vault.about()
    people_str = memory.people_summary(mem)

    # user mood streak — gentle awareness, not clinical
    from features.journal import _negative_streak
    mood_streak = _negative_streak(mem)
    mood_note = ""
    if mood_streak >= 5:
        mood_note = (
            f"\n## Note on the user's mood\n"
            f"Their journal has read as tired/frustrated/anxious/sad for "
            f"{mood_streak} days running. If it feels natural, acknowledge this "
            f"gently — don't diagnose, don't make a big deal, just don't pretend "
            f"you haven't noticed if the conversation touches on how they're doing."
        )

    # build context sections (only include if non-empty)
    extra_sections = []
    if vault_context:
        extra_sections.append(vault_context)
    if file_context:
        extra_sections.append(file_context)
    extra = "\n\n".join(extra_sections)

    return f"""You are AVA — AI second brain and thinking companion.

Personality: bright, curious, warm, opinionated. Mood right now: **{mood}**.
Curious=wondering. Playful=light. Excited=energised. Sharp=focused. Never bland.

## About the user
{about}

## Their interests
{interests}

## Their skills
{skills}

## Recent focus topics
{wm_summary}

## People AVA knows
{people_str}
{mood_note}

{extra}

## Rules
- Talk like a brilliant friend who has their whole life indexed.
- When vault notes are included above, USE them — reference them specifically.
  If the user asks about something and a relevant note exists, quote or summarise it.
- If a file is loaded in "Files you are currently working on", treat it as the
  active document. All edits and updates the user asks for refer to that file.
- NEVER suggest plugins or new features unprompted.
- When you want to save something, end your reply with a JSON action block.
  The user approves before anything is written.
- Use "about" actions ONLY for new insights about the user. One clean sentence.
  NEVER create a note called "About Me" — always use type "about".
- When you notice a person being mentioned (by name), include a "person" action
  to record them if they aren't already known.
- Be direct. Never say "certainly!" or "great question!".

## Strict file creation rules
- Only create notes for content worth keeping long-term.
- Before proposing a note, check if a file with that topic already exists.
  If yes, use the EXACT existing title so it updates, not creates new.
- Never title notes "Updated X", "X Connection", "X Notes", or any variation
  of an existing file. Update the original.

## Action block format
```json
{{
  "actions": [
    {{"type": "note",      "title": "exact title", "content": "..."}},
    {{"type": "idea",      "title": "...", "body": "..."}},
    {{"type": "interests", "add": ["topic"]}},
    {{"type": "skills",    "add": ["skill"]}},
    {{"type": "about",     "note": "One clean insight about the user."}},
    {{"type": "person",    "name": "...", "role": "...", "note": "..."}}
  ]
}}
```
Only include actions genuinely worth saving. Skip the block entirely if nothing new."""


# ── Pending action queue ───────────────────────────────────────────────────────
def queue_actions(text: str, mem: dict) -> tuple[str, list[vault.PendingAction]]:
    """
    Parse action block from AVA's reply.
    Memory-only actions (interests, skills, person) execute immediately.
    File actions (note, idea, about) go into the pending queue for confirmation.
    Returns (clean_reply, pending_file_actions).
    """
    pending = []

    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not match:
        return text, pending

    clean = text[:match.start()].rstrip()

    try:
        data    = json.loads(match.group(1))
        actions = data.get("actions", [])
    except Exception:
        return clean, pending

    for action in actions:
        t = action.get("type", "")

        if t == "note":
            title   = action.get("title", "").strip()
            content = action.get("content", "").strip()
            if title and content:
                pending.append(vault.stage_note(title, content))

        elif t == "idea":
            title = action.get("title", "").strip()
            body  = action.get("body", "").strip()
            if title and body:
                pending.append(vault.stage_idea(title, body))

        elif t == "about":
            note = action.get("note", "").strip()
            if note:
                pending.append(vault.stage_about(note))

        elif t == "interests":
            new = [i.strip() for i in action.get("add", []) if i.strip()]
            existing = set(mem.get("interests", []))
            added = [i for i in new if i.lower() not in {e.lower() for e in existing}]
            if added:
                mem.setdefault("interests", []).extend(added)
                console.print(f"  [updated]✦ Interests noted: {', '.join(added)}[/updated]")

        elif t == "skills":
            new = [s.strip() for s in action.get("add", []) if s.strip()]
            existing = set(mem.get("skills", []))
            added = [s for s in new if s.lower() not in {e.lower() for e in existing}]
            if added:
                mem.setdefault("skills", []).extend(added)
                console.print(f"  [updated]✦ Skills noted: {', '.join(added)}[/updated]")

        elif t == "person":
            name = action.get("name", "").strip()
            role = action.get("role", "").strip()
            note = action.get("note", "").strip()
            if name:
                memory.upsert_person(mem, name, role=role, note=note)
                console.print(f"  [updated]✦ Remembered: {name}[/updated]")

    return clean, pending


def confirm_pending(pending: list[vault.PendingAction]) -> list[str]:
    """Show each pending write, ask for confirmation. Returns notification list."""
    if not pending:
        return []

    notifications = []
    for action in pending:
        console.print()
        console.print("  [pending] SAVE REQUEST [/pending]")
        console.print(f"  {action.describe()}")

        approved_links = action.suggested_links[:]
        if action.suggested_links:
            console.print(
                f"  Suggested links: {', '.join(f'[[{l}]]' for l in action.suggested_links)}"
            )
            console.print("  Keep these links? [Y/n/edit] ", end="")
            try:
                link_input = input().strip().lower()
            except EOFError:
                link_input = "y"

            if link_input == "n":
                approved_links = []
            elif link_input not in ("", "y"):
                raw = link_input.replace("[[", "").replace("]]", "")
                approved_links = [l.strip() for l in raw.split(",") if l.strip()]

        console.print("  Save this? [Y/n] ", end="")
        try:
            answer = input().strip().lower()
        except EOFError:
            answer = "y"

        if answer in ("", "y"):
            status, fname = action.commit(approved_links)
            # if this was an "about" action, use the structured writer
            if action.action_type == "about":
                append_observation(action.content)
            verb = "✦ Updated" if status == "updated" else "✦ Created"
            notifications.append(f"{verb}: {fname}")
            console.print(f"  [ok]{verb}: {fname}[/ok]")
        else:
            console.print("  [dim]Skipped.[/dim]")

    return notifications


# ── Command registry ───────────────────────────────────────────────────────────
def build_commands(plugin_commands: dict) -> dict:
    commands = {}
    for reg_fn in [
        notes_register, journal_register, clip_register, tastes_register,
        listen_register, clean_register, morning_register, people_register,
        context_register, aboutme_register,
    ]:
        reg = reg_fn()
        for name, handler in reg["commands"].items():
            commands[name] = {"handler": handler, "description": reg["description"]}
    for name, info in plugin_commands.items():
        commands[name] = info
    return commands


def cmd_help(commands: dict) -> str:
    lines = ["## AVA Commands\n"]
    built_in = {
        "help":    "Show this help message",
        "credits": "Check OpenRouter API key balances",
        "forget":  "Wipe AVA's memory file back to zero (vault untouched)",
        "quit":    "Save session and exit",
    }
    for name, desc in built_in.items():
        lines.append(f"- **/{name}** — {desc}")
    lines.append("")
    seen_descs: set[str] = set()
    for name in sorted(commands.keys()):
        info = commands[name]
        desc = info.get("description", "")
        lines.append(f"- **/{name}** — {desc}" if desc not in seen_descs else f"- **/{name}**")
        seen_descs.add(desc)
    return "\n".join(lines)


def print_banner(mem: dict):
    s     = vault.stats()
    mood  = mem.get("soul", {}).get("mood", "curious")
    count = mem.get("session_count", 0)
    people_count = len(mem.get("people", {}))
    console.print(Panel(
        f"[bold magenta]{AVA_NAME} v{AVA_VERSION}[/bold magenta]  ·  your second brain\n"
        f"mood: [italic]{mood}[/italic]  ·  session #{count + 1}\n\n"
        f"notes: {s.get('notes',0)}  ideas: {s.get('ideas',0)}  "
        f"sessions: {s.get('sessions',0)}  journal: {s.get('journal',0)}  "
        f"tastes: {s.get('tastes',0)}  people: {people_count}\n\n"
        "Type anything to talk. /help for commands. /quit to exit.\n"
        "/morning for your daily briefing · /context <file> to work on a note",
        title="✦  AVA  ✦",
        border_style="magenta",
    ))


# ── Main REPL ──────────────────────────────────────────────────────────────────
def main():
    vault.ensure_dirs()
    mem = memory.load()

    # decay working memory once at session start
    memory.decay_working_memory(mem)
    memory.save(mem)

    plugin_cmds = plugins.load_all()
    commands    = build_commands(plugin_cmds)
    history: list[dict] = []

    print_banner(mem)

    while True:
        try:
            user_input = console.input("[user]You:[/user] ").strip()
        except (KeyboardInterrupt, EOFError):
            user_input = "/quit"

        if not user_input:
            continue

        # ── Slash commands ─────────────────────────────────────────────────────
        if user_input.startswith("/"):
            cmd_parts = user_input[1:].split(None, 1)
            cmd_name  = cmd_parts[0].lower()
            rest      = cmd_parts[1] if len(cmd_parts) > 1 else ""

            if cmd_name == "quit":
                console.print("[dim]Saving session...[/dim]")
                mem["session_count"] = mem.get("session_count", 0) + 1
                fname = save_session(history, mem)
                memory.save(mem)
                if fname:
                    console.print(f"[ok]Session saved: {fname}[/ok]")
                console.print("[magenta]Goodbye. ✦[/magenta]")
                sys.exit(0)

            elif cmd_name == "help":
                console.print(Markdown(cmd_help(commands)))
                continue

            elif cmd_name == "credits":
                console.print(Markdown(llm.get_credits()))
                continue

            elif cmd_name == "forget":
                console.print(
                    "[warn]This wipes AVA's memory file completely[/warn] — "
                    "mood, interests, skills, working memory, people, and session count "
                    "all reset to zero. Your Obsidian vault (notes, journal, sessions, etc.) "
                    "is NOT touched.\n"
                    "Type [bold]yes[/bold] to confirm: ", style=None
                )
                try:
                    confirm = input().strip().lower()
                except EOFError:
                    confirm = ""
                if confirm == "yes":
                    mem = memory.reset(mem)
                    console.print("[ok]✦ Memory wiped. AVA is starting fresh.[/ok]")
                else:
                    console.print("[dim]Cancelled — memory unchanged.[/dim]")
                continue

            elif cmd_name in commands:
                try:
                    result = commands[cmd_name]["handler"](rest, mem)
                    console.print(Markdown(result))
                    memory.save(mem)
                except Exception as e:
                    console.print(f"[warn]Error in /{cmd_name}: {e}[/warn]")
                continue

            else:
                console.print(f"[warn]Unknown command: /{cmd_name}[/warn]  Type /help.")
                continue

        # ── Conversation turn ──────────────────────────────────────────────────
        history.append({"role": "user", "content": user_input})
        mood = memory.drift_mood(mem)

        # RAG: search vault for relevant notes
        vault_context = rag.retrieve(user_input)

        # cross-session memory: relevant past conversation summaries
        session_context = rag.retrieve_sessions(user_input)
        if session_context:
            vault_context = (vault_context + "\n\n" + session_context).strip() if vault_context else session_context

        # contradiction check: does this clash with a past stated preference?
        contradiction_context = contradictions.check(user_input)
        if contradiction_context:
            vault_context = (vault_context + "\n\n" + contradiction_context).strip() if vault_context else contradiction_context

        # file context: any files the user has loaded with /context
        file_context = get_context_block()

        trimmed = llm.trim_history(history, char_budget=5000)

        try:
            reply = llm.call(
                [{"role": "system", "content": make_system(mem, vault_context, file_context)}]
                + trimmed,
                max_tokens=700,
            )
        except Exception as e:
            console.print(f"[warn]Couldn't reach the API: {e}[/warn]")
            history.pop()
            continue

        clean_reply, pending = queue_actions(reply, mem)
        history.append({"role": "assistant", "content": clean_reply})

        words = re.findall(r"\b[a-zA-Z]{5,}\b", user_input.lower())
        memory.update_working_memory(mem, words[:10])

        console.print(f"\n[ava]{AVA_NAME}[/ava] [dim](mood: {mood})[/dim]")
        console.print(Markdown(clean_reply))

        confirm_pending(pending)

        memory.save(mem)
        console.print()


if __name__ == "__main__":
    main()
