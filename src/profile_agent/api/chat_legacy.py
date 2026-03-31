"""Streaming chat API — AI SDK Data Stream Protocol endpoint."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from profile_agent.api.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# In-memory session cache: session_id -> InterviewSession
# In production, consider a proper session store with TTL.
_active_sessions: dict[str, Any] = {}


class ChatMessagePart(BaseModel):
    type: str = "text"
    text: str = ""


class ChatMessage(BaseModel):
    role: str
    content: str | None = None
    parts: list[ChatMessagePart] = Field(default_factory=list)

    def get_text(self) -> str:
        """Extract text content from either content field or parts array."""
        if self.content:
            return self.content
        return "".join(p.text for p in self.parts if p.type == "text")


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1)
    # AI SDK v6 also sends these fields
    id: str | None = None
    trigger: str | None = None
    messageId: str | None = None
    hasImage: bool = False


@router.post("/sessions/{session_id}/chat")
async def chat(
    session_id: str,
    body: ChatRequest,
    user: dict = Depends(get_current_user),
):
    """Stream a chat response using AI SDK Data Stream Protocol.

    Accepts the standard AI SDK message format and returns SSE-style
    streaming with text deltas (0:) and data annotations (2:).
    """
    from profile_agent.services.interview_service import InterviewService

    service = InterviewService()

    # Get or create the interview session
    if session_id not in _active_sessions:
        # Verify the session exists
        from profile_agent.api.dependencies import get_session_service

        svc = get_session_service()
        session_record = await svc.get_session(session_id)
        if not session_record:
            raise HTTPException(status_code=404, detail="Session not found")

        client, project_client, credential = await service.create_openai_client()
        interview_session = await service.init_session(session_id, client)
        _active_sessions[session_id] = {
            "interview": interview_session,
            "project_client": project_client,
            "credential": credential,
        }

    interview_session = _active_sessions[session_id]["interview"]

    # Extract the latest user message
    last_msg = body.messages[-1]
    if last_msg.role != "user":
        raise HTTPException(status_code=400, detail="Last message must be from user")

    user_text = last_msg.get_text().strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="Message content must not be empty")

    has_image = body.hasImage

    async def stream_response():
        async for chunk in service.process_turn_streaming(interview_session, user_text, has_image=has_image):
            yield chunk

        # Persist progress after streaming completes
        try:
            await _persist_session(session_id, interview_session)
        except Exception:
            logger.exception("Failed to persist session %s", session_id)

    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


async def _persist_session(session_id: str, interview_session) -> None:
    """Persist transcript and stage state after a turn."""
    from profile_agent.memory.session_store import create_session_store
    from profile_agent.memory.transcript_store import create_transcript_store
    from profile_agent.config.settings import get_settings

    settings = get_settings()
    session_store = await create_session_store(settings)
    transcript_store = await create_transcript_store(settings)

    await session_store.save_stage_state(interview_session.stage_state)
    await transcript_store.save_transcript(interview_session.transcript)

    # Update session record
    session_record = await session_store.get_session(session_id)
    if session_record:
        session_record.current_stage_id = interview_session.stage_state.current_stage_id
        session_record.completed_stages = interview_session.stage_state.completed_stage_ids
        session_record.turn_count = interview_session.transcript.turn_count
        from datetime import datetime
        session_record.updated_at = datetime.utcnow()
        await session_store.update_session(session_record)
