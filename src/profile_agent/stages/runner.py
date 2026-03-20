"""Stage runner — manages turns within a single stage."""

from __future__ import annotations

import logging
from datetime import datetime

from profile_agent.models.conversation import Message, Role, Transcript
from profile_agent.models.stage_state import StageProgress, StageState, StageStatus
from profile_agent.stages.models import StageDefinition

logger = logging.getLogger(__name__)


class StageRunner:
    """Manages the lifecycle of a single interview stage.

    Responsibilities:
    - Track turns within the stage
    - Signal when compression is needed (max_turns_before_compaction)
    - Signal when stage completion criteria are met
    - Provide context for the agent's next response
    """

    def __init__(self, stage: StageDefinition, state: StageState, transcript: Transcript) -> None:
        self._stage = stage
        self._state = state
        self._transcript = transcript

    @property
    def stage(self) -> StageDefinition:
        return self._stage

    @property
    def progress(self) -> StageProgress:
        return self._state.get_progress(self._stage.id)

    @property
    def turns_in_stage(self) -> int:
        return len(self._transcript.turns_for_stage(self._stage.id))

    @property
    def needs_compaction(self) -> bool:
        return self.turns_in_stage >= self._stage.max_turns_before_compaction

    def enter(self) -> str:
        """Enter the stage and return the opening prompt."""
        self._state.enter_stage(self._stage.id)
        logger.info("Entering stage: %s (%s)", self._stage.id, self._stage.title)
        return self._stage.opening_prompt

    def record_turn(self, user_msg: Message, assistant_msg: Message) -> None:
        """Record a turn within this stage."""
        self._transcript.append_turn(user_msg, assistant_msg, self._stage.id)
        progress = self.progress
        progress.turns_completed += 1

    def mark_extraction_done(self) -> None:
        self.progress.extraction_count += 1

    def mark_compression_done(self) -> None:
        self.progress.compression_count += 1

    def request_confirmation(self, summary: str) -> None:
        """Move stage to awaiting-confirmation state."""
        progress = self.progress
        progress.status = StageStatus.AWAITING_CONFIRMATION
        progress.summary = summary

    def accept_confirmation(self) -> None:
        progress = self.progress
        progress.confirmation_accepted = True
        progress.status = StageStatus.CONFIRMED

    def reject_confirmation(self) -> None:
        progress = self.progress
        progress.confirmation_accepted = False
        progress.status = StageStatus.IN_PROGRESS

    def complete(self, summary: str) -> None:
        self._state.complete_stage(self._stage.id, summary)
        logger.info("Completed stage: %s", self._stage.id)

    def get_stage_context(self) -> dict:
        """Build context dict for prompt construction."""
        return {
            "stage_id": self._stage.id,
            "stage_title": self._stage.title,
            "purpose": self._stage.purpose,
            "user_experience_goal": self._stage.user_experience_goal,
            "follow_up_style": self._stage.follow_up_style,
            "extraction_targets": self._stage.extraction_targets,
            "completion_criteria": self._stage.completion_criteria,
            "turns_completed": self.turns_in_stage,
            "needs_compaction": self.needs_compaction,
        }
