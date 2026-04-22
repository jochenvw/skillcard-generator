"""SkillCardProfile — the locked schema returned by card-generation."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


def _strip_and_truncate(items: list[str]) -> list[str]:
    cleaned = [item.strip() for item in items if isinstance(item, str) and item.strip()]
    return cleaned[:5]


class SkillCardProfile(BaseModel):
    """Profile shape consumed by the frontend card renderer and image prompt.

    Required non-empty lists: strengths, aspirations, learn_grow.
    Optional lists (may be empty): clifton_strengths, inspirations, accomplishments.
    All list fields are capped at 5 items and individual strings are stripped.
    """

    name: str = ""
    title: str = ""
    industry: str = ""
    strengths: list[str] = Field(min_length=1)
    clifton_strengths: list[str] = Field(default_factory=list)
    inspirations: list[str] = Field(default_factory=list)
    aspirations: list[str] = Field(min_length=1)
    learn_grow: list[str] = Field(min_length=1)
    accomplishments: list[str] = Field(default_factory=list)
    growth_focus: str = ""
    flavor_text: str = ""

    @field_validator("name", "title", "industry", "growth_focus", "flavor_text", mode="before")
    @classmethod
    def _strip_string(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator(
        "strengths",
        "clifton_strengths",
        "inspirations",
        "aspirations",
        "learn_grow",
        "accomplishments",
        mode="before",
    )
    @classmethod
    def _clean_list(cls, value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            return []
        return _strip_and_truncate(value)
