"""Configuration for the LLM Council.

The council no longer talks to OpenRouter by default. Instead each member is a
locally-installed agent CLI (Claude Code, OpenAI Codex, Gemini CLI, Antigravity
`agy`) that is driven in headless mode and authenticates with its OWN session.
This means: no API key in the app, no OAuth code, "login" == you already ran
`claude` / `codex` / `gemini` / `agy` once on this machine.

The OpenRouter constants below are kept so the optional `type: "openrouter"`
provider branch (in openrouter.py) still works for anyone who prefers API keys.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# --- Council line-up (CLI agents) -------------------------------------------
# Each spec: id, label (shown in UI), type ("cli" | "openrouter"), cmd, model.
# model=None means "use the smart default for this CLI" — resolved at call time
# by agents.resolve_default_model() so it AUTO-UPDATES to newer models. Nothing
# here pins a version; the resolution rules live in one place (agents.py):
#   claude -> CLI's own latest default (Opus 4.8[1m] today)
#   codex  -> CLI's own latest default (gpt-5.5 today)
#   gemini -> alias that tracks the latest 3.x Pro (gemini-3.1-pro-preview today)
#   agy    -> newest "Flash ... (High)" from `agy models` (extended thinking)
COUNCIL_AGENTS = [
    {"id": "claude", "label": "Claude",                    "type": "cli", "cmd": "claude", "model": None},
    {"id": "codex",  "label": "GPT (Codex)",               "type": "cli", "cmd": "codex",  "model": None},
    {"id": "gemini", "label": "Gemini Pro",                "type": "cli", "cmd": "gemini", "model": None},
    {"id": "agy",    "label": "Antigravity (Gemini Flash)", "type": "cli", "cmd": "agy",   "model": None},
]

# Chairman synthesises the final answer. Default to Claude: clean JSON output,
# strong synthesis, and not subject to the 18 Jun 2026 Gemini-CLI sunset.
CHAIRMAN_AGENT = {"id": "claude", "label": "Claude", "type": "cli", "cmd": "claude", "model": None}

# Agent for the cheap "name this conversation" call (uses gemini's bare default,
# i.e. a Flash tier — fast & cheap; resolution is skipped for titles).
TITLE_AGENT = {"id": "gemini", "label": "Gemini", "type": "cli", "cmd": "gemini", "model": None}

# Model lists are DYNAMIC — never hardcode model names (they go stale fast).
#  - agy: fetched live via `agy models`.
#  - claude/codex/gemini: no list command exists, and probing `<cli> models`
#    would be misread as a prompt; so the UI uses a free-text combobox plus a
#    "(default)" option that lets each CLI pick its own latest model.
# This dict only declares which CLIs support live discovery.
LIVE_MODEL_DISCOVERY = {"agy": True, "claude": False, "codex": False, "gemini": False}

# --- OpenRouter (optional, only for type:"openrouter" specs) -----------------
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# --- Storage -----------------------------------------------------------------
DATA_DIR = "data/conversations"
ATTACHMENTS_DIR = "data/attachments"
# Neutral, near-empty working dir so the CLIs don't scan/ingest this project.
SCRATCH_DIR = "data/scratch"
