"""CliftonStrengths extraction endpoint — stateless POST /api/extract-strengths."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from profile_agent.api.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["strengths"])

_MAX_TEXT_LEN = 200_000


class ExtractStrengthsRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=_MAX_TEXT_LEN)


@router.post("/extract-strengths")
async def extract_strengths_endpoint(
    body: ExtractStrengthsRequest,
    user: dict = Depends(get_current_user),  # noqa: B008
) -> dict:
    """Extract top CliftonStrengths themes from arbitrary document text.

    Stateless — input is not persisted. Returns a JSON object with `strengths` and `summary`.
    """
    from profile_agent.services.strengths_extraction_service import (
        StrengthsExtractionError,
        extract_strengths,
    )

    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text must not be empty")
    if len(body.text) > _MAX_TEXT_LEN:
        raise HTTPException(status_code=413, detail="text exceeds maximum allowed length")

    from profile_agent.config.context import hash_user_id, user_id_var
    from profile_agent.config.events import timed_event
    user_id_var.set(hash_user_id(user.get("user_id") or user.get("email", "")))

    with timed_event("extract_strengths.completed", text_len=len(text)) as ev:
        try:
            result = await extract_strengths(text)
        except StrengthsExtractionError:
            logger.exception("strengths extraction failed | text_len=%d", len(text))
            raise HTTPException(status_code=500, detail="Failed to extract strengths") from None
        except Exception:
            logger.exception("unexpected error in strengths extraction | text_len=%d", len(text))
            raise HTTPException(status_code=500, detail="Failed to extract strengths") from None
        ev["strengths_count"] = len(result.get("strengths", []))
        return result
