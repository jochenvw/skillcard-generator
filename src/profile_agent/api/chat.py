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
    title: str = ""
    photoStatus: str = "unknown"


class CompletedStageSummary(BaseModel):
    id: str
    summary: str


class _CardStyleBody(BaseModel):
    stylePreset: str | None = None
    personaSetting: str | None = None
    accentColor: str | None = None


class StatelessChatRequest(BaseModel):
    message: str
    currentStageId: str = "introduction"
    completedStageSummaries: list[CompletedStageSummary] = Field(default_factory=list)
    currentStageMessages: list[dict] = Field(default_factory=list)
    identity: IdentityContext = Field(default_factory=IdentityContext)
    hasImage: bool = False
    photoBase64: str | None = None
    cliftonStrengths: list[str] = Field(default_factory=list)
    style: _CardStyleBody | None = None


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
    from profile_agent.models.llm_contracts import CardStyle
    from profile_agent.services.stateless_interview_service import (
        CompletedStageSummary as SvcSummary,
        IdentityContext as SvcIdentity,
        process_stateless_turn,
    )

    user_text = body.message.strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="Message must not be empty")

    logger.info(
        "POST /api/chat | stage=%s user=%s msg=%s has_photo=%s",
        body.currentStageId,
        body.identity.name or user.get("name", "anon"),
        user_text[:60],
        bool(body.photoBase64),
    )

    # Map request models to service dataclasses
    identity = SvcIdentity(
        name=body.identity.name,
        role=body.identity.role,
        title=body.identity.title,
        photo_status=body.identity.photoStatus,
    )
    completed = [
        SvcSummary(id=s.id, summary=s.summary)
        for s in body.completedStageSummaries
    ]

    style: CardStyle | None = None
    if body.style is not None and any(
        v for v in (body.style.stylePreset, body.style.personaSetting, body.style.accentColor)
    ):
        style = CardStyle(
            style_preset=body.style.stylePreset,
            persona_setting=body.style.personaSetting,
            accent_color=body.style.accentColor,
        )

    async def stream_response():
        async for chunk in process_stateless_turn(
            user_text=user_text,
            current_stage_id=body.currentStageId,
            completed_summaries=completed,
            current_stage_messages=body.currentStageMessages,
            identity=identity,
            has_image=body.hasImage,
            photo_base64=body.photoBase64,
            clifton_strengths=body.cliftonStrengths,
            style=style,
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
