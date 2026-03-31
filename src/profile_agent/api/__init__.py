"""FastAPI application factory — mounts Chainlit, auth, API routes, health."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from profile_agent.config.settings import get_settings

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
        allow_headers=["*"],
    )

    # Health / readiness
    from profile_agent.api.health import router as health_router
    app.include_router(health_router)

    # Session management API
    from profile_agent.api.sessions import router as sessions_router
    app.include_router(sessions_router, prefix="/api")

    # Upload API
    from profile_agent.api.uploads import router as uploads_router
    app.include_router(uploads_router, prefix="/api")

    # Stateless streaming chat API (AI SDK Data Stream Protocol)
    from profile_agent.api.chat import router as chat_router
    app.include_router(chat_router, prefix="/api")

    # Legacy stateful chat API (kept for backward compatibility)
    from profile_agent.api.chat_legacy import router as chat_legacy_router
    app.include_router(chat_legacy_router, prefix="/api")

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
