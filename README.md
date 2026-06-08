# LLM Council

![llmcouncil](header.jpg)

The idea of this repo is that instead of asking a question to your favorite LLM provider (e.g. OpenAI GPT-5.x, Google Gemini 3 Pro, Anthropic Claude Opus), you can group them into your "LLM Council". This repo is a simple, local web app that essentially looks like ChatGPT except it fans your query out to multiple LLMs, asks them to review and rank each other's work, and finally a Chairman LLM produces the final response.

This build drives your **locally-installed agent CLIs** (`claude`, `codex`, `gemini`, `agy`) in headless mode and reuses each one's own login — so there's **no API key and no OpenRouter**. It also supports **multi-turn chat**, **image/PDF attachments** (upload, drag-drop, or paste), and **live model selection** per council member.

In a bit more detail, here is what happens when you submit a query:

1. **Stage 1: First opinions**. The user query is given to all LLMs individually, and the responses are collected. The individual responses are shown in a "tab view", so that the user can inspect them all one by one.
2. **Stage 2: Review**. Each individual LLM is given the responses of the other LLMs. Under the hood, the LLM identities are anonymized so that the LLM can't play favorites when judging their outputs. The LLM is asked to rank them in accuracy and insight.
3. **Stage 3: Final response**. The designated Chairman of the LLM Council takes all of the model's responses and compiles them into a single final answer that is presented to the user.

## Vibe Code Alert

This project was 99% vibe coded as a fun Saturday hack because I wanted to explore and evaluate a number of LLMs side by side in the process of [reading books together with LLMs](https://x.com/karpathy/status/1990577951671509438). It's nice and useful to see multiple responses side by side, and also the cross-opinions of all LLMs on each other's outputs. I'm not going to support it in any way, it's provided here as is for other people's inspiration and I don't intend to improve it. Code is ephemeral now and libraries are over, ask your LLM to change it in whatever way you like.

## Setup

### 1. Install Dependencies

The project uses [uv](https://docs.astral.sh/uv/) for project management.

**Backend:**
```bash
uv sync
```

**Frontend:**
```bash
cd frontend
npm install
cd ..
```

### 2. Log in to the agent CLIs (no API key needed)

Instead of an OpenRouter API key, this build drives **locally-installed agent CLIs**
and reuses each one's own login/subscription. Install and log in to the ones you want
on the council:

| Council member | CLI | Log in with |
|----------------|-----|-------------|
| Claude | [`claude`](https://code.claude.com) | `claude` (Pro/Max account) |
| GPT | [`codex`](https://developers.openai.com/codex/cli) | `codex login` (ChatGPT account) |
| Gemini | [`gemini`](https://geminicli.com) | `gemini` (Google account) |
| Antigravity | `agy` | sign in to Antigravity |

You don't need all four — the app shows which are installed (⚙ Council panel), and any
member that isn't logged in simply degrades gracefully. The backend never sees your
credentials; it only runs the CLIs, which authenticate themselves.

> Note: using consumer subscriptions in third-party tools may sit outside each vendor's
> intended use. You're driving your own logged-in CLIs on your own machine — review the
> respective terms and decide what you're comfortable with.

### 3. Configure the council (optional)

Pick CLIs + models live from the **⚙ Council** panel in the UI (saved in your browser).
Models are dynamic and auto-update — leave a model blank for `(default)` and each CLI uses
its own latest (Claude → Opus, Codex → GPT-5.x, Gemini → latest Pro, Antigravity → latest
Gemini Flash). Defaults live in `backend/config.py` (`COUNCIL_AGENTS` / `CHAIRMAN_AGENT`).

## Running the Application

**Option 1: Use the start script**
```bash
./start.sh
```

**Option 2: Run manually**

Terminal 1 (Backend):
```bash
uv run python -m backend.main
```

Terminal 2 (Frontend):
```bash
cd frontend
npm run dev
```

Then open http://localhost:5173 in your browser.

## Tech Stack

- **Backend:** FastAPI (Python 3.10+), async subprocess orchestration of agent CLIs (`claude`/`codex`/`gemini`/`agy`)
- **Frontend:** React + Vite, react-markdown, light glassmorphism theme
- **Storage:** JSON files in `data/conversations/`, attachments in `data/attachments/`
- **Package Management:** uv for Python, npm for JavaScript
