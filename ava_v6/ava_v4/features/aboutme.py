"""
aboutme.py — Structured About Me management
Commands: /about            — show the About Me file
          /about <section>  — show one section
          /aboutset <section> | <content>  — set or update a section

About Me has named sections so AVA can reason about you precisely:

  ## Identity
  ## Creative Projects
  ## People I Know
  ## Things I'm Learning
  ## How I Think
  ## Notes        ← AVA's running observations (auto-managed)

AVA's "about" actions now write to the Notes section only.
The other sections are for you to set and AVA to read.
"""

import re
from datetime import date
import core.vault as vault
from core.config import ABOUT_FILE

# The canonical sections About Me can have
SECTIONS = [
    "Identity",
    "Creative Projects",
    "People I Know",
    "Things I'm Learning",
    "How I Think",
    "Notes",
]


def _ensure_structure() -> str:
    """
    Make sure About Me exists and has all canonical sections.
    Returns the current content.
    """
    today   = date.today().isoformat()
    content = vault.read_file(ABOUT_FILE)

    if not content:
        # build fresh structured file
        sections_text = "\n\n".join(
            f"## {s}\n\n*(not yet filled in)*" for s in SECTIONS
        )
        content = (
            f"---\ntags:\n  - about\ndate: {today}\n---\n\n"
            f"# About Me\n\n{sections_text}\n"
        )
        vault.write_file(ABOUT_FILE, content)
        return content

    # add any missing sections at the end
    changed = False
    for section in SECTIONS:
        if f"## {section}" not in content:
            content = content.rstrip() + f"\n\n## {section}\n\n*(not yet filled in)*\n"
            changed = True

    if changed:
        vault.write_file(ABOUT_FILE, content)

    return content


def _get_section(content: str, section_name: str) -> str:
    """Extract the content of a named section."""
    pattern = rf"## {re.escape(section_name)}\n(.*?)(?=\n## |\Z)"
    m = re.search(pattern, content, re.DOTALL)
    if not m:
        return ""
    return m.group(1).strip()


def _set_section(content: str, section_name: str, new_body: str) -> str:
    """Replace the content of a named section."""
    pattern = rf"(## {re.escape(section_name)}\n)(.*?)(?=\n## |\Z)"
    replacement = rf"\g<1>{new_body}\n"
    new_content, count = re.subn(pattern, replacement, content, flags=re.DOTALL)
    if count == 0:
        # section doesn't exist — add it
        new_content = content.rstrip() + f"\n\n## {section_name}\n\n{new_body}\n"
    return new_content


def _append_to_section(content: str, section_name: str, item: str) -> str:
    """Append a bullet to a section."""
    today = date.today().isoformat()
    bullet = f"- **{today}:** {item}"
    current = _get_section(content, section_name)
    if current in ("*(not yet filled in)*", ""):
        new_body = bullet
    else:
        new_body = current.rstrip() + f"\n{bullet}"
    return _set_section(content, section_name, new_body)


# ── Public write API (called from vault.py's update_about) ────────────────────

def append_observation(note: str):
    """AVA adds an observation to the Notes section."""
    content = _ensure_structure()
    content = _append_to_section(content, "Notes", note)
    vault.write_file(ABOUT_FILE, content)
    vault.invalidate()


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_about(rest: str, mem: dict) -> str:
    """
    /about              — show full About Me
    /about <section>    — show one section
    """
    content = _ensure_structure()
    body    = vault.strip_frontmatter(content)
    name    = rest.strip()

    if not name:
        return body

    # fuzzy section match
    target = next(
        (s for s in SECTIONS if name.lower() in s.lower()),
        None
    )
    if not target:
        opts = ", ".join(SECTIONS)
        return f"Unknown section **{name}**.\n\nAvailable sections: {opts}"

    section_content = _get_section(content, target)
    return f"## {target}\n\n{section_content or '*(empty)*'}"


def cmd_aboutset(rest: str, mem: dict) -> str:
    """
    /aboutset <section> | <content>
    Set or update a section of About Me.

    Examples:
      /aboutset Identity | I'm a musician and programmer in Trinidad
      /aboutset Creative Projects | Working on AVA (AI second brain), guitar compositions
      /aboutset How I Think | I think in systems. I like to name things.
    """
    if "|" not in rest:
        opts = ", ".join(SECTIONS)
        return (
            "Format: `/aboutset <section> | <content>`\n\n"
            f"Sections: {opts}"
        )

    section_name, _, new_content = rest.partition("|")
    section_name = section_name.strip()
    new_content  = new_content.strip()

    if not section_name or not new_content:
        return "Both section name and content are required."

    # fuzzy match
    target = next(
        (s for s in SECTIONS if section_name.lower() in s.lower()),
        None
    )
    if not target:
        opts = ", ".join(SECTIONS)
        return f"Unknown section **{section_name}**.\n\nAvailable: {opts}"

    if target == "Notes":
        return (
            "The Notes section is managed by AVA automatically.\n"
            "To add your own note, try updating another section instead."
        )

    content = _ensure_structure()
    content = _set_section(content, target, new_content)
    vault.write_file(ABOUT_FILE, content)
    vault.invalidate()

    return f"✦ Updated **{target}** in About Me."


def register():
    return {
        "commands": {
            "about":    cmd_about,
            "aboutset": cmd_aboutset,
        },
        "description": "About Me — /about to view, /aboutset <section> | <content> to edit",
    }
