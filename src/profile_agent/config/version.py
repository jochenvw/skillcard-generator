"""Single source of truth for the running application version.

Resolution order:
1. ``APP_VERSION`` env var (set by Dockerfile from the GIT_SHA build-arg)
2. ``GIT_SHA`` env var (legacy / shared with the frontend build stage)
3. ``profile_agent.__version__`` from the installed package metadata
4. ``"dev"`` as a final fallback for local non-installed runs

The resolved version is the canonical value used by:
- OTel resource attribute ``service.version`` (set by :mod:`config.telemetry`)
- Every wide event (auto-injected by :func:`config.events.wide_event` as
  ``app_version``)
- The ``/api/health`` endpoint (so deploys can be verified by curl)
"""

from __future__ import annotations

import os
from functools import lru_cache


@lru_cache(maxsize=1)
def get_app_version() -> str:
    for env_key in ("APP_VERSION", "GIT_SHA"):
        v = os.environ.get(env_key)
        if v and v != "dev":
            # Use short SHA for human-readable correlation while keeping the
            # full value available via the env var if needed.
            return v[:12] if len(v) >= 40 else v
    try:
        from importlib.metadata import version

        return version("profile-agent")
    except Exception:  # noqa: BLE001
        return "dev"


@lru_cache(maxsize=1)
def get_app_git_tag() -> str | None:
    """Optional git tag (e.g. v0.1.0) for tagged releases. None for SHA-only deploys."""
    v = os.environ.get("APP_GIT_TAG") or os.environ.get("GIT_TAG")
    return v.strip() if v and v.strip() else None
