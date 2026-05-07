"""Public telemetry config endpoint — exposes App Insights connection string to the SPA.

The connection string is browser-safe: the App Insights JS SDK is designed to be
loaded client-side and the ingestion endpoint accepts the key as a routing token,
not a secret. Treating it as a public config value is the standard pattern.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from profile_agent.config.settings import Settings, get_settings

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


@router.get("/config")
async def telemetry_config(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Return App Insights config for the SPA. Empty connectionString disables client telemetry."""
    return {
        "connectionString": settings.appinsights_connection_string or "",
        "roleName": "profile-agent-frontend",
        "environment": settings.environment.value,
    }
