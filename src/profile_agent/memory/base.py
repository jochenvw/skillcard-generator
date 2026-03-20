"""Abstract base protocols for persistence stores."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from profile_agent.models.assets import GeneratedCard, UploadedImage
from profile_agent.models.conversation import Transcript
from profile_agent.models.evidence import EvidenceRecord, ProfileSignal
from profile_agent.models.llm_contracts import GuidedCompressionResult, SessionSnapshot
from profile_agent.models.profile import UserProfile
from profile_agent.models.skill_matrix import SkillMatrix
from profile_agent.models.stage_state import StageState


class SessionStore(ABC):
    """Persist and retrieve session state."""

    @abstractmethod
    async def create_session(self, session_id: str, user_id: str) -> SessionSnapshot:
        ...

    @abstractmethod
    async def get_session(self, session_id: str) -> SessionSnapshot | None:
        ...

    @abstractmethod
    async def update_session(self, snapshot: SessionSnapshot) -> None:
        ...

    @abstractmethod
    async def list_sessions(self, user_id: str) -> list[SessionSnapshot]:
        ...

    @abstractmethod
    async def delete_session(self, session_id: str) -> None:
        ...

    @abstractmethod
    async def save_stage_state(self, state: StageState) -> None:
        ...

    @abstractmethod
    async def get_stage_state(self, session_id: str) -> StageState | None:
        ...


class TranscriptStore(ABC):
    """Persist and retrieve conversation transcripts."""

    @abstractmethod
    async def save_transcript(self, transcript: Transcript) -> None:
        ...

    @abstractmethod
    async def get_transcript(self, session_id: str) -> Transcript | None:
        ...

    @abstractmethod
    async def save_stage_summary(self, session_id: str, stage_id: str, summary: GuidedCompressionResult) -> None:
        ...

    @abstractmethod
    async def get_stage_summary(self, session_id: str, stage_id: str) -> GuidedCompressionResult | None:
        ...


class ProfileStore(ABC):
    """Persist and retrieve user profiles and skill matrices."""

    @abstractmethod
    async def save_profile(self, profile: UserProfile) -> None:
        ...

    @abstractmethod
    async def get_profile(self, session_id: str) -> UserProfile | None:
        ...

    @abstractmethod
    async def save_skill_matrix(self, matrix: SkillMatrix) -> None:
        ...

    @abstractmethod
    async def get_skill_matrix(self, session_id: str) -> SkillMatrix | None:
        ...

    @abstractmethod
    async def save_evidence(self, record: EvidenceRecord) -> None:
        ...

    @abstractmethod
    async def get_evidence(self, session_id: str) -> list[EvidenceRecord]:
        ...

    @abstractmethod
    async def save_signal(self, signal: ProfileSignal) -> None:
        ...

    @abstractmethod
    async def get_signals(self, session_id: str) -> list[ProfileSignal]:
        ...


class AssetStore(ABC):
    """Persist and retrieve binary assets (images)."""

    @abstractmethod
    async def upload_image(self, session_id: str, filename: str, data: bytes, content_type: str) -> UploadedImage:
        ...

    @abstractmethod
    async def save_generated_card(
        self, session_id: str, image_data: bytes, content_type: str, metadata: dict[str, Any]
    ) -> GeneratedCard:
        ...

    @abstractmethod
    async def get_uploaded_image(self, session_id: str) -> UploadedImage | None:
        ...

    @abstractmethod
    async def get_generated_card(self, session_id: str) -> GeneratedCard | None:
        ...

    @abstractmethod
    async def download_asset(self, blob_path: str) -> bytes:
        ...
