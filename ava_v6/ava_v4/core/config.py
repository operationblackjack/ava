"""
config.py — AVA configuration
Edit this file to set your vault path, API keys, and model.
"""

from pathlib import Path

# ── Vault ─────────────────────────────────────────────────────────────────────
# Path to your Obsidian vault folder. Change this to wherever your vault lives.
VAULT = Path("C:/Users/Administrator/Videos/ava")

# ── OpenRouter ────────────────────────────────────────────────────────────────
# Add your OpenRouter API keys here. AVA will rotate between them automatically
# if one runs out of credits. You can add as many keys as you like.
OPENROUTER_KEYS = [
    "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",
    "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",
]

# ── Groq (primary) ───────────────────────────────────────────────────────────
GROQ_KEYS = [
    "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",  # paste your fresh key here
]

MODEL       = "llama-3.3-70b-versatile"   # primary model on Groq
GROQ_MODEL  = "llama-3.3-70b-versatile"   # same — used by llm.py

# ── Model ─────────────────────────────────────────────────────────────────────
# The model AVA uses to think. You can find model names at openrouter.ai/models
MODEL = "anthropic/claude-3.5-haiku"

# ── Vision model ──────────────────────────────────────────────────────────────
# Used by /vision and /see to describe images. Groq's Llama-4 Scout is fast and
# free-tier friendly; OpenRouter fallback uses a Claude vision model.
GROQ_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
OPENROUTER_VISION_MODEL = "anthropic/claude-3.5-haiku"

# ── Memory file ───────────────────────────────────────────────────────────────
# Where AVA saves her memory between sessions. Leave this as-is unless you
# want to move it.
MEMORY_PATH = Path.home() / ".ava_memory.json"

# ── Vault folders ─────────────────────────────────────────────────────────────
# AVA will create these folders inside your vault if they don't exist.
NOTES_DIR    = VAULT / "Notes"
IDEAS_DIR    = VAULT / "Ideas"
SKILLS_DIR   = VAULT / "Skills"
PROJECTS_DIR = VAULT / "Projects"
SESSIONS_DIR = VAULT / "Sessions"
JOURNAL_DIR  = VAULT / "Journal"
TEMPLATES_DIR= VAULT / "Templates"
TASTES_DIR   = VAULT / "Tastes"

ABOUT_FILE        = VAULT / "About Me.md"
SESSIONS_INDEX    = VAULT / "Sessions.md"

# ── Protected files ───────────────────────────────────────────────────────────
# AVA will never delete these, even if asked.
PROTECTED = {"About Me", "Sessions"}

# ── Display ───────────────────────────────────────────────────────────────────
AVA_NAME    = "AVA"
AVA_VERSION = "1.0"
