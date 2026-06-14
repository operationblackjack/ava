"""
projects.py — Creative project tracker ("captain's log" style)

/project <name>                       — create or view a project
/projects                             — list all projects with status
/projectstatus <name> | <status>      — set status (idea / active / paused / done)
/decision <name> | <decision text>    — log a decision made
/question <name> | <question text>    — add an open question
/answer <name> | <question> | <answer> — resolve an open question
/next <name> | <action text>          — add a next action
/done <name> | <action text>          — mark a next action as done
/projectlog <name> | <update>         — free-form log entry (kept for compatibility)

Each project is a single uniform note in Projects/ with sections:
Status, Overview, Decisions, Open Questions, Next Actions, Log.
"""

from datetime import date, datetime
import core.vault as vault
from core.config import PROJECTS_DIR

_VALID_STATUSES = {"idea", "active", "paused", "done"}
_STATUS_EMOJI = {"idea": "💡", "active": "🟢", "paused": "⏸", "done": "✅"}


def _path(name: str):
    return PROJECTS_DIR / f"{vault.safe_name(name)}.md"


def _template(name: str, today: str) -> str:
    return (
        f"---\ntags:\n  - project\ndate: {today}\nstatus: idea\n---\n\n"
        f"# {name}\n\n"
        f"## Status\n\nidea\n\n"
        f"## Overview\n\n*What is this project?*\n\n"
        f"## Decisions\n\n"
        f"## Open Questions\n\n"
        f"## Next Actions\n\n"
        f"## Log\n\n**{today}** — Project created.\n"
    )


def _get_status(content: str) -> str:
    if "## Status" in content:
        section = content.split("## Status", 1)[1].split("##", 1)[0]
        for line in section.splitlines():
            line = line.strip().lower()
            if line in _VALID_STATUSES:
                return line
    return "idea"


def _set_section_status(content: str, status: str) -> str:
    if "## Status" in content:
        before, _, after = content.partition("## Status")
        rest_after_section = after.split("##", 1)
        tail = "##" + rest_after_section[1] if len(rest_after_section) > 1 else ""
        return f"{before}## Status\n\n{status}\n\n{tail}"
    return content + f"\n\n## Status\n\n{status}\n"


def _append_to_section(content: str, section: str, line: str) -> str:
    """Append a bullet line under the given ## section, creating it if absent."""
    header = f"## {section}"
    if header in content:
        before, _, after = content.partition(header)
        parts = after.split("##", 1)
        section_body = parts[0].rstrip()
        tail = "\n\n##" + parts[1] if len(parts) > 1 else "\n"
        new_section = f"{section_body}\n{line}".strip()
        return f"{before}{header}\n\n{new_section}\n{tail}".rstrip() + "\n"
    else:
        return content.rstrip() + f"\n\n{header}\n\n{line}\n"


def handle_project(rest: str, mem: dict) -> str:
    name = rest.strip()
    if not name:
        return "Which project? /project <name>"
    path = _path(name)
    today = date.today().isoformat()

    if path.exists():
        content = vault.strip_frontmatter(vault.read_file(path))
        status = _get_status(vault.read_file(path))
        emoji = _STATUS_EMOJI.get(status, "")
        return f"## {name} {emoji} ({status})\n\n{content}"

    vault.write_file(path, _template(name, today))
    projects = mem.setdefault("projects", [])
    if name not in projects:
        projects.append(name)
    return (
        f"✦ Project created: **{name}** (status: idea)\n\n"
        f"Use `/projectstatus {name} | active` once you start, "
        f"`/decision`, `/question`, `/next` to build out the log."
    )


def handle_projects(rest: str, mem: dict) -> str:
    try:
        files = list(PROJECTS_DIR.glob("*.md"))
    except Exception:
        return "No projects folder found."
    if not files:
        return "No projects yet. Create one with /project <name>"

    by_status: dict[str, list[str]] = {}
    for f in sorted(files):
        content = vault.read_file(f)
        status = _get_status(content)
        by_status.setdefault(status, []).append(f.stem)

    lines = ["## Projects\n"]
    for status in ["active", "idea", "paused", "done"]:
        names = by_status.get(status, [])
        if not names:
            continue
        emoji = _STATUS_EMOJI.get(status, "")
        lines.append(f"\n**{emoji} {status.title()}**")
        for n in names:
            lines.append(f"- {n}")

    return "\n".join(lines)


def handle_projectstatus(rest: str, mem: dict) -> str:
    if "|" not in rest:
        return "Format: /projectstatus <project name> | <idea|active|paused|done>"
    name, _, status = rest.partition("|")
    name, status = name.strip(), status.strip().lower()
    if status not in _VALID_STATUSES:
        return f"Status must be one of: {', '.join(_VALID_STATUSES)}"
    path = _path(name)
    if not path.exists():
        return f"No project called **{name}**. Create it with /project {name}"
    content = vault.read_file(path)
    content = _set_section_status(content, status)
    # also update frontmatter status if present
    if content.startswith("---"):
        import re
        content = re.sub(r"(?m)^status:.*$", f"status: {status}", content, count=1)
    vault.write_file(path, content)
    today = date.today().isoformat()
    content = vault.read_file(path)
    content = _append_to_section(content, "Log", f"**{today}** — status changed to {status}")
    vault.write_file(path, content)
    return f"✦ **{name}** status set to **{status}** {_STATUS_EMOJI.get(status,'')}"


def handle_decision(rest: str, mem: dict) -> str:
    if "|" not in rest:
        return "Format: /decision <project name> | <decision made>"
    name, _, decision = rest.partition("|")
    name, decision = name.strip(), decision.strip()
    path = _path(name)
    if not path.exists():
        return f"No project called **{name}**. Create it with /project {name}"
    today = date.today().isoformat()
    content = vault.read_file(path)
    content = _append_to_section(content, "Decisions", f"- **{today}**: {decision}")
    content = _append_to_section(content, "Log", f"**{today}** — Decision: {decision}")
    vault.write_file(path, content)
    return f"✦ Decision logged for **{name}**: {decision}"


def handle_question(rest: str, mem: dict) -> str:
    if "|" not in rest:
        return "Format: /question <project name> | <open question>"
    name, _, question = rest.partition("|")
    name, question = name.strip(), question.strip()
    path = _path(name)
    if not path.exists():
        return f"No project called **{name}**. Create it with /project {name}"
    content = vault.read_file(path)
    content = _append_to_section(content, "Open Questions", f"- {question}")
    vault.write_file(path, content)
    return f"✦ Open question added to **{name}**: {question}"


def handle_answer(rest: str, mem: dict) -> str:
    parts = [p.strip() for p in rest.split("|")]
    if len(parts) != 3:
        return "Format: /answer <project name> | <question text or part of it> | <answer>"
    name, question_match, answer = parts
    path = _path(name)
    if not path.exists():
        return f"No project called **{name}**. Create it with /project {name}"
    content = vault.read_file(path)
    if "## Open Questions" not in content:
        return f"No open questions tracked for **{name}** yet."

    before, _, after = content.partition("## Open Questions")
    section, _, tail = after.partition("##")
    tail = "##" + tail if tail else ""

    lines = section.splitlines()
    new_lines = []
    resolved = None
    for line in lines:
        if line.strip().startswith("-") and question_match.lower() in line.lower():
            resolved = line.strip().lstrip("- ").strip()
            continue  # remove resolved question
        new_lines.append(line)

    if resolved is None:
        return f"Couldn't find an open question matching \"{question_match}\" in **{name}**."

    new_section = "\n".join(new_lines).rstrip()
    content = f"{before}## Open Questions\n{new_section}\n\n{tail}".rstrip() + "\n"

    today = date.today().isoformat()
    content = _append_to_section(content, "Decisions", f"- **{today}**: (resolved \"{resolved}\") → {answer}")
    content = _append_to_section(content, "Log", f"**{today}** — Resolved question \"{resolved}\": {answer}")
    vault.write_file(path, content)
    return f"✦ Resolved in **{name}**: \"{resolved}\" → {answer}"


def handle_next(rest: str, mem: dict) -> str:
    if "|" not in rest:
        return "Format: /next <project name> | <next action>"
    name, _, action = rest.partition("|")
    name, action = name.strip(), action.strip()
    path = _path(name)
    if not path.exists():
        return f"No project called **{name}**. Create it with /project {name}"
    content = vault.read_file(path)
    content = _append_to_section(content, "Next Actions", f"- [ ] {action}")
    vault.write_file(path, content)
    return f"✦ Next action added to **{name}**: {action}"


def handle_done(rest: str, mem: dict) -> str:
    parts = [p.strip() for p in rest.split("|")]
    if len(parts) != 2:
        return "Format: /done <project name> | <action text or part of it>"
    name, action_match = parts
    path = _path(name)
    if not path.exists():
        return f"No project called **{name}**. Create it with /project {name}"
    content = vault.read_file(path)
    if "## Next Actions" not in content:
        return f"No next actions tracked for **{name}** yet."

    before, _, after = content.partition("## Next Actions")
    section, _, tail = after.partition("##")
    tail = "##" + tail if tail else ""

    lines = section.splitlines()
    new_lines = []
    completed = None
    for line in lines:
        if line.strip().startswith("- [ ]") and action_match.lower() in line.lower():
            text = line.strip()[5:].strip()
            new_lines.append(f"- [x] {text}")
            completed = text
        else:
            new_lines.append(line)

    if completed is None:
        return f"Couldn't find a pending action matching \"{action_match}\" in **{name}**."

    new_section = "\n".join(new_lines).rstrip()
    content = f"{before}## Next Actions\n{new_section}\n\n{tail}".rstrip() + "\n"
    today = date.today().isoformat()
    content = _append_to_section(content, "Log", f"**{today}** — Done: {completed}")
    vault.write_file(path, content)
    return f"✦ Marked done in **{name}**: {completed}"


def handle_projectlog(rest: str, mem: dict) -> str:
    if "|" not in rest:
        return "Format: /projectlog <project name> | <update>"
    name, _, update = rest.partition("|")
    name = name.strip(); update = update.strip()
    if not name or not update:
        return "Need both a project name and an update."
    path = _path(name)
    if not path.exists():
        return f"No project called **{name}**. Create it with /project {name}"
    content = vault.read_file(path)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    content = _append_to_section(content, "Log", f"**{stamp}** — {update}")
    vault.write_file(path, content)
    return f"✦ Logged to **{name}**: *{update}*"


def register():
    return {
        "commands": {
            "project":       handle_project,
            "projects":      handle_projects,
            "projectstatus": handle_projectstatus,
            "decision":      handle_decision,
            "question":      handle_question,
            "answer":        handle_answer,
            "next":          handle_next,
            "done":          handle_done,
            "projectlog":    handle_projectlog,
        },
        "description": (
            "Creative project tracker — /project /projects /projectstatus /decision "
            "/question /answer /next /done /projectlog"
        ),
    }
