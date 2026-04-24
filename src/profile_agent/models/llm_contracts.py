"""Typed contracts for LLM structured outputs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ── Extraction ──────────────────────────────────────────────────────


class ExtractedFact(BaseModel):
    category: str
    content: str
    source_quote: str = ""
    confidence: str = "medium"
    skill_dimensions: list[str] = Field(default_factory=list)


class StageExtractionResult(BaseModel):
    """Structured output from the extraction LLM call."""

    facts: list[ExtractedFact] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    stage_id: str = ""


# ── Validation ──────────────────────────────────────────────────────


class ValidationIssue(BaseModel):
    criterion: str
    met: bool
    detail: str = ""


class StageValidationResult(BaseModel):
    """Structured output from the stage-completion validation call."""

    stage_id: str = ""
    is_complete: bool = False
    issues: list[ValidationIssue] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    suggested_next_question: str = ""


# ── Compression ─────────────────────────────────────────────────────


class GuidedCompressionResult(BaseModel):
    """Output of guided compression — preserves critical details."""

    stage_id: str = ""
    distilled_summary: str = ""
    preserved_examples: list[str] = Field(default_factory=list)
    preserved_motivations: list[str] = Field(default_factory=list)
    preserved_domains: list[str] = Field(default_factory=list)
    evidence_snippets: list[str] = Field(default_factory=list)
    unresolved_ambiguities: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


# ── Inference ───────────────────────────────────────────────────────


class SkillAssessment(BaseModel):
    """LLM-produced assessment for a single skill dimension."""

    dimension: str
    score: str = "unknown"
    confidence: str = "low"
    reasoning: str = ""
    evidence_references: list[str] = Field(default_factory=list)


class ProfileSignalInference(BaseModel):
    """Batch of profile signals inferred from evidence."""

    signals: list[SkillAssessment] = Field(default_factory=list)
    archetype_suggestion: str = ""
    archetype_reasoning: str = ""


# ── Session ─────────────────────────────────────────────────────────


class SessionSnapshot(BaseModel):
    """Point-in-time snapshot of a session for persistence/resume."""

    session_id: str
    user_id: str = ""
    current_stage_id: str = ""
    completed_stages: list[str] = Field(default_factory=list)
    turn_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    profile_picture_uploaded: bool = False
    card_generated: bool = False


# ── Card Generation ─────────────────────────────────────────────────


class CardStyle(BaseModel):
    """User-controlled stylistic preferences for the generated card image.

    All fields optional; a fully-empty CardStyle (or None) yields the default
    look (Futuristic Metallic / Professional / blue-cyan accents). The card
    *layout* is unaffected — only the image-prompt's design block, accent-
    color line, and portrait line are touched.
    """

    style_preset: str | None = None
    persona_setting: str | None = None
    accent_color: str | None = None


class CardAbility(BaseModel):
    name: str
    description: str
    power_level: int = 5  # 1-10


class CardSpec(BaseModel):
    """Specification for the final strengths card."""

    session_id: str = ""
    display_name: str = ""
    title: str = ""
    archetype: str = ""
    flavor_text: str = ""
    abilities: list[CardAbility] = Field(default_factory=list)
    signature_domains: list[str] = Field(default_factory=list)
    rarity: str = "rare"  # common / uncommon / rare / legendary / mythic
    theme: str = ""
    portrait_description: str = ""


class ImageGenerationRequest(BaseModel):
    """Request payload for image generation."""

    prompt: str
    model_deployment: str = ""
    size: str = "1024x1024"
    quality: str = "hd"
    style: str = "vivid"
    session_id: str = ""
    card_spec_id: str = ""


class ImageGenerationResult(BaseModel):
    """Result from image generation API."""

    success: bool = False
    image_url: str = ""
    raw_bytes: bytes | None = None  # populated when model returns base64 (e.g. gpt-image-1.5)
    blob_path: str = ""
    revised_prompt: str = ""
    model_deployment: str = ""
    error: str = ""
    generated_at: datetime = Field(default_factory=datetime.utcnow)
