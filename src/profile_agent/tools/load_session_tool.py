"""Tool: Load/resume a session from persistence."""

from __future__ import annotations

import logging

from profile_agent.memory.base import SessionStore, TranscriptStore, ProfileStore
from profile_agent.models.conversation import Transcript
from profile_agent.models.llm_contracts import SessionSnapshot
from profile_agent.models.profile import UserProfile
from profile_agent.models.skill_matrix import SkillMatrix
from profile_agent.models.stage_state import StageState

logger = logging.getLogger(__name__)


class SessionData:
    """Aggregated session data for resumption."""

    def __init__(
        self,
        snapshot: SessionSnapshot,
        stage_state: StageState | None,
        transcript: Transcript | None,
        profile: UserProfile | None,
        skill_matrix: SkillMatrix | None,
    ) -> None:
        self.snapshot = snapshot
        self.stage_state = stage_state or StageState(session_id=snapshot.session_id)
        self.transcript = transcript or Transcript(session_id=snapshot.session_id)
        self.profile = profile or UserProfile(session_id=snapshot.session_id)
        self.skill_matrix = skill_matrix or SkillMatrix(session_id=snapshot.session_id)


async def load_session(
    session_store: SessionStore,
    transcript_store: TranscriptStore,
    profile_store: ProfileStore,
    session_id: str,
) -> SessionData | None:
    """Load all session data for resumption. Returns None if session not found."""
    snapshot = await session_store.get_session(session_id)
    if not snapshot:
        logger.info("Session %s not found", session_id)
        return None

    stage_state = await session_store.get_stage_state(session_id)
    transcript = await transcript_store.get_transcript(session_id)
    profile = await profile_store.get_profile(session_id)
    skill_matrix = await profile_store.get_skill_matrix(session_id)

    logger.info("Loaded session %s (stage: %s, turns: %d)",
                session_id, snapshot.current_stage_id, snapshot.turn_count)
    return SessionData(snapshot, stage_state, transcript, profile, skill_matrix)
