"""Tests for the card-image prompt builder (style customization)."""

from __future__ import annotations

from profile_agent.models.llm_contracts import CardStyle
from profile_agent.services.stateless_interview_service import _build_card_image_prompt

SAMPLE_CARD = {
    "name": "Sam Sample",
    "title": "Engineer",
    "industry": "Technology",
    "strengths": ["Systems thinking", "Pragmatic synthesis"],
    "clifton_strengths": ["Strategic", "Learner"],
    "inspirations": ["Open-source maintainers"],
    "aspirations": ["Build meaningful systems"],
    "learn_grow": ["Distributed systems"],
    "accomplishments": ["Shipped X"],
    "growth_focus": "Sharpen breadth.",
    "flavor_text": "A quiet maker.",
}


# Snapshot of the prompt the implementation produced before the customization
# feature existed. Locks in "no style == current look".
EXPECTED_DEFAULT = (
    'A premium, high-end digital trading card for a futuristic skill-based game. '
    'Full card layout, vertical orientation.\n\n'
    'Design:\n'
    '- metallic sci-fi frame with beveled edges\n'
    '- layered UI panels with depth and shadows\n'
    '- blue and cyan glowing accents\n'
    '- polished, sharp, AAA game UI quality\n'
    '- high contrast, crisp edges, no blur\n\n'
    'Top section:\n'
    '- bold header bar reading "SKILL DECK"\n'
    '- name plate reading "Sam Sample" with subtitle "Engineer · Technology"\n\n'
    'Portrait:\n'
    '- centered character portrait inside a framed window\n'
    '- the person is a confident professional, Engineer appearance\n'
    '- background: blurred tech dashboards, code, holographic graphs\n'
    '- cinematic lighting, rim light, sharp focus\n\n'
    'Lower sections (six panels in a 2-column grid, consistent spacing, grid-aligned):\n'
    '- left panel titled "STRENGTHS" (blue-themed):\n'
    '• Systems thinking\n• Pragmatic synthesis\n\n'
    '- right panel titled "CLIFTON STRENGTHS" (purple-themed):\n'
    '• Strategic\n• Learner\n\n'
    '- next row left panel titled "INSPIRATIONS":\n'
    '• Open-source maintainers\n\n'
    '- next row right panel titled "ASPIRATIONS":\n'
    '• Build meaningful systems\n\n'
    '- next row left panel titled "LEARN / GROW":\n'
    '• Distributed systems\n\n'
    '- next row right panel titled "ACCOMPLISHMENTS":\n'
    '• Shipped X\n\n'
    '- clean separation between all panels, grid-aligned, consistent spacing\n\n'
    'Bottom section:\n'
    '- growth focus tagline: "Sharpen breadth."\n'
    '- flavor text quote: "A quiet maker."\n\n'
    'Style: clean structured UI, resembles a collectible card game interface, '
    'precise alignment, symmetrical layout, subtle gradients and metallic textures.\n'
    'Quality: ultra detailed, sharp legible typography, no distortions, consistent spacing.'
)


class TestDefaultLook:
    def test_no_style_matches_snapshot(self):
        assert _build_card_image_prompt(SAMPLE_CARD, None) == EXPECTED_DEFAULT

    def test_empty_style_matches_snapshot(self):
        empty = CardStyle()
        assert _build_card_image_prompt(SAMPLE_CARD, empty) == EXPECTED_DEFAULT

    def test_default_named_presets_are_no_op(self):
        # Selecting the explicit "current" defaults from the UI must not change the prompt.
        s = CardStyle(
            style_preset="Futuristic Metallic",
            persona_setting="Professional",
            accent_color=None,
        )
        assert _build_card_image_prompt(SAMPLE_CARD, s) == EXPECTED_DEFAULT


class TestStylePreset:
    def test_cyberpunk_replaces_design_block(self):
        out = _build_card_image_prompt(SAMPLE_CARD, CardStyle(style_preset="Cyberpunk Neon"))
        assert "cyberpunk" in out.lower()
        assert "neon" in out.lower()
        # Default metallic frame description should be gone.
        assert "metallic sci-fi frame with beveled edges" not in out
        # Outro style line is the cyberpunk one.
        assert "neon-drenched" in out

    def test_pokemon_preset(self):
        out = _build_card_image_prompt(SAMPLE_CARD, CardStyle(style_preset="Pokémon TCG"))
        assert "holofoil" in out.lower()
        assert "metallic sci-fi frame with beveled edges" not in out

    def test_unknown_preset_falls_back_to_default(self):
        out = _build_card_image_prompt(SAMPLE_CARD, CardStyle(style_preset="Made-Up-Style"))
        # Unknown values must not mangle the prompt — fall through to default.
        assert out == EXPECTED_DEFAULT


class TestPersona:
    def test_superhero_replaces_portrait_line(self):
        out = _build_card_image_prompt(SAMPLE_CARD, CardStyle(persona_setting="Superhero"))
        assert "superhero" in out.lower()
        assert "facial likeness from the reference photo" in out
        # The default professional line should be replaced.
        assert "the person is a confident professional, Engineer appearance" not in out

    def test_unknown_persona_keeps_default(self):
        out = _build_card_image_prompt(SAMPLE_CARD, CardStyle(persona_setting="Pirate Captain"))
        assert "the person is a confident professional, Engineer appearance" in out


class TestAccentColor:
    def test_accent_color_replaces_default_line(self):
        out = _build_card_image_prompt(SAMPLE_CARD, CardStyle(accent_color="hot pink"))
        assert "- hot pink glowing accents" in out
        assert "- blue and cyan glowing accents" not in out

    def test_accent_color_with_preset(self):
        # The accent color line replacement should also apply within preset blocks.
        out = _build_card_image_prompt(
            SAMPLE_CARD,
            CardStyle(style_preset="Cyberpunk Neon", accent_color="#ff00aa"),
        )
        assert "- #ff00aa glowing accents" in out

    def test_empty_accent_color_is_noop(self):
        out = _build_card_image_prompt(SAMPLE_CARD, CardStyle(accent_color=""))
        assert out == EXPECTED_DEFAULT


class TestLayoutInvariant:
    """All section headers must be present regardless of style — the layout
    is non-negotiable per the user's requirement."""

    REQUIRED = [
        'reading "SKILL DECK"',
        '"STRENGTHS"',
        '"CLIFTON STRENGTHS"',
        '"INSPIRATIONS"',
        '"ASPIRATIONS"',
        '"LEARN / GROW"',
        '"ACCOMPLISHMENTS"',
        'growth focus tagline:',
        'flavor text quote:',
    ]

    def test_layout_preserved_with_full_customization(self):
        out = _build_card_image_prompt(
            SAMPLE_CARD,
            CardStyle(
                style_preset="Cyberpunk Neon",
                persona_setting="Superhero",
                accent_color="electric magenta",
            ),
        )
        for token in self.REQUIRED:
            assert token in out, f"Missing required layout element: {token}"
