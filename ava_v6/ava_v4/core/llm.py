"""
llm.py — AVA LLM routing
Primary: Groq (free, fast, OpenAI-compatible)
Fallback: OpenRouter (if all Groq keys exhausted)
"""

import httpx
from core.config import (
    OPENROUTER_KEYS, GROQ_KEYS, GROQ_MODEL, MODEL,
    GROQ_VISION_MODEL, OPENROUTER_VISION_MODEL,
)

# ── Key state ─────────────────────────────────────────────────────────────────
_groq_idx = 0
_or_idx   = 0

_GROQ_BASE = "https://api.groq.com/openai/v1/chat/completions"
_OR_BASE   = "https://openrouter.ai/api/v1/chat/completions"


# ── Key rotation helpers ───────────────────────────────────────────────────────

def _next_groq() -> bool:
    global _groq_idx
    start = _groq_idx
    for _ in range(len(GROQ_KEYS)):
        _groq_idx = (_groq_idx + 1) % len(GROQ_KEYS)
        if not GROQ_KEYS[_groq_idx].startswith("YOUR_"):
            if _groq_idx != start:
                return True
    return False


def _next_or() -> bool:
    global _or_idx
    start = _or_idx
    for _ in range(len(OPENROUTER_KEYS)):
        _or_idx = (_or_idx + 1) % len(OPENROUTER_KEYS)
        if not OPENROUTER_KEYS[_or_idx].startswith("YOUR_"):
            if _or_idx != start:
                return True
    return False


def _groq_configured() -> bool:
    return any(not k.startswith("YOUR_") for k in GROQ_KEYS)


def _or_configured() -> bool:
    return any(not k.startswith("YOUR_") for k in OPENROUTER_KEYS)


# ── Core call ─────────────────────────────────────────────────────────────────

def call(
    messages: list[dict],
    model: str | None = None,
    max_tokens: int = 600,
) -> str:
    """
    Send messages to Groq first, fall back to OpenRouter if Groq
    is exhausted or unconfigured.
    """
    # ── Try Groq ──────────────────────────────────────────────────────────────
    if _groq_configured():
        result = _call_groq(messages, model or GROQ_MODEL, max_tokens)
        if result is not None:
            return result
        print("  [Groq exhausted — falling back to OpenRouter]")

    # ── Try OpenRouter ────────────────────────────────────────────────────────
    if _or_configured():
        result = _call_openrouter(messages, model or MODEL, max_tokens)
        if result is not None:
            return result

    raise RuntimeError(
        "All API keys are exhausted or unconfigured. "
        "Check GROQ_KEYS / OPENROUTER_KEYS in core/config.py"
    )


def call_vision(prompt: str, image_b64: str, mime: str = "image/jpeg", max_tokens: int = 500) -> str:
    """
    Send an image + text prompt to a vision-capable model.
    Tries Groq's vision model first, then OpenRouter's.
    image_b64 must be raw base64 (no data: prefix).
    """
    content = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
    ]
    messages = [{"role": "user", "content": content}]

    if _groq_configured():
        result = _call_groq(messages, GROQ_VISION_MODEL, max_tokens)
        if result is not None:
            return result
        print("  [Groq vision exhausted — falling back to OpenRouter]")

    if _or_configured():
        result = _call_openrouter(messages, OPENROUTER_VISION_MODEL, max_tokens)
        if result is not None:
            return result

    raise RuntimeError(
        "All API keys are exhausted or unconfigured for vision. "
        "Check GROQ_KEYS / OPENROUTER_KEYS in core/config.py"
    )



    global _groq_idx
    tried: set[int] = set()

    while True:
        key = GROQ_KEYS[_groq_idx]
        if key.startswith("YOUR_") or _groq_idx in tried:
            if not _next_groq():
                return None
            continue

        tried.add(_groq_idx)

        try:
            resp = httpx.post(
                _GROQ_BASE,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type":  "application/json",
                },
                json={
                    "model":      model,
                    "messages":   messages,
                    "max_tokens": max_tokens,
                },
                timeout=60,
            )

            if resp.status_code == 429:
                # rate limited or out of daily quota
                body = resp.json()
                err  = body.get("error", {}).get("message", "rate limit")
                print(f"  [Groq key {_groq_idx + 1}: {err}. Rotating...]")
                if not _next_groq():
                    return None
                tried.add(_groq_idx - 1)
                continue

            if resp.status_code in (401, 403):
                print(f"  [Groq key {_groq_idx + 1}: auth error. Rotating...]")
                if not _next_groq():
                    return None
                continue

            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code in (429, 401, 403):
                if not _next_groq():
                    return None
                continue
            raise

        except httpx.TimeoutException:
            print("  [Groq timeout — retrying with next key]")
            if not _next_groq():
                return None
            continue


def _call_openrouter(messages: list[dict], model: str, max_tokens: int) -> str | None:
    global _or_idx
    tried: set[int] = set()

    while True:
        key = OPENROUTER_KEYS[_or_idx]
        if key.startswith("YOUR_") or _or_idx in tried:
            if not _next_or():
                return None
            continue

        tried.add(_or_idx)

        try:
            resp = httpx.post(
                _OR_BASE,
                headers={
                    "Authorization": f"Bearer {key}",
                    "HTTP-Referer":  "ava",
                    "X-Title":       "AVA Second Brain",
                    "Content-Type":  "application/json",
                },
                json={
                    "model":      model,
                    "messages":   messages,
                    "max_tokens": max_tokens,
                },
                timeout=60,
            )

            if resp.status_code == 402:
                body = resp.json()
                meta = body.get("error", {}).get("metadata", {})
                print(
                    f"  [OpenRouter key {_or_idx + 1} out of credits — "
                    f"need {meta.get('tokens_needed','?')}, "
                    f"have {meta.get('tokens_remaining','?')}. Switching...]"
                )
                if not _next_or():
                    return None
                tried.add(_or_idx - 1)
                continue

            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 402:
                if not _next_or():
                    return None
                continue
            raise


# ── Token-budget history trimmer ───────────────────────────────────────────────

def trim_history(history: list[dict], char_budget: int = 6000) -> list[dict]:
    """Return the tail of history that fits within char_budget characters."""
    if not history:
        return history
    total = 0
    kept  = []
    for msg in reversed(history):
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
        total += len(content)
        if total > char_budget and len(kept) >= 2:
            break
        kept.append(msg)
    return list(reversed(kept))


# ── Credits display ───────────────────────────────────────────────────────────

def get_credits() -> str:
    lines = ["## Groq keys\n"]

    for i, key in enumerate(GROQ_KEYS):
        label  = f"Key {i + 1}"
        active = " ◀ active" if i == _groq_idx else ""
        if key.startswith("YOUR_"):
            lines.append(f"{label}: not configured")
            continue
        try:
            # Groq doesn't have a credits endpoint — show a usage ping instead
            resp = httpx.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {key}"},
                timeout=10,
            )
            if resp.status_code == 200:
                lines.append(f"{label}{active}: ✓ connected (free tier — no credit balance to show)")
            else:
                lines.append(f"{label}{active}: status {resp.status_code}")
        except Exception as e:
            lines.append(f"{label}{active}: error — {e}")

    lines.append("\n## OpenRouter keys\n")
    for i, key in enumerate(OPENROUTER_KEYS):
        label  = f"Key {i + 1}"
        active = " ◀ active" if i == _or_idx else ""
        if key.startswith("YOUR_"):
            lines.append(f"{label}: not configured (fallback unused)")
            continue
        try:
            resp = httpx.get(
                "https://openrouter.ai/api/v1/credits",
                headers={"Authorization": f"Bearer {key}"},
                timeout=10,
            )
            resp.raise_for_status()
            data      = resp.json()
            total     = data.get("data", {}).get("total_credits", 0)
            used      = data.get("data", {}).get("total_usage", 0)
            remaining = round(total - used, 4)
            lines.append(
                f"{label}{active}: ${remaining:.4f} remaining "
                f"(${used:.4f} used of ${total:.4f})"
            )
        except Exception as e:
            lines.append(f"{label}{active}: error — {e}")

    return "\n".join(lines)
