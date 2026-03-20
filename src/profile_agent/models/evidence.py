"""Evidence and profile signal models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class EvidenceRecord(BaseModel):
    """A single piece of evidence extracted from conversation."""

    evidence_id: str = ""
    session_id: str = ""
    stage_id: str = ""
    turn_number: int = 0
    category: str = ""  # e.g. "technical_strength", "value", "influence", "aspiration"
    content: str = ""
    source_quote: str = ""
    confidence: str = "medium"  # low / medium / high
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    skill_dimensions: list[str] = Field(default_factory=list)


class ProfileSignal(BaseModel):
    """An inferred signal about the user, derived from one or more evidence records."""

    session_id: str = ""
    signal_type: str  # e.g. "strength", "value", "aspiration", "collaboration_style"
    description: str
    strength: str = "medium"  # weak / medium / strong
    supporting_evidence: list[str] = Field(default_factory=list)  # evidence_ids
    source_stages: list[str] = Field(default_factory=list)
    inferred_at: datetime = Field(default_factory=datetime.utcnow)
