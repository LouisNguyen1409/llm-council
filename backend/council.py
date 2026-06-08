"""3-stage LLM Council orchestration.

Stage 1: every council member answers independently.
Stage 2: members rank each other's ANONYMISED answers (no favouritism).
Stage 3: the chairman synthesises a final answer.

The deliberation logic is provider-agnostic — members are resolved to agent
specs and executed by agents.query_agent(). Conversation history is rendered
into each prompt so the council has multi-turn context (the CLIs are invoked
one-shot per turn, so we carry context as text rather than a live session).
"""

from typing import List, Dict, Any, Tuple, Optional

from .agents import query_agent, query_agents_parallel
from .config import COUNCIL_AGENTS, CHAIRMAN_AGENT, TITLE_AGENT

CLI_LABELS = {
    "claude": "Claude",
    "codex": "GPT (Codex)",
    "gemini": "Gemini",
    "agy": "Antigravity",
}

# Shown when a slot is on "(default)" — reflects the auto-updating tier it
# resolves to (see agents.resolve_default_model), so the tab name is meaningful.
DEFAULT_LABELS = {
    "claude": "Claude",
    "codex": "GPT (Codex)",
    "gemini": "Gemini Pro",
    "agy": "Antigravity (Gemini Flash)",
}


# --- Line-up resolution ------------------------------------------------------

def _spec_from_choice(choice: Dict[str, Any]) -> Dict[str, Any]:
    """Turn a UI choice {cli, model} into a full agent spec with a unique label."""
    cli = choice["cli"]
    model = choice.get("model") or None
    if model in ("", "(default)"):
        model = None
    label = f"{CLI_LABELS.get(cli, cli)} · {model}" if model else DEFAULT_LABELS.get(cli, cli)
    return {"id": cli, "label": label, "type": "cli", "cmd": cli, "model": model}


def resolve_lineup(council_override: Optional[Dict[str, Any]]):
    """Return (council_agents, chairman_agent), honouring a UI override if given."""
    if not council_override:
        return COUNCIL_AGENTS, CHAIRMAN_AGENT
    members = [_spec_from_choice(c) for c in council_override.get("members", [])]
    if not members:
        members = COUNCIL_AGENTS
    chairman_choice = council_override.get("chairman")
    chairman = _spec_from_choice(chairman_choice) if chairman_choice else CHAIRMAN_AGENT
    return members, chairman


# --- History rendering -------------------------------------------------------

def _build_transcript(history: List[Dict[str, Any]]) -> str:
    lines = []
    for m in history:
        if m.get("role") == "user":
            content = m.get("content", "")
            atts = m.get("attachments") or []
            if atts:
                names = ", ".join(a.get("filename", "file") for a in atts)
                content = f"{content} [attached: {names}]"
            lines.append(f"User: {content}")
        elif m.get("role") == "assistant":
            ans = (m.get("stage3") or {}).get("response", "")
            if ans:
                lines.append(f"Council answer: {ans}")
    return "\n\n".join(lines)


def _context_block(history: List[Dict[str, Any]]) -> str:
    transcript = _build_transcript(history)
    if not transcript:
        return ""
    return f"Conversation so far (for context):\n\n{transcript}\n\n---\n\n"


# --- Stage 1 -----------------------------------------------------------------

async def stage1_collect_responses(
    history: List[Dict[str, Any]],
    user_query: str,
    attachments: Optional[List[Dict[str, Any]]] = None,
    agents: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Collect an independent answer from every council member."""
    agents = agents or COUNCIL_AGENTS
    prompt = f"{_context_block(history)}{user_query}"

    responses = await query_agents_parallel(agents, prompt, attachments)

    stage1_results = []
    for agent, response in zip(agents, responses):
        if response is not None:
            stage1_results.append({
                "model": agent["label"],
                "response": response.get("content", ""),
            })
    return stage1_results


# --- Stage 2 -----------------------------------------------------------------

async def stage2_collect_rankings(
    history: List[Dict[str, Any]],
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    agents: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Each member ranks the anonymised Stage-1 answers."""
    agents = agents or COUNCIL_AGENTS
    labels = [chr(65 + i) for i in range(len(stage1_results))]  # A, B, C, ...

    label_to_model = {
        f"Response {label}": result["model"]
        for label, result in zip(labels, stage1_results)
    }

    responses_text = "\n\n".join([
        f"Response {label}:\n{result['response']}"
        for label, result in zip(labels, stage1_results)
    ])

    ranking_prompt = f"""You are evaluating different responses to the following question:

Question: {user_query}

Here are the responses from different models (anonymized):

{responses_text}

Your task:
1. First, evaluate each response individually. For each response, explain what it does well and what it does poorly.
2. Then, at the very end of your response, provide a final ranking.

IMPORTANT: Your final ranking MUST be formatted EXACTLY as follows:
- Start with the line "FINAL RANKING:" (all caps, with colon)
- Then list the responses from best to worst as a numbered list
- Each line should be: number, period, space, then ONLY the response label (e.g., "1. Response A")
- Do not add any other text or explanations in the ranking section

Example of the correct format for your ENTIRE response:

Response A provides good detail on X but misses Y...
Response B is accurate but lacks depth on Z...
Response C offers the most comprehensive answer...

FINAL RANKING:
1. Response C
2. Response A
3. Response B

Now provide your evaluation and ranking:"""

    # Rankings are pure text reasoning — no attachments needed.
    responses = await query_agents_parallel(agents, ranking_prompt, None)

    stage2_results = []
    for agent, response in zip(agents, responses):
        if response is not None:
            full_text = response.get("content", "")
            parsed = parse_ranking_from_text(full_text)
            stage2_results.append({
                "model": agent["label"],
                "ranking": full_text,
                "parsed_ranking": parsed,
            })

    return stage2_results, label_to_model


# --- Stage 3 -----------------------------------------------------------------

async def stage3_synthesize_final(
    history: List[Dict[str, Any]],
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    chairman: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Chairman synthesises the final answer from all responses + rankings."""
    chairman = chairman or CHAIRMAN_AGENT

    stage1_text = "\n\n".join([
        f"Model: {result['model']}\nResponse: {result['response']}"
        for result in stage1_results
    ])
    stage2_text = "\n\n".join([
        f"Model: {result['model']}\nRanking: {result['ranking']}"
        for result in stage2_results
    ])

    chairman_prompt = f"""You are the Chairman of an LLM Council. Multiple AI models have provided responses to a user's question, and then ranked each other's responses.

{_context_block(history)}Original Question: {user_query}

STAGE 1 - Individual Responses:
{stage1_text}

STAGE 2 - Peer Rankings:
{stage2_text}

Your task as Chairman is to synthesize all of this information into a single, comprehensive, accurate answer to the user's original question. Consider:
- The individual responses and their insights
- The peer rankings and what they reveal about response quality
- Any patterns of agreement or disagreement

Provide a clear, well-reasoned final answer that represents the council's collective wisdom:"""

    response = await query_agent(chairman, chairman_prompt)

    if response is None:
        return {
            "model": chairman["label"],
            "response": "Error: Unable to generate final synthesis.",
        }
    return {
        "model": chairman["label"],
        "response": response.get("content", ""),
    }


# --- Ranking parsing & aggregation (unchanged logic) -------------------------

def parse_ranking_from_text(ranking_text: str) -> List[str]:
    """Extract the FINAL RANKING section into an ordered list of response labels."""
    import re

    if "FINAL RANKING:" in ranking_text:
        parts = ranking_text.split("FINAL RANKING:")
        if len(parts) >= 2:
            ranking_section = parts[1]
            numbered_matches = re.findall(r'\d+\.\s*Response [A-Z]', ranking_section)
            if numbered_matches:
                return [re.search(r'Response [A-Z]', m).group() for m in numbered_matches]
            matches = re.findall(r'Response [A-Z]', ranking_section)
            return matches

    matches = re.findall(r'Response [A-Z]', ranking_text)
    return matches


def calculate_aggregate_rankings(
    stage2_results: List[Dict[str, Any]],
    label_to_model: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Average each model's rank position across all peer evaluations."""
    from collections import defaultdict

    model_positions = defaultdict(list)
    for ranking in stage2_results:
        parsed_ranking = parse_ranking_from_text(ranking["ranking"])
        for position, label in enumerate(parsed_ranking, start=1):
            if label in label_to_model:
                model_positions[label_to_model[label]].append(position)

    aggregate = []
    for model, positions in model_positions.items():
        if positions:
            aggregate.append({
                "model": model,
                "average_rank": round(sum(positions) / len(positions), 2),
                "rankings_count": len(positions),
            })
    aggregate.sort(key=lambda x: x["average_rank"])
    return aggregate


# --- Title + full run --------------------------------------------------------

async def generate_conversation_title(user_query: str) -> str:
    """Short title for the conversation, via the cheap title agent."""
    title_prompt = f"""Generate a very short title (3-5 words maximum) that summarizes the following question.
The title should be concise and descriptive. Do not use quotes or punctuation in the title.

Question: {user_query}

Title:"""

    # resolve_default=False -> gemini's bare default (Flash tier): fast & cheap
    # for titles, instead of the heavier Pro the council default would pick.
    response = await query_agent(TITLE_AGENT, title_prompt, timeout=60.0, resolve_default=False)
    if response is None:
        return "New Conversation"

    title = response.get("content", "New Conversation").strip().strip('"\'')
    # Titles should be one line.
    title = title.splitlines()[0].strip() if title else "New Conversation"
    if len(title) > 50:
        title = title[:47] + "..."
    return title or "New Conversation"


async def run_full_council(
    history: List[Dict[str, Any]],
    user_query: str,
    attachments: Optional[List[Dict[str, Any]]] = None,
    council_override: Optional[Dict[str, Any]] = None,
) -> Tuple[List, List, Dict, Dict]:
    """Run all three stages and return (stage1, stage2, stage3, metadata)."""
    agents, chairman = resolve_lineup(council_override)

    stage1_results = await stage1_collect_responses(history, user_query, attachments, agents)
    if not stage1_results:
        return [], [], {
            "model": "error",
            "response": "All council members failed to respond. Please try again.",
        }, {}

    stage2_results, label_to_model = await stage2_collect_rankings(
        history, user_query, stage1_results, agents
    )
    aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)

    stage3_result = await stage3_synthesize_final(
        history, user_query, stage1_results, stage2_results, chairman
    )

    metadata = {
        "label_to_model": label_to_model,
        "aggregate_rankings": aggregate_rankings,
    }
    return stage1_results, stage2_results, stage3_result, metadata
