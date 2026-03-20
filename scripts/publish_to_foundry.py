"""Publish agent to Azure AI Foundry.

Usage:
    python -m profile_agent.scripts.publish_to_foundry --endpoint <endpoint> --image <image>
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


async def publish(endpoint: str, image: str) -> None:
    from azure.ai.projects.aio import AIProjectClient
    from azure.identity.aio import DefaultAzureCredential

    async with DefaultAzureCredential() as credential:
        client = AIProjectClient(endpoint=endpoint, credential=credential)

        # Check if agent exists
        agent_name = "profile-interview-agent"
        try:
            existing = await client.agents.get_agent(agent_name)
            logger.info("Updating existing agent: %s (id=%s)", existing.name, existing.id)
            # Update agent with new image
            await client.agents.update_agent(
                assistant_id=existing.id,
                name=agent_name,
                instructions="Profile interview agent",
                model="gpt-4o",
            )
            logger.info("Agent updated successfully")
        except Exception:
            logger.info("Creating new agent: %s", agent_name)
            agent = await client.agents.create_agent(
                model="gpt-4o",
                name=agent_name,
                instructions="Profile interview agent",
            )
            logger.info("Agent created: %s (id=%s)", agent.name, agent.id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish agent to Foundry")
    parser.add_argument("--endpoint", required=True, help="Foundry project endpoint")
    parser.add_argument("--image", required=True, help="Container image reference")
    args = parser.parse_args()

    asyncio.run(publish(args.endpoint, args.image))


if __name__ == "__main__":
    main()
