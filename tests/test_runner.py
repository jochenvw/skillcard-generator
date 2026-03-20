"""Tests for the stage runner and transition engine."""

import pytest
from profile_agent.stages.loader import load_stages
from profile_agent.stages.runner import StageRunner
from profile_agent.stages.transition_engine import TransitionEngine
from profile_agent.models.stage_state import StageState
from profile_agent.models.conversation import Transcript


@pytest.fixture
def stages():
    return load_stages()


@pytest.fixture
def state():
    return StageState(session_id="test-session")


@pytest.fixture
def transcript():
    return Transcript(session_id="test-session")


class TestStageRunner:
    def test_create_runner(self, stages, state, transcript):
        runner = StageRunner(stage=stages[0], state=state, transcript=transcript)
        assert runner.stage.id == "introduction"
        assert runner.turns_in_stage == 0

    def test_record_turn(self, stages, state, transcript):
        from profile_agent.models.conversation import Message, Role
        runner = StageRunner(stage=stages[0], state=state, transcript=transcript)
        runner.record_turn(
            Message(role=Role.USER, content="hi"),
            Message(role=Role.ASSISTANT, content="hello"),
        )
        assert runner.turns_in_stage == 1


class TestTransitionEngine:
    def test_start_interview(self, stages, state, transcript):
        engine = TransitionEngine(stages=stages, state=state, transcript=transcript)
        engine.start_interview()
        assert state.current_stage_id == "introduction"

    def test_advance_stage(self, stages, state, transcript):
        engine = TransitionEngine(stages=stages, state=state, transcript=transcript)
        engine.start_interview()
        next_stage = engine.advance()
        assert next_stage is not None
        assert state.current_stage_id == "heroes"

    def test_get_progress_summary(self, stages, state, transcript):
        engine = TransitionEngine(stages=stages, state=state, transcript=transcript)
        engine.start_interview()
        summary = engine.get_progress_summary()
        assert "introduction" in summary
        assert len(summary) == 10
