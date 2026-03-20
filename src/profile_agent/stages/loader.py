"""Stage definition loader — reads YAML files and returns validated StageDefinition list."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from profile_agent.stages.models import StageDefinition

logger = logging.getLogger(__name__)

_DEFAULT_DEFINITIONS_DIR = Path(__file__).parent / "definitions"


def load_stages(definitions_dir: Path | None = None) -> list[StageDefinition]:
    """Load all YAML stage definitions, validate, and return sorted by filename prefix."""
    directory = definitions_dir or _DEFAULT_DEFINITIONS_DIR
    if not directory.exists():
        raise FileNotFoundError(f"Stage definitions directory not found: {directory}")

    stages: list[StageDefinition] = []
    for yaml_file in sorted(directory.glob("*.yaml")):
        logger.info("Loading stage definition: %s", yaml_file.name)
        with open(yaml_file, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        if raw is None:
            logger.warning("Empty stage file: %s", yaml_file.name)
            continue
        # Use filename prefix as sort_order if not set
        try:
            prefix = int(yaml_file.stem.split("_")[0])
        except (ValueError, IndexError):
            prefix = 999
        raw.setdefault("sort_order", prefix)
        stage = StageDefinition.model_validate(raw)
        stages.append(stage)

    stages.sort(key=lambda s: s.sort_order)
    logger.info("Loaded %d stage definitions", len(stages))
    return stages


def build_stage_index(stages: list[StageDefinition]) -> dict[str, StageDefinition]:
    """Build a lookup dict keyed by stage id."""
    return {s.id: s for s in stages}
