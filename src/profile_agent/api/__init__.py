"""FastAPI application factory — mounts Chainlit, auth, API routes, health."""

from __future__ import annotations

import logging

import mimetypes

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from profile_agent.config.settings import get_settings

# Ensure .mjs is served as JavaScript so browsers will accept it as an ES module
# (default Python mimetypes returns text/plain, which browsers reject for `import`).
mimetypes.add_type("text/javascript", ".mjs")

logger = logging.getLogger(__name__)


def create_fastapi_app() -> FastAPI:
    """Build and configure the FastAPI app."""
    settings = get_settings()

    app = FastAPI(
        title="Profile Agent",
        version="0.1.0",
        docs_url="/api/docs" if settings.run_mode == "web" else None,
    )

    # CORS — restrict in production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins if hasattr(settings, "cors_origins") else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=[
            "*",
            "X-Request-Id",
            "X-Session-Id",
            "X-Client-Id",
            "traceparent",
            "tracestate",
        ],
        expose_headers=["X-Request-Id"],
    )

    # Per-request context (request_id, session_id, client_id)
    from profile_agent.api.middleware import RequestContextMiddleware
    app.add_middleware(RequestContextMiddleware)

    # Health / readiness
    from profile_agent.api.health import router as health_router
    app.include_router(health_router)

    # Stateless streaming chat API (AI SDK Data Stream Protocol)
    from profile_agent.api.chat import router as chat_router
    app.include_router(chat_router, prefix="/api")

    # CliftonStrengths extraction API (stateless)
    from profile_agent.api.strengths import router as strengths_router
    app.include_router(strengths_router, prefix="/api")

    # LinkedIn + GitHub profile extraction API (stateless)
    from profile_agent.api.profiles import router as profiles_router
    app.include_router(profiles_router, prefix="/api")

    # Demo card endpoint (returns pre-baked persona + generated image)
    from profile_agent.api.demo import router as demo_router
    app.include_router(demo_router, prefix="/api")

    # Regenerate card from existing session state (no interview re-run)
    from profile_agent.api.regenerate import router as regenerate_router
    app.include_router(regenerate_router, prefix="/api")

    # Auth config endpoint (public — returns client ID / tenant for SPA)
    from profile_agent.api.auth import router as auth_router
    app.include_router(auth_router)

    # Telemetry config endpoint (public — returns App Insights connection string for SPA)
    from profile_agent.api.telemetry import router as telemetry_router
    app.include_router(telemetry_router)

    # OpenTelemetry auto-instrumentation (FastAPI + httpx)
    try:
        from profile_agent.config.telemetry import instrument_app
        instrument_app(app)
    except Exception as e:  # noqa: BLE001
        logger.warning("Telemetry instrumentation skipped: %s", e)

    # Serve React frontend (built static files)
    import os
    from pathlib import Path

    # Check multiple possible locations for frontend dist
    frontend_dist = None
    candidates = [
        Path(os.environ.get("FRONTEND_DIST", "")) if os.environ.get("FRONTEND_DIST") else None,
        Path("/app/frontend/dist"),
        Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "dist",
    ]
    for candidate in candidates:
        if candidate and candidate.exists() and (candidate / "index.html").exists():
            frontend_dist = candidate
            break

    if frontend_dist:
        from starlette.staticfiles import StaticFiles
        from starlette.responses import FileResponse

        # Serve static assets (JS, CSS, etc.)
        app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="frontend-assets")

        # SPA fallback — serve index.html for all non-API routes
        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str):
            # Serve actual files if they exist, otherwise index.html
            file_path = frontend_dist / full_path
            if full_path and file_path.exists() and file_path.is_file():
                return FileResponse(str(file_path))
            return FileResponse(str(frontend_dist / "index.html"))

        logger.info("Serving React frontend from %s", frontend_dist)
    else:
        logger.info("No frontend build found at %s — skipping static file serving", frontend_dist)

    logger.info("FastAPI app configured (mode=%s)", settings.run_mode)
    return app
