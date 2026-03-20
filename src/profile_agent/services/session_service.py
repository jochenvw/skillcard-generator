"""Session service — session lifecycle management."""

from __future__ import annotations

import logging
import uuid

from profile_agent.memory.base import SessionStore
from profile_agent.models.llm_contracts import SessionSnapshot

logger = logging.getLogger(__name__)


class SessionService:
    """Manages session creation, resumption, and listing."""

    def __init__(self, session_store: SessionStore) -> None:
        self._store = session_store

    async def create_session(self, user_id: str) -> SessionSnapshot:
        session_id = str(uuid.uuid4())
        snapshot = await self._store.create_session(session_id, user_id)
        logger.info("Created session %s for user %s", session_id, user_id)
        return snapshot

    async def get_session(self, session_id: str) -> SessionSnapshot | None:
        return await self._store.get_session(session_id)

    async def list_sessions(self, user_id: str) -> list[SessionSnapshot]:
        return await self._store.list_sessions(user_id)

    async def delete_session(self, session_id: str) -> None:
        await self._store.delete_session(session_id)
        logger.info("Deleted session %s", session_id)

    async def update_session(self, snapshot: SessionSnapshot) -> None:
        await self._store.update_session(snapshot)
