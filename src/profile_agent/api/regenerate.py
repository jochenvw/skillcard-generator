"""Regenerate the SkillCard from already-captured session state.

Lets the user re-run synthesis + card generation (and image generation)
without going through the interview again. All context is supplied by
the client from its persisted localStorage session.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from profile_agent.api.auth import get_current_user
from profile_agent.config.context import hash_user_id, user_id_var
from profile_agent.config.events import wide_event
from profile_agent.config.settings import get_settings
from profile_agent.services import image_cache
from profile_agent.services.image_queue import (
    QueueFullError,
    STATE_DONE,
    get_queue,
)

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

    # ── Cache lookup (text-only) ──────────────────────────────────────────────
    # Identical inputs → identical card text. Survives only while this replica
    # lives (filesystem-only). Image is always generated separately downstream.
    from profile_agent.services import card_text_cache
    cache_key = card_text_cache.compute_key(
        deployment=settings.effective_azure_openai_deployment,
        identity=body.identity.model_dump(),
        completed_stages=[{"id": s.id, "summary": s.summary} for s in body.completedStageSummaries],
        clifton_strengths=body.cliftonStrengths,
        linkedin_skills=body.linkedin_skills,
        github_skills=body.github_skills,
        bulk_extracted=body.bulk_extracted,
        style=body.style.model_dump() if body.style else None,
    )
    cached_card = card_text_cache.get(cache_key)
    if cached_card is not None:
        wide_event(
            "regenerate.completed",
            outcome="ok",
            cache_hit=True,
            cache_key=cache_key[:12],
            duration_ms=int((time.perf_counter() - t0) * 1000),
            synthesis_ms=0,
            card_ms=0,
            image_ms=0,
            image_outcome="skipped",
            image_error_type=None,
            image_error_message=None,
            **base_attrs,
        )
        # Cache returns text only; client kicks off image gen via /api/regenerate/image.
        return {"cardData": cached_card, "cacheHit": True}

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
        # Persist to text cache so identical re-clicks short-circuit.
        card_text_cache.put(cache_key, card_data)
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


# ─────────────────────────────────────────────────────────────────────────────
# Background image regeneration (queued + polled). Throttled by the singleton
# image queue so we don't hammer the upstream rate limit.
# ─────────────────────────────────────────────────────────────────────────────


class ImageJobRequest(BaseModel):
    cardData: dict
    photoBase64: str | None = None
    style: _CardStyleBody | None = None


async def image_worker(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Worker invoked by the queue. Performs the actual upstream image call.

    Payload shape (set by ``start_image_job``):
        {"card_data": dict, "photo_base64": str|None, "style": dict|None}

    Returns the raw image_service result dict so the queue can interpret
    success / rate_limit / generic failure uniformly.
    """
    from profile_agent.models.llm_contracts import CardStyle
    from profile_agent.services.stateless_interview_service import _generate_card_image, _get_openai_client

    settings = get_settings()
    client = await _get_openai_client(settings)
    style_dict = payload.get("style")
    style: CardStyle | None = None
    if style_dict and any(style_dict.get(k) for k in ("stylePreset", "personaSetting", "accentColor")):
        style = CardStyle(
            style_preset=style_dict.get("stylePreset"),
            persona_setting=style_dict.get("personaSetting"),
            accent_color=style_dict.get("accentColor"),
        )
    return await _generate_card_image(
        client,
        settings,
        payload["card_data"],
        photo_base64=payload.get("photo_base64"),
        style=style,
    )


@router.post("/regenerate/image")
async def start_image_job(body: ImageJobRequest, user: dict = Depends(get_current_user)):
    """Submit an image-generation job to the queue.

    Behavior:
    - Cache hit → returns ``state="done"`` inline with the cached image, skipping the queue.
    - Queue full → 429 with ``retry_after_s``.
    - Otherwise → ``state="queued"`` with ``queue_position`` and ``estimated_wait_s``.
    """
    from profile_agent.services.stateless_interview_service import _build_card_image_prompt
    user_hash = hash_user_id(user.get("user_id") or user.get("email", ""))
    user_id_var.set(user_hash)

    # ── Image cache short-circuit (skips the queue entirely) ─────────────────
    settings = get_settings()
    photo_bytes = None
    if body.photoBase64:
        try:
            import base64 as _b64
            photo_bytes = _b64.b64decode(body.photoBase64)
        except Exception:  # noqa: BLE001
            photo_bytes = None
    try:
        prompt = _build_card_image_prompt(body.cardData)
        deployment = settings.foundry_image_deployment_name
        cache_key = image_cache.compute_key(
            deployment=deployment,
            size="1024x1536",
            prompt=prompt,
            photo_bytes=photo_bytes,
        )
        cached = image_cache.get(cache_key)
    except Exception:  # noqa: BLE001
        cache_key = ""
        cached = None
    if cached is not None:
        wide_event(
            "image_job.cache_hit",
            outcome="ok",
            cache_key=cache_key[:12],
        )
        return {
            "state": STATE_DONE,
            "result": {"base64": cached["base64"]},
            "cache_hit": True,
        }

    # ── Enqueue ──────────────────────────────────────────────────────────────
    queue = get_queue()
    try:
        job = queue.enqueue(
            user_hash=user_hash,
            payload={
                "card_data": body.cardData,
                "photo_base64": body.photoBase64,
                "style": body.style.model_dump() if body.style else None,
            },
            has_photo=bool(body.photoBase64),
            cache_key_prefix=cache_key,
        )
    except QueueFullError as exc:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "queue_full",
                "queue_depth": exc.depth,
                "retry_after_s": exc.retry_after_s,
                "message": (
                    "We're generating a lot of cards right now. "
                    "Please try again in a few minutes."
                ),
            },
            headers={"Retry-After": str(exc.retry_after_s)},
        ) from exc

    return {
        "job_id": job.job_id,
        "state": job.state,
        "queue_position": job.queue_position,
        "queue_depth": queue.stats()["queue_depth"],
        "estimated_wait_s": queue.estimate_wait_s(job.queue_position),
    }


@router.get("/regenerate/image/{job_id}")
async def poll_image_job(job_id: str, user: dict = Depends(get_current_user)):
    """Poll an image-generation job."""
    user_hash = hash_user_id(user.get("user_id") or user.get("email", ""))
    queue = get_queue()
    status = queue.status(job_id, user_hash)
    if status is None:
        wide_event("image_job.not_found", outcome="error", job_id=job_id, level=logging.WARNING)
        raise HTTPException(status_code=404, detail="Job not found, expired, or not yours")
    return {"job_id": job_id, **status}


@router.get("/regenerate/queue/stats")
async def queue_stats():
    """Operator endpoint — no auth required, no PII. Useful for dashboards."""
    return get_queue().stats()
