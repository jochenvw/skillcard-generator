"""Prompt template loading and rendering."""

from __future__ import annotations

import logging
from pathlib import Path
from string import Template

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def load_template(name: str) -> str:
    """Load a prompt template by name (without extension)."""
    path = _TEMPLATE_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8")


def render_template(name: str, **kwargs: str) -> str:
    """Load and render a prompt template with $-style substitution."""
    raw = load_template(name)
    return Template(raw).safe_substitute(**kwargs)
