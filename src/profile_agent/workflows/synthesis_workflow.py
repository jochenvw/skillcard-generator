"""Synthesis workflow — post-interview profile and archetype generation."""

from __future__ import annotations

import logging

from profile_agent.models.evidence import EvidenceRecord
from profile_agent.models.llm_contracts import ProfileSignalInference
from profile_agent.models.profile import UserProfile
from profile_agent.models.skill_matrix import SkillMatrix

logger = logging.getLogger(__name__)


class SynthesisWorkflow:
    """Synthesizes the final profile, skill matrix, and archetype from interview evidence.

    This runs after all interview stages are complete, before card generation:
    1. Aggregate all evidence records across stages
    2. Run the profiler agent to infer skill scores
    3. Determine archetype / class
    4. Build the final UserProfile
    """

    def __init__(self, session_id: str, profile: UserProfile, skill_matrix: SkillMatrix) -> None:
        self._session_id = session_id
        self._profile = profile
        self._skill_matrix = skill_matrix

    async def synthesize(
        self,
        evidence: list[EvidenceRecord],
        stage_summaries: dict[str, str],
        inference_callback,
    ) -> UserProfile:
        """Run the full synthesis pipeline.

        Args:
            evidence: All evidence records from the interview.
            stage_summaries: Dict of stage_id -> distilled summary text.
            inference_callback: Async callable that takes evidence text and returns
                               ProfileSignalInference (typically calls the profiler agent).
        """
        logger.info("Starting synthesis for session %s with %d evidence records", self._session_id, len(evidence))

        # Build evidence text for the profiler
        evidence_text = self._format_evidence(evidence, stage_summaries)

        # Call the profiler agent via callback
        inference: ProfileSignalInference = await inference_callback(evidence_text)

        # Update skill matrix from inference
        for assessment in inference.signals:
            self._skill_matrix.update_dimension(
                name=assessment.dimension,
                score=assessment.score,  # type: ignore[arg-type]
                confidence=assessment.confidence,  # type: ignore[arg-type]
                evidence=assessment.reasoning,
            )

        # Update profile archetype
        if inference.archetype_suggestion:
            self._profile.identity.archetype = inference.archetype_suggestion
            self._profile.identity.flavor_text = inference.archetype_reasoning

        self._profile.updated_at = __import__("datetime").datetime.utcnow()
        logger.info("Synthesis complete — archetype: %s", self._profile.identity.archetype)
        return self._profile

    def _format_evidence(self, evidence: list[EvidenceRecord], stage_summaries: dict[str, str]) -> str:
        """Format evidence into a text block for the profiler agent."""
        parts = ["# Interview Evidence\n"]

        if stage_summaries:
            parts.append("## Stage Summaries\n")
            for stage_id, summary in stage_summaries.items():
                parts.append(f"### {stage_id}\n{summary}\n")

        if evidence:
            parts.append("## Extracted Evidence\n")
            for e in evidence:
                parts.append(
                    f"- [{e.category}] {e.content}"
                    + (f' (quote: "{e.source_quote}")' if e.source_quote else "")
                    + f" [confidence: {e.confidence}]\n"
                )

        return "\n".join(parts)
