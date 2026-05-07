"""Regenerate the SkillCard from already-captured session state.

Lets the user re-run synthesis + card generation (and image generation)
without going through the interview again. All context is supplied by
the client from its persisted localStorage session.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from profile_agent.api.auth import get_current_user
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
    import time
    from profile_agent.services.stateless_interview_service import (
        CompletedStageSummary,
        _generate_card_image,
        _get_openai_client,
        _run_card_generation,
        _run_synthesis,
    )

    settings = get_settings()

    if not body.completedStageSummaries:
        raise HTTPException(
            status_code=400,
            detail="No completed stage summaries — cannot regenerate without interview content.",
        )

    completed = [CompletedStageSummary(id=s.id, summary=s.summary) for s in body.completedStageSummaries]
    display_name = body.identity.name or user.get("name", "") or "Anonymous"

    t0 = time.perf_counter()
    logger.info("POST /api/regenerate START | name=%s stages=%d image=%s",
                display_name, len(completed), body.includeImage)

    client = await _get_openai_client(settings)
    try:
        # Build additional context from bulk-extracted profile data
        additional_context: str | None = None
        if body.bulk_extracted:
            import json as _json
            additional_context = f"Bulk-extracted profile data: {_json.dumps(body.bulk_extracted)}"

        t_synth = time.perf_counter()
        synthesis_json = await _run_synthesis(
            client, settings, completed, [],
            additional_context=additional_context,
        )
        logger.info("regenerate: synthesis done in %.2fs", time.perf_counter() - t_synth)

        t_card = time.perf_counter()
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
        logger.info("regenerate: card generation done in %.2fs", time.perf_counter() - t_card)
    except Exception as exc:
        logger.exception("Regeneration failed after %.2fs", time.perf_counter() - t0)
        raise HTTPException(status_code=500, detail=f"Regeneration failed: {exc}") from exc

    response: dict = {"cardData": card_data}

    if body.includeImage:
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
            t_img = time.perf_counter()
            img = await _generate_card_image(client, settings, card_data, photo_base64=body.photoBase64, style=style)
            logger.info("regenerate: image generation done in %.2fs", time.perf_counter() - t_img)
            if img and "base64" in img:
                response["cardImage"] = img
            elif img and img.get("error") == "rate_limited":
                ra = img.get("retry_after")
                response["cardImageError"] = "rate_limited"
                if ra:
                    response["cardImageRetryAfter"] = ra
            elif img and img.get("error"):
                response["cardImageError"] = "failed"
        except Exception:
            logger.exception("Image regeneration failed after %.2fs total", time.perf_counter() - t0)
            response["cardImageError"] = "image generation failed"

    logger.info("POST /api/regenerate DONE in %.2fs", time.perf_counter() - t0)
    return response
