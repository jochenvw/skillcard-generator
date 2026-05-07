"""Health check endpoints for container orchestration."""

from __future__ import annotations

from fastapi import APIRouter

from profile_agent.config.version import get_app_git_tag, get_app_version

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {
        "status": "healthy",
        "version": get_app_version(),
        "git_tag": get_app_git_tag(),
    }


@router.get("/readiness")
async def readiness():
    return {"status": "ready", "version": get_app_version()}
