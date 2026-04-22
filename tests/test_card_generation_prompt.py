"""Tests for the card_generation prompt template rendering."""

from __future__ import annotations

from profile_agent.prompts import render_template


def _render(**overrides) -> str:
    defaults = {
        "display_name": "Sam Sample",
        "archetype": "Platform Alchemist",
        "top_strengths": '["Systems thinking"]',
        "skill_matrix": "[]",
        "evidence_highlights": "- foo: bar",
        "clifton_strengths": "• Strategic\n• Learner",
    }
    defaults.update(overrides)
    return render_template("card_generation", **defaults)


class TestCardGenerationPrompt:
    def test_all_template_vars_substituted(self):
        out = _render()
        assert "Sam Sample" in out
        assert "Platform Alchemist" in out
        assert "Systems thinking" in out
        assert "• Strategic" in out
        assert "$display_name" not in out
        assert "$clifton_strengths" not in out
        assert "$archetype" not in out

    def test_drops_gamey_field_instructions(self):
        out = _render()
        for banned in ["top_stats", "weaknesses", "signature_ability", "rarity", "xp_to_next_level"]:
            assert banned in out  # mentioned in the "do NOT output" list — that's fine
        # The example must NOT contain the gamey JSON keys in object form
        assert '"top_stats":' not in out
        assert '"weaknesses":' not in out
        assert '"signature_ability":' not in out
        assert '"rarity":' not in out
        assert '"level":' not in out

    def test_includes_required_section_headers(self):
        out = _render()
        for header in [
            "Profile Source Material",
            "Skill Matrix",
            "Evidence Highlights",
            "CliftonStrengths",
            "Field mapping",
            "Response Format",
            "Example",
        ]:
            assert header in out

    def test_example_is_present_with_new_schema(self):
        out = _render()
        assert "Alex Rivers" in out
        assert '"name":' in out
        assert '"strengths":' in out
        assert '"clifton_strengths":' in out
        assert '"inspirations":' in out
        assert '"aspirations":' in out
        assert '"learn_grow":' in out
        assert '"accomplishments":' in out
        assert '"growth_focus":' in out
        assert '"flavor_text":' in out

    def test_empty_clifton_strengths_renders_cleanly(self):
        out = _render(clifton_strengths="")
        assert "CliftonStrengths" in out
