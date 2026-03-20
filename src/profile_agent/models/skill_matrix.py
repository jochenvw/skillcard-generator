"""Skill matrix models for behind-the-scenes profiling."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class SkillScore(str, Enum):
    UNKNOWN = "unknown"
    EMERGING = "emerging"
    WORKING = "working"
    STRONG = "strong"
    EXPERT = "expert"


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SkillDimension(BaseModel):
    """Assessment of a single skill area."""

    dimension: str
    score: SkillScore = SkillScore.UNKNOWN
    confidence: Confidence = Confidence.LOW
    evidence: list[str] = Field(default_factory=list)
    source_stages: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class SkillMatrix(BaseModel):
    """Full skills matrix across all tracked dimensions."""

    session_id: str
    dimensions: dict[str, SkillDimension] = Field(default_factory=dict)

    def get_dimension(self, name: str) -> SkillDimension:
        if name not in self.dimensions:
            self.dimensions[name] = SkillDimension(dimension=name)
        return self.dimensions[name]

    def update_dimension(
        self,
        name: str,
        score: SkillScore | None = None,
        confidence: Confidence | None = None,
        evidence: str | None = None,
        source_stage: str | None = None,
    ) -> None:
        dim = self.get_dimension(name)
        if score is not None:
            dim.score = score
        if confidence is not None:
            dim.confidence = confidence
        if evidence:
            dim.evidence.append(evidence)
        if source_stage and source_stage not in dim.source_stages:
            dim.source_stages.append(source_stage)

    @property
    def strong_areas(self) -> list[SkillDimension]:
        return [d for d in self.dimensions.values() if d.score in (SkillScore.STRONG, SkillScore.EXPERT)]

    @property
    def gap_areas(self) -> list[SkillDimension]:
        return [d for d in self.dimensions.values() if d.gaps]


# Default skill dimensions from the spec
SKILL_DIMENSIONS = [
    "identity",
    "networking",
    "governance",
    "infrastructure",
    "application_development",
    "data",
    "relational_databases",
    "nosql",
    "graph_databases",
    "ai_ml_genai",
    "containers_orchestration",
    "security",
    "performance_optimization",
    "system_design",
    "cloud_design_patterns",
    "architecture_methods",
    "stakeholder_management",
    "collaboration_influence",
    "software_engineering_craftsmanship",
]
