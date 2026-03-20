"""Cosmos DB NoSQL implementation of persistence stores — used in Azure production.

Cosmos DB NoSQL chosen over Azure SQL because:
- Session/profile data is semi-structured and schema-flexible (nested JSON).
- Natural document model fits evidence lists, skill matrices, and stage summaries.
- Partition-per-session gives efficient single-session reads/writes.
- Serverless tier keeps costs low for bursty interview workloads.
"""

from __future__ import annotations

import uuid
from typing import Any

from azure.cosmos.aio import CosmosClient, ContainerProxy

from profile_agent.memory.base import AssetStore, ProfileStore, SessionStore, TranscriptStore
from profile_agent.models.assets import GeneratedCard, UploadedImage
from profile_agent.models.conversation import Transcript
from profile_agent.models.evidence import EvidenceRecord, ProfileSignal
from profile_agent.models.llm_contracts import GuidedCompressionResult, SessionSnapshot
from profile_agent.models.profile import UserProfile
from profile_agent.models.skill_matrix import SkillMatrix
from profile_agent.models.stage_state import StageState


class _CosmosBase:
    """Shared Cosmos DB helpers."""

    def __init__(self, client: CosmosClient, database_name: str) -> None:
        self._client = client
        self._database_name = database_name

    async def _container(self, name: str) -> ContainerProxy:
        db = self._client.get_database_client(self._database_name)
        return db.get_container_client(name)


class CosmosSessionStore(_CosmosBase, SessionStore):
    async def create_session(self, session_id: str, user_id: str) -> SessionSnapshot:
        snap = SessionSnapshot(session_id=session_id, user_id=user_id)
        container = await self._container("sessions")
        doc = snap.model_dump(mode="json")
        doc["id"] = session_id
        await container.upsert_item(doc)
        return snap

    async def get_session(self, session_id: str) -> SessionSnapshot | None:
        container = await self._container("sessions")
        try:
            doc = await container.read_item(item=session_id, partition_key=session_id)
            return SessionSnapshot.model_validate(doc)
        except Exception:
            return None

    async def update_session(self, snapshot: SessionSnapshot) -> None:
        container = await self._container("sessions")
        doc = snapshot.model_dump(mode="json")
        doc["id"] = snapshot.session_id
        await container.upsert_item(doc)

    async def list_sessions(self, user_id: str) -> list[SessionSnapshot]:
        container = await self._container("sessions")
        query = "SELECT * FROM c WHERE c.user_id = @uid"
        params: list[dict[str, str]] = [{"name": "@uid", "value": user_id}]
        results = []
        async for item in container.query_items(query=query, parameters=params):
            results.append(SessionSnapshot.model_validate(item))
        return results

    async def delete_session(self, session_id: str) -> None:
        container = await self._container("sessions")
        try:
            await container.delete_item(item=session_id, partition_key=session_id)
        except Exception:
            pass
        try:
            await container.delete_item(item=f"stage_state_{session_id}", partition_key=session_id)
        except Exception:
            pass
        try:
            await container.delete_item(item=f"transcript_{session_id}", partition_key=session_id)
        except Exception:
            pass

    async def save_stage_state(self, state: StageState) -> None:
        container = await self._container("sessions")
        doc = state.model_dump(mode="json")
        doc["id"] = f"stage_state_{state.session_id}"
        doc["session_id"] = state.session_id
        await container.upsert_item(doc)

    async def get_stage_state(self, session_id: str) -> StageState | None:
        container = await self._container("sessions")
        try:
            doc = await container.read_item(item=f"stage_state_{session_id}", partition_key=session_id)
            return StageState.model_validate(doc)
        except Exception:
            return None


class CosmosTranscriptStore(_CosmosBase, TranscriptStore):
    async def save_transcript(self, transcript: Transcript) -> None:
        container = await self._container("sessions")
        doc = transcript.model_dump(mode="json")
        doc["id"] = f"transcript_{transcript.session_id}"
        doc["session_id"] = transcript.session_id
        await container.upsert_item(doc)

    async def get_transcript(self, session_id: str) -> Transcript | None:
        container = await self._container("sessions")
        try:
            doc = await container.read_item(item=f"transcript_{session_id}", partition_key=session_id)
            return Transcript.model_validate(doc)
        except Exception:
            return None

    async def save_stage_summary(self, session_id: str, stage_id: str, summary: GuidedCompressionResult) -> None:
        container = await self._container("sessions")
        doc = summary.model_dump(mode="json")
        doc["id"] = f"summary_{session_id}_{stage_id}"
        doc["session_id"] = session_id
        await container.upsert_item(doc)

    async def get_stage_summary(self, session_id: str, stage_id: str) -> GuidedCompressionResult | None:
        container = await self._container("sessions")
        try:
            doc = await container.read_item(item=f"summary_{session_id}_{stage_id}", partition_key=session_id)
            return GuidedCompressionResult.model_validate(doc)
        except Exception:
            return None


class CosmosProfileStore(_CosmosBase, ProfileStore):
    async def save_profile(self, profile: UserProfile) -> None:
        container = await self._container("profiles")
        doc = profile.model_dump(mode="json")
        doc["id"] = profile.session_id
        await container.upsert_item(doc)

    async def get_profile(self, session_id: str) -> UserProfile | None:
        container = await self._container("profiles")
        try:
            doc = await container.read_item(item=session_id, partition_key=session_id)
            return UserProfile.model_validate(doc)
        except Exception:
            return None

    async def save_skill_matrix(self, matrix: SkillMatrix) -> None:
        container = await self._container("profiles")
        doc = matrix.model_dump(mode="json")
        doc["id"] = f"skills_{matrix.session_id}"
        doc["session_id"] = matrix.session_id
        await container.upsert_item(doc)

    async def get_skill_matrix(self, session_id: str) -> SkillMatrix | None:
        container = await self._container("profiles")
        try:
            doc = await container.read_item(item=f"skills_{session_id}", partition_key=session_id)
            return SkillMatrix.model_validate(doc)
        except Exception:
            return None

    async def save_evidence(self, record: EvidenceRecord) -> None:
        if not record.evidence_id:
            record.evidence_id = str(uuid.uuid4())
        container = await self._container("profiles")
        doc = record.model_dump(mode="json")
        doc["id"] = record.evidence_id
        doc["session_id"] = record.session_id
        doc["doc_type"] = "evidence"
        await container.upsert_item(doc)

    async def get_evidence(self, session_id: str) -> list[EvidenceRecord]:
        container = await self._container("profiles")
        query = "SELECT * FROM c WHERE c.session_id = @sid AND c.doc_type = 'evidence'"
        params: list[dict[str, str]] = [{"name": "@sid", "value": session_id}]
        results = []
        async for item in container.query_items(query=query, parameters=params):
            results.append(EvidenceRecord.model_validate(item))
        return results

    async def save_signal(self, signal: ProfileSignal) -> None:
        container = await self._container("profiles")
        doc = signal.model_dump(mode="json")
        signal_id = str(uuid.uuid4())
        doc["id"] = signal_id
        session_id = signal.source_stages[0] if signal.source_stages else ""
        doc["session_id"] = session_id
        doc["doc_type"] = "signal"
        await container.upsert_item(doc)

    async def get_signals(self, session_id: str) -> list[ProfileSignal]:
        container = await self._container("profiles")
        query = "SELECT * FROM c WHERE c.session_id = @sid AND c.doc_type = 'signal'"
        params: list[dict[str, str]] = [{"name": "@sid", "value": session_id}]
        results = []
        async for item in container.query_items(query=query, parameters=params):
            results.append(ProfileSignal.model_validate(item))
        return results


class CosmosAssetStore(_CosmosBase, AssetStore):
    """Asset metadata in Cosmos — binary data goes to Blob Storage via BlobAssetStore.

    This store only tracks metadata. Pair it with BlobAssetStore for actual file storage.
    """

    async def upload_image(self, session_id: str, filename: str, data: bytes, content_type: str) -> UploadedImage:
        raise NotImplementedError("Use BlobAssetStore for binary uploads; CosmosAssetStore stores metadata only.")

    async def save_generated_card(
        self, session_id: str, image_data: bytes, content_type: str, metadata: dict[str, Any]
    ) -> GeneratedCard:
        raise NotImplementedError("Use BlobAssetStore for binary uploads; CosmosAssetStore stores metadata only.")

    async def get_uploaded_image(self, session_id: str) -> UploadedImage | None:
        container = await self._container("profiles")
        try:
            doc = await container.read_item(item=f"upload_{session_id}", partition_key=session_id)
            return UploadedImage.model_validate(doc)
        except Exception:
            return None

    async def get_generated_card(self, session_id: str) -> GeneratedCard | None:
        container = await self._container("profiles")
        try:
            doc = await container.read_item(item=f"card_{session_id}", partition_key=session_id)
            return GeneratedCard.model_validate(doc)
        except Exception:
            return None

    async def download_asset(self, blob_path: str) -> bytes:
        raise NotImplementedError("Use BlobAssetStore for binary downloads.")
