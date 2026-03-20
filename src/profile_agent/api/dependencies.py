"""Dependency injection for API layer — lazy service instantiation."""

from __future__ import annotations

from functools import lru_cache

from profile_agent.config.settings import get_settings


@lru_cache
def get_session_service():
    from profile_agent.memory.implementations.sqlite_store import SQLiteSessionStore
    from profile_agent.services.session_service import SessionService

    settings = get_settings()
    if not settings.is_dev:
        raise RuntimeError("get_session_service() sync factory only supports dev/SQLite mode")
    return SessionService(SQLiteSessionStore())


@lru_cache
def get_asset_service():
    from profile_agent.memory.implementations.sqlite_store import SQLiteAssetStore
    from profile_agent.services.asset_service import AssetService

    settings = get_settings()
    if not settings.is_dev:
        raise RuntimeError("get_asset_service() sync factory only supports dev/SQLite mode")
    return AssetService(SQLiteAssetStore())
