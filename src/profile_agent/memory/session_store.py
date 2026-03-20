"""Session store facade — returns the configured implementation."""

from __future__ import annotations

from profile_agent.config.settings import Settings
from profile_agent.memory.base import SessionStore


async def create_session_store(settings: Settings) -> SessionStore:
    if settings.is_dev:
        from profile_agent.memory.implementations.sqlite_store import SQLiteSessionStore

        return SQLiteSessionStore()
    else:
        from azure.cosmos.aio import CosmosClient

        from profile_agent.config.settings import get_azure_credential
        from profile_agent.memory.implementations.cosmos_store import CosmosSessionStore

        credential = await get_azure_credential(settings)
        client = CosmosClient(url=settings.cosmos_endpoint, credential=credential)
        return CosmosSessionStore(client, settings.cosmos_database_name)
