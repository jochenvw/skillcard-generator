"""Health check endpoints for container orchestration."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "healthy"}


@router.get("/readiness")
async def readiness():
    return {"status": "ready"}
