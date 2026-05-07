"""Per-request context — request_id, session_id, client_id, user_id.

These flow through `contextvars` so any log emitted inside a request handler is
auto-enriched without explicit threading. Reset in middleware `finally`.
"""

from __future__ import annotations

import hashlib
import uuid
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="")
session_id_var: ContextVar[str] = ContextVar("session_id", default="")
client_id_var: ContextVar[str] = ContextVar("client_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")


def new_request_id() -> str:
    return uuid.uuid4().hex


def hash_user_id(raw: str) -> str:
    """Stable, opaque user identifier — never log raw email/UPN/oid."""
    if not raw:
        return ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def context_snapshot() -> dict[str, str]:
    """Return current contextvars as a plain dict (omitting empties)."""
    return {
        k: v
        for k, v in {
            "request_id": request_id_var.get(),
            "session_id": session_id_var.get(),
            "client_id": client_id_var.get(),
            "user_id": user_id_var.get(),
        }.items()
        if v
    }
