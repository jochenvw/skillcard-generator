"""User profile, identity, and archetype models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Identity(BaseModel):
    """Core identity attributes derived from interview."""

    display_name: str = ""
    title: str = ""
    archetype: str = ""  # e.g. "The Systems Architect", "The Craft-Obsessed Builder"
    tagline: str = ""
    flavor_text: str = ""


class DomainAffinity(BaseModel):
    """An area of strength or interest."""

    domain: str
    affinity_level: str = "medium"  # low / medium / high / primary
    evidence_summary: str = ""


class Aspiration(BaseModel):
    """A stated or inferred aspiration."""

    description: str
    timeframe: str = ""  # near-term / long-term
    confidence: str = "medium"


class Influence(BaseModel):
    """A person, book, talk, or quote that shaped the user."""

    kind: str  # person / book / video / quote / other
    name: str
    why_meaningful: str = ""


class UserProfile(BaseModel):
    """Aggregated profile built up across interview stages."""

    session_id: str
    user_id: str = ""
    identity: Identity = Field(default_factory=Identity)
    domain_affinities: list[DomainAffinity] = Field(default_factory=list)
    aspirations: list[Aspiration] = Field(default_factory=list)
    influences: list[Influence] = Field(default_factory=list)
    values: list[str] = Field(default_factory=list)
    hero_projects: list[str] = Field(default_factory=list)
    hobby_projects: list[str] = Field(default_factory=list)
    shower_thoughts: list[str] = Field(default_factory=list)
    collaboration_style: str = ""
    raw_signals: dict[str, list[str]] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
