"""Profile store facade — returns the configured implementation."""

from __future__ import annotations

from profile_agent.config.settings import Settings
from profile_agent.memory.base import ProfileStore


async def create_profile_store(settings: Settings) -> ProfileStore:
    if settings.is_dev:
        from profile_agent.memory.implementations.sqlite_store import SQLiteProfileStore

        return SQLiteProfileStore()
    else:
        from azure.cosmos.aio import CosmosClient

        from profile_agent.config.settings import get_azure_credential
        from profile_agent.memory.implementations.cosmos_store import CosmosProfileStore

        credential = await get_azure_credential(settings)
        client = CosmosClient(url=settings.cosmos_endpoint, credential=credential)
        return CosmosProfileStore(client, settings.cosmos_database_name)
