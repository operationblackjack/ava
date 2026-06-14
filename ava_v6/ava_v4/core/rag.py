"""
rag.py — Vault RAG (Retrieval-Augmented Generation)

Before AVA answers, this module searches the vault for notes relevant
to what the user just said and injects them into her context window.
She actually reads your notes before replying.

Design:
  - Fast keyword search first (no API cost)
  - Score by term frequency + recency bonus
  - Return top N note snippets, capped at a token budget
  - Graceful: if vault is empty or search fails, returns ""
"""

import re
from datetime import date
from pathlib import Path

from core.config import VAULT, NOTES_DIR, IDEAS_DIR, JOURNAL_DIR, TASTES_DIR, SESSIONS_DIR

# Folders RAG searches (ordered by priority)
_SEARCH_DIRS = [NOTES_DIR, IDEAS_DIR, JOURNAL_DIR, TASTES_DIR]

# Stop-words to ignore when scoring
_STOP = {
    "the", "and", "for", "that", "this", "with", "from", "have", "will",
    "your", "they", "been", "what", "when", "were", "their", "there",
    "about", "which", "some", "more", "also", "into", "just", "like",
    "very", "much", "know", "think", "want", "need", "make", "good",
    "would", "could", "should", "really", "thing", "things",
}

_MAX_RESULTS   = 4     # max notes to include
_SNIPPET_CHARS = 400   # chars per note snippet
_MIN_SCORE     = 2     # minimum keyword hits to qualify


def _extract_query_terms(user_input: str) -> set[str]:
    """Pull meaningful terms from the user's message."""
    words = re.findall(r"\b[a-zA-Z]{3,}\b", user_input.lower())
    return {w for w in words if w not in _STOP}


def _score_file(path: Path, terms: set[str]) -> float:
    """Score a note file by keyword overlap + recency bonus."""
    try:
        text = path.read_text(encoding="utf-8").lower()
    except Exception:
        return 0.0

    score = 0.0
    for term in terms:
        count = text.count(term)
        if count > 0:
            score += 1 + min(count - 1, 3) * 0.25  # diminishing returns

    if score < _MIN_SCORE:
        return 0.0

    # recency bonus: prefer recently modified files
    try:
        mtime = path.stat().st_mtime
        import time
        days_old = (time.time() - mtime) / 86400
        if days_old < 7:
            score += 1.0
        elif days_old < 30:
            score += 0.5
    except Exception:
        pass

    return score


def _extract_snippet(path: Path, terms: set[str]) -> str:
    """Extract the most relevant snippet from a note."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return ""

    # strip frontmatter
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            text = text[end + 3:].lstrip()

    # strip title line
    lines = text.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]

    # find the paragraph most dense with query terms
    paragraphs = "\n".join(lines).split("\n\n")
    best_para  = ""
    best_score = 0
    for para in paragraphs:
        para_lower = para.lower()
        s = sum(para_lower.count(t) for t in terms)
        if s > best_score:
            best_score = s
            best_para  = para

    snippet = (best_para or "\n".join(lines[:8])).strip()
    if len(snippet) > _SNIPPET_CHARS:
        snippet = snippet[:_SNIPPET_CHARS].rsplit(" ", 1)[0] + "…"

    return snippet


def surface_stale_relevant(mem: dict, stale_days: int = 14, max_results: int = 3) -> str:
    """
    Find notes that haven't been touched in a while but share keywords with
    the user's current working-memory focus topics. These are candidates to
    "bubble up" — things connected to what you're thinking about now that
    you haven't revisited recently.

    Returns a formatted string for injection into the system prompt or
    morning briefing, or "" if nothing qualifies.
    """
    import time

    wm = mem.get("working_memory", {})
    if not wm:
        return ""

    # take the hottest current topics as our "active" keyword set
    hot_topics = sorted(wm.items(), key=lambda x: x[1].get("weight", 0)
                         if isinstance(x[1], dict) else x[1], reverse=True)
    hot_terms = {t for t, _ in hot_topics[:8] if t not in _STOP}
    if not hot_terms:
        return ""

    now    = time.time()
    cutoff = now - stale_days * 86400

    candidates: list[tuple[float, Path, int]] = []  # (score, path, days_old)

    for search_dir in _SEARCH_DIRS:
        if not search_dir.exists():
            continue
        for path in search_dir.glob("*.md"):
            try:
                mtime = path.stat().st_mtime
            except Exception:
                continue
            if mtime > cutoff:
                continue  # only interested in stale notes

            try:
                text = path.read_text(encoding="utf-8").lower()
            except Exception:
                continue

            overlap = sum(1 for t in hot_terms if t in text)
            if overlap < 2:
                continue

            days_old = int((now - mtime) / 86400)
            candidates.append((overlap, path, days_old))

    if not candidates:
        return ""

    candidates.sort(key=lambda x: x[0], reverse=True)
    top = candidates[:max_results]

    lines = ["## Notes worth revisiting\n"]
    for _, path, days_old in top:
        lines.append(
            f"- [[{path.stem}]] — untouched for {days_old} days, but connects to "
            f"things you've been talking about lately ({', '.join(list(hot_terms)[:4])})"
        )
    return "\n".join(lines)

def retrieve(user_input: str, max_results: int = _MAX_RESULTS) -> str:
    """
    Search the vault for notes relevant to user_input.
    Returns a formatted string ready to inject into the system prompt,
    or "" if nothing relevant is found.
    """
    terms = _extract_query_terms(user_input)
    if not terms:
        return ""

    scored: list[tuple[float, Path]] = []

    for search_dir in _SEARCH_DIRS:
        if not search_dir.exists():
            continue
        for path in search_dir.glob("*.md"):
            score = _score_file(path, terms)
            if score >= _MIN_SCORE:
                scored.append((score, path))

    if not scored:
        return ""

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:max_results]

    blocks = []
    for score, path in top:
        snippet = _extract_snippet(path, terms)
        if snippet:
            blocks.append(f"[[{path.stem}]]\n{snippet}")

    if not blocks:
        return ""

    return "## Relevant notes from your vault\n\n" + "\n\n---\n\n".join(blocks)


def retrieve_sessions(user_input: str, max_results: int = 2) -> str:
    """
    Search past session summaries for ones relevant to user_input.
    Returns a formatted string with the matching session summaries
    (so AVA can say "last time we talked about this you said X"),
    or "" if nothing relevant is found.
    """
    terms = _extract_query_terms(user_input)
    if not terms or not SESSIONS_DIR.exists():
        return ""

    scored: list[tuple[float, Path]] = []
    for path in SESSIONS_DIR.glob("*.md"):
        score = _score_file(path, terms)
        if score >= _MIN_SCORE:
            scored.append((score, path))

    if not scored:
        return ""

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:max_results]

    blocks = []
    for score, path in top:
        text = path.read_text(encoding="utf-8")
        if text.startswith("---"):
            end = text.find("---", 3)
            if end != -1:
                text = text[end + 3:].lstrip()
        # pull just the Summary section if present
        if "## Summary" in text:
            summary = text.split("## Summary", 1)[1].strip()
        else:
            summary = text.strip()
        if len(summary) > _SNIPPET_CHARS:
            summary = summary[:_SNIPPET_CHARS].rsplit(" ", 1)[0] + "…"
        blocks.append(f"[[{path.stem}]]\n{summary}")

    if not blocks:
        return ""

    return "## Relevant past conversations\n\n" + "\n\n---\n\n".join(blocks)

