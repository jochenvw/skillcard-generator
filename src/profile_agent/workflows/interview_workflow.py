"""Interview workflow — orchestrates the multi-stage interview loop."""

from __future__ import annotations

import logging
from datetime import datetime

from profile_agent.models.conversation import Message, Role, Transcript
from profile_agent.models.stage_state import StageState, StageStatus
from profile_agent.stages.loader import load_stages
from profile_agent.stages.runner import StageRunner
from profile_agent.stages.transition_engine import TransitionEngine

logger = logging.getLogger(__name__)


class InterviewWorkflow:
    """Orchestrates the full interview flow across all stages.

    Per-turn pipeline (from the spec):
    1. Append raw turn to transcript
    2. Extract structured facts from turn
    3. Validate completion criteria for current stage
    4. Compute missing information / next best question
    5. If context is getting long, run guided compression
    6. Persist transcript + distilled memory + evidence
    7. Update inferred profile signals
    8. Emit telemetry spans/metrics/logs
    9. Generate next assistant turn
    10. If stage complete, present confirmation summary
    11. Only transition after confirmation or acceptable auto-advance policy
    """

    def __init__(self, session_id: str, state: StageState | None = None, transcript: Transcript | None = None) -> None:
        self._session_id = session_id
        self._stages = load_stages()
        self._state = state or StageState(session_id=session_id)
        self._transcript = transcript or Transcript(session_id=session_id)
        self._engine = TransitionEngine(self._stages, self._state, self._transcript)
        self._current_runner: StageRunner | None = None

    @property
    def state(self) -> StageState:
        return self._state

    @property
    def transcript(self) -> Transcript:
        return self._transcript

    @property
    def engine(self) -> TransitionEngine:
        return self._engine

    @property
    def current_runner(self) -> StageRunner | None:
        return self._current_runner

    @property
    def is_complete(self) -> bool:
        return self._engine.is_interview_complete

    def start(self) -> str:
        """Start or resume the interview. Returns the opening message."""
        self._current_runner = self._engine.start_interview()
        return self._current_runner.stage.opening_prompt

    def get_current_stage_context(self) -> dict:
        """Get context for the current stage (used by the agent for prompt construction)."""
        if self._current_runner:
            return self._current_runner.get_stage_context()
        return {}

    def record_turn(self, user_text: str, assistant_text: str) -> None:
        """Record a completed turn."""
        if not self._current_runner:
            return
        user_msg = Message(role=Role.USER, content=user_text)
        assistant_msg = Message(role=Role.ASSISTANT, content=assistant_text)
        self._current_runner.record_turn(user_msg, assistant_msg)

    def needs_compaction(self) -> bool:
        """Check if the current stage needs context compaction."""
        return self._current_runner.needs_compaction if self._current_runner else False

    def mark_stage_complete(self, summary: str) -> str | None:
        """Mark current stage complete and advance. Returns next stage opening or None."""
        if not self._current_runner:
            return None

        self._current_runner.complete(summary)
        next_runner = self._engine.advance()

        if next_runner is None:
            logger.info("Interview complete for session %s", self._session_id)
            return None

        self._current_runner = next_runner
        return next_runner.stage.opening_prompt

    def request_confirmation(self, summary: str) -> str:
        """Request user confirmation for the current stage."""
        if self._current_runner:
            self._current_runner.request_confirmation(summary)
        return summary

    def process_confirmation(self, accepted: bool) -> None:
        """Process user's confirmation response."""
        if not self._current_runner:
            return
        if accepted:
            self._current_runner.accept_confirmation()
        else:
            self._current_runner.reject_confirmation()

    def get_progress(self) -> dict[str, str]:
        """Get progress summary across all stages."""
        return self._engine.get_progress_summary()
