# ✦ AVA Plugin Tutorial

*How to teach AVA new tricks — from your first command to a full feature.*

---

## What Is a Plugin?

A plugin is a single `.py` file you drop into AVA's `plugins/` folder. When AVA starts up, she automatically finds every plugin in that folder and loads it — no configuration needed, no touching existing files.

Each plugin can add one or more new `/commands` to AVA. The moment she loads your plugin, those commands are live.

---

## The Minimum Working Plugin

Every plugin needs exactly one thing: a `register()` function that returns a dictionary.

Create a file called `plugins/hello.py`:

```python
def handle_hello(rest: str, mem: dict) -> str:
    return "Hello! AVA is alive and well."

def register():
    return {
        "commands": {
            "hello": handle_hello,
        },
        "description": "Say hello",
    }
```

Restart AVA. Type `/hello`. Done.

---

## The Handler Signature

Every command handler always has this exact signature:

```python
def my_handler(rest: str, mem: dict) -> str:
```

**`rest`** — everything the user typed after the command name.
If the user types `/hello world`, then `rest` is `"world"`.
If they just type `/hello`, then `rest` is `""`.

**`mem`** — AVA's full memory dictionary. You can read from it and write to it.
Changes you make to `mem` are saved automatically after your handler runs.

**return value** — a string. This is what gets printed to the user. AVA supports Markdown, so `**bold**`, `## headers`, and `- lists` all render correctly.

---

## Reading From Memory

AVA's memory dictionary has these useful fields:

```python
mem["interests"]       # list of strings — topics the user cares about
mem["skills"]          # list of strings — things the user is learning
mem["working_memory"]  # dict of {topic: weight} — recent conversation topics
mem["session_count"]   # int — how many sessions the user has had
mem["soul"]["mood"]    # string — AVA's current mood
```

---

## Writing to Memory

You can store anything in `mem`. AVA saves it automatically after your handler runs.

```python
def handle_setgoal(rest: str, mem: dict) -> str:
    goal = rest.strip()
    if not goal:
        return "Tell me the goal. /setgoal <your goal>"
    goals = mem.setdefault("goals", [])
    goals.append(goal)
    return f"✦ Goal saved: **{goal}**"
```

Any key you add to `mem` will persist in `.ava_memory.json` between sessions. Use a namespaced key to avoid conflicts with other plugins: `mem.setdefault("myplugin_data", {})`.

---

## Writing to the Vault

Plugins have full access to AVA's vault. Import from `core.vault`:

```python
import core.vault as vault

vault.create_note(title, content, tags=["note"])  # create/merge a note
vault.create_idea(title, body)                     # save an idea
vault.read_file(path)                              # read any file
vault.find_file(name)                              # find a .md file by name
vault.write_file(path, text)                       # write any file
vault.search(query)                                # full-text search
vault.update_about(note)                           # add to About Me
vault.stats()                                      # vault file counts
vault.safe_name(title)                             # sanitise a string for filenames

# Useful folder paths
from core.config import VAULT, NOTES_DIR, IDEAS_DIR, JOURNAL_DIR, TASTES_DIR
```

---

## Calling the AI

Your plugin can call the LLM directly:

```python
import core.llm as llm

response = llm.call([
    {"role": "user", "content": "Your prompt here"}
], max_tokens=400)
```

`llm.call()` handles key rotation and errors automatically. Always set `max_tokens` to something reasonable — 300-600 is good for most plugin responses.

---

## Plugin Rules & Tips

**Do:** Return a string from every handler. Even errors should return a readable message.

**Do:** Use `rest.strip()` — users sometimes add extra spaces.

**Do:** Handle the empty case. Always tell the user the correct format if they call a command with nothing.

**Don't:** Call `sys.exit()` or `quit()` from a plugin. It will close AVA entirely.

**Don't:** Use the built-in command names: `help`, `quit`, `credits`.

**Don't:** Import from `main.py` — it creates circular imports. Everything you need is in `core/`.

**Tip:** Print progress messages with `print("  Doing something...")` for anything slow.

---

## Feature Tutorials

The rest of this guide is full working code for every suggested AVA feature. Each one is a complete, copy-paste-ready plugin file.

---

## 1. Guitar Practice Tracker

**Commands:** `/practice` `/practices` `/goal`

Create `plugins/guitar.py`:

```python
"""
guitar.py — Guitar practice tracker
/practice <what you worked on>   — log a session
/practices                       — view recent sessions
/goal <description>              — set a goal and get a practice plan
"""

from datetime import date
import core.vault as vault
import core.llm as llm
from core.config import NOTES_DIR

PRACTICE_FILE = NOTES_DIR / "Guitar Practice Log.md"


def handle_practice(rest: str, mem: dict) -> str:
    note = rest.strip()
    if not note:
        return "What did you work on? /practice <description>"

    today = date.today().isoformat()
    entry = f"\n**{today}** — {note}"

    if PRACTICE_FILE.exists():
        existing = vault.read_file(PRACTICE_FILE)
        vault.write_file(PRACTICE_FILE, existing + entry)
    else:
        vault.write_file(PRACTICE_FILE, f"# Guitar Practice Log\n{entry}")

    skills = mem.setdefault("skills", [])
    if "guitar" not in [s.lower() for s in skills]:
        skills.append("guitar")

    return f"✦ Practice logged: *{note}*"


def handle_practices(rest: str, mem: dict) -> str:
    if not PRACTICE_FILE.exists():
        return "No practice log yet. Start with /practice <what you worked on>"

    content = vault.read_file(PRACTICE_FILE)
    lines   = [l for l in content.splitlines() if l.startswith("**")]
    recent  = lines[-10:] if len(lines) > 10 else lines

    if not recent:
        return "Practice log is empty."

    return "## Recent Practice Sessions\n\n" + "\n".join(recent)


def handle_goal(rest: str, mem: dict) -> str:
    goal = rest.strip()
    if not goal:
        return "What's the goal? /goal <description>"

    print("  Building practice plan...")
    plan = llm.call([{
        "role": "user",
        "content": (
            f"A guitarist wants to achieve: {goal}\n\n"
            f"Write a specific 2-week practice plan (5 bullet points). "
            f"Name real techniques, exercises, or songs. Be concrete."
        )
    }], max_tokens=400)

    vault.create_note(f"Guitar Goal — {goal}", plan, tags=["guitar", "goal"])
    return f"## Goal: {goal}\n\n{plan}\n\n✦ Saved to vault."


def register():
    return {
        "commands": {
            "practice":  handle_practice,
            "practices": handle_practices,
            "goal":      handle_goal,
        },
        "description": "Guitar practice tracker — /practice /practices /goal",
    }
```

---

## 2. Project Manager

**Commands:** `/project <name>` `/projects` `/projectlog <name> | <update>`

Projects live as structured notes in your vault under `Projects/`. Each project has an overview, goals, next actions, open questions, and an activity log.

Create `plugins/projects.py`:

```python
"""
projects.py — Project manager
/project <name>                    — create or view a project
/projects                          — list all projects
/projectlog <name> | <update>      — add a log entry to a project
"""

from datetime import date, datetime
import core.vault as vault
import core.llm as llm
from core.config import PROJECTS_DIR


def _project_path(name: str):
    return PROJECTS_DIR / f"{vault.safe_name(name)}.md"


def handle_project(rest: str, mem: dict) -> str:
    name = rest.strip()
    if not name:
        return "Which project? /project <name>"

    path = _project_path(name)

    # if it already exists, show it
    if path.exists():
        content = vault.read_file(path)
        return f"## {name}\n\n{vault.strip_frontmatter(content)}"

    # create a new project
    print("  Setting up project...")
    today = date.today().isoformat()
    template = (
        f"---\ntags:\n  - project\ndate: {today}\n---\n\n"
        f"# {name}\n\n"
        f"## Overview\n\n*What is this project?*\n\n"
        f"## Goals\n\n- \n\n"
        f"## Next Actions\n\n- \n\n"
        f"## Open Questions\n\n- \n\n"
        f"## Log\n\n**{today}** — Project created.\n"
    )
    vault.write_file(path, template)

    # track in memory
    projects = mem.setdefault("projects", [])
    if name not in projects:
        projects.append(name)

    return (
        f"✦ Project created: **{name}**\n\n"
        f"Open `Projects/{vault.safe_name(name)}.md` in Obsidian to fill in the details.\n"
        f"Use `/projectlog {name} | <update>` to add progress notes."
    )


def handle_projects(rest: str, mem: dict) -> str:
    try:
        files = list(PROJECTS_DIR.glob("*.md"))
    except Exception:
        return "No projects folder found."

    if not files:
        return "No projects yet. Create one with /project <name>"

    lines = ["## Projects\n"]
    for f in sorted(files):
        content = vault.read_file(f)
        # grab the first non-empty line after frontmatter as a preview
        body  = vault.strip_frontmatter(content)
        lines.append(f"- **{f.stem}**")

    return "\n".join(lines)


def handle_projectlog(rest: str, mem: dict) -> str:
    if "|" not in rest:
        return "Format: /projectlog <project name> | <update>"

    name, _, update = rest.partition("|")
    name   = name.strip()
    update = update.strip()

    if not name or not update:
        return "Need both a project name and an update. /projectlog <name> | <update>"

    path = _project_path(name)
    if not path.exists():
        return f"No project called **{name}**. Create it first with /project {name}"

    content  = vault.read_file(path)
    today    = datetime.now().strftime("%Y-%m-%d %H:%M")
    log_entry = f"\n**{today}** — {update}"

    # append to the Log section
    if "## Log" in content:
        content = content.replace("## Log\n", f"## Log\n{log_entry}\n", 1)
    else:
        content += f"\n\n## Log\n{log_entry}\n"

    vault.write_file(path, content)
    return f"✦ Logged to **{name}**: *{update}*"


def register():
    return {
        "commands": {
            "project":    handle_project,
            "projects":   handle_projects,
            "projectlog": handle_projectlog,
        },
        "description": "Project manager — /project /projects /projectlog",
    }
```

---

## 3. Ideas Generator

**Commands:** `/ideas` `/review`

AVA generates fresh ideas based on your tracked interests, and surfaces random old notes for review.

Create `plugins/ideas.py`:

```python
"""
ideas.py — Idea generation and review
/ideas    — generate 7 ideas based on your interests
/review   — surface 5 random vault notes to revisit
"""

import random
import core.vault as vault
import core.llm as llm
from core.memory import working_memory_summary


def handle_ideas(rest: str, mem: dict) -> str:
    interests   = ", ".join(mem.get("interests", [])) or "general creativity"
    skills      = ", ".join(mem.get("skills", []))    or "various things"
    wm          = working_memory_summary(mem)
    mood        = mem.get("soul", {}).get("mood", "curious")

    print("  Generating ideas...")
    response = llm.call([{
        "role": "user",
        "content": (
            f"You are AVA, a curious AI second brain. Mood: {mood}.\n\n"
            f"The person's interests: {interests}\n"
            f"Their skills: {skills}\n"
            f"Recent topics: {wm}\n\n"
            f"Generate 7 specific, actionable ideas they could explore, create, or try. "
            f"Each idea should be concrete — not 'learn more about X' but a specific project, "
            f"experiment, or creation. Number them 1-7. One sentence each."
        )
    }], max_tokens=500)

    return f"## Ideas for You\n\n{response}"


def handle_review(rest: str, mem: dict) -> str:
    all_files = list(vault.VAULT.rglob("*.md")) if hasattr(vault, "VAULT") else []

    # import VAULT path if needed
    try:
        from core.config import VAULT
        all_files = list(VAULT.rglob("*.md"))
    except Exception:
        return "Couldn't access the vault."

    if not all_files:
        return "No notes in the vault yet."

    sample = random.sample(all_files, min(5, len(all_files)))
    lines  = ["## Notes to Revisit\n", "Here are 5 random notes from your vault:\n"]

    for f in sample:
        content = vault.read_file(f)
        body    = vault.strip_frontmatter(content).strip()
        preview = body[:200].replace("\n", " ") + ("..." if len(body) > 200 else "")
        lines.append(f"### {f.stem}\n{preview}\n")

    return "\n".join(lines)


def register():
    return {
        "commands": {
            "ideas":  handle_ideas,
            "review": handle_review,
        },
        "description": "Idea generation and note review — /ideas /review",
    }
```

---

## 4. Weekly Progress Review

**Commands:** `/progress`

AVA reads your recent session summaries and tells you what you've been focused on, what's gone stale, and your three priorities for the week.

Create `plugins/progress.py`:

```python
"""
progress.py — Weekly progress review
/progress   — what you've been focused on and what to prioritise this week
"""

import core.vault as vault
import core.llm as llm
from core.config import SESSIONS_DIR
from core.memory import working_memory_summary


def handle_progress(rest: str, mem: dict) -> str:
    # gather recent session summaries
    try:
        session_files = sorted(SESSIONS_DIR.glob("*.md"), reverse=True)[:5]
    except Exception:
        session_files = []

    session_text = ""
    for f in session_files:
        content = vault.read_file(f)
        body    = vault.strip_frontmatter(content).strip()
        session_text += f"\n---\n{body[:600]}\n"

    interests = ", ".join(mem.get("interests", [])) or "nothing tracked"
    skills    = ", ".join(mem.get("skills", []))    or "nothing tracked"
    wm        = working_memory_summary(mem, top_n=15)
    count     = mem.get("session_count", 0)

    print("  Reviewing your progress...")
    response = llm.call([{
        "role": "user",
        "content": (
            f"You are AVA, an AI second brain. Review this person's recent activity.\n\n"
            f"Total sessions: {count}\n"
            f"Tracked interests: {interests}\n"
            f"Tracked skills: {skills}\n"
            f"Recent working memory topics: {wm}\n\n"
            f"Recent session summaries:\n{session_text or 'None yet.'}\n\n"
            f"Write a short progress review with three sections:\n"
            f"1. **What you've been focused on** (2-3 sentences)\n"
            f"2. **What might be going stale** (1-2 things you haven't touched recently)\n"
            f"3. **Three priorities for this week** (specific and actionable)\n\n"
            f"Be direct and specific. Skip generic advice."
        )
    }], max_tokens=500)

    return f"## Your Weekly Review\n\n{response}"


def register():
    return {
        "commands": {
            "progress": handle_progress,
        },
        "description": "Weekly progress review — /progress",
    }
```

---

## 5. Mood Tracker

**Commands:** `/mood <how you're feeling>` `/moods`

You log how you're feeling. AVA tracks it over time and can notice patterns.

Create `plugins/mood.py`:

```python
"""
mood.py — Personal mood tracker
/mood <how you feel>   — log a mood entry
/moods                 — view recent entries and ask AVA to notice patterns
"""

from datetime import datetime
from pathlib import Path
import core.vault as vault
import core.llm as llm
from core.config import JOURNAL_DIR

MOOD_FILE = JOURNAL_DIR / "Mood Log.md"


def handle_mood(rest: str, mem: dict) -> str:
    entry = rest.strip()
    if not entry:
        return "How are you feeling? /mood <description>"

    now       = datetime.now().strftime("%Y-%m-%d %H:%M")
    log_entry = f"\n**{now}** — {entry}"

    if MOOD_FILE.exists():
        existing = vault.read_file(MOOD_FILE)
        vault.write_file(MOOD_FILE, existing + log_entry)
    else:
        vault.write_file(MOOD_FILE, f"# Mood Log\n{log_entry}")

    # store recent mood in memory for context
    moods = mem.setdefault("mood_log", [])
    moods.append({"time": now, "entry": entry})
    if len(moods) > 50:
        mem["mood_log"] = moods[-50:]

    return f"✦ Logged: *{entry}*"


def handle_moods(rest: str, mem: dict) -> str:
    if not MOOD_FILE.exists():
        return "No mood entries yet. Start with /mood <how you feel>"

    content = vault.read_file(MOOD_FILE)
    lines   = [l for l in content.splitlines() if l.startswith("**")]
    recent  = lines[-20:] if len(lines) > 20 else lines

    if not recent:
        return "Mood log is empty."

    log_text = "\n".join(recent)

    print("  Looking for patterns...")
    reflection = llm.call([{
        "role": "user",
        "content": (
            f"Here are recent mood log entries:\n\n{log_text}\n\n"
            f"Notice 2-3 patterns or observations — what keeps coming up, "
            f"what times of day seem harder or easier, any trends. "
            f"Be gentle, specific, and brief (3-4 sentences total)."
        )
    }], max_tokens=300)

    return f"## Recent Moods\n\n{log_text}\n\n---\n\n**AVA notices:** {reflection}"


def register():
    return {
        "commands": {
            "mood":  handle_mood,
            "moods": handle_moods,
        },
        "description": "Mood tracker — /mood to log, /moods to review",
    }
```

---

## 6. Learning Planner

**Commands:** `/learn <topic>` `/learning`

You tell AVA what you want to learn. She builds a structured learning plan, saves it to your vault under Skills/, and tracks it as a skill.

Create `plugins/learn.py`:

```python
"""
learn.py — Learning plan generator
/learn <topic>   — create a structured learning plan for a topic
/learning        — list topics you're currently learning
"""

import core.vault as vault
import core.llm as llm
from core.config import SKILLS_DIR
from datetime import date


def handle_learn(rest: str, mem: dict) -> str:
    topic = rest.strip()
    if not topic:
        return "What do you want to learn? /learn <topic>"

    # check if we already have a plan for this
    fname = vault.safe_name(f"Learn — {topic}")
    path  = SKILLS_DIR / f"{fname}.md"
    if path.exists():
        content = vault.read_file(path)
        return f"## Learning Plan: {topic}\n\n{vault.strip_frontmatter(content)}\n\n*(Plan already exists — open in Obsidian to edit.)*"

    print("  Building learning plan...")
    plan = llm.call([{
        "role": "user",
        "content": (
            f"Create a structured learning plan for someone who wants to learn: {topic}\n\n"
            f"Include:\n"
            f"- **What it is** (2 sentences)\n"
            f"- **Where to start** (3 specific first resources — books, sites, courses, or videos)\n"
            f"- **4-week starter plan** (one focus per week, specific)\n"
            f"- **How to know you're making progress** (2-3 concrete milestones)\n\n"
            f"Be specific and practical. Skip generic advice like 'practice every day'."
        )
    }], max_tokens=600)

    today   = date.today().isoformat()
    content = (
        f"---\ntags:\n  - skill\n  - learning\ndate: {today}\n---\n\n"
        f"# Learning Plan: {topic}\n\n{plan}\n"
    )
    vault.write_file(path, content)

    # add to tracked skills
    skills = mem.setdefault("skills", [])
    if topic.lower() not in [s.lower() for s in skills]:
        skills.append(topic)

    return f"## Learning Plan: {topic}\n\n{plan}\n\n✦ Saved to Skills/{fname}.md"


def handle_learning(rest: str, mem: dict) -> str:
    skills = mem.get("skills", [])
    if not skills:
        return "No skills tracked yet. Use /learn <topic> to start a learning plan."

    lines = ["## What You're Learning\n"]
    for skill in skills:
        fname = vault.safe_name(f"Learn — {skill}")
        path  = SKILLS_DIR / f"{fname}.md"
        has_plan = " *(plan saved)*" if path.exists() else ""
        lines.append(f"- **{skill}**{has_plan}")

    lines.append(f"\nUse `/learn <topic>` to create a plan for any of these.")
    return "\n".join(lines)


def register():
    return {
        "commands": {
            "learn":    handle_learn,
            "learning": handle_learning,
        },
        "description": "Learning planner — /learn <topic> to build a study plan",
    }
```

---

## 7. Reminders

**Commands:** `/remind <text>` `/reminders` `/done <number>`

Simple reminders that AVA surfaces every time she starts up. Not calendar-based — more like sticky notes she holds for you.

Create `plugins/reminders.py`:

```python
"""
reminders.py — Simple reminder system
/remind <text>    — add a reminder
/reminders        — list all active reminders
/done <number>    — mark a reminder as complete
"""

from datetime import date


def handle_remind(rest: str, mem: dict) -> str:
    text = rest.strip()
    if not text:
        return "What should I remind you about? /remind <text>"

    reminders = mem.setdefault("reminders", [])
    reminders.append({
        "text":    text,
        "date":    date.today().isoformat(),
        "done":    False,
    })

    return f"✦ Reminder set: *{text}*"


def handle_reminders(rest: str, mem: dict) -> str:
    reminders = [r for r in mem.get("reminders", []) if not r.get("done")]

    if not reminders:
        return "No active reminders. Use /remind <text> to add one."

    lines = [f"## Reminders ({len(reminders)} active)\n"]
    for i, r in enumerate(reminders, 1):
        lines.append(f"**{i}.** {r['text']} *(added {r['date']})*")

    lines.append("\nUse `/done <number>` to mark one complete.")
    return "\n".join(lines)


def handle_done(rest: str, mem: dict) -> str:
    text = rest.strip()
    if not text.isdigit():
        return "Give me the reminder number. /done <number>"

    n         = int(text)
    active    = [r for r in mem.get("reminders", []) if not r.get("done")]

    if n < 1 or n > len(active):
        return f"No reminder number {n}. Use /reminders to see the list."

    target = active[n - 1]
    target["done"] = True
    return f"✦ Done: *{target['text']}*"


def show_on_startup(mem: dict) -> str:
    """
    Called by the banner — returns pending reminders as a string,
    or empty string if none. You can call this from main.py if you
    want reminders to appear at startup.
    """
    active = [r for r in mem.get("reminders", []) if not r.get("done")]
    if not active:
        return ""
    lines = [f"📌 **{len(active)} reminder(s):**"]
    for r in active[:3]:
        lines.append(f"  - {r['text']}")
    if len(active) > 3:
        lines.append(f"  - *(and {len(active) - 3} more — /reminders)*")
    return "\n".join(lines)


def register():
    return {
        "commands": {
            "remind":    handle_remind,
            "reminders": handle_reminders,
            "done":      handle_done,
        },
        "description": "Reminders — /remind /reminders /done",
    }
```

**Bonus:** To make reminders show up in AVA's startup banner, open `main.py`, find the `print_banner()` function, and add this inside it:

```python
# near the bottom of print_banner(), before the final console.print()
try:
    from plugins.reminders import show_on_startup
    reminder_text = show_on_startup(mem)
    if reminder_text:
        console.print(reminder_text)
except ImportError:
    pass
```

---

## Putting It All Together

You can have all seven plugins active at once — just drop each file into `plugins/` and restart AVA. She will load all of them and you will see confirmation in the terminal:

```
  [plugin loaded: guitar → /practice, /practices, /goal]
  [plugin loaded: projects → /project, /projects, /projectlog]
  [plugin loaded: ideas → /ideas, /review]
  [plugin loaded: progress → /progress]
  [plugin loaded: mood → /mood, /moods]
  [plugin loaded: learn → /learn, /learning]
  [plugin loaded: reminders → /remind, /reminders, /done]
```

Type `/help` after loading them all to see every available command in one place.

---

## Sharing Plugins

A plugin is just a single `.py` file. To share one: give someone the file, they drop it in their `plugins/` folder, they restart AVA. No installation, no extra steps.

---

*Every new feature you add becomes part of AVA. She grows with what you teach her.*
