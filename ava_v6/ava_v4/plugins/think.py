"""
think.py — A proper thinking partner
/think <question or problem>

Instead of answering immediately, AVA:
  1. Searches the vault broadly for anything related (notes, ideas, tastes,
     journal, sessions, projects).
  2. Looks for contradictions or tensions between what it finds.
  3. Reasons step by step, citing the user's own prior notes back to them.
  4. Returns a structured response: relevant context, tensions/connections,
     reasoning, and a conclusion or next step.

This is intentionally slower and more deliberate than normal chat.
"""

import re
from pathlib import Path

import core.llm as llm
import core.vault as vault
from core.config import (
    NOTES_DIR, IDEAS_DIR, JOURNAL_DIR, TASTES_DIR, PROJECTS_DIR, SESSIONS_DIR
)

_SEARCH_DIRS = [NOTES_DIR, IDEAS_DIR, TASTES_DIR, PROJECTS_DIR, JOURNAL_DIR, SESSIONS_DIR]

_STOP = {
    "the", "and", "for", "that", "this", "with", "from", "have", "will",
    "your", "they", "been", "what", "when", "were", "their", "there",
    "about", "which", "some", "more", "also", "into", "just", "like",
    "very", "much", "know", "think", "want", "need", "make", "good",
    "would", "could", "should", "really", "thing", "things", "does",
    "should", "doing", "going",
}

_MAX_SOURCES   = 6
_SNIPPET_CHARS = 350
_MIN_SCORE     = 2


def _terms(text: str) -> set[str]:
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    return {w for w in words if w not in _STOP}


def _gather_sources(question: str) -> list[tuple[Path, str]]:
    """Find vault files relevant to the question, return (path, snippet) pairs."""
    terms = _terms(question)
    if not terms:
        return []

    scored: list[tuple[float, Path]] = []
    for d in _SEARCH_DIRS:
        if not d.exists():
            continue
        for path in d.glob("*.md"):
            try:
                text = path.read_text(encoding="utf-8").lower()
            except Exception:
                continue
            score = sum(1 + min(text.count(t) - 1, 3) * 0.25 for t in terms if t in text)
            if score >= _MIN_SCORE:
                scored.append((score, path))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:_MAX_SOURCES]

    results = []
    for _, path in top:
        try:
            raw = vault.strip_frontmatter(vault.read_file(path)).strip()
        except Exception:
            continue
        if len(raw) > _SNIPPET_CHARS:
            raw = raw[:_SNIPPET_CHARS].rsplit(" ", 1)[0] + "…"
        results.append((path, raw))

    return results


def handle_think(rest: str, mem: dict) -> str:
    question = rest.strip()
    if not question:
        return "What's on your mind? `/think <question or problem>`"

    print("  Reading through your vault...")
    sources = _gather_sources(question)

    if sources:
        source_block = "\n\n---\n\n".join(
            f"[[{path.stem}]] ({path.parent.name})\n{snippet}"
            for path, snippet in sources
        )
    else:
        source_block = "(Nothing directly relevant found in the vault — reason from first principles, but say so.)"

    print("  Thinking it through...")

    prompt = f"""You are AVA, acting as a thinking partner — not a chatbot giving a quick answer.

The user has a question or problem they want to think through:

"{question}"

Here is material from their own vault (notes, ideas, journal, projects, past sessions)
that might be relevant:

{source_block}

Your job:
1. **Relevant context** — briefly summarise what their own notes already say that's
   relevant (cite specific notes by [[name]] where you draw on them). If nothing is
   relevant, say so plainly.
2. **Tensions or connections** — point out any contradictions, unresolved questions,
   or interesting connections between what you found. Be honest if their past
   thinking conflicts with the framing of their current question.
3. **Reasoning** — walk through the problem step by step. Use their own prior
   thinking as material to reason WITH, not just decoration.
4. **Where this leaves you** — a clear conclusion, recommendation, or — if the
   problem is genuinely unresolved — a sharper version of the question they
   should actually be asking.

Be direct and substantive. This should feel like thinking out loud with someone
who actually knows their stuff, not a generic answer. Use headers for the four
sections above. Aim for 300-500 words."""

    response = llm.call([{"role": "user", "content": prompt}], max_tokens=900)
    return response


def register():
    return {
        "commands": {"think": handle_think},
        "description": "Structured reasoning — /think <question>, draws on your vault as source material",
    }
