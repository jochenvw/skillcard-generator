"""Foundry hosting adapter — wraps InterviewAgent for Foundry deployment."""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def create_foundry_server():
    """Create and return the Foundry hosting adapter server.

    Uses azure-ai-agentserver-agentframework to wrap the InterviewAgent
    as an HTTP server on port 8088, compatible with Foundry's Responses API.
    """
    load_dotenv(override=False)

    from azure_ai_agentserver_agentframework import from_agent_framework

    from profile_agent.agents.interview_agent import InterviewAgent

    agent = InterviewAgent(name="profile-interview-agent")
    server = from_agent_framework(agent)
    return server


def run_foundry_server() -> None:
    """Start the Foundry hosting adapter HTTP server (default entrypoint for Foundry)."""
    server = create_foundry_server()
    port = int(os.getenv("PORT", "8088"))
    logger.info("Starting Foundry hosting adapter on port %d", port)
    server.run(port=port)
