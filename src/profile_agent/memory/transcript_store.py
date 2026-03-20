"""Transcript store facade — returns the configured implementation."""

from __future__ import annotations

from profile_agent.config.settings import Settings
from profile_agent.memory.base import TranscriptStore


async def create_transcript_store(settings: Settings) -> TranscriptStore:
    if settings.is_dev:
        from profile_agent.memory.implementations.sqlite_store import SQLiteTranscriptStore

        return SQLiteTranscriptStore()
    else:
        from azure.cosmos.aio import CosmosClient

        from profile_agent.config.settings import get_azure_credential
        from profile_agent.memory.implementations.cosmos_store import CosmosTranscriptStore

        credential = await get_azure_credential(settings)
        client = CosmosClient(url=settings.cosmos_endpoint, credential=credential)
        return CosmosTranscriptStore(client, settings.cosmos_database_name)
