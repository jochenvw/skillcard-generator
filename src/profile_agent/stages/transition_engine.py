"""Transition engine — orchestrates movement between interview stages."""

from __future__ import annotations

import logging

from profile_agent.models.conversation import Transcript
from profile_agent.models.stage_state import StageState, StageStatus
from profile_agent.stages.loader import build_stage_index
from profile_agent.stages.models import StageDefinition
from profile_agent.stages.runner import StageRunner

logger = logging.getLogger(__name__)


class TransitionEngine:
    """Manages the full interview flow across stages.

    - Determines which stage to enter next.
    - Creates StageRunner instances for each active stage.
    - Handles confirmation gates before transitions.
    - Detects interview completion.
    """

    def __init__(self, stages: list[StageDefinition], state: StageState, transcript: Transcript) -> None:
        self._stages = stages
        self._stage_index = build_stage_index(stages)
        self._state = state
        self._transcript = transcript
        self._current_runner: StageRunner | None = None

    @property
    def current_runner(self) -> StageRunner | None:
        return self._current_runner

    @property
    def current_stage(self) -> StageDefinition | None:
        if self._state.current_stage_id:
            return self._stage_index.get(self._state.current_stage_id)
        return None

    @property
    def is_interview_complete(self) -> bool:
        """True if the last stage has been completed."""
        if not self._stages:
            return True
        last_stage = self._stages[-1]
        progress = self._state.get_progress(last_stage.id)
        return progress.status == StageStatus.COMPLETED

    @property
    def completed_stages(self) -> list[str]:
        return self._state.completed_stage_ids

    def get_first_stage(self) -> StageDefinition:
        return self._stages[0]

    def get_next_stage(self, current_stage_id: str) -> StageDefinition | None:
        """Determine the next stage after the given one."""
        current = self._stage_index.get(current_stage_id)
        if current and current.next_stage:
            return self._stage_index.get(current.next_stage)
        # Fall back to sequential order
        for i, stage in enumerate(self._stages):
            if stage.id == current_stage_id and i + 1 < len(self._stages):
                return self._stages[i + 1]
        return None

    def enter_stage(self, stage_id: str) -> StageRunner:
        """Create a runner for the given stage and mark it as entered."""
        stage = self._stage_index[stage_id]
        runner = StageRunner(stage, self._state, self._transcript)
        runner.enter()
        self._current_runner = runner
        return runner

    def start_interview(self) -> StageRunner:
        """Begin from the first stage or resume from current."""
        if self._state.current_stage_id:
            stage_id = self._state.current_stage_id
        else:
            stage_id = self.get_first_stage().id
        return self.enter_stage(stage_id)

    def advance(self) -> StageRunner | None:
        """Advance to the next stage. Returns None if interview is complete."""
        if not self._state.current_stage_id:
            return self.start_interview()

        next_stage = self.get_next_stage(self._state.current_stage_id)
        if next_stage is None:
            logger.info("Interview complete — no more stages")
            return None

        return self.enter_stage(next_stage.id)

    def can_advance(self) -> bool:
        """Check if the current stage is ready to advance (confirmed or no confirmation needed)."""
        if not self._current_runner:
            return False
        progress = self._current_runner.progress
        stage = self._current_runner.stage
        if not stage.confirmation_required:
            return progress.status in (StageStatus.CONFIRMED, StageStatus.COMPLETED)
        return progress.status == StageStatus.CONFIRMED

    def get_progress_summary(self) -> dict[str, str]:
        """Return a summary of progress across all stages."""
        result = {}
        for stage in self._stages:
            progress = self._state.get_progress(stage.id)
            result[stage.id] = progress.status.value
        return result
