"""Main entrypoint — starts the Profile Agent in the configured mode."""

from __future__ import annotations

import logging
import os
import sys

from dotenv import load_dotenv


def main() -> None:
    load_dotenv(override=False)

    from profile_agent.config.settings import get_settings
    from profile_agent.config.logging import configure_logging

    settings = get_settings()
    configure_logging(settings)
    logger = logging.getLogger(__name__)

    logger.info("Profile Agent starting — environment=%s, mode=%s", settings.environment.value, settings.run_mode.value)

    # Initialize telemetry early
    try:
        from profile_agent.config.telemetry import configure_telemetry
        configure_telemetry(connection_string=settings.appinsights_connection_string or None)
        logger.info("Telemetry initialized")
    except Exception as e:
        logger.warning("Telemetry setup skipped: %s", e)

    if settings.run_mode.value == "foundry":
        # Foundry hosting adapter mode — HTTP server on port 8088
        logger.info("Starting in Foundry adapter mode")
        from profile_agent.agents.foundry_adapter import run_foundry_server
        run_foundry_server()

    elif settings.run_mode.value == "web":
        # Web mode — FastAPI + Chainlit
        logger.info("Starting in Web mode (FastAPI + Chainlit)")
        import uvicorn
        from profile_agent.api import create_fastapi_app

        app = create_fastapi_app()
        uvicorn.run(
            app,
            host=settings.host,
            port=settings.web_port,
            log_level="info",
        )
    else:
        logger.error("Unknown RUN_MODE: %s", settings.run_mode.value)
        sys.exit(1)


if __name__ == "__main__":
    main()
