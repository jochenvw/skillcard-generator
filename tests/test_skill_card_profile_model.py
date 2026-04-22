"""Tests for the SkillCardProfile pydantic model."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from profile_agent.models.skill_card_profile import SkillCardProfile


def _good_payload(**overrides) -> dict:
    base = {
        "name": "Alex Rivers",
        "title": "Principal Engineer",
        "industry": "Cloud Infrastructure",
        "strengths": ["Systems thinking", "Mentorship"],
        "clifton_strengths": ["Strategic", "Learner"],
        "inspirations": ["Leslie Lamport"],
        "aspirations": ["Lead AI platform"],
        "learn_grow": ["Rust async", "LLM evals"],
        "accomplishments": ["Migrated 200 services"],
        "growth_focus": "Bridge classical and AI-native systems.",
        "flavor_text": "Patterns light tomorrow's path.",
    }
    base.update(overrides)
    return base


class TestSkillCardProfile:
    def test_accepts_good_input(self):
        profile = SkillCardProfile.model_validate(_good_payload())
        assert profile.name == "Alex Rivers"
        assert profile.strengths == ["Systems thinking", "Mentorship"]
        assert profile.clifton_strengths == ["Strategic", "Learner"]

    def test_optional_lists_default_to_empty(self):
        payload = _good_payload()
        del payload["clifton_strengths"]
        del payload["inspirations"]
        del payload["accomplishments"]
        profile = SkillCardProfile.model_validate(payload)
        assert profile.clifton_strengths == []
        assert profile.inspirations == []
        assert profile.accomplishments == []

    def test_rejects_empty_strengths(self):
        with pytest.raises(ValidationError):
            SkillCardProfile.model_validate(_good_payload(strengths=[]))

    def test_rejects_empty_aspirations(self):
        with pytest.raises(ValidationError):
            SkillCardProfile.model_validate(_good_payload(aspirations=[]))

    def test_rejects_empty_learn_grow(self):
        with pytest.raises(ValidationError):
            SkillCardProfile.model_validate(_good_payload(learn_grow=[]))

    def test_truncates_lists_to_five(self):
        ten = [f"Item{i}" for i in range(10)]
        profile = SkillCardProfile.model_validate(_good_payload(strengths=ten))
        assert len(profile.strengths) == 5
        assert profile.strengths == ten[:5]

    def test_strips_whitespace_from_strings(self):
        profile = SkillCardProfile.model_validate(
            _good_payload(
                name="  Alex Rivers  ",
                growth_focus="  bridge worlds  ",
                strengths=["  hello  ", "world\n"],
            )
        )
        assert profile.name == "Alex Rivers"
        assert profile.growth_focus == "bridge worlds"
        assert profile.strengths == ["hello", "world"]

    def test_drops_empty_string_items(self):
        profile = SkillCardProfile.model_validate(
            _good_payload(strengths=["   ", "", "real strength"])
        )
        assert profile.strengths == ["real strength"]
