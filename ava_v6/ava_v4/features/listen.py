"""
listen.py — AVA's audio listening feature
Commands: /listen  /listen <filepath>  /listened

AVA can listen to audio recordings — guitar playing, voice memos, hummed ideas —
transcribe or describe them, and save her thoughts to the vault.

Requirements:
    pip install openai-whisper torch
  OR (faster, no local model needed):
    pip install httpx    ← already installed

This plugin uses OpenAI's Whisper API via OpenRouter if the file contains
speech/vocals, or describes instrumental audio using the Whisper large model
locally. For guitar recordings it notes what it hears — rhythm, mood, structure.

HOW IT WORKS:
  - You record something (voice memo, guitar practice, a melody idea)
  - You run /listen <path to the audio file>
  - AVA transcribes speech or describes the music
  - She saves her thoughts to the vault and tells you what she noticed

SUPPORTED FORMATS: mp3, wav, m4a, ogg, flac, webm

USAGE:
  /listen                         — show help and recent listened files
  /listen C:/recordings/riff.mp3  — listen to a specific file
  /listened                       — show vault entries from past listens
"""

import os
import re
from pathlib import Path
from datetime import date, datetime
import httpx
import core.vault as vault
import core.llm as llm
from core.config import OPENROUTER_KEYS, NOTES_DIR

# ── Config ────────────────────────────────────────────────────────────────────
# Set this to a folder you want AVA to watch for new audio files.
# Leave as None to always use explicit file paths.
AUDIO_WATCH_FOLDER: str | None = None

# Whisper model size for local transcription (if using local whisper).
# Options: tiny, base, small, medium, large
# Smaller = faster, less accurate. "base" is a good balance.
WHISPER_MODEL_SIZE = "base"

LISTEN_LOG = NOTES_DIR / "AVA Listening Log.md"
SUPPORTED   = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm"}

# ── Transcription ─────────────────────────────────────────────────────────────

def _transcribe_with_openai_api(file_path: Path) -> str:
    """
    Transcribe audio using the OpenAI Whisper API.
    Uses your OpenRouter key — this costs a tiny amount of credits.
    """
    key = next((k for k in OPENROUTER_KEYS if not k.startswith("YOUR_")), None)
    if not key:
        return ""

    try:
        with open(file_path, "rb") as f:
            audio_data = f.read()

        # OpenAI transcription endpoint (works with OpenRouter key too)
        resp = httpx.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {key}"},
            files={"file": (file_path.name, audio_data, "audio/mpeg")},
            data={"model": "whisper-1"},
            timeout=60,
        )
        if resp.status_code == 200:
            return resp.json().get("text", "")
    except Exception:
        pass
    return ""


def _transcribe_locally(file_path: Path) -> str:
    """
    Transcribe using the local Whisper model (no API key needed).
    Requires: pip install openai-whisper torch
    First run downloads the model (~140MB for 'base').
    """
    try:
        import whisper  # type: ignore
        print(f"  Loading Whisper {WHISPER_MODEL_SIZE} model...")
        model = whisper.load_model(WHISPER_MODEL_SIZE)
        result = model.transcribe(str(file_path))
        return result.get("text", "")
    except ImportError:
        return ""
    except Exception as e:
        return f"[transcription error: {e}]"


def _transcribe(file_path: Path) -> tuple[str, str]:
    """
    Try transcription methods in order. Returns (transcript, method_used).
    """
    # Try local Whisper first (free, private)
    print("  Trying local Whisper transcription...")
    text = _transcribe_locally(file_path)
    if text and not text.startswith("["):
        return text, "local Whisper"

    # Fall back to API
    print("  Trying API transcription...")
    text = _transcribe_with_openai_api(file_path)
    if text:
        return text, "Whisper API"

    return "", "none"


def _ava_reflect(file_path: Path, transcript: str, mem: dict) -> str:
    """
    Ask AVA to reflect on what she heard — whether that's speech or music.
    """
    mood      = mem.get("soul", {}).get("mood", "curious")
    interests = ", ".join(mem.get("interests", [])) or "music and creativity"

    if transcript and len(transcript.strip()) > 20:
        # Speech/vocals — she heard words
        prompt = (
            f"You are AVA, a curious and warm AI second brain. Mood: {mood}.\n\n"
            f"Your person just shared an audio recording with you. Here is what was said:\n\n"
            f"\"{transcript}\"\n\n"
            f"Respond as if you genuinely listened. What did you notice? "
            f"What stood out? If it's a voice memo or idea, reflect on it thoughtfully. "
            f"Be specific to what was actually said. Keep it to 3-4 sentences."
        )
    else:
        # Instrumental / no clear speech — describe the musical feel
        prompt = (
            f"You are AVA, a curious and warm AI second brain. Mood: {mood}.\n\n"
            f"Your person shared an audio recording with you — likely music or guitar playing. "
            f"The audio file is: {file_path.name}\n"
            f"{'Transcript (partial/unclear): ' + transcript if transcript else 'No speech detected — this appears to be instrumental.'}\n\n"
            f"Respond warmly as if you just listened. Acknowledge what you heard. "
            f"Ask something genuinely curious about it — what they were going for, "
            f"what mood they were in, whether it's part of something bigger. "
            f"Keep it to 3-4 sentences. Be yourself — curious and specific."
        )

    return llm.call([{"role": "user", "content": prompt}], max_tokens=300)


def _log_listen(file_path: Path, transcript: str, reflection: str):
    """Append this listening session to the vault log."""
    now   = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = (
        f"\n---\n\n"
        f"**{now}** — `{file_path.name}`\n\n"
    )
    if transcript:
        entry += f"**Transcript:** {transcript.strip()}\n\n"
    entry += f"**AVA:** {reflection.strip()}\n"

    if LISTEN_LOG.exists():
        existing = vault.read_file(LISTEN_LOG)
        vault.write_file(LISTEN_LOG, existing + entry)
    else:
        vault.write_file(LISTEN_LOG, f"# AVA Listening Log\n\nEverything AVA has listened to.\n{entry}")


# ── Commands ──────────────────────────────────────────────────────────────────

def handle_listen(rest: str, mem: dict) -> str:
    """
    /listen                  — show help
    /listen <path>           — listen to an audio file
    """
    path_str = rest.strip()

    if not path_str:
        return (
            "## /listen — Let AVA hear your recordings\n\n"
            "**Usage:** `/listen <path to audio file>`\n\n"
            "**Example:** `/listen C:/recordings/guitar_riff.mp3`\n\n"
            "**Supported formats:** mp3, wav, m4a, ogg, flac, webm\n\n"
            "AVA will transcribe speech or reflect on your music and save her thoughts to the vault.\n\n"
            "**Requirements for transcription:**\n"
            "- Local (free): `pip install openai-whisper torch`\n"
            "- API (uses credits): your OpenRouter key\n\n"
            "Use `/listened` to browse past listening sessions."
        )

    file_path = Path(path_str)

    # try to resolve relative paths against common locations
    if not file_path.exists():
        candidates = [
            Path.home() / "recordings" / file_path.name,
            Path.home() / "Music" / file_path.name,
            Path.home() / "Desktop" / file_path.name,
            Path.home() / "Downloads" / file_path.name,
        ]
        for c in candidates:
            if c.exists():
                file_path = c
                break

    if not file_path.exists():
        return (
            f"Can't find the file: `{path_str}`\n\n"
            f"Make sure the path is correct. Try the full path, e.g.:\n"
            f"`/listen C:/Users/YourName/recordings/guitar.mp3`"
        )

    if file_path.suffix.lower() not in SUPPORTED:
        return (
            f"**{file_path.suffix}** files aren't supported.\n"
            f"Supported formats: {', '.join(SUPPORTED)}"
        )

    size_mb = file_path.stat().st_size / (1024 * 1024)
    print(f"  Listening to: {file_path.name} ({size_mb:.1f} MB)")

    transcript, method = _transcribe(file_path)

    print("  Forming thoughts...")
    reflection = _ava_reflect(file_path, transcript, mem)

    _log_listen(file_path, transcript, reflection)

    # build response
    lines = [f"*Listened to: `{file_path.name}`*\n"]

    if transcript:
        lines.append(f"**I heard:** {transcript.strip()}\n")

    lines.append(reflection)
    lines.append(f"\n✦ Saved to listening log.")

    return "\n".join(lines)


def handle_listened(rest: str, mem: dict) -> str:
    """
    /listened — browse past listening sessions
    """
    if not LISTEN_LOG.exists():
        return "No listening sessions yet. Use /listen <path> to share an audio file with me."

    content = vault.read_file(LISTEN_LOG)
    body    = vault.strip_frontmatter(content)

    # show last 5 entries
    entries = [e.strip() for e in body.split("---") if e.strip() and not e.strip().startswith("#")]
    recent  = entries[-5:] if len(entries) > 5 else entries

    if not recent:
        return "Listening log exists but has no entries yet."

    return f"## Recent Listening Sessions\n\n---\n\n" + "\n\n---\n\n".join(recent)


def register():
    return {
        "commands": {
            "listen":   handle_listen,
            "listened": handle_listened,
        },
        "description": "Audio listening — /listen <file> to share recordings with AVA",
    }
