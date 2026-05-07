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
    linkedin_skills: dict | None = None
    github_skills: dict | None = None
    bulk_extracted: dict | None = None
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

    # Bind validated user identity into request context (hashed — no PII in logs)
    from profile_agent.config.context import hash_user_id, user_id_var
    from profile_agent.config.events import wide_event
    user_id_var.set(hash_user_id(user.get("user_id") or user.get("email", "")))

    wide_event(
        "chat.received",
        stage_id=body.currentStageId,
        message_len=len(user_text),
        has_photo=bool(body.photoBase64),
        has_clifton=bool(body.cliftonStrengths),
        has_linkedin=bool(body.linkedin_skills),
        has_github=bool(body.github_skills),
        completed_stages=len(body.completedStageSummaries),
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
            linkedin_skills=body.linkedin_skills,
            github_skills=body.github_skills,
            bulk_extracted=body.bulk_extracted,
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
