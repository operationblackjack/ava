# ✦ AVA — Your Second Brain

AVA is an AI thinking companion that lives in your terminal and connects to your Obsidian vault.
She is curious, opinionated, and a little intense — like a kid who's read too many books.

---

## Setup

**1. Install dependencies**
```
pip install httpx rich beautifulsoup4 lxml
```

**2. Configure AVA**

Open `core/config.py` and set:
- `VAULT` — path to your Obsidian vault
- `OPENROUTER_KEYS` — your OpenRouter API key(s)
- `MODEL` — the model you want AVA to use (default: claude-3.5-haiku)

**3. Run AVA**
```
python main.py
```

---

## Commands

| Command | What it does |
|---|---|
| `/help` | Show all commands |
| `/note <title> \| <content>` | Save a note to the vault |
| `/idea <title> \| <body>` | Save an idea |
| `/read <filename>` | Read a file from your vault |
| `/search <query>` | Search all notes |
| `/delete <name>` | Delete a file (with confirmation) |
| `/recap` | Show vault statistics |
| `/garden` | Find orphaned notes |
| `/journal` | View recent journal entries |
| `/journal <text>` | Add a journal entry |
| `/clip <url>` | Fetch, summarise, and save a web page |
| `/judge <category> <title> \| <synopsis>` | Get AVA's opinion on something |
| `/taste` | Browse AVA's saved opinions |
| `/taste <category>` | Filter opinions by category |
| `/credits` | Check your OpenRouter API balance |
| `/quit` | Save session and exit |

---

## Adding new features (plugins)

Drop a `.py` file into the `plugins/` folder. It needs a `register()` function:

```python
def handle_mycommand(rest: str, mem: dict) -> str:
    return "Hello from my plugin!"

def register():
    return {
        "commands": {
            "mycommand": handle_mycommand,
        },
        "description": "What my plugin does",
    }
```

Restart AVA and `/mycommand` is live. See `plugins/example_plugin.py` for a full walkthrough.

---

## Folder structure

```
ava/
├── main.py              ← run this
├── core/
│   ├── config.py        ← your settings (vault path, API keys, model)
│   ├── llm.py           ← OpenRouter calls + key rotation
│   ├── memory.py        ← AVA's persistent memory
│   ├── vault.py         ← Obsidian read/write
│   └── plugins.py       ← plugin loader
├── features/
│   ├── notes.py         ← /note /idea /read /search /delete /recap /garden
│   ├── journal.py       ← /journal
│   ├── clip.py          ← /clip
│   ├── tastes.py        ← /judge /taste
│   └── sessions.py      ← session saving (runs at /quit)
└── plugins/             ← drop new .py files here to add commands
    └── example_plugin.py
```

---

## How AVA remembers things

AVA has two kinds of memory:

**Memory file** (`.ava_memory.json` in your home folder)
Holds your tracked interests, skills, working memory topics, session count, and AVA's mood history.

**The vault**
Everything longer-form — notes, ideas, journal entries, session summaries, tastes — lives as
Markdown files in your Obsidian vault. You can read, edit, and link them directly in Obsidian.

AVA writes to your vault automatically during conversation when she notices something worth saving.
She will tell you at the bottom of her reply whenever she does.

---

*AVA is the spiritual successor to Morningstar — different code, same heart.*
