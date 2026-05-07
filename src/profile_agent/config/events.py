"""Wide-event helper — emit one structured log per unit-of-work.

Schema (every event):
  event_name      str   required — dot-separated, e.g. "regenerate.completed"
  event_version   int   required — bump when attribute set changes
  outcome         str   "ok" | "error" | "rate_limited" | "timeout" (recommended)
  duration_ms     int   for timed operations (recommended)
  ...             additional structured attributes

Per-request context (request_id, session_id, client_id, user_id, trace_id,
span_id) is added automatically by the LogRecord factory.

Use sparingly: one event per top-level request or major state transition.
Don't call inside tight loops or per-token streams.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any

from profile_agent.config.version import get_app_git_tag, get_app_version

_logger = logging.getLogger("profile_agent.events")

EVENT_VERSION = 1
_APP_VERSION = get_app_version()
_APP_GIT_TAG = get_app_git_tag()


def wide_event(
    event_name: str,
    *,
    outcome: str = "ok",
    level: int = logging.INFO,
    **attrs: Any,
) -> None:
    """Emit a structured wide event.

    Every event automatically carries ``app_version`` (and ``app_git_tag`` when
    set) so logs, errors and metrics can be correlated to a specific deploy.

    Example:
        wide_event(
            "regenerate.completed",
            outcome="ok",
            duration_ms=int((time.perf_counter() - t0) * 1000),
            num_stages=len(completed),
            include_image=body.includeImage,
            image_outcome="ok",
        )
    """
    extra: dict[str, Any] = {
        "event_name": event_name,
        "event_version": EVENT_VERSION,
        "outcome": outcome,
        "app_version": _APP_VERSION,
    }
    if _APP_GIT_TAG:
        extra["app_git_tag"] = _APP_GIT_TAG
    for k, v in attrs.items():
        # Cap large strings to keep ingestion cost bounded.
        if isinstance(v, str) and len(v) > 2048:
            extra[k] = v[:2048] + "…[truncated]"
        else:
            extra[k] = v

    _logger.log(level, event_name, extra=extra)


@contextmanager
def timed_event(event_name: str, **base_attrs: Any):
    """Context manager: emits one event on exit with duration_ms + outcome.

    Usage:
        with timed_event("regenerate.completed", num_stages=n) as ev:
            ...
            ev["image_outcome"] = "ok"   # add fields as you go
    """
    t0 = time.perf_counter()
    extras: dict[str, Any] = dict(base_attrs)
    try:
        yield extras
    except Exception as exc:
        extras.setdefault("error_type", type(exc).__name__)
        extras.setdefault("error_message", str(exc)[:500])
        wide_event(
            event_name,
            outcome="error",
            level=logging.ERROR,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            **extras,
        )
        raise
    else:
        wide_event(
            event_name,
            outcome=extras.pop("outcome", "ok"),
            duration_ms=int((time.perf_counter() - t0) * 1000),
            **extras,
        )
