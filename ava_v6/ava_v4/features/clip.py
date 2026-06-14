"""
clip.py — Web clipping
Handles: /clip <url>
Fetches a page, summarises it with the LLM, and saves it as a note.
"""

import re
import httpx
import core.vault as vault
import core.llm as llm


def _fetch_page(url: str) -> tuple[str, str]:
    """Fetch page text and title. Returns (title, text)."""
    try:
        resp = httpx.get(url, timeout=20, follow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0 (AVA/1.0)"})
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        return "", f"Could not fetch the page: {e}"

    # pull title
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else "Web Clip"
    title = re.sub(r"\s+", " ", title)

    # strip tags, collapse whitespace
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&[a-z]+;", " ", text)
    text = re.sub(r"\s{3,}", "\n\n", text)
    text = text[:6000]   # keep it manageable for the LLM

    return title, text


def cmd_clip(rest: str, mem: dict) -> str:
    """Usage: /clip <url>"""
    url = rest.strip()
    if not url:
        return "Give me a URL. /clip <url>"
    if not url.startswith("http"):
        url = "https://" + url

    print("  Fetching page...")
    title, page_text = _fetch_page(url)

    if not page_text or page_text.startswith("Could not"):
        return page_text or "Failed to fetch the page."

    print("  Summarising...")
    summary = llm.call([
        {
            "role": "user",
            "content": (
                f"Summarise this web page concisely for a personal knowledge base. "
                f"Include: what it's about, key points, and why it might be useful. "
                f"Keep it under 300 words. Use plain prose, no headers.\n\n"
                f"Page title: {title}\n\nContent:\n{page_text}"
            ),
        }
    ], max_tokens=400)

    note_content = f"Source: {url}\n\n{summary}"
    status, fname = vault.create_note(title, note_content, tags=["clip", "web"])

    return f"✦ Clipped and saved: **{fname}**\n\n{summary}"


def register():
    return {
        "commands": {
            "clip": cmd_clip,
        },
        "description": "Web clipping — /clip <url> to save and summarise a page",
    }
