"""FastAPI backend for LLM Council."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from pathlib import Path
import base64
import mimetypes
import uuid
import json
import asyncio

from . import storage
from .agents import list_agy_models, check_agent_available, resolve_default_model
from .config import COUNCIL_AGENTS, LIVE_MODEL_DISCOVERY, ATTACHMENTS_DIR
from .council import (
    run_full_council,
    resolve_lineup,
    generate_conversation_title,
    stage1_collect_responses,
    stage2_collect_rankings,
    stage3_synthesize_final,
    calculate_aggregate_rankings,
)

app = FastAPI(title="LLM Council API")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded attachments back to the UI (e.g. /attachments/<conv>/<file>).
Path(ATTACHMENTS_DIR).mkdir(parents=True, exist_ok=True)
app.mount("/attachments", StaticFiles(directory=ATTACHMENTS_DIR), name="attachments")


# --- Request/response models -------------------------------------------------

class CreateConversationRequest(BaseModel):
    pass


class Attachment(BaseModel):
    """An uploaded file from the client (base64-encoded, possibly a data URL)."""
    filename: str
    mime: str = ""
    data_base64: str


class SendMessageRequest(BaseModel):
    content: str
    attachments: List[Attachment] = []
    # Optional council line-up chosen in the UI:
    #   {"members": [{"cli": "claude", "model": null}, ...],
    #    "chairman": {"cli": "claude", "model": null}}
    council: Optional[Dict[str, Any]] = None


class ConversationMetadata(BaseModel):
    id: str
    created_at: str
    title: str
    message_count: int


class Conversation(BaseModel):
    id: str
    created_at: str
    title: str
    messages: List[Dict[str, Any]]


# --- Attachment helpers ------------------------------------------------------

def _save_attachments(conversation_id: str, attachments: List[Attachment]) -> List[Dict[str, Any]]:
    """Decode base64 attachments to disk; return refs for the CLIs + the UI."""
    saved: List[Dict[str, Any]] = []
    if not attachments:
        return saved

    dest_dir = Path(ATTACHMENTS_DIR) / conversation_id
    dest_dir.mkdir(parents=True, exist_ok=True)

    for att in attachments:
        data = att.data_base64
        if data.strip().startswith("data:") and "," in data:
            data = data.split(",", 1)[1]  # strip the data-URL prefix
        try:
            raw = base64.b64decode(data)
        except Exception:
            continue

        ext = Path(att.filename).suffix or mimetypes.guess_extension(att.mime or "") or ""
        stored = f"{uuid.uuid4().hex}{ext}"
        (dest_dir / stored).write_bytes(raw)

        saved.append({
            "filename": att.filename,
            "mime": att.mime,
            "path": str((dest_dir / stored).resolve()),  # absolute -> for CLIs
            "url": f"/attachments/{conversation_id}/{stored}",  # -> for the UI
        })
    return saved


# --- Endpoints ---------------------------------------------------------------

@app.get("/")
async def root():
    return {"status": "ok", "service": "LLM Council API"}


@app.get("/api/agents/status")
async def agents_status():
    """Which council CLIs are installed + what their auto "(default)" resolves to."""
    out = []
    for a in COUNCIL_AGENTS:
        default_model = await resolve_default_model(a["cmd"])
        out.append({
            "id": a["id"],
            "label": a["label"],
            "cmd": a["cmd"],
            "available": check_agent_available(a),
            "default_model": default_model or "(CLI default)",
        })
    return out


@app.get("/api/models")
async def list_models():
    """Selectable models per CLI — fetched dynamically, never hardcoded.

    Returns {cli: {"models": [...], "live": bool}}. Only `agy` exposes a real
    list command; for the others `models` is empty and `live` is false, so the
    UI offers a free-text field + a "(default)" option (latest model per CLI).
    """
    result = {}
    for cli, live in LIVE_MODEL_DISCOVERY.items():
        models = await list_agy_models() if cli == "agy" else []
        result[cli] = {"models": models, "live": live}
    return result


@app.get("/api/conversations", response_model=List[ConversationMetadata])
async def list_conversations():
    return storage.list_conversations()


@app.post("/api/conversations", response_model=Conversation)
async def create_conversation(request: CreateConversationRequest):
    conversation_id = str(uuid.uuid4())
    return storage.create_conversation(conversation_id)


@app.get("/api/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str):
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.post("/api/conversations/{conversation_id}/message")
async def send_message(conversation_id: str, request: SendMessageRequest):
    """Send a message and run the full 3-stage council process (non-streaming)."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    history = list(conversation["messages"])  # context BEFORE this turn
    is_first_message = len(history) == 0
    saved_attachments = _save_attachments(conversation_id, request.attachments)

    storage.add_user_message(conversation_id, request.content, saved_attachments)

    if is_first_message:
        title = await generate_conversation_title(request.content)
        storage.update_conversation_title(conversation_id, title)

    stage1_results, stage2_results, stage3_result, metadata = await run_full_council(
        history, request.content, saved_attachments, request.council
    )

    storage.add_assistant_message(conversation_id, stage1_results, stage2_results, stage3_result)

    return {
        "stage1": stage1_results,
        "stage2": stage2_results,
        "stage3": stage3_result,
        "metadata": metadata,
    }


@app.post("/api/conversations/{conversation_id}/message/stream")
async def send_message_stream(conversation_id: str, request: SendMessageRequest):
    """Send a message and stream each stage as Server-Sent Events."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    history = list(conversation["messages"])  # context BEFORE this turn
    is_first_message = len(history) == 0
    saved_attachments = _save_attachments(conversation_id, request.attachments)
    agents, chairman = resolve_lineup(request.council)

    async def event_generator():
        try:
            storage.add_user_message(conversation_id, request.content, saved_attachments)

            title_task = None
            if is_first_message:
                title_task = asyncio.create_task(generate_conversation_title(request.content))

            # Stage 1
            yield f"data: {json.dumps({'type': 'stage1_start'})}\n\n"
            stage1_results = await stage1_collect_responses(
                history, request.content, saved_attachments, agents
            )
            yield f"data: {json.dumps({'type': 'stage1_complete', 'data': stage1_results})}\n\n"

            # Stage 2
            yield f"data: {json.dumps({'type': 'stage2_start'})}\n\n"
            stage2_results, label_to_model = await stage2_collect_rankings(
                history, request.content, stage1_results, agents
            )
            aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
            yield f"data: {json.dumps({'type': 'stage2_complete', 'data': stage2_results, 'metadata': {'label_to_model': label_to_model, 'aggregate_rankings': aggregate_rankings}})}\n\n"

            # Stage 3
            yield f"data: {json.dumps({'type': 'stage3_start'})}\n\n"
            stage3_result = await stage3_synthesize_final(
                history, request.content, stage1_results, stage2_results, chairman
            )
            yield f"data: {json.dumps({'type': 'stage3_complete', 'data': stage3_result})}\n\n"

            if title_task:
                title = await title_task
                storage.update_conversation_title(conversation_id, title)
                yield f"data: {json.dumps({'type': 'title_complete', 'data': {'title': title}})}\n\n"

            storage.add_assistant_message(conversation_id, stage1_results, stage2_results, stage3_result)
            yield f"data: {json.dumps({'type': 'complete'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
