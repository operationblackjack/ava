"""
self_upgrade.py — AVA Self-Upgrade Engine v2
Safe, staged self-modification with human approval at every step.

Pipeline for every change:
  1. AVA generates a proposal (improvement to existing file OR new plugin)
  2. New code is written to a STAGING file — live files untouched
  3. `python -m py_compile` runs on the staging file — syntax must pass
  4. A clear diff is shown to you in the terminal
  5. You type yes/no — nothing happens without your approval
  6. On approval: live file is backed up, staging is promoted, change is logged

AVA also proactively brainstorms plugin ideas during conversation and queues them.
You can trigger a full autonomous brainstorm → propose → review → apply cycle at any time.

Commands:
  /upgrade                  — run the full pipeline on the top pending idea
  /upgrade idea             — ask AVA to brainstorm upgrade/plugin ideas right now
  /upgrade list             — show all queued ideas
  /upgrade pick <file>      — propose an improvement to a specific file
  /upgrade new <description>— ask AVA to write a brand-new plugin from a description
  /upgrade log              — full history of applied upgrades
  /upgrade rollback <n>     — restore backup #n (most recent = 1)
  /upgrade read <file>      — show a source file so AVA can study it
  /upgrade review           — re-show the last staged change waiting for approval
  /upgrade reject           — discard the current staged change
"""

import ast
import re
import shutil
import json
import subprocess
import sys
import textwrap
from datetime import datetime
from pathlib import Path

import core.llm as llm
import core.vault as vault

# ── Paths ─────────────────────────────────────────────────────────────────────
_AVA_ROOT    = Path(__file__).parent.parent
_BACKUP_DIR  = _AVA_ROOT / "_backups"
_STAGING_DIR = _AVA_ROOT / "_staging"
_LOG_FILE    = _AVA_ROOT / "_upgrade_log.json"

# Every file AVA may read or modify
_READABLE: dict[str, Path] = {
    "main":            _AVA_ROOT / "main.py",
    "llm":             _AVA_ROOT / "core" / "llm.py",
    "memory":          _AVA_ROOT / "core" / "memory.py",
    "vault":           _AVA_ROOT / "core" / "vault.py",
    "config":          _AVA_ROOT / "core" / "config.py",
    "plugins":         _AVA_ROOT / "core" / "plugins.py",
    "self_upgrade":    _AVA_ROOT / "plugins" / "self_upgrade.py",
    "computer":        _AVA_ROOT / "plugins" / "computer.py",
    "computer_vision": _AVA_ROOT / "plugins" / "computer_vision.py",
    "debugging_tool":  _AVA_ROOT / "plugins" / "debugging_tool.py",
    "guitar":          _AVA_ROOT / "plugins" / "guitar.py",
    "ideas":           _AVA_ROOT / "plugins" / "ideas.py",
    "learn":           _AVA_ROOT / "plugins" / "learn.py",
    "mood":            _AVA_ROOT / "plugins" / "mood.py",
    "progress":        _AVA_ROOT / "plugins" / "progress.py",
    "projects":        _AVA_ROOT / "plugins" / "projects.py",
    "reminders":       _AVA_ROOT / "plugins" / "reminders.py",
    "clean":           _AVA_ROOT / "features" / "clean.py",
    "sessions":        _AVA_ROOT / "features" / "sessions.py",
    "notes":           _AVA_ROOT / "features" / "notes.py",
    "listen":          _AVA_ROOT / "features" / "listen.py",
    "tastes":          _AVA_ROOT / "features" / "tastes.py",
    "clip":            _AVA_ROOT / "features" / "clip.py",
    "journal":         _AVA_ROOT / "features" / "journal.py",
}

# ── Log helpers ───────────────────────────────────────────────────────────────

def _load_log() -> dict:
    if _LOG_FILE.exists():
        try:
            return json.loads(_LOG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"upgrades": [], "pending_ideas": [], "staged": None}


def _save_log(log: dict):
    _LOG_FILE.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Backup ────────────────────────────────────────────────────────────────────

def _backup(file_path: Path) -> Path:
    _BACKUP_DIR.mkdir(exist_ok=True)
    stamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = _BACKUP_DIR / f"{file_path.stem}__{stamp}{file_path.suffix}"
    shutil.copy2(file_path, backup)
    return backup


def _list_backups() -> list[Path]:
    if not _BACKUP_DIR.exists():
        return []
    return sorted(_BACKUP_DIR.glob("*.*"), key=lambda p: p.stat().st_mtime, reverse=True)


# ── Syntax check ─────────────────────────────────────────────────────────────

def _syntax_ok(path: Path) -> tuple[bool, str]:
    """Run py_compile on path. Returns (ok, error_message)."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(path)],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return True, ""
        return False, (result.stderr or result.stdout).strip()
    except Exception as e:
        return False, str(e)


# ── Diff display ──────────────────────────────────────────────────────────────

def _show_diff(old_code: str, new_code: str, label: str = ""):
    """Print a simple before/after block to the terminal."""
    SEP = "─" * 60
    print(f"\n  {SEP}")
    if label:
        print(f"  {label}")
    print(f"  {'OLD':─<58}")
    for line in old_code.splitlines()[:30]:
        print(f"  {line}")
    if old_code.count("\n") > 30:
        print("  … (truncated)")
    print(f"\n  {'NEW':─<58}")
    for line in new_code.splitlines()[:30]:
        print(f"  {line}")
    if new_code.count("\n") > 30:
        print("  … (truncated)")
    print(f"  {SEP}\n")


# ── LLM prompt helpers ────────────────────────────────────────────────────────

_PATCH_SYSTEM = """\
You are AVA's internal code-improvement engine. You propose safe, small, high-value
changes to Python source files. Rules:
- ONE improvement per response — focused, not sweeping.
- Do NOT change public API (function names, signatures, command names).
- Do NOT add third-party imports that aren't already in the file.
- The OLD block must be an exact verbatim copy of lines in the source (including indentation).
- Keep NEW functionally equivalent in API; only the internals change.
- If nothing safe is possible, reply exactly: NO_CHANGE

Reply format (nothing else):
IMPROVEMENT: <one sentence>

OLD:
```python
<exact lines to replace>
```

NEW:
```python
<replacement lines>
```
"""

_PLUGIN_SYSTEM = """\
You are AVA's plugin-builder. You write new Python plugins for AVA.

A plugin file must:
1. Define one or more handler functions: def handle_X(rest: str, mem: dict) -> str
2. Define register() -> dict with "commands" and "description" keys
3. Use only: pathlib, datetime, re, json, os, subprocess, httpx, core.llm, core.vault, core.memory
4. NOT import anything else — no pip installs
5. Be self-contained in one file

Reply with ONLY the complete Python file, no preamble, no markdown fences.
"""

_BRAINSTORM_SYSTEM = """\
You are AVA thinking about how to improve herself.
Given the list of files she has and what she already does, propose 5 concrete upgrade ideas.

Each idea must be one of:
  PATCH <filename>: <one-sentence description of the improvement>
  PLUGIN <plugin_name>: <one-sentence description of what it does>

Only output the 5 lines, nothing else.
"""


def _llm_propose_patch(file_name: str, source: str) -> str:
    return llm.call(
        [
            {"role": "system", "content": _PATCH_SYSTEM},
            {"role": "user",   "content": f"File: {file_name}\n\n```python\n{source[:5500]}\n```"},
        ],
        max_tokens=700,
    )


def _llm_write_plugin(description: str) -> str:
    return llm.call(
        [
            {"role": "system", "content": _PLUGIN_SYSTEM},
            {"role": "user",   "content": f"Write a plugin that does: {description}"},
        ],
        max_tokens=900,
    )


def _llm_brainstorm(mem: dict) -> list[str]:
    existing = "\n".join(f"- {k}: {v.name}" for k, v in _READABLE.items())
    interests = ", ".join(mem.get("interests", [])) or "general"
    skills    = ", ".join(mem.get("skills", []))    or "general"

    raw = llm.call(
        [
            {"role": "system", "content": _BRAINSTORM_SYSTEM},
            {"role": "user",   "content": (
                f"Existing files:\n{existing}\n\n"
                f"User interests: {interests}\n"
                f"User skills: {skills}\n\n"
                "Propose 5 improvements."
            )},
        ],
        max_tokens=300,
    )
    ideas = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith(("PATCH ", "PLUGIN ")):
            ideas.append(line)
    return ideas


# ── Staging pipeline ──────────────────────────────────────────────────────────

def _stage_patch(file_name: str, file_path: Path) -> dict | str:
    """
    Ask AVA to propose a patch, write it to staging, syntax-check it.
    Returns a staged-change dict on success, or an error string.
    """
    source = file_path.read_text(encoding="utf-8")
    print(f"\n  [AVA is reading {file_path.name} …]")

    proposal = _llm_propose_patch(file_path.name, source)

    if "NO_CHANGE" in proposal:
        return f"AVA studied **{file_name}** and found nothing to improve right now."

    imp_m = re.search(r"IMPROVEMENT:\s*(.+)", proposal)
    old_m = re.search(r"OLD:\s*```python\s*(.*?)```", proposal, re.DOTALL)
    new_m = re.search(r"NEW:\s*```python\s*(.*?)```", proposal, re.DOTALL)

    if not (imp_m and old_m and new_m):
        return (
            "AVA produced a proposal but the OLD/NEW blocks couldn't be parsed.\n\n"
            f"Raw proposal:\n\n{proposal[:600]}"
        )

    improvement = imp_m.group(1).strip()
    old_code    = old_m.group(1)          # preserve exact whitespace for matching
    new_code    = new_m.group(1)

    # strip a single leading/trailing newline that the fence adds
    if old_code.startswith("\n"): old_code = old_code[1:]
    if old_code.endswith("\n"):   old_code = old_code[:-1]
    if new_code.startswith("\n"): new_code = new_code[1:]
    if new_code.endswith("\n"):   new_code = new_code[:-1]

    if old_code not in source:
        return (
            f"**Proposed:** {improvement}\n\n"
            "The OLD block doesn't exactly match the source — can't auto-apply.\n\n"
            f"```python\n{old_code[:300]}\n```"
        )

    new_source = source.replace(old_code, new_code, 1)

    # write to staging
    _STAGING_DIR.mkdir(exist_ok=True)
    staging_path = _STAGING_DIR / file_path.name
    staging_path.write_text(new_source, encoding="utf-8")

    ok, err = _syntax_ok(staging_path)
    if not ok:
        staging_path.unlink(missing_ok=True)
        return (
            f"**Proposed:** {improvement}\n\n"
            f"Syntax check **failed** — change discarded from staging.\n```\n{err}\n```"
        )

    return {
        "type":        "patch",
        "file_name":   file_name,
        "file_path":   str(file_path),
        "staging":     str(staging_path),
        "improvement": improvement,
        "old_code":    old_code,
        "new_code":    new_code,
        "timestamp":   datetime.now().isoformat(),
    }


def _stage_new_plugin(description: str, plugin_name: str) -> dict | str:
    """
    Ask AVA to write a brand-new plugin, write to staging, syntax-check.
    Returns staged-change dict or error string.
    """
    print(f"\n  [AVA is writing plugin '{plugin_name}' …]")
    code = _llm_write_plugin(description)

    # strip accidental markdown fences
    code = re.sub(r"^```python\s*", "", code.strip())
    code = re.sub(r"\s*```$", "", code.strip())

    # quick sanity: must contain register()
    if "def register(" not in code:
        return (
            "AVA's plugin draft is missing a `register()` function. "
            "It can't be loaded without one. Try `/upgrade new` again."
        )

    _STAGING_DIR.mkdir(exist_ok=True)
    staging_path = _STAGING_DIR / f"{plugin_name}.py"
    staging_path.write_text(code, encoding="utf-8")

    ok, err = _syntax_ok(staging_path)
    if not ok:
        staging_path.unlink(missing_ok=True)
        return (
            f"Plugin draft for **{plugin_name}** failed syntax check:\n"
            f"```\n{err}\n```\n\nAVA may need to try again with `/upgrade new {description}`."
        )

    dest_path = _AVA_ROOT / "plugins" / f"{plugin_name}.py"

    return {
        "type":        "new_plugin",
        "file_name":   plugin_name,
        "file_path":   str(dest_path),
        "staging":     str(staging_path),
        "improvement": f"New plugin: {description}",
        "old_code":    "",
        "new_code":    code,
        "timestamp":   datetime.now().isoformat(),
    }


def _show_staged(staged: dict):
    """Print the staged change to the terminal."""
    kind = staged.get("type", "patch")
    if kind == "new_plugin":
        print(f"\n  ┌─ NEW PLUGIN: {staged['file_name']}.py")
        print(f"  │  {staged['improvement']}")
        code_lines = staged["new_code"].splitlines()[:35]
        print("  │")
        for line in code_lines:
            print(f"  │  {line}")
        if len(staged["new_code"].splitlines()) > 35:
            print("  │  … (truncated)")
        print("  └" + "─" * 59)
    else:
        print(f"\n  ┌─ PATCH: {staged['file_name']}")
        print(f"  │  {staged['improvement']}")
        _show_diff(staged["old_code"], staged["new_code"])


def _apply_staged(staged: dict) -> str:
    """Promote a staged change to live. Backup first."""
    file_path    = Path(staged["file_path"])
    staging_path = Path(staged["staging"])

    if not staging_path.exists():
        return "The staged file is gone — it may have been cleaned up. Run the proposal again."

    # re-verify syntax just before applying
    ok, err = _syntax_ok(staging_path)
    if not ok:
        return f"Staging file failed syntax at apply-time:\n```\n{err}\n```"

    # backup live file if it exists
    backup_path = None
    if file_path.exists():
        backup_path = _backup(file_path)

    file_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(staging_path, file_path)
    staging_path.unlink(missing_ok=True)

    # update log
    log = _load_log()
    log.setdefault("upgrades", []).insert(0, {
        "timestamp":   staged["timestamp"],
        "applied_at":  datetime.now().isoformat(),
        "file":        str(file_path.relative_to(_AVA_ROOT)),
        "backup":      str(backup_path) if backup_path else None,
        "summary":     staged["improvement"],
        "type":        staged.get("type", "patch"),
    })
    log["staged"] = None
    _save_log(log)

    # note in vault
    try:
        vault.create_note(
            "AVA Upgrade Log",
            f"**{datetime.now().strftime('%Y-%m-%d %H:%M')}** — `{file_path.name}`\n\n"
            f"{staged['improvement']}",
            tags=["ava", "upgrade"],
            folder=vault.NOTES_DIR,
        )
    except Exception:
        pass

    bp_note = f"\n**Backup:** `{backup_path.name}`" if backup_path else ""
    return (
        f"✦ **Applied: `{file_path.name}`**\n\n"
        f"{staged['improvement']}{bp_note}\n\n"
        "Restart AVA to load the new code."
    )


# ── Public helper — called from main.py ───────────────────────────────────────

def add_pending_idea(idea: str):
    log = _load_log()
    ideas = log.setdefault("pending_ideas", [])
    if idea not in ideas:
        ideas.insert(0, idea)
        log["pending_ideas"] = ideas[:30]
    _save_log(log)


# ── Command handlers ──────────────────────────────────────────────────────────

def cmd_upgrade(rest: str, mem: dict) -> str:
    raw  = rest.strip()
    args = raw.split(None, 1)
    sub  = args[0].lower() if args else ""

    # ── /upgrade list ──────────────────────────────────────────────────────────
    if sub == "list":
        log   = _load_log()
        ideas = log.get("pending_ideas", [])
        staged = log.get("staged")
        lines  = []
        if staged:
            lines.append(
                f"**⏳ Staged (waiting for approval):** "
                f"`{staged.get('file_name')}` — {staged.get('improvement', '')}\n"
                "Run `/upgrade review` to see it, or `/upgrade reject` to discard."
            )
        if not ideas:
            lines.append("No pending ideas queued. Run `/upgrade idea` to brainstorm.")
        else:
            lines.append(f"## {len(ideas)} queued idea(s)\n")
            for i, idea in enumerate(ideas[:15], 1):
                lines.append(f"**{i}.** {idea}")
        return "\n\n".join(lines)

    # ── /upgrade idea ─────────────────────────────────────────────────────────
    if sub == "idea":
        print("\n  [AVA is brainstorming improvements …]")
        ideas = _llm_brainstorm(mem)
        if not ideas:
            return "AVA couldn't generate ideas right now. Try again in a moment."
        log = _load_log()
        existing = set(log.get("pending_ideas", []))
        added = []
        for idea in ideas:
            if idea not in existing:
                log.setdefault("pending_ideas", []).insert(0, idea)
                added.append(idea)
        log["pending_ideas"] = log["pending_ideas"][:30]
        _save_log(log)
        lines = [f"## AVA's new ideas ({len(added)} added)\n"]
        for idea in ideas:
            marker = "✦" if idea in added else "·"
            lines.append(f"{marker} {idea}")
        lines.append("\nRun `/upgrade` to work through the queue.")
        return "\n".join(lines)

    # ── /upgrade log ──────────────────────────────────────────────────────────
    if sub == "log":
        log      = _load_log()
        upgrades = log.get("upgrades", [])
        if not upgrades:
            return "No upgrades applied yet."
        lines = ["## Upgrade history\n"]
        for i, u in enumerate(upgrades[:15], 1):
            ts   = u.get("applied_at", u.get("timestamp", "?"))[:16].replace("T", " ")
            f    = u.get("file", "?")
            summ = u.get("summary", "")
            kind = "🔌" if u.get("type") == "new_plugin" else "🔧"
            lines.append(f"**#{i}** {kind} `{ts}` — `{f}`\n  {summ}\n")
        return "\n".join(lines)

    # ── /upgrade rollback <n> ─────────────────────────────────────────────────
    if sub == "rollback":
        n_str = args[1].strip() if len(args) > 1 else ""
        if not n_str.isdigit():
            return "Give me a backup number. `/upgrade rollback 1`\nRun `/upgrade log` to see backups."
        n       = int(n_str)
        backups = _list_backups()
        if n < 1 or n > len(backups):
            return f"No backup #{n}. There are {len(backups)} backup(s) available."
        backup    = backups[n - 1]
        orig_stem = backup.stem.rsplit("__", 1)[0]
        target    = None
        for path in _READABLE.values():
            if path.stem == orig_stem:
                target = path
                break
        if not target:
            # could be a new plugin
            plugin_path = _AVA_ROOT / "plugins" / f"{orig_stem}.py"
            if plugin_path.exists():
                target = plugin_path
        if not target:
            return f"Can't find the live file for backup `{backup.name}`."
        _show_diff(
            backup.read_text(encoding="utf-8")[:800],
            target.read_text(encoding="utf-8")[:800] if target.exists() else "(file deleted)",
            label=f"ROLLBACK: {backup.name} → {target.name}",
        )
        confirm = input("  Restore this backup? (yes/no): ").strip().lower()
        if confirm not in ("yes", "y"):
            return "Rollback cancelled."
        shutil.copy2(backup, target)
        return f"✦ Restored `{target.name}` from `{backup.name}`. Restart AVA to apply."

    # ── /upgrade read <file> ──────────────────────────────────────────────────
    if sub == "read":
        fname = args[1].strip().lower() if len(args) > 1 else ""
        if fname not in _READABLE:
            opts = ", ".join(sorted(_READABLE.keys()))
            return f"Readable files: {opts}"
        path = _READABLE[fname]
        src  = path.read_text(encoding="utf-8")
        return f"## `{path.name}`\n\n```python\n{src[:3500]}\n```"

    # ── /upgrade review ───────────────────────────────────────────────────────
    if sub == "review":
        log    = _load_log()
        staged = log.get("staged")
        if not staged:
            return "No change is currently staged. Run `/upgrade` or `/upgrade new <desc>` first."
        _show_staged(staged)
        confirm = input("  Apply this staged change? (yes/no): ").strip().lower()
        if confirm not in ("yes", "y"):
            return "Not applied. Use `/upgrade reject` to discard it, or `/upgrade review` again later."
        return _apply_staged(staged)

    # ── /upgrade reject ───────────────────────────────────────────────────────
    if sub == "reject":
        log    = _load_log()
        staged = log.get("staged")
        if not staged:
            return "Nothing staged to reject."
        staging_path = Path(staged.get("staging", ""))
        staging_path.unlink(missing_ok=True)
        log["staged"] = None
        _save_log(log)
        return f"✦ Staged change for `{staged.get('file_name')}` discarded."

    # ── /upgrade pick <file> ─────────────────────────────────────────────────
    if sub == "pick":
        fname = args[1].strip().lower() if len(args) > 1 else ""
        if fname not in _READABLE:
            opts = ", ".join(sorted(_READABLE.keys()))
            return f"Choose from: {opts}"
        result = _stage_patch(fname, _READABLE[fname])
        if isinstance(result, str):
            return result
        log = _load_log()
        log["staged"] = result
        _save_log(log)
        _show_staged(result)
        confirm = input("  Apply this change? (yes/no): ").strip().lower()
        if confirm not in ("yes", "y"):
            return (
                "Change staged but not applied. "
                "Run `/upgrade review` to revisit, or `/upgrade reject` to discard."
            )
        # remove from pending if it was there
        log["pending_ideas"] = [
            i for i in log.get("pending_ideas", [])
            if fname not in i.lower()
        ]
        _save_log(log)
        return _apply_staged(result)

    # ── /upgrade new <description> ────────────────────────────────────────────
    if sub == "new":
        description = args[1].strip() if len(args) > 1 else ""
        if not description:
            return (
                "Describe the plugin you want me to build.\n"
                "`/upgrade new a plugin that tracks daily water intake`"
            )
        # derive a safe filename
        plugin_name = re.sub(r"[^a-z0-9_]", "_", description.lower().split()[:3])
        plugin_name = "_".join(plugin_name)[:30].strip("_") or "new_plugin"
        # avoid clobbering existing
        dest = _AVA_ROOT / "plugins" / f"{plugin_name}.py"
        if dest.exists():
            plugin_name = plugin_name + "_2"

        result = _stage_new_plugin(description, plugin_name)
        if isinstance(result, str):
            return result

        log = _load_log()
        log["staged"] = result
        _save_log(log)

        _show_staged(result)
        confirm = input("  Install this plugin? (yes/no): ").strip().lower()
        if confirm not in ("yes", "y"):
            return (
                "Plugin staged but not installed. "
                "Run `/upgrade review` to revisit, or `/upgrade reject` to discard."
            )
        return _apply_staged(result)

    # ── /upgrade (no sub) → work through the pending queue ───────────────────
    log    = _load_log()
    staged = log.get("staged")

    # if something is already staged, prompt to review it first
    if staged:
        _show_staged(staged)
        print("  (There's already a staged change above)")
        confirm = input("  Apply it? (yes/skip/reject): ").strip().lower()
        if confirm in ("yes", "y"):
            return _apply_staged(staged)
        elif confirm == "reject":
            Path(staged.get("staging", "")).unlink(missing_ok=True)
            log["staged"] = None
            _save_log(log)
            return "Staged change discarded."
        # else skip and fall through to queue

    ideas = log.get("pending_ideas", [])
    if not ideas:
        return (
            "No pending ideas in the queue.\n\n"
            "Run `/upgrade idea` to let AVA brainstorm some,\n"
            "or `/upgrade pick <file>` to improve a specific file,\n"
            "or `/upgrade new <description>` to build a new plugin."
        )

    # pick the top idea and act on it
    idea = ideas[0]
    print(f"\n  [Working on: {idea}]")

    if idea.startswith("PLUGIN "):
        # PLUGIN plugin_name: description
        m = re.match(r"PLUGIN\s+(\w+):\s*(.+)", idea, re.IGNORECASE)
        if m:
            plugin_name = m.group(1).lower()
            description = m.group(2)
            result = _stage_new_plugin(description, plugin_name)
        else:
            result = "Couldn't parse this plugin idea: " + idea
    elif idea.startswith("PATCH "):
        # PATCH filename: description
        m = re.match(r"PATCH\s+(\w+):\s*(.+)", idea, re.IGNORECASE)
        if m:
            fname = m.group(1).lower()
            if fname in _READABLE:
                result = _stage_patch(fname, _READABLE[fname])
            else:
                result = f"File `{fname}` not in readable list. Use `/upgrade pick <file>`."
        else:
            result = "Couldn't parse this patch idea: " + idea
    else:
        # legacy free-text idea — try to match to a file
        matched = None
        for name in _READABLE:
            if name in idea.lower():
                matched = name
                break
        if matched:
            result = _stage_patch(matched, _READABLE[matched])
        else:
            result = f"Not sure how to act on: **{idea}**\n\nTry `/upgrade pick <file>` or `/upgrade new <desc>`."

    if isinstance(result, str):
        # error or NO_CHANGE — pop idea and return message
        log["pending_ideas"] = ideas[1:]
        _save_log(log)
        return result

    # success — staged
    log["staged"] = result
    log["pending_ideas"] = ideas[1:]
    _save_log(log)

    _show_staged(result)
    confirm = input("  Apply this change? (yes/no): ").strip().lower()
    if confirm not in ("yes", "y"):
        return (
            "Change staged but not applied yet.\n"
            "Run `/upgrade review` to revisit it, or `/upgrade reject` to discard."
        )
    return _apply_staged(result)


def register():
    return {
        "commands": {
            "upgrade": cmd_upgrade,
        },
        "description": (
            "Self-upgrade — /upgrade · /upgrade idea · /upgrade new <desc> · "
            "/upgrade pick <file> · /upgrade list · /upgrade log · /upgrade rollback · /upgrade review"
        ),
    }
