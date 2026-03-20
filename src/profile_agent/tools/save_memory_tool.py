"""Tool: Save extracted facts and summaries to session memory."""

from __future__ import annotations

import logging

from profile_agent.memory.base import ProfileStore, TranscriptStore
from profile_agent.models.evidence import EvidenceRecord
from profile_agent.models.llm_contracts import GuidedCompressionResult

logger = logging.getLogger(__name__)


async def save_evidence(
    profile_store: ProfileStore,
    session_id: str,
    stage_id: str,
    facts: list[dict],
) -> list[str]:
    """Save extracted evidence records. Returns list of evidence IDs."""
    evidence_ids = []
    for fact in facts:
        record = EvidenceRecord(
            session_id=session_id,
            stage_id=stage_id,
            category=fact.get("category", ""),
            content=fact.get("content", ""),
            source_quote=fact.get("source_quote", ""),
            confidence=fact.get("confidence", "medium"),
            skill_dimensions=fact.get("skill_dimensions", []),
        )
        await profile_store.save_evidence(record)
        evidence_ids.append(record.evidence_id)
        logger.info("Saved evidence %s for session %s stage %s", record.evidence_id, session_id, stage_id)
    return evidence_ids


async def save_stage_summary(
    transcript_store: TranscriptStore,
    session_id: str,
    stage_id: str,
    summary: GuidedCompressionResult,
) -> None:
    """Save a guided compression summary for a stage."""
    await transcript_store.save_stage_summary(session_id, stage_id, summary)
    logger.info("Saved stage summary for session %s stage %s", session_id, stage_id)
