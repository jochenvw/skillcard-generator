"""Stage definition model — maps 1:1 to YAML stage files."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RetryPolicy(BaseModel):
    max_retries: int = 2
    backoff_message: str = "Let me rephrase that..."


class SummarizationPolicy(BaseModel):
    strategy: str = "guided"  # guided / simple / none
    preserve_examples: bool = True
    preserve_quotes: bool = True
    max_summary_tokens: int = 500


class ProfileMappingRule(BaseModel):
    source_field: str
    target_field: str
    mapping_type: str = "direct"  # direct / append / merge


class StageDefinition(BaseModel):
    """Declarative definition of an interview stage, loaded from YAML."""

    id: str
    title: str
    purpose: str = ""
    user_experience_goal: str = ""
    opening_prompt: str = ""
    follow_up_style: str = "reflective"
    completion_criteria: list[str] = Field(default_factory=list)
    extraction_targets: list[str] = Field(default_factory=list)
    validation_rules: list[str] = Field(default_factory=list)
    confirmation_required: bool = True
    next_stage: str | None = None
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    max_turns_before_compaction: int = 8
    summarization_policy: SummarizationPolicy = Field(default_factory=SummarizationPolicy)
    profile_mapping_rules: list[ProfileMappingRule] = Field(default_factory=list)
    sort_order: int = 0
