"""
contradictions.py — Lightweight contradiction detection

Before AVA acts on something new the user said, this module does a cheap
keyword-based scan of the vault (tastes, notes, about-me) for statements
that might conflict — e.g. "I hate horror" vs "recommend me horror movies".

It does NOT try to be a general logic checker. It looks for a small set of
strong-opinion/preference patterns (like/dislike, love/hate, always/never)
sharing a topic word, and flags them for AVA to ask about rather than
silently overwrite. Final judgment is left to the LLM — this just surfaces
candidates.
"""

import re
from pathlib import Path
from core.config import TASTES_DIR, NOTES_DIR, ABOUT_FILE

# Opposing sentiment word pairs. If the user's current message and a past
# note both mention the same topic but use opposite-polarity words, flag it.
_POSITIVE = {
    "love", "like", "enjoy", "enjoys", "favorite", "favourite", "into", "obsessed",
    # interest/request signals — asking for more of something counts as "wanting" it
    "recommend", "recommendation", "recommendations", "suggest", "suggestions",
    "looking for", "want more", "more of", "any good", "give me",
}
_NEGATIVE = {"hate", "hates", "dislike", "dislikes", "can't stand", "cant stand", "avoid", "despise", "never"}

_STOP = {
    "the", "and", "for", "that", "this", "with", "from", "have", "will",
    "your", "they", "been", "what", "when", "were", "their", "there",
    "about", "which", "some", "more", "also", "into", "just", "like",
    "very", "much", "know", "think", "want", "need", "make", "good",
    "would", "could", "should", "really", "thing", "things", "love",
    "hate", "favorite", "favourite",
}

_SEARCH_DIRS = [TASTES_DIR, NOTES_DIR]


def _polarity(text: str) -> str | None:
    text_l = text.lower()
    has_pos = any(w in text_l for w in _POSITIVE)
    has_neg = any(w in text_l for w in _NEGATIVE)
    if has_pos and not has_neg:
        return "positive"
    if has_neg and not has_pos:
        return "negative"
    return None


def _topic_words(text: str) -> set[str]:
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    return {w for w in words if w not in _STOP}


def check(user_input: str, max_results: int = 2) -> str:
    """
    Scan tastes/notes/About Me for statements that share a topic with
    user_input but have opposite sentiment polarity.

    Returns a formatted string for the system prompt describing potential
    contradictions, or "" if none found or input has no clear polarity.
    """
    current_polarity = _polarity(user_input)
    if current_polarity is None:
        return ""

    topics = _topic_words(user_input)
    if not topics:
        return ""

    candidates: list[tuple[int, Path, str]] = []  # (overlap, path, snippet)

    files: list[Path] = []
    for d in _SEARCH_DIRS:
        if d.exists():
            files.extend(d.glob("*.md"))
    if ABOUT_FILE.exists():
        files.append(ABOUT_FILE)

    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue

        # check paragraph by paragraph for opposite polarity + topic overlap
        for para in text.split("\n\n"):
            para_l = para.lower()
            para_polarity = _polarity(para)
            if para_polarity is None or para_polarity == current_polarity:
                continue
            para_topics = _topic_words(para)
            overlap = topics & para_topics
            if len(overlap) >= 1:
                snippet = para.strip().replace("\n", " ")
                if len(snippet) > 200:
                    snippet = snippet[:200].rsplit(" ", 1)[0] + "…"
                candidates.append((len(overlap), path, snippet))

    if not candidates:
        return ""

    candidates.sort(key=lambda x: x[0], reverse=True)
    top = candidates[:max_results]

    lines = ["## Possible contradiction detected\n"]
    lines.append(
        f"The user just said something with **{current_polarity}** sentiment. "
        f"But the following past notes express the **opposite** sentiment "
        f"on what looks like the same topic:\n"
    )
    for _, path, snippet in top:
        lines.append(f"- [[{path.stem}]]: \"{snippet}\"")
    lines.append(
        "\nDon't silently overwrite or ignore this. Gently point out the "
        "tension and ask which one reflects how they currently feel — "
        "maybe their taste changed, maybe this is a different context, "
        "or maybe it's worth noting as nuance rather than a flat contradiction."
    )
    return "\n".join(lines)
