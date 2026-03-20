"""Tests for prompt template loading and rendering."""

import pytest
from profile_agent.prompts import load_template, render_template


class TestPromptTemplates:
    def test_load_interview_system(self):
        template = load_template("interview_system")
        assert "conversational interviewer" in template
        assert "$stage_title" in template

    def test_load_extraction(self):
        template = load_template("extraction")
        assert "extraction agent" in template

    def test_load_validation(self):
        template = load_template("validation")
        assert "completion criteria" in template

    def test_load_compression(self):
        template = load_template("compression")
        assert "GUIDED COMPRESSION" in template

    def test_load_synthesis(self):
        template = load_template("synthesis")
        assert "skill matrix" in template

    def test_load_card_generation(self):
        template = load_template("card_generation")
        assert "trading card" in template

    def test_load_confirmation(self):
        template = load_template("confirmation")
        assert "confirmation" in template.lower()

    def test_render_interview_system(self):
        rendered = render_template(
            "interview_system",
            stage_title="Introduction",
            stage_purpose="Get to know the person",
            opening_prompt="Hi there!",
            context_summary="No context yet",
            extraction_targets="- Name\n- Role",
            follow_up_style="warm and curious",
            completion_criteria="- Learned name",
        )
        assert "Introduction" in rendered
        assert "$stage_title" not in rendered
        assert "Hi there!" in rendered

    def test_load_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            load_template("nonexistent_template")
