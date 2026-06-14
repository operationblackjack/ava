"""
memory.py — AVA's persistent memory with decay

Working memory now fades over time — topics lose weight each session
unless reinforced. This keeps AVA's sense of "what you're focused on"
accurate rather than accumulating forever.
"""

import json
import time
from pathlib import Path
from core.config import MEMORY_PATH

_DEFAULTS = {
    "interests":      [],
    "skills":         [],
    "working_memory": {},   # {topic: {"weight": float, "last_seen": timestamp}}
    "session_count":  0,
    "soul": {
        "mood":         "curious",
        "mood_history": [],
    },
    "people": {},           # {name: {role, notes, last_mentioned}}
}

_MOODS = ["curious", "playful", "excited", "contemplative", "wistful", "sharp"]

# Decay: each session, topics lose this fraction of their weight
_DECAY_RATE   = 0.15   # 15% decay per session
_MIN_WEIGHT   = 0.1    # topics below this are pruned
_MAX_TOPICS   = 80


def load() -> dict:
    if MEMORY_PATH.exists():
        try:
            data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
            for k, v in _DEFAULTS.items():
                data.setdefault(k, v)
            # migrate old flat working_memory format {topic: int} → new format
            wm = data.get("working_memory", {})
            if wm and isinstance(next(iter(wm.values()), None), (int, float)):
                data["working_memory"] = {
                    t: {"weight": float(w), "last_seen": time.time()}
                    for t, w in wm.items()
                }
            return data
        except Exception:
            pass
    mem = {k: (v.copy() if isinstance(v, (dict, list)) else v) for k, v in _DEFAULTS.items()}
    mem["soul"] = {"mood": "curious", "mood_history": []}
    save(mem)
    return mem


def save(mem: dict):
    MEMORY_PATH.write_text(
        json.dumps(mem, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def decay_working_memory(mem: dict):
    """
    Apply time-based decay to working memory topics.
    Called once per session at startup — topics fade unless you keep talking about them.
    """
    wm = mem.get("working_memory", {})
    now = time.time()
    decayed = {}
    for topic, data in wm.items():
        if isinstance(data, dict):
            w = data.get("weight", 1.0)
            ls = data.get("last_seen", now)
        else:
            w = float(data)
            ls = now

        # extra decay if topic hasn't been mentioned in a long time
        days_since = (now - ls) / 86400
        extra = 1 + (days_since / 30) * 0.5   # up to 50% extra decay over a month
        new_weight = w * (1 - _DECAY_RATE * extra)

        if new_weight >= _MIN_WEIGHT:
            decayed[topic] = {"weight": round(new_weight, 4), "last_seen": ls}

    mem["working_memory"] = decayed


def update_working_memory(mem: dict, topics: list[str]):
    """Reinforce topics from the current turn. Resets their decay clock."""
    wm  = mem.setdefault("working_memory", {})
    now = time.time()
    for t in topics:
        t = t.strip().lower()
        if not t:
            continue
        existing = wm.get(t, {"weight": 0.0, "last_seen": now})
        wm[t] = {
            "weight":    min(existing.get("weight", 0.0) + 1.0, 20.0),
            "last_seen": now,
        }
    # prune to max size, keeping heaviest
    if len(wm) > _MAX_TOPICS:
        top = sorted(wm.items(), key=lambda x: x[1].get("weight", 0), reverse=True)
        mem["working_memory"] = dict(top[:_MAX_TOPICS])


def working_memory_summary(mem: dict, top_n: int = 10) -> str:
    """Return a comma-separated string of the top N topics, with staleness hints."""
    wm  = mem.get("working_memory", {})
    now = time.time()
    if not wm:
        return "nothing in particular yet"

    items = []
    for t, data in wm.items():
        if isinstance(data, dict):
            w  = data.get("weight", 0)
            ls = data.get("last_seen", now)
        else:
            w, ls = float(data), now
        items.append((t, w, ls))

    items.sort(key=lambda x: x[1], reverse=True)
    top = items[:top_n]

    parts = []
    for t, w, ls in top:
        days = (now - ls) / 86400
        if days > 14:
            parts.append(f"{t} (old)")
        else:
            parts.append(t)
    return ", ".join(parts)


def drift_mood(mem: dict) -> str:
    import random
    soul    = mem.setdefault("soul", {"mood": "curious", "mood_history": []})
    current = soul.get("mood", "curious")
    idx     = _MOODS.index(current) if current in _MOODS else 0
    if random.random() < 0.30:
        idx = (idx + random.choice([-1, 1])) % len(_MOODS)
    new_mood = _MOODS[idx]
    soul["mood"] = new_mood
    history = soul.setdefault("mood_history", [])
    history.append(new_mood)
    if len(history) > 50:
        soul["mood_history"] = history[-50:]
    return new_mood


def reset(mem: dict) -> dict:
    """
    Wipe AVA's memory back to defaults (interests, skills, working memory,
    mood, people, session count, mood log — everything in the JSON memory
    file). Does NOT touch the Obsidian vault itself; that's a separate,
    user-driven cleanup. Returns the fresh memory dict and saves it.
    """
    fresh = {k: (v.copy() if isinstance(v, (dict, list)) else v) for k, v in _DEFAULTS.items()}
    fresh["soul"] = {"mood": "curious", "mood_history": []}
    save(fresh)
    return fresh




def upsert_person(mem: dict, name: str, role: str = "", note: str = ""):
    """Add or update a person in memory."""
    people = mem.setdefault("people", {})
    key    = name.strip().lower()
    if key not in people:
        people[key] = {
            "name":           name,
            "role":           role,
            "notes":          [],
            "last_mentioned": time.time(),
        }
    else:
        people[key]["last_mentioned"] = time.time()
        if role:
            people[key]["role"] = role
    if note:
        notes = people[key].setdefault("notes", [])
        if note not in notes:
            notes.append(note)
            if len(notes) > 20:
                people[key]["notes"] = notes[-20:]


def get_person(mem: dict, name: str) -> dict | None:
    people = mem.get("people", {})
    return people.get(name.strip().lower())


def people_summary(mem: dict) -> str:
    """Brief summary of known people for the system prompt."""
    people = mem.get("people", {})
    if not people:
        return "no one tracked yet"
    lines = []
    for key, p in list(people.items())[:15]:
        role  = f" ({p['role']})" if p.get("role") else ""
        notes = p.get("notes", [])
        last  = notes[-1] if notes else ""
        lines.append(f"- **{p['name']}**{role}" + (f": {last}" if last else ""))
    return "\n".join(lines)
