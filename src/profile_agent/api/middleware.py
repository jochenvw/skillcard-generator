"""ASGI middleware that binds per-request context (request_id, session_id, client_id).

Headers consumed (all optional — generated/empty if absent):
  X-Request-Id   — echoed back in response, also exposed via CORS expose-headers
  X-Session-Id   — opaque client-supplied UUID for this user session
  X-Client-Id    — stable per-browser UUID (localStorage)

W3C `traceparent` is handled by FastAPIInstrumentor (OTel auto-instrumentation),
so trace_id correlation flows through that — we don't touch it here.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from profile_agent.config.context import (
    client_id_var,
    new_request_id,
    request_id_var,
    session_id_var,
)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        request_id = request.headers.get("x-request-id") or new_request_id()
        session_id = request.headers.get("x-session-id", "")
        client_id = request.headers.get("x-client-id", "")

        rid_token = request_id_var.set(request_id)
        sid_token = session_id_var.set(session_id)
        cid_token = client_id_var.set(client_id)

        try:
            response = await call_next(request)
            response.headers["x-request-id"] = request_id
            return response
        finally:
            request_id_var.reset(rid_token)
            session_id_var.reset(sid_token)
            client_id_var.reset(cid_token)
