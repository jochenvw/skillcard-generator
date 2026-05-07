"""Regenerate the SkillCard from already-captured session state.

Lets the user re-run synthesis + card generation (and image generation)
without going through the interview again. All context is supplied by
the client from its persisted localStorage session.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from profile_agent.api.auth import get_current_user
from profile_agent.config.context import hash_user_id, user_id_var
from profile_agent.config.events import wide_event
from profile_agent.config.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["regenerate"])

# In-memory job store for image-generation polling. The Container Apps ingress
# request timeout is hard-capped at 240s on the Consumption plan, but image
# generation can take 200-320s — so we run it in the background and let the
# client poll. Single-replica deployment means we don't need a shared store.
_IMAGE_JOBS: dict[str, dict[str, Any]] = {}
_JOB_TTL = timedelta(minutes=30)
_JOB_HARD_TIMEOUT_S = 600  # 10 minutes — give up on the image even if the model is still working


def _cleanup_expired_jobs() -> None:
    now = datetime.now(UTC)
    expired = [jid for jid, job in _IMAGE_JOBS.items() if now - job["created_at"] > _JOB_TTL]
    for jid in expired:
        _IMAGE_JOBS.pop(jid, None)
    if expired:
        wide_event("regenerate.image.jobs.evicted", outcome="ok", count=len(expired))


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
# Background image regeneration (job + poll API) — works around the 240s
# Container Apps ingress timeout.
# ─────────────────────────────────────────────────────────────────────────────


class ImageJobRequest(BaseModel):
    cardData: dict
    photoBase64: str | None = None
    style: _CardStyleBody | None = None


@router.post("/regenerate/image")
async def start_image_job(body: ImageJobRequest, user: dict = Depends(get_current_user)):
    """Kick off image generation in a background task; return a job_id to poll."""
    _cleanup_expired_jobs()
    user_hash = hash_user_id(user.get("user_id") or user.get("email", ""))
    user_id_var.set(user_hash)
    job_id = uuid.uuid4().hex
    _IMAGE_JOBS[job_id] = {
        "status": "pending",
        "created_at": datetime.now(UTC),
        "user_id_hash": user_hash,
    }
    asyncio.create_task(_run_image_job(job_id, body, user_hash))
    wide_event(
        "regenerate.image.job.created",
        outcome="ok",
        job_id=job_id,
        has_photo=bool(body.photoBase64),
    )
    return {"job_id": job_id, "status": "pending"}


@router.get("/regenerate/image/{job_id}")
async def poll_image_job(job_id: str, user: dict = Depends(get_current_user)):
    """Poll an image-generation job. Returns status + image (when ready) or error."""
    job = _IMAGE_JOBS.get(job_id)
    if job is None:
        wide_event("regenerate.image.job.not_found", outcome="error", job_id=job_id, level=logging.WARNING)
        raise HTTPException(status_code=404, detail="Job not found or expired")
    expected_hash = hash_user_id(user.get("user_id") or user.get("email", ""))
    if job["user_id_hash"] != expected_hash:
        wide_event("regenerate.image.job.forbidden", outcome="error", job_id=job_id, level=logging.WARNING)
        raise HTTPException(status_code=403, detail="Not your job")

    resp: dict[str, Any] = {"status": job["status"]}
    if job["status"] == "ready":
        resp["image"] = job["image"]
        resp["duration_ms"] = job.get("duration_ms")
    elif job["status"] == "failed":
        resp["error"] = job.get("error", "unknown")
        resp["error_type"] = job.get("error_type")
        if job.get("retry_after"):
            resp["retry_after"] = job["retry_after"]
    return resp


async def _run_image_job(job_id: str, body: ImageJobRequest, user_hash: str) -> None:
    """Background task that generates the image and stashes the result on the job."""
    from profile_agent.models.llm_contracts import CardStyle
    from profile_agent.services.stateless_interview_service import _generate_card_image, _get_openai_client

    # Restore request context vars in this background task so wide_events stay correlated
    user_id_var.set(user_hash)
    settings = get_settings()
    t0 = time.perf_counter()
    wide_event(
        "regenerate.image.job.started",
        outcome="ok",
        job_id=job_id,
        has_photo=bool(body.photoBase64),
    )
    try:
        client = await _get_openai_client(settings)
        style: CardStyle | None = None
        if body.style is not None and any(
            v for v in (body.style.stylePreset, body.style.personaSetting, body.style.accentColor)
        ):
            style = CardStyle(
                style_preset=body.style.stylePreset,
                persona_setting=body.style.personaSetting,
                accent_color=body.style.accentColor,
            )
        img = await asyncio.wait_for(
            _generate_card_image(client, settings, body.cardData, photo_base64=body.photoBase64, style=style),
            timeout=_JOB_HARD_TIMEOUT_S,
        )
        duration_ms = int((time.perf_counter() - t0) * 1000)
        if img and "base64" in img:
            _IMAGE_JOBS[job_id].update({"status": "ready", "image": img, "duration_ms": duration_ms})
            wide_event(
                "regenerate.image.job.completed",
                outcome="ok",
                job_id=job_id,
                duration_ms=duration_ms,
            )
        elif img and img.get("error") == "rate_limited":
            _IMAGE_JOBS[job_id].update(
                {
                    "status": "failed",
                    "error": "rate_limited",
                    "error_type": "rate_limited",
                    "retry_after": img.get("retry_after"),
                    "duration_ms": duration_ms,
                }
            )
            wide_event(
                "regenerate.image.job.completed",
                outcome="error",
                error_type="rate_limited",
                job_id=job_id,
                duration_ms=duration_ms,
                level=logging.WARNING,
            )
        else:
            err_kind = (img or {}).get("error", "generation_failed") if img else "no_image"
            _IMAGE_JOBS[job_id].update(
                {
                    "status": "failed",
                    "error": str(err_kind),
                    "error_type": "generation_failed",
                    "duration_ms": duration_ms,
                }
            )
            wide_event(
                "regenerate.image.job.completed",
                outcome="error",
                error_type=str(err_kind),
                job_id=job_id,
                duration_ms=duration_ms,
                level=logging.ERROR,
            )
    except TimeoutError:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        _IMAGE_JOBS[job_id].update(
            {
                "status": "failed",
                "error": f"image generation exceeded {_JOB_HARD_TIMEOUT_S}s timeout",
                "error_type": "TimeoutError",
                "duration_ms": duration_ms,
            }
        )
        wide_event(
            "regenerate.image.job.completed",
            outcome="error",
            error_type="TimeoutError",
            job_id=job_id,
            duration_ms=duration_ms,
            level=logging.ERROR,
        )
        logger.error("Image job %s timed out after %ds", job_id, _JOB_HARD_TIMEOUT_S)
    except Exception as exc:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        _IMAGE_JOBS[job_id].update(
            {
                "status": "failed",
                "error": str(exc)[:500],
                "error_type": type(exc).__name__,
                "duration_ms": duration_ms,
            }
        )
        wide_event(
            "regenerate.image.job.completed",
            outcome="error",
            error_type=type(exc).__name__,
            error_message=str(exc)[:500],
            job_id=job_id,
            duration_ms=duration_ms,
            level=logging.ERROR,
        )
        logger.exception("Image job %s failed", job_id)
