"""Public telemetry config endpoint — exposes App Insights connection string to the SPA.

The connection string is browser-safe: the App Insights JS SDK is designed to be
loaded client-side and the ingestion endpoint accepts the key as a routing token,
not a secret. Treating it as a public config value is the standard pattern.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response, status

from profile_agent.config.events import wide_event
from profile_agent.config.settings import Settings, get_settings
from profile_agent.config.version import get_app_git_tag, get_app_version

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


@router.get("/config")
async def telemetry_config(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Return App Insights config for the SPA. Empty connectionString disables client telemetry."""
    return {
        "connectionString": settings.appinsights_connection_string or "",
        "roleName": "profile-agent-frontend",
        "environment": settings.environment.value,
        "appVersion": get_app_version(),
        "appGitTag": get_app_git_tag(),
    }


@router.post("/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
async def heartbeat() -> Response:
    """Per-tab heartbeat ping used to compute concurrent active users.

    The frontend posts every ~30s while the tab is visible. We emit a
    ``session.heartbeat`` wide event carrying the request-context client_id /
    session_id / user_id (set by RequestContextMiddleware from request headers)
    so KQL can dcount() distinct callers per bin to estimate concurrency.
    """
    wide_event("session.heartbeat")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

