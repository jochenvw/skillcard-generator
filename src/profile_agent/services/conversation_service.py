"""Conversation service — per-turn pipeline orchestrating the 11-step flow."""

from __future__ import annotations

import logging
from datetime import datetime

from profile_agent.memory.base import ProfileStore, SessionStore, TranscriptStore
from profile_agent.models.conversation import Message, Role
from profile_agent.models.llm_contracts import SessionSnapshot
from profile_agent.models.stage_state import StageState
from profile_agent.services.extraction_service import ExtractionService
from profile_agent.services.validation_service import ValidationService
from profile_agent.services.compression_service import CompressionService
from profile_agent.services.inference_service import InferenceService
from profile_agent.workflows.interview_workflow import InterviewWorkflow

logger = logging.getLogger(__name__)


class ConversationService:
    """Orchestrates the per-turn pipeline for the interview.

    After every user turn:
    1. Append raw turn to transcript
    2. Extract structured facts
    3. Validate completion criteria
    4. Compute missing info / next best question
    5. If context long, run guided compression
    6. Persist transcript + distilled memory + evidence
    7. Update inferred profile signals
    8. Emit telemetry
    9. Generate next assistant turn
    10. If stage complete, present confirmation summary
    11. Only transition after confirmation
    """

    def __init__(
        self,
        workflow: InterviewWorkflow,
        session_store: SessionStore,
        transcript_store: TranscriptStore,
        profile_store: ProfileStore,
        extraction_service: ExtractionService,
        validation_service: ValidationService,
        compression_service: CompressionService,
        inference_service: InferenceService,
    ) -> None:
        self._workflow = workflow
        self._session_store = session_store
        self._transcript_store = transcript_store
        self._profile_store = profile_store
        self._extraction = extraction_service
        self._validation = validation_service
        self._compression = compression_service
        self._inference = inference_service

    async def process_turn(self, user_text: str, assistant_text: str) -> dict:
        """Process a completed turn through the full pipeline.

        Returns a dict with status info for the caller.
        """
        runner = self._workflow.current_runner
        if not runner:
            return {"error": "No active stage"}

        stage_id = runner.stage.id
        session_id = self._workflow.state.session_id

        # 1. Record turn
        self._workflow.record_turn(user_text, assistant_text)

        # 2. Extract facts
        extraction_result = await self._extraction.extract(
            user_text=user_text,
            assistant_text=assistant_text,
            stage_id=stage_id,
            extraction_targets=runner.stage.extraction_targets,
        )
        runner.mark_extraction_done()

        # 3. Validate completion
        validation_result = await self._validation.validate(
            stage_id=stage_id,
            completion_criteria=runner.stage.completion_criteria,
            extracted_facts=extraction_result.facts,
        )

        # 4. Missing info captured in validation_result.missing_information

        # 5. Compression if needed
        if self._workflow.needs_compaction():
            stage_turns = self._workflow.transcript.turns_for_stage(stage_id)
            turn_texts = [f"User: {t.user_message.content}\nAssistant: {t.assistant_message.content}" for t in stage_turns]
            compression_result = await self._compression.compress(
                stage_id=stage_id,
                transcript_text="\n\n".join(turn_texts),
                extraction_targets=runner.stage.extraction_targets,
            )
            runner.mark_compression_done()
            await self._transcript_store.save_stage_summary(
                session_id, stage_id, compression_result
            )

        # 6. Persist
        await self._transcript_store.save_transcript(self._workflow.transcript)
        for fact in extraction_result.facts:
            from profile_agent.models.evidence import EvidenceRecord
            record = EvidenceRecord(
                session_id=session_id,
                stage_id=stage_id,
                category=fact.category,
                content=fact.content,
                source_quote=fact.source_quote,
                confidence=fact.confidence,
                skill_dimensions=fact.skill_dimensions,
            )
            await self._profile_store.save_evidence(record)

        # 7. Update profile signals
        await self._inference.update_from_evidence(session_id, extraction_result.facts)

        # 8. Telemetry emitted by instrumented methods (spans/metrics)

        # 10. Stage completion check
        result = {
            "stage_id": stage_id,
            "turn_count": runner.turns_in_stage,
            "is_stage_complete": validation_result.is_complete,
            "missing_information": validation_result.missing_information,
            "suggested_next_question": validation_result.suggested_next_question,
        }

        if validation_result.is_complete and runner.stage.confirmation_required:
            result["needs_confirmation"] = True
        elif validation_result.is_complete and not runner.stage.confirmation_required:
            result["auto_advance"] = True

        # 9. Save state
        await self._session_store.save_stage_state(self._workflow.state)
        snapshot = SessionSnapshot(
            session_id=session_id,
            current_stage_id=stage_id,
            completed_stages=self._workflow.state.completed_stage_ids,
            turn_count=self._workflow.transcript.turn_count,
        )
        await self._session_store.update_session(snapshot)

        return result
