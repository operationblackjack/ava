"""
sessions.py — Session saving and summaries
Auto-saves a summary of each conversation to the vault at /quit.
Sessions use the uniform note structure and only link to other sessions.
"""

from datetime import datetime
import core.vault as vault
import core.llm as llm
from core.config import SESSIONS_DIR, SESSIONS_INDEX


def ensure_index():
    if not SESSIONS_INDEX.exists():
        vault.write_file(
            SESSIONS_INDEX,
            "---\ntags:\n  - index\n---\n\n# Sessions\n\nAll conversations with AVA.\n"
        )


def save(history: list[dict], mem: dict) -> str:
    """
    Summarise the conversation and save it as a uniform structured note.
    Returns the filename stem.
    """
    ensure_index()
    if not history:
        return ""

    transcript_lines = []
    for msg in history[-30:]:
        role    = "You" if msg["role"] == "user" else "AVA"
        content = msg["content"]
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
        transcript_lines.append(f"{role}: {content}")
    transcript = "\n".join(transcript_lines)

    summary = llm.call([{
        "role": "user",
        "content": (
            "Summarise this conversation between a user and their AI second brain (AVA). "
            "In 3-5 sentences: what was discussed, what was decided or created, "
            "any interesting ideas that came up. Be concise and factual.\n\n"
            f"Conversation:\n{transcript}"
        ),
    }], max_tokens=300)

    now    = datetime.now()
    stamp  = now.strftime("%Y-%m-%d_%H%M")
    title  = f"Session {stamp}"
    today  = now.strftime("%Y-%m-%d")

    # body for the uniform note
    body = (
        f"**Date:** {now.strftime('%Y-%m-%d %H:%M')}  \n"
        f"**Session #:** {mem.get('session_count', 0)}\n\n"
        f"## Summary\n\n{summary}"
    )

    # session notes only link to other session notes
    related = vault.smart_related(summary, exclude_stem=title, folder=SESSIONS_DIR, max_links=3)

    note_str = vault.build_frontmatter(["session"], {"session_n": mem.get("session_count", 0)})
    note_str += f"# {title}\n\n{body}\n"
    if related:
        note_str += "\n## Related\n" + "\n".join(f"- [[{r}]]" for r in related) + "\n"

    path = SESSIONS_DIR / f"{title}.md"
    vault.write_file(path, note_str)

    # update the Sessions index cleanly (no raw appending)
    index = vault.read_file(SESSIONS_INDEX)
    if f"[[{title}]]" not in index:
        index = index.rstrip() + f"\n- [[{title}]]\n"
        vault.write_file(SESSIONS_INDEX, index)

    return title
