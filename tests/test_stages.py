"""Tests for stage loading and definitions."""

import pytest
from pathlib import Path


class TestStageLoader:
    def test_load_stages(self):
        from profile_agent.stages.loader import load_stages

        stages = load_stages()
        assert len(stages) == 10
        assert stages[0].id == "introduction"
        assert stages[-1].id == "card_generation"

    def test_stages_have_required_fields(self):
        from profile_agent.stages.loader import load_stages

        stages = load_stages()
        for stage in stages:
            assert stage.title, f"Stage {stage.id} missing title"
            assert stage.purpose, f"Stage {stage.id} missing purpose"
            assert stage.opening_prompt, f"Stage {stage.id} missing opening_prompt"
            assert len(stage.completion_criteria) > 0, f"Stage {stage.id} missing completion_criteria"
            assert len(stage.extraction_targets) > 0, f"Stage {stage.id} missing extraction_targets"

    def test_stages_sorted_by_prefix(self):
        from profile_agent.stages.loader import load_stages

        stages = load_stages()
        ids = [s.id for s in stages]
        assert ids[0] == "introduction"
        assert ids[1] == "heroes"

    def test_build_stage_index(self):
        from profile_agent.stages.loader import load_stages, build_stage_index

        stages = load_stages()
        index = build_stage_index(stages)
        assert "introduction" in index
        assert "card_generation" in index
        assert len(index) == 10


class TestStageDefinitionYaml:
    def test_yaml_files_exist(self):
        definitions_dir = Path(__file__).parent.parent / "src" / "profile_agent" / "stages" / "definitions"
        yaml_files = sorted(definitions_dir.glob("*.yaml"))
        assert len(yaml_files) == 10

    def test_yaml_files_have_correct_prefixes(self):
        definitions_dir = Path(__file__).parent.parent / "src" / "profile_agent" / "stages" / "definitions"
        yaml_files = sorted(definitions_dir.glob("*.yaml"))
        expected_prefixes = ["00", "10", "20", "30", "40", "50", "60", "70", "80", "90"]
        for f, prefix in zip(yaml_files, expected_prefixes):
            assert f.name.startswith(prefix), f"Expected {f.name} to start with {prefix}"
