"""Profile extraction endpoints — LinkedIn text + GitHub username analysis."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from profile_agent.api.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["profiles"])

_MAX_TEXT_LEN = 200_000


class ExtractLinkedInRequest(BaseModel):
    text: str | None = Field(default=None, max_length=_MAX_TEXT_LEN)
    url: str | None = Field(default=None, max_length=500)


class ExtractGitHubRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=39)


@router.post("/extract-linkedin")
async def extract_linkedin_endpoint(
    body: ExtractLinkedInRequest,
    user: dict = Depends(get_current_user),  # noqa: B008
) -> dict:
    """Extract professional skills from a LinkedIn URL or pasted profile text."""
    from profile_agent.services.profile_extraction_service import (
        ProfileExtractionError,
        extract_linkedin_skills,
        fetch_linkedin_profile_text,
    )

    text = (body.text or "").strip()
    url = (body.url or "").strip()

    if not text and not url:
        raise HTTPException(status_code=400, detail="Provide either 'text' or 'url'")

    from profile_agent.config.context import hash_user_id, user_id_var
    from profile_agent.config.events import timed_event
    user_id_var.set(hash_user_id(user.get("user_id") or user.get("email", "")))

    with timed_event(
        "extract_linkedin.completed",
        source="url" if url and not body.text else "text",
        url_provided=bool(url),
    ) as ev:
        if url and not text:
            try:
                text = await fetch_linkedin_profile_text(url)
            except ProfileExtractionError as exc:
                ev["fetch_outcome"] = "failed"
                raise HTTPException(status_code=422, detail=str(exc)) from None
            ev["fetch_outcome"] = "ok"

        ev["text_len"] = len(text)
        try:
            result = await extract_linkedin_skills(text)
        except ProfileExtractionError as exc:
            logger.exception("linkedin extraction failed")
            raise HTTPException(status_code=500, detail=str(exc)) from None
        except Exception:
            logger.exception("unexpected error in linkedin extraction")
            raise HTTPException(status_code=500, detail="Failed to extract LinkedIn skills") from None

        ev["skills_count"] = len(result.get("skills", []))
        return result


@router.post("/extract-github")
async def extract_github_endpoint(
    body: ExtractGitHubRequest,
    user: dict = Depends(get_current_user),  # noqa: B008
) -> dict:
    """Analyze a public GitHub profile and extract technical skills."""
    from profile_agent.services.profile_extraction_service import (
        ProfileExtractionError,
        extract_github_skills,
    )

    username = body.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="username must not be empty")

    from profile_agent.config.context import hash_user_id, user_id_var
    from profile_agent.config.events import timed_event
    user_id_var.set(hash_user_id(user.get("user_id") or user.get("email", "")))

    with timed_event("extract_github.completed", github_user=username) as ev:
        try:
            result = await extract_github_skills(username)
        except ProfileExtractionError as exc:
            logger.exception("github extraction failed | username=%s", username)
            raise HTTPException(status_code=422, detail=str(exc)) from None
        except Exception:
            logger.exception("unexpected error in github extraction | username=%s", username)
            raise HTTPException(status_code=500, detail="Failed to extract GitHub skills") from None
        ev["skills_count"] = len(result.get("skills", []))
        return result
