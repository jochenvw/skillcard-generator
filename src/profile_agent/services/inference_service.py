"""Inference service — updates skill matrix from evidence."""

from __future__ import annotations

import logging

from profile_agent.memory.base import ProfileStore
from profile_agent.models.llm_contracts import ExtractedFact
from profile_agent.models.skill_matrix import Confidence, SkillMatrix, SkillScore

logger = logging.getLogger(__name__)

# Mapping from extraction categories to skill dimensions
_CATEGORY_TO_DIMENSIONS: dict[str, list[str]] = {
    "technical_strength": ["application_development", "software_engineering_craftsmanship"],
    "architecture": ["system_design", "cloud_design_patterns", "architecture_methods"],
    "infrastructure": ["infrastructure", "containers_orchestration"],
    "data": ["data", "relational_databases", "nosql"],
    "ai_ml": ["ai_ml_genai"],
    "security": ["security"],
    "performance": ["performance_optimization"],
    "collaboration": ["collaboration_influence", "stakeholder_management"],
    "leadership": ["stakeholder_management", "collaboration_influence"],
    "cloud": ["cloud_design_patterns", "infrastructure"],
    "networking": ["networking"],
    "governance": ["governance"],
    "graph": ["graph_databases"],
    "containers": ["containers_orchestration"],
    "identity": ["identity"],
}


class InferenceService:
    """Updates the skill matrix based on extracted evidence."""

    def __init__(self, profile_store: ProfileStore) -> None:
        self._profile_store = profile_store

    async def update_from_evidence(self, session_id: str, facts: list[ExtractedFact]) -> SkillMatrix:
        """Update skill matrix dimensions based on newly extracted facts."""
        matrix = await self._profile_store.get_skill_matrix(session_id)
        if not matrix:
            matrix = SkillMatrix(session_id=session_id)

        for fact in facts:
            dimensions = self._resolve_dimensions(fact)
            confidence = self._map_confidence(fact.confidence)
            score = self._infer_score(fact)

            for dim_name in dimensions:
                matrix.update_dimension(
                    name=dim_name,
                    score=score,
                    confidence=confidence,
                    evidence=fact.content,
                    source_stage=fact.category,
                )

            # Also use explicitly tagged dimensions from extraction
            for dim_name in fact.skill_dimensions:
                matrix.update_dimension(
                    name=dim_name,
                    score=score,
                    confidence=confidence,
                    evidence=fact.content,
                )

        await self._profile_store.save_skill_matrix(matrix)
        logger.info("Updated skill matrix for session %s: %d dimensions active",
                     session_id, len(matrix.dimensions))
        return matrix

    def _resolve_dimensions(self, fact: ExtractedFact) -> list[str]:
        """Map a fact's category to skill dimensions."""
        return _CATEGORY_TO_DIMENSIONS.get(fact.category, [])

    def _map_confidence(self, confidence_str: str) -> Confidence:
        mapping = {"low": Confidence.LOW, "medium": Confidence.MEDIUM, "high": Confidence.HIGH}
        return mapping.get(confidence_str, Confidence.LOW)

    def _infer_score(self, fact: ExtractedFact) -> SkillScore:
        """Infer a skill score from fact confidence and content signals."""
        # Simple heuristic — more sophisticated in production with the profiler agent
        if fact.confidence == "high":
            return SkillScore.STRONG
        elif fact.confidence == "medium":
            return SkillScore.WORKING
        else:
            return SkillScore.EMERGING
