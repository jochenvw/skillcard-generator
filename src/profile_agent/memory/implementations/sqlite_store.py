"""SQLite implementation of persistence stores — used for local development."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import aiosqlite

from profile_agent.memory.base import AssetStore, ProfileStore, SessionStore, TranscriptStore
from profile_agent.models.assets import GeneratedCard, UploadedImage
from profile_agent.models.conversation import Transcript
from profile_agent.models.evidence import EvidenceRecord, ProfileSignal
from profile_agent.models.llm_contracts import GuidedCompressionResult, SessionSnapshot
from profile_agent.models.profile import UserProfile
from profile_agent.models.skill_matrix import SkillMatrix
from profile_agent.models.stage_state import StageState

_DEFAULT_DB = "profile_agent_dev.db"


class SQLiteSessionStore(SessionStore):
    def __init__(self, db_path: str = _DEFAULT_DB) -> None:
        self._db_path = db_path

    async def _ensure_tables(self, db: aiosqlite.Connection) -> None:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS stage_states (
                session_id TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )
        """)
        await db.commit()

    async def create_session(self, session_id: str, user_id: str) -> SessionSnapshot:
        snap = SessionSnapshot(session_id=session_id, user_id=user_id)
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_tables(db)
            await db.execute(
                "INSERT OR REPLACE INTO sessions (session_id, data) VALUES (?, ?)",
                (session_id, snap.model_dump_json()),
            )
            await db.commit()
        return snap

    async def get_session(self, session_id: str) -> SessionSnapshot | None:
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_tables(db)
            async with db.execute("SELECT data FROM sessions WHERE session_id = ?", (session_id,)) as cur:
                row = await cur.fetchone()
                return SessionSnapshot.model_validate_json(row[0]) if row else None

    async def update_session(self, snapshot: SessionSnapshot) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_tables(db)
            await db.execute(
                "INSERT OR REPLACE INTO sessions (session_id, data) VALUES (?, ?)",
                (snapshot.session_id, snapshot.model_dump_json()),
            )
            await db.commit()

    async def list_sessions(self, user_id: str) -> list[SessionSnapshot]:
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_tables(db)
            async with db.execute("SELECT data FROM sessions") as cur:
                rows = await cur.fetchall()
                results = []
                for row in rows:
                    snap = SessionSnapshot.model_validate_json(row[0])
                    if snap.user_id == user_id:
                        results.append(snap)
                return results

    async def delete_session(self, session_id: str) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_tables(db)
            await db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            await db.execute("DELETE FROM stage_states WHERE session_id = ?", (session_id,))
            await db.commit()

    async def save_stage_state(self, state: StageState) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_tables(db)
            await db.execute(
                "INSERT OR REPLACE INTO stage_states (session_id, data) VALUES (?, ?)",
                (state.session_id, state.model_dump_json()),
            )
            await db.commit()

    async def get_stage_state(self, session_id: str) -> StageState | None:
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_tables(db)
            async with db.execute("SELECT data FROM stage_states WHERE session_id = ?", (session_id,)) as cur:
                row = await cur.fetchone()
                return StageState.model_validate_json(row[0]) if row else None


class SQLiteTranscriptStore(TranscriptStore):
    def __init__(self, db_path: str = _DEFAULT_DB) -> None:
        self._db_path = db_path

    async def _ensure_tables(self, db: aiosqlite.Connection) -> None:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transcripts (
                session_id TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS stage_summaries (
                session_id TEXT NOT NULL,
                stage_id TEXT NOT NULL,
                data TEXT NOT NULL,
                PRIMARY KEY (session_id, stage_id)
            )
        """)
        await db.commit()

    async def save_transcript(self, transcript: Transcript) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_tables(db)
            await db.execute(
                "INSERT OR REPLACE INTO transcripts (session_id, data) VALUES (?, ?)",
                (transcript.session_id, transcript.model_dump_json()),
            )
            await db.commit()

    async def get_transcript(self, session_id: str) -> Transcript | None:
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_tables(db)
            async with db.execute("SELECT data FROM transcripts WHERE session_id = ?", (session_id,)) as cur:
                row = await cur.fetchone()
                return Transcript.model_validate_json(row[0]) if row else None

    async def save_stage_summary(self, session_id: str, stage_id: str, summary: GuidedCompressionResult) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_tables(db)
            await db.execute(
                "INSERT OR REPLACE INTO stage_summaries (session_id, stage_id, data) VALUES (?, ?, ?)",
                (session_id, stage_id, summary.model_dump_json()),
            )
            await db.commit()

    async def get_stage_summary(self, session_id: str, stage_id: str) -> GuidedCompressionResult | None:
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_tables(db)
            async with db.execute(
                "SELECT data FROM stage_summaries WHERE session_id = ? AND stage_id = ?",
                (session_id, stage_id),
            ) as cur:
                row = await cur.fetchone()
                return GuidedCompressionResult.model_validate_json(row[0]) if row else None


class SQLiteProfileStore(ProfileStore):
    def __init__(self, db_path: str = _DEFAULT_DB) -> None:
        self._db_path = db_path

    async def _ensure_tables(self, db: aiosqlite.Connection) -> None:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                session_id TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS skill_matrices (
                session_id TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS evidence (
                evidence_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                data TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                data TEXT NOT NULL
            )
        """)
        await db.commit()

    async def save_profile(self, profile: UserProfile) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_tables(db)
            await db.execute(
                "INSERT OR REPLACE INTO profiles (session_id, data) VALUES (?, ?)",
                (profile.session_id, profile.model_dump_json()),
            )
            await db.commit()

    async def get_profile(self, session_id: str) -> UserProfile | None:
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_tables(db)
            async with db.execute("SELECT data FROM profiles WHERE session_id = ?", (session_id,)) as cur:
                row = await cur.fetchone()
                return UserProfile.model_validate_json(row[0]) if row else None

    async def save_skill_matrix(self, matrix: SkillMatrix) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_tables(db)
            await db.execute(
                "INSERT OR REPLACE INTO skill_matrices (session_id, data) VALUES (?, ?)",
                (matrix.session_id, matrix.model_dump_json()),
            )
            await db.commit()

    async def get_skill_matrix(self, session_id: str) -> SkillMatrix | None:
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_tables(db)
            async with db.execute("SELECT data FROM skill_matrices WHERE session_id = ?", (session_id,)) as cur:
                row = await cur.fetchone()
                return SkillMatrix.model_validate_json(row[0]) if row else None

    async def save_evidence(self, record: EvidenceRecord) -> None:
        if not record.evidence_id:
            record.evidence_id = str(uuid.uuid4())
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_tables(db)
            await db.execute(
                "INSERT OR REPLACE INTO evidence (evidence_id, session_id, data) VALUES (?, ?, ?)",
                (record.evidence_id, record.session_id, record.model_dump_json()),
            )
            await db.commit()

    async def get_evidence(self, session_id: str) -> list[EvidenceRecord]:
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_tables(db)
            async with db.execute("SELECT data FROM evidence WHERE session_id = ?", (session_id,)) as cur:
                rows = await cur.fetchall()
                return [EvidenceRecord.model_validate_json(r[0]) for r in rows]

    async def save_signal(self, signal: ProfileSignal) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_tables(db)
            await db.execute(
                "INSERT INTO signals (session_id, data) VALUES (?, ?)",
                (signal.session_id, signal.model_dump_json()),
            )
            await db.commit()

    async def get_signals(self, session_id: str) -> list[ProfileSignal]:
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_tables(db)
            async with db.execute("SELECT data FROM signals WHERE session_id = ?", (session_id,)) as cur:
                rows = await cur.fetchall()
                return [ProfileSignal.model_validate_json(r[0]) for r in rows]


class SQLiteAssetStore(AssetStore):
    """Local filesystem-based asset storage for dev — mimics blob interface."""

    def __init__(self, db_path: str = _DEFAULT_DB, assets_dir: str = "local_assets") -> None:
        self._db_path = db_path
        self._assets_dir = Path(assets_dir)
        self._assets_dir.mkdir(parents=True, exist_ok=True)

    async def _ensure_tables(self, db: aiosqlite.Connection) -> None:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS assets (
                asset_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                data TEXT NOT NULL
            )
        """)
        await db.commit()

    async def upload_image(self, session_id: str, filename: str, data: bytes, content_type: str) -> UploadedImage:
        asset_id = str(uuid.uuid4())
        blob_path = f"{session_id}/uploads/{asset_id}_{filename}"
        local_path = self._assets_dir / blob_path.replace("/", "_")
        local_path.write_bytes(data)

        img = UploadedImage(
            asset_id=asset_id,
            session_id=session_id,
            blob_path=blob_path,
            blob_url=str(local_path),
            content_type=content_type,
            size_bytes=len(data),
            original_filename=filename,
        )
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_tables(db)
            await db.execute(
                "INSERT OR REPLACE INTO assets (asset_id, session_id, asset_type, data) VALUES (?, ?, ?, ?)",
                (asset_id, session_id, "uploaded_image", img.model_dump_json()),
            )
            await db.commit()
        return img

    async def save_generated_card(
        self, session_id: str, image_data: bytes, content_type: str, metadata: dict[str, Any]
    ) -> GeneratedCard:
        asset_id = str(uuid.uuid4())
        blob_path = f"{session_id}/cards/{asset_id}.png"
        local_path = self._assets_dir / blob_path.replace("/", "_")
        local_path.write_bytes(image_data)

        card = GeneratedCard(
            asset_id=asset_id,
            session_id=session_id,
            blob_path=blob_path,
            blob_url=str(local_path),
            content_type=content_type,
            size_bytes=len(image_data),
            prompt_used=metadata.get("prompt_used", ""),
            model_deployment=metadata.get("model_deployment", ""),
        )
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_tables(db)
            await db.execute(
                "INSERT OR REPLACE INTO assets (asset_id, session_id, asset_type, data) VALUES (?, ?, ?, ?)",
                (asset_id, session_id, "generated_card", card.model_dump_json()),
            )
            await db.commit()
        return card

    async def get_uploaded_image(self, session_id: str) -> UploadedImage | None:
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_tables(db)
            async with db.execute(
                "SELECT data FROM assets WHERE session_id = ? AND asset_type = 'uploaded_image' ORDER BY rowid DESC LIMIT 1",
                (session_id,),
            ) as cur:
                row = await cur.fetchone()
                return UploadedImage.model_validate_json(row[0]) if row else None

    async def get_generated_card(self, session_id: str) -> GeneratedCard | None:
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_tables(db)
            async with db.execute(
                "SELECT data FROM assets WHERE session_id = ? AND asset_type = 'generated_card' ORDER BY rowid DESC LIMIT 1",
                (session_id,),
            ) as cur:
                row = await cur.fetchone()
                return GeneratedCard.model_validate_json(row[0]) if row else None

    async def download_asset(self, blob_path: str) -> bytes:
        local_path = self._assets_dir / blob_path.replace("/", "_")
        return local_path.read_bytes()
