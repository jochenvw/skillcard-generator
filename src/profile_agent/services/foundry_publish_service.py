"""Foundry publish service — thin wrapper for publishing agent to Foundry."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class FoundryPublishService:
    """Wraps Foundry agent publishing operations.

    This isolates Foundry SDK calls so future API changes are contained.
    Actual deployment is typically done via CLI or the publish_to_foundry.py script.
    """

    def __init__(self, project_endpoint: str) -> None:
        self._endpoint = project_endpoint

    async def get_agent_status(self, agent_name: str) -> dict | None:
        """Check if an agent exists and its current status."""
        try:
            from azure.ai.projects.aio import AIProjectClient
            from azure.identity.aio import DefaultAzureCredential

            async with DefaultAzureCredential() as credential:
                client = AIProjectClient(endpoint=self._endpoint, credential=credential)
                agent = await client.agents.get_agent(agent_name)
                return {"name": agent.name, "model": agent.model, "id": agent.id}
        except Exception as e:
            logger.warning("Could not get agent status for %s: %s", agent_name, e)
            return None

    # TODO: Add create/update agent methods as Foundry SDK stabilizes.
    # The publish_to_foundry.py script handles the full build → push → deploy pipeline.
