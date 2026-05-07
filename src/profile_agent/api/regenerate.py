"""Regenerate the SkillCard from already-captured session state.

Lets the user re-run synthesis + card generation (and image generation)
without going through the interview again. All context is supplied by
the client from its persisted localStorage session.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from profile_agent.api.auth import get_current_user
from profile_agent.config.context import hash_user_id, user_id_var
from profile_agent.config.events import wide_event
from profile_agent.config.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["regenerate"])


class _Identity(BaseModel):
    name: str = ""
    role: str = ""
    title: str | None = None
    photoStatus: str = "unknown"


class _Stage(BaseModel):
    id: str
    summary: str


class _CardStyleBody(BaseModel):
    stylePreset: str | None = None
    personaSetting: str | None = None
    accentColor: str | None = None


class RegenerateRequest(BaseModel):
    identity: _Identity = Field(default_factory=_Identity)
    completedStageSummaries: list[_Stage] = Field(default_factory=list)
    cliftonStrengths: list[str] = Field(default_factory=list)
    linkedin_skills: dict | None = None
    github_skills: dict | None = None
    bulk_extracted: dict | None = None
    photoBase64: str | None = None
    includeImage: bool = True
    style: _CardStyleBody | None = None


@router.post("/regenerate")
async def regenerate(body: RegenerateRequest, user: dict = Depends(get_current_user)):
    from profile_agent.services.stateless_interview_service import (
        CompletedStageSummary,
        _generate_card_image,
        _get_openai_client,
        _run_card_generation,
        _run_synthesis,
    )

    settings = get_settings()

    # Bind validated user identity into request context (hashed — no PII in logs)
    user_id_var.set(hash_user_id(user.get("user_id") or user.get("email", "")))

    if not body.completedStageSummaries:
        wide_event("regenerate.rejected", outcome="error", reason="no_stages")
        raise HTTPException(
            status_code=400,
            detail="No completed stage summaries — cannot regenerate without interview content.",
        )

    completed = [CompletedStageSummary(id=s.id, summary=s.summary) for s in body.completedStageSummaries]
    display_name = body.identity.name or user.get("name", "") or "Anonymous"

    base_attrs = {
        "num_stages": len(completed),
        "include_image": body.includeImage,
        "has_clifton": bool(body.cliftonStrengths),
        "has_linkedin": bool(body.linkedin_skills),
        "has_github": bool(body.github_skills),
        "has_bulk": bool(body.bulk_extracted),
        "has_photo": bool(body.photoBase64),
        "photo_status": body.identity.photoStatus,
    }
    wide_event("regenerate.started", **base_attrs)

    t0 = time.perf_counter()
    synthesis_ms = card_ms = image_ms = 0
    image_outcome = "skipped"
    image_error_type: str | None = None
    image_error_message: str | None = None
    current_step = "init"
    client = await _get_openai_client(settings)

    try:
        # Build additional context from bulk-extracted profile data
        additional_context: str | None = None
        if body.bulk_extracted:
            import json as _json
            additional_context = f"Bulk-extracted profile data: {_json.dumps(body.bulk_extracted)}"

        current_step = "synthesis"
        t = time.perf_counter()
        synthesis_json = await _run_synthesis(
            client, settings, completed, [],
            additional_context=additional_context,
        )
        synthesis_ms = int((time.perf_counter() - t) * 1000)

        current_step = "card_generation"
        t = time.perf_counter()
        card_data = await _run_card_generation(
            client,
            settings,
            synthesis_json,
            display_name,
            body.identity.photoStatus,
            clifton_strengths=body.cliftonStrengths,
            linkedin_skills=body.linkedin_skills,
            github_skills=body.github_skills,
            completed_summaries=completed,
            role_text=body.identity.title or body.identity.role,
        )
        card_ms = int((time.perf_counter() - t) * 1000)
    except Exception as exc:
        wide_event(
            "regenerate.failed",
            outcome="error",
            level=logging.ERROR,
            failed_step=current_step,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            synthesis_ms=synthesis_ms,
            card_ms=card_ms,
            error_type=type(exc).__name__,
            error_message=str(exc)[:500],
            **base_attrs,
        )
        # logger.exception emits an ExceptionTelemetry record (stack trace) into App Insights
        # via the OpenTelemetry logging instrumentation.
        logger.exception(
            "Regeneration failed at step=%s error_type=%s",
            current_step,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Regeneration failed during {current_step}: {exc}",
        ) from exc

    response: dict = {"cardData": card_data}

    if body.includeImage:
        current_step = "image_generation"
        try:
            from profile_agent.models.llm_contracts import CardStyle
            style: CardStyle | None = None
            if body.style is not None and any(
                v for v in (body.style.stylePreset, body.style.personaSetting, body.style.accentColor)
            ):
                style = CardStyle(
                    style_preset=body.style.stylePreset,
                    persona_setting=body.style.personaSetting,
                    accent_color=body.style.accentColor,
                )
            t = time.perf_counter()
            img = await _generate_card_image(client, settings, card_data, photo_base64=body.photoBase64, style=style)
            image_ms = int((time.perf_counter() - t) * 1000)
            if img and "base64" in img:
                response["cardImage"] = img
                image_outcome = "ok"
            elif img and img.get("error") == "rate_limited":
                ra = img.get("retry_after")
                response["cardImageError"] = "rate_limited"
                image_outcome = "rate_limited"
                if ra:
                    response["cardImageRetryAfter"] = ra
            elif img and img.get("error"):
                response["cardImageError"] = "failed"
                image_outcome = "failed"
                image_error_type = str(img.get("error"))[:100]
                image_error_message = str(img.get("message") or img.get("error"))[:500]
        except Exception as exc:
            image_outcome = "exception"
            image_error_type = type(exc).__name__
            image_error_message = str(exc)[:500]
            response["cardImageError"] = "image generation failed"
            wide_event(
                "regenerate.image.failed",
                outcome="error",
                level=logging.ERROR,
                duration_ms=int((time.perf_counter() - t0) * 1000),
                image_ms=int((time.perf_counter() - t) * 1000),
                error_type=image_error_type,
                error_message=image_error_message,
                **base_attrs,
            )
            logger.exception("Image regeneration failed (text card succeeded)")

    overall_outcome = "ok"
    overall_level = logging.INFO
    if image_outcome in ("exception", "failed", "rate_limited"):
        overall_outcome = "partial"
        overall_level = logging.WARNING

    wide_event(
        "regenerate.completed",
        outcome=overall_outcome,
        level=overall_level,
        duration_ms=int((time.perf_counter() - t0) * 1000),
        synthesis_ms=synthesis_ms,
        card_ms=card_ms,
        image_ms=image_ms,
        image_outcome=image_outcome,
        image_error_type=image_error_type,
        image_error_message=image_error_message,
        **base_attrs,
    )
    return response
