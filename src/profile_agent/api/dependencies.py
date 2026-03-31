"""Dependency injection for API layer — lazy service instantiation."""

from __future__ import annotations

from functools import lru_cache

from profile_agent.config.settings import get_settings


@lru_cache
def get_session_service():
    from profile_agent.services.session_service import SessionService

    settings = get_settings()
    if settings.cosmos_endpoint:
        from profile_agent.memory.implementations.cosmos_store import CosmosSessionStore
        return SessionService(CosmosSessionStore(settings.cosmos_endpoint))
    else:
        from profile_agent.memory.implementations.sqlite_store import SQLiteSessionStore
        return SessionService(SQLiteSessionStore())


@lru_cache
def get_asset_service():
    from profile_agent.services.asset_service import AssetService

    settings = get_settings()
    if settings.azure_storage_account_url:
        from profile_agent.memory.implementations.blob_store import BlobAssetStore
        return AssetService(BlobAssetStore(settings.azure_storage_account_url))
    else:
        from profile_agent.memory.implementations.sqlite_store import SQLiteAssetStore
        return AssetService(SQLiteAssetStore())
