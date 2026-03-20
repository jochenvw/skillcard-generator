"""Card generation workflow — synthesize card spec and generate image."""

from __future__ import annotations

import logging

from profile_agent.models.assets import GeneratedCard
from profile_agent.models.llm_contracts import CardAbility, CardSpec, ImageGenerationRequest, ImageGenerationResult
from profile_agent.models.profile import UserProfile
from profile_agent.models.skill_matrix import SkillMatrix

logger = logging.getLogger(__name__)


class CardGenerationWorkflow:
    """Generates the final strengths card from a completed profile.

    Pipeline:
    1. Build CardSpec from profile + skill matrix
    2. Generate image prompt from CardSpec
    3. Call image generation API
    4. Store generated card asset
    """

    def __init__(self, session_id: str, profile: UserProfile, skill_matrix: SkillMatrix) -> None:
        self._session_id = session_id
        self._profile = profile
        self._skill_matrix = skill_matrix

    def build_card_spec(self) -> CardSpec:
        """Build a CardSpec from the profile and skill matrix."""
        # Top abilities from strong/expert skills
        abilities = []
        for dim in self._skill_matrix.strong_areas[:8]:
            abilities.append(CardAbility(
                name=dim.dimension.replace("_", " ").title(),
                description=dim.evidence[0] if dim.evidence else "",
                power_level=9 if dim.score.value == "expert" else 7,
            ))

        # Signature domains from domain affinities
        signature_domains = [da.domain for da in self._profile.domain_affinities[:6]]

        # Determine rarity based on number of strong areas
        strong_count = len(self._skill_matrix.strong_areas)
        if strong_count >= 8:
            rarity = "mythic"
        elif strong_count >= 5:
            rarity = "legendary"
        elif strong_count >= 3:
            rarity = "rare"
        else:
            rarity = "uncommon"

        return CardSpec(
            session_id=self._session_id,
            display_name=self._profile.identity.display_name,
            title=self._profile.identity.title,
            archetype=self._profile.identity.archetype,
            flavor_text=self._profile.identity.flavor_text,
            abilities=abilities,
            signature_domains=signature_domains,
            rarity=rarity,
            portrait_description=self._build_portrait_description(),
        )

    def build_image_prompt(self, card_spec: CardSpec) -> str:
        """Generate a DALL-E prompt from the CardSpec."""
        abilities_text = ", ".join(a.name for a in card_spec.abilities[:6])

        return (
            f"A fantasy-style collectible card featuring a stylized portrait of a person. "
            f"The card title is '{card_spec.archetype}'. "
            f"The person is a {card_spec.title} with abilities: {abilities_text}. "
            f"Style: Pokémon/Magic: The Gathering card art, vibrant colors, "
            f"professional digital illustration, ornate card border with "
            f"{card_spec.rarity} rarity styling. "
            f"The portrait should be heroic and inspiring but respectful. "
            f"Include subtle visual elements representing their domains: "
            f"{', '.join(card_spec.signature_domains[:4])}. "
            f"Flavor text at bottom: \"{card_spec.flavor_text[:100]}\" "
            f"High quality, detailed, fantasy art style."
        )

    def create_image_request(self, card_spec: CardSpec, model_deployment: str = "") -> ImageGenerationRequest:
        """Create the image generation request."""
        return ImageGenerationRequest(
            prompt=self.build_image_prompt(card_spec),
            model_deployment=model_deployment,
            size="1024x1024",
            quality="hd",
            style="vivid",
            session_id=self._session_id,
        )

    def _build_portrait_description(self) -> str:
        """Build a text description of the person for image generation.

        Note: Azure OpenAI DALL-E 3 does not support reference-image input.
        This text description is used instead. The image_service adapter is
        designed so a future model with reference-image support can be swapped in.
        """
        parts = [f"A {self._profile.identity.title or 'technologist'}"]
        if self._profile.identity.archetype:
            parts.append(f"embodying the archetype of '{self._profile.identity.archetype}'")
        if self._profile.values:
            parts.append(f"who values {', '.join(self._profile.values[:3])}")
        return " ".join(parts)
