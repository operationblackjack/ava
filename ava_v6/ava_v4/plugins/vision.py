"""
vision.py — AVA can see and describe images
/vision <path or url> [question]   — describe a local image, or ask about it
/see <path or url> [question]      — alias for /vision

Supports local file paths (png, jpg, jpeg, gif, webp) and http(s) URLs.
Uses core.llm.call_vision, which routes through Groq's vision model first
and falls back to OpenRouter.
"""

import base64
import mimetypes
from pathlib import Path

import httpx
import core.llm as llm
import core.vault as vault

_DEFAULT_PROMPT = (
    "Describe this image in detail. Note the overall scene, key subjects, "
    "colours, mood, and any text visible in the image."
)

_VALID_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def _load_image(src: str) -> tuple[str, str] | tuple[None, str]:
    """
    Returns (base64_data, mime_type) on success, or (None, error_message).
    """
    src = src.strip().strip('"').strip("'")

    if src.startswith("http://") or src.startswith("https://"):
        try:
            resp = httpx.get(src, timeout=30, follow_redirects=True)
            resp.raise_for_status()
        except Exception as e:
            return None, f"Couldn't download image: {e}"
        mime = resp.headers.get("content-type", "").split(";")[0].strip()
        if not mime or not mime.startswith("image/"):
            mime = mimetypes.guess_type(src)[0] or "image/jpeg"
        return base64.b64encode(resp.content).decode("ascii"), mime

    path = Path(src)
    if not path.exists():
        return None, f"File not found: {src}"
    if path.suffix.lower() not in _VALID_EXT:
        return None, f"Unsupported image type: {path.suffix}. Use png, jpg, jpeg, gif, or webp."
    try:
        data = path.read_bytes()
    except Exception as e:
        return None, f"Couldn't read file: {e}"
    mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    return base64.b64encode(data).decode("ascii"), mime


def handle_vision(rest: str, mem: dict) -> str:
    rest = rest.strip()
    if not rest:
        return (
            "Give me an image to look at: `/vision <path or url>` "
            "or `/vision <path or url> | <question>`"
        )

    # allow "/vision path | question" or "/vision path question"
    if "|" in rest:
        src, _, question = rest.partition("|")
        src, question = src.strip(), question.strip()
    else:
        parts = rest.split(None, 1)
        src = parts[0]
        question = parts[1].strip() if len(parts) > 1 else ""

    b64, mime_or_err = _load_image(src)
    if b64 is None:
        return f"⚠ {mime_or_err}"

    prompt = question or _DEFAULT_PROMPT
    print("  Looking at the image...")

    try:
        description = llm.call_vision(prompt, b64, mime=mime_or_err, max_tokens=500)
    except Exception as e:
        return f"⚠ Vision call failed: {e}"

    return f"## What I see\n\n{description}"


def register():
    return {
        "commands": {
            "vision": handle_vision,
            "see":    handle_vision,
        },
        "description": "AVA can see images — /vision <path or url> [| question]",
    }
