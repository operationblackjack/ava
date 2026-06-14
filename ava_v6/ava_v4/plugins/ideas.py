"""
ideas.py — Idea generation and note review
/ideas    — generate 7 ideas based on your interests
/review   — surface 5 random vault notes to revisit
"""

import random
import core.vault as vault
import core.llm as llm
from core.memory import working_memory_summary
from core.config import VAULT


def handle_ideas(rest: str, mem: dict) -> str:
    interests = ", ".join(mem.get("interests", [])) or "general creativity"
    skills    = ", ".join(mem.get("skills", []))    or "various things"
    wm        = working_memory_summary(mem)
    mood      = mem.get("soul", {}).get("mood", "curious")
    print("  Generating ideas...")
    response = llm.call([{"role": "user", "content": (
        f"You are AVA, a curious AI second brain. Mood: {mood}.\n\n"
        f"Person's interests: {interests}\nSkills: {skills}\nRecent topics: {wm}\n\n"
        f"Generate 7 specific, actionable ideas they could explore or create. "
        f"Each should be a concrete project or experiment, not generic advice. "
        f"Number them 1-7. One sentence each."
    )}], max_tokens=500)
    return f"## Ideas for You\n\n{response}"


def handle_review(rest: str, mem: dict) -> str:
    try:
        all_files = list(VAULT.rglob("*.md"))
    except Exception:
        return "Couldn't access the vault."
    if not all_files:
        return "No notes in the vault yet."
    sample = random.sample(all_files, min(5, len(all_files)))
    lines  = ["## Notes to Revisit\n"]
    for f in sample:
        body    = vault.strip_frontmatter(vault.read_file(f)).strip()
        preview = body[:200].replace("\n", " ") + ("..." if len(body) > 200 else "")
        lines.append(f"### {f.stem}\n{preview}\n")
    return "\n".join(lines)


def register():
    return {
        "commands": {"ideas": handle_ideas, "review": handle_review},
        "description": "Idea generation and review — /ideas /review",
    }
