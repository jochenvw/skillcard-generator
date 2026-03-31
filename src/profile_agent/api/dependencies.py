"""Dependency injection for API layer — lazy service instantiation."""

from __future__ import annotations

import logging
from functools import lru_cache

from profile_agent.config.settings import get_settings

logger = logging.getLogger(__name__)


def _try_cosmos_session_store():
    """Attempt to create a Cosmos session store. Returns None on failure."""
    try:
        from azure.cosmos.aio import CosmosClient
        from profile_agent.memory.implementations.cosmos_store import CosmosSessionStore
        from profile_agent.config.settings import get_azure_credential
        import asyncio

        settings = get_settings()
        credential = asyncio.get_event_loop().run_until_complete(get_azure_credential(settings))
        client = CosmosClient(settings.cosmos_endpoint, credential=credential)
        return CosmosSessionStore(client, settings.cosmos_database_name)
    except Exception as e:
        logger.warning("Cosmos session store unavailable, falling back to SQLite: %s", e)
        return None


@lru_cache
def get_session_service():
    from profile_agent.services.session_service import SessionService
    from profile_agent.memory.implementations.sqlite_store import SQLiteSessionStore

    settings = get_settings()
    if settings.cosmos_endpoint:
        store = _try_cosmos_session_store()
        if store:
            return SessionService(store)

    return SessionService(SQLiteSessionStore())


@lru_cache
def get_asset_service():
    from profile_agent.services.asset_service import AssetService
    from profile_agent.memory.implementations.sqlite_store import SQLiteAssetStore

    return AssetService(SQLiteAssetStore())
