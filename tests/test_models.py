"""Tests for Pydantic models."""

import pytest
from profile_agent.models.conversation import Message, Role, Turn, Transcript
from profile_agent.models.stage_state import StageState, StageProgress, StageStatus
from profile_agent.models.profile import UserProfile
from profile_agent.models.skill_matrix import SkillMatrix, SkillScore, Confidence
from profile_agent.models.evidence import EvidenceRecord
from profile_agent.models.assets import UploadedImage, GeneratedCard
from profile_agent.models.llm_contracts import StageExtractionResult, StageValidationResult


class TestMessage:
    def test_create_user_message(self):
        msg = Message(role=Role.USER, content="Hello")
        assert msg.role == Role.USER
        assert msg.content == "Hello"

    def test_create_assistant_message(self):
        msg = Message(role=Role.ASSISTANT, content="Hi there")
        assert msg.role == Role.ASSISTANT


class TestTurn:
    def test_create_turn(self):
        user_msg = Message(role=Role.USER, content="test")
        asst_msg = Message(role=Role.ASSISTANT, content="response")
        turn = Turn(turn_number=1, user_message=user_msg, assistant_message=asst_msg, stage_id="intro")
        assert turn.stage_id == "intro"
        assert turn.turn_number == 1


class TestTranscript:
    def test_empty_transcript(self):
        t = Transcript(session_id="s1")
        assert t.turn_count == 0

    def test_add_turn(self):
        t = Transcript(session_id="s1")
        user_msg = Message(role=Role.USER, content="hello")
        asst_msg = Message(role=Role.ASSISTANT, content="hi")
        turn = t.append_turn(user_msg, asst_msg, "intro")
        assert t.turn_count == 1
        assert turn.turn_number == 1


class TestStageState:
    def test_initial_state(self):
        state = StageState(session_id="s1")
        assert state.current_stage_id == ""
        assert len(state.stage_progress) == 0

    def test_progress_tracking(self):
        state = StageState(session_id="s1")
        state.current_stage_id = "introduction"
        progress = StageProgress(stage_id="introduction", status=StageStatus.IN_PROGRESS)
        state.stage_progress["introduction"] = progress
        assert state.stage_progress["introduction"].status == StageStatus.IN_PROGRESS


class TestSkillMatrix:
    def test_empty_matrix(self):
        matrix = SkillMatrix(session_id="s1")
        assert len(matrix.dimensions) == 0

    def test_add_dimension(self):
        matrix = SkillMatrix(session_id="s1")
        matrix.update_dimension(
            name="application_development",
            score=SkillScore.STRONG,
            confidence=Confidence.HIGH,
            evidence="Built multiple full-stack apps",
        )
        assert len(matrix.dimensions) == 1
        assert matrix.dimensions["application_development"].score == SkillScore.STRONG


class TestEvidenceRecord:
    def test_create_record(self):
        record = EvidenceRecord(
            session_id="s1",
            stage_id="heroes",
            category="technical_strength",
            content="Expert in distributed systems",
            confidence="high",
        )
        assert record.category == "technical_strength"


class TestLLMContracts:
    def test_extraction_result_empty(self):
        result = StageExtractionResult(stage_id="test")
        assert len(result.facts) == 0

    def test_validation_result_defaults(self):
        result = StageValidationResult(stage_id="test", is_complete=False)
        assert not result.is_complete
