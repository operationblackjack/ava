"""
learn.py — Learning plan generator
/learn <topic>   — create a structured learning plan
/learning        — list what you're currently learning
"""

from datetime import date
import core.vault as vault
import core.llm as llm
from core.config import SKILLS_DIR


def handle_learn(rest: str, mem: dict) -> str:
    topic = rest.strip()
    if not topic:
        return "What do you want to learn? /learn <topic>"
    fname = vault.safe_name(f"Learn — {topic}")
    path  = SKILLS_DIR / f"{fname}.md"
    if path.exists():
        return (
            f"## Learning Plan: {topic}\n\n"
            f"{vault.strip_frontmatter(vault.read_file(path))}\n\n"
            f"*(Plan already exists — open in Obsidian to edit.)*"
        )
    print("  Building learning plan...")
    plan = llm.call([{"role": "user", "content": (
        f"Create a structured learning plan for: {topic}\n\n"
        f"Include:\n"
        f"- **What it is** (2 sentences)\n"
        f"- **Where to start** (3 specific resources — books, sites, or courses)\n"
        f"- **4-week starter plan** (one focus per week, specific)\n"
        f"- **How to know you're progressing** (2-3 concrete milestones)\n\n"
        f"Be practical. Skip generic advice."
    )}], max_tokens=600)
    today   = date.today().isoformat()
    content = f"---\ntags:\n  - skill\n  - learning\ndate: {today}\n---\n\n# Learning Plan: {topic}\n\n{plan}\n"
    vault.write_file(path, content)
    skills = mem.setdefault("skills", [])
    if topic.lower() not in [s.lower() for s in skills]:
        skills.append(topic)
    return f"## Learning Plan: {topic}\n\n{plan}\n\n✦ Saved to Skills/{fname}.md"


def handle_learning(rest: str, mem: dict) -> str:
    skills = mem.get("skills", [])
    if not skills:
        return "No skills tracked yet. Use /learn <topic> to start a plan."
    lines = ["## What You're Learning\n"]
    for skill in skills:
        fname    = vault.safe_name(f"Learn — {skill}")
        has_plan = " *(plan saved)*" if (SKILLS_DIR / f"{fname}.md").exists() else ""
        lines.append(f"- **{skill}**{has_plan}")
    return "\n".join(lines)


def register():
    return {
        "commands": {"learn": handle_learn, "learning": handle_learning},
        "description": "Learning planner — /learn <topic> /learning",
    }
