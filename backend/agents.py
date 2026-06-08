"""Provider layer: drive local agent CLIs in headless mode.

This replaces OpenRouter as the default council backend. Each council member is
an installed CLI binary (claude / codex / gemini / agy) invoked as a subprocess
in a clean scratch directory, with output parsed back into plain text.

Why subprocess (ACP-style) instead of reusing OAuth tokens? Because running the
vendor's OWN binary, authenticated by its OWN session, is the sanctioned path —
no token minting, no ToS violation. The CLI handles auth; we just orchestrate.

Verified invocation/output shapes (probed on 2026-06-08):
  claude -p "<p>" --output-format json   -> stdout JSON, answer in .result
  gemini -p "<p>" -o json                -> stdout JSON, answer in .response
  codex exec "<p>" --skip-git-repo-check --sandbox read-only  -> stdout text
  agy    -p "<p>"                        -> stdout text
"""

import asyncio
import json
import os
import re
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional

from .config import SCRATCH_DIR

DEFAULT_TIMEOUT = 300.0  # CLIs are heavier than HTTP; give them room.

# Replaces each CLI's default (often coding-agent) framing with a plain
# council-member persona so answers stay direct and tool-free.
ANSWER_PERSONA = (
    "You are one member of an AI council answering a user's question. "
    "Answer directly, thoroughly and helpfully in Markdown. "
    "Do NOT edit files, run commands, or take actions — only read an attached "
    "file if one is referenced. Output only your answer, no preamble."
)


def _scratch_cwd() -> str:
    """A near-empty dir used as cwd so CLIs don't ingest this whole project."""
    p = Path(SCRATCH_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return str(p.resolve())


def _clean_env() -> dict:
    """Env for spawned CLIs, stripped of the launching Claude Code session's
    injected vars (CLAUDE_CODE_*). Otherwise a backend started from inside
    Claude Code would leak the parent's session id / model / effort into the
    `claude` subprocess and distort its behaviour. End users running the backend
    in a normal shell aren't affected, but stripping keeps both paths identical.
    """
    return {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_CODE_")}


def _extract_json(text: str) -> Optional[dict]:
    """Pull the first JSON object out of stdout (tolerates leading log noise)."""
    start = text.find("{")
    if start == -1:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
        return obj
    except json.JSONDecodeError:
        return None


# Agent turn-control tokens some CLIs occasionally leak into their final text
# (e.g. a trailing "turn_key_to_user: {}"). Strip them from displayed content.
_CONTROL_ARTIFACT = re.compile(r"turn_key_to_user\s*:\s*\{[^{}]*\}")


def _clean_content(text: Optional[str]) -> Optional[str]:
    if not text:
        return text
    return _CONTROL_ARTIFACT.sub("", text).strip()


def _split_attachments(attachments: List[Dict[str, Any]]):
    images = [a for a in attachments if str(a.get("mime", "")).startswith("image/")]
    others = [a for a in attachments if not str(a.get("mime", "")).startswith("image/")]
    return images, others


def _build_invocation(cmd: str, prompt: str, attachments: List[Dict[str, Any]],
                      model: Optional[str]):
    """Return (argv, parser_name) for a given CLI.

    Each CLI references attachments differently:
      - claude/agy: list absolute paths in the prompt + grant read access via flags
      - gemini:     @<abs-path> tokens in the prompt trigger multimodal inclusion
      - codex:      images via -i; other files referenced by path (read-only fs)
    """
    images, others = _split_attachments(attachments)
    attach_dir = _scratch_cwd()
    if attachments:
        # All attachments for a turn live under the same dir; expose it.
        attach_dir = str(Path(attachments[0]["path"]).resolve().parent)

    if cmd == "claude":
        body = prompt
        if attachments:
            paths = "\n".join(a["path"] for a in attachments)
            body = f"{prompt}\n\nAttached files (read them before answering):\n{paths}"
        argv = ["claude", "-p", body, "--output-format", "json",
                "--system-prompt", ANSWER_PERSONA]
        if model:
            argv += ["--model", model]
        if attachments:
            argv += ["--allowedTools", "Read", "--add-dir", attach_dir]
        return argv, "claude"

    if cmd == "gemini":
        body = f"{ANSWER_PERSONA}\n\n{prompt}"
        if attachments:
            refs = " ".join(f"@{a['path']}" for a in attachments)
            body = f"{body}\n\n{refs}"
        argv = ["gemini", "-p", body, "-o", "json"]
        if model:
            argv += ["-m", model]
        return argv, "gemini"

    if cmd == "codex":
        body = f"{ANSWER_PERSONA}\n\n{prompt}"
        if others:
            paths = "\n".join(a["path"] for a in others)
            body = f"{body}\n\nAttached file paths:\n{paths}"
        argv = ["codex", "exec", body, "--skip-git-repo-check", "--sandbox", "read-only"]
        if model:
            argv += ["-m", model]
        for im in images:
            argv += ["-i", im["path"]]
        return argv, "text"

    if cmd == "agy":
        body = f"{ANSWER_PERSONA}\n\n{prompt}"
        if attachments:
            paths = "\n".join(a["path"] for a in attachments)
            body = f"{body}\n\nAttached files (read them before answering):\n{paths}"
        argv = ["agy", "-p", body]
        if model:
            argv += ["--model", model]
        if attachments:
            argv += ["--add-dir", attach_dir, "--dangerously-skip-permissions"]
        return argv, "text"

    raise ValueError(f"Unknown CLI agent: {cmd}")


def _parse_output(parser: str, stdout: str) -> Optional[str]:
    if parser == "claude":
        obj = _extract_json(stdout)
        if obj is None or obj.get("is_error"):
            return None
        return _clean_content(obj.get("result"))
    if parser == "gemini":
        obj = _extract_json(stdout)
        return _clean_content(obj.get("response")) if obj else None
    # plain text (codex, agy)
    return _clean_content(stdout.strip()) or None


async def query_agent(
    agent_spec: Dict[str, Any],
    prompt: str,
    attachments: Optional[List[Dict[str, Any]]] = None,
    model: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT,
    resolve_default: bool = True,
) -> Optional[Dict[str, Any]]:
    """Run one council member (CLI agent) and return {'content': str} or None."""
    attachments = attachments or []
    cmd = agent_spec["cmd"]
    # Resolve the model: an explicit arg wins; else the spec's model; if that's
    # blank, apply the smart per-CLI default (auto-updating) unless told not to.
    use_model = model if model is not None else agent_spec.get("model")
    if use_model in (None, "", "(default)"):
        use_model = (await resolve_default_model(cmd)) if resolve_default else None

    if shutil.which(cmd) is None:
        print(f"Agent CLI not found on PATH: {cmd}")
        return None

    try:
        argv, parser = _build_invocation(cmd, prompt, attachments, use_model)
    except ValueError as e:
        print(f"Error building command: {e}")
        return None

    # CLIs only "see" files inside their working dir. With attachments, run in
    # the attachment dir (all of a turn's files live there) so @-references and
    # path reads resolve; otherwise use the empty scratch dir.
    run_cwd = _scratch_cwd()
    if attachments:
        run_cwd = str(Path(attachments[0]["path"]).resolve().parent)

    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,   # critical for codex (no stdin wait)
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=run_cwd,
            env=_clean_env(),
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            print(f"Agent {agent_spec['id']} timed out after {timeout}s")
            return None

        stdout = stdout_b.decode("utf-8", errors="replace")
        if proc.returncode != 0:
            stderr = stderr_b.decode("utf-8", errors="replace")[:500]
            print(f"Agent {agent_spec['id']} exited {proc.returncode}: {stderr}")
            # Some CLIs print the answer on stdout even with a nonzero code; still try.
        content = _parse_output(parser, stdout)
        if content is None:
            print(f"Agent {agent_spec['id']} produced no parseable answer.")
            return None
        return {"content": content}

    except Exception as e:  # noqa: BLE001 - graceful degradation per design
        print(f"Error querying agent {agent_spec['id']}: {e}")
        return None


async def query_agents_parallel(
    agents: List[Dict[str, Any]],
    prompt: str,
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> List[Optional[Dict[str, Any]]]:
    """Run all council members concurrently; results align with `agents` order."""
    tasks = [query_agent(a, prompt, attachments, a.get("model")) for a in agents]
    return await asyncio.gather(*tasks)


def check_agent_available(agent_spec: Dict[str, Any]) -> bool:
    """Best-effort: is this CLI installed on PATH? (Login is verified at call time.)"""
    return shutil.which(agent_spec["cmd"]) is not None


async def list_agy_models() -> List[str]:
    """Fetch live model list from `agy models`."""
    if shutil.which("agy") is None:
        return []
    try:
        proc = await asyncio.create_subprocess_exec(
            "agy", "models",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            cwd=_scratch_cwd(),
            env=_clean_env(),
        )
        out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=30.0)
        lines = [ln.strip() for ln in out_b.decode("utf-8", "replace").splitlines()]
        return [ln for ln in lines if ln]
    except Exception:  # noqa: BLE001
        return []


def _pick_latest(models: List[str], must_include: List[str]) -> Optional[str]:
    """From a model list, pick the highest-versioned entry containing all keywords.

    e.g. must_include=["Flash","(High)"] over `agy models` -> "Gemini 3.5 Flash (High)"
    and automatically prefers "Gemini 3.6 Flash (High)" once it appears.
    """
    cands = [m for m in models if all(k.lower() in m.lower() for k in must_include)]
    if not cands:
        return None

    def version(s: str) -> float:
        nums = re.findall(r"\d+(?:\.\d+)?", s)
        return float(nums[0]) if nums else 0.0

    return max(cands, key=version)


async def resolve_default_model(cli: str) -> Optional[str]:
    """The single source of truth for each CLI's auto-updating default model.

    Returns None when the CLI's own built-in default already tracks the latest
    (claude, codex) — passing no --model is then correct and future-proof.
    """
    if cli == "gemini":
        # Alias resolves to the latest 3.x Pro (gemini-3.1-pro-preview today).
        return "gemini-3-pro-preview"
    if cli == "agy":
        # Newest Gemini Flash with extended thinking, fetched live.
        return _pick_latest(await list_agy_models(), ["Flash", "(High)"])
    return None  # claude / codex -> their own latest default
