"""Stateless streaming chat API — AI SDK Data Stream Protocol endpoint.

The server holds no session state. All context is passed in each request
and state updates are returned in the SSE stream for the client to persist.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from profile_agent.api.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


# ── Request models ──


class IdentityContext(BaseModel):
    name: str = ""
    role: str = ""
    photoStatus: str = "unknown"


class CompletedStageSummary(BaseModel):
    id: str
    summary: str


class StatelessChatRequest(BaseModel):
    message: str
    currentStageId: str = "introduction"
    completedStageSummaries: list[CompletedStageSummary] = Field(default_factory=list)
    currentStageMessages: list[dict] = Field(default_factory=list)
    identity: IdentityContext = Field(default_factory=IdentityContext)
    hasImage: bool = False


# ── Endpoint ──


@router.post("/chat")
async def chat(
    body: StatelessChatRequest,
    user: dict = Depends(get_current_user),
):
    """Stateless streaming chat — all context in the request body.

    Returns an SSE stream with text-start/text-delta/text-end events
    followed by a data-stateUpdate event containing the updated state
    for the client to persist in localStorage.
    """
    from profile_agent.services.stateless_interview_service import (
        CompletedStageSummary as SvcSummary,
        IdentityContext as SvcIdentity,
        process_stateless_turn,
    )

    user_text = body.message.strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="Message must not be empty")

    # Map request models to service dataclasses
    identity = SvcIdentity(
        name=body.identity.name,
        role=body.identity.role,
        photo_status=body.identity.photoStatus,
    )
    completed = [
        SvcSummary(id=s.id, summary=s.summary)
        for s in body.completedStageSummaries
    ]

    async def stream_response():
        async for chunk in process_stateless_turn(
            user_text=user_text,
            current_stage_id=body.currentStageId,
            completed_summaries=completed,
            current_stage_messages=body.currentStageMessages,
            identity=identity,
            has_image=body.hasImage,
        ):
            yield chunk

    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
