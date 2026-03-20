"""Tests for the SQLite persistence implementations."""

import pytest
import pytest_asyncio
import tempfile
from pathlib import Path

from profile_agent.memory.implementations.sqlite_store import (
    SQLiteSessionStore,
    SQLiteTranscriptStore,
    SQLiteProfileStore,
    SQLiteAssetStore,
)
from profile_agent.models.conversation import Message, Role, Transcript
from profile_agent.models.skill_matrix import SkillMatrix, SkillScore, Confidence
from profile_agent.models.evidence import EvidenceRecord


@pytest_asyncio.fixture
async def db_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield str(Path(tmpdir) / "test.db")


@pytest.mark.asyncio
class TestSQLiteSessionStore:
    async def test_create_and_get_session(self, db_path):
        store = SQLiteSessionStore(db_path)

        session = await store.create_session("s1", "user1")
        assert session.session_id == "s1"

        retrieved = await store.get_session("s1")
        assert retrieved is not None
        assert retrieved.session_id == "s1"

    async def test_list_sessions(self, db_path):
        store = SQLiteSessionStore(db_path)

        await store.create_session("s1", "user1")
        await store.create_session("s2", "user1")
        await store.create_session("s3", "user2")

        user1_sessions = await store.list_sessions("user1")
        assert len(user1_sessions) == 2


@pytest.mark.asyncio
class TestSQLiteTranscriptStore:
    async def test_save_and_load_transcript(self, db_path):
        store = SQLiteTranscriptStore(db_path)

        t = Transcript(session_id="s1")
        t.append_turn(
            Message(role=Role.USER, content="hi"),
            Message(role=Role.ASSISTANT, content="hello"),
            "intro",
        )

        await store.save_transcript(t)
        loaded = await store.get_transcript("s1")
        assert loaded is not None
        assert loaded.turn_count == 1


@pytest.mark.asyncio
class TestSQLiteProfileStore:
    async def test_save_and_get_evidence(self, db_path):
        store = SQLiteProfileStore(db_path)

        record = EvidenceRecord(
            session_id="s1",
            stage_id="heroes",
            category="technical",
            content="Expert in Python",
            confidence="high",
        )
        await store.save_evidence(record)

        evidence = await store.get_evidence("s1")
        assert len(evidence) == 1
        assert evidence[0].content == "Expert in Python"

    async def test_save_and_get_skill_matrix(self, db_path):
        store = SQLiteProfileStore(db_path)

        matrix = SkillMatrix(session_id="s1")
        matrix.update_dimension(
            name="application_development",
            score=SkillScore.STRONG,
            confidence=Confidence.HIGH,
            evidence="Built apps",
        )

        await store.save_skill_matrix(matrix)
        loaded = await store.get_skill_matrix("s1")
        assert loaded is not None
        assert len(loaded.dimensions) == 1
