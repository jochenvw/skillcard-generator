"""Demo card endpoint — returns a pre-baked persona + generated card image.

Useful for screenshots, smoke-testing the rendering pipeline, and showing off
the app without going through the full interview flow.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from profile_agent.api.auth import get_current_user
from profile_agent.config.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["demo"])


# ---------------------------------------------------------------------------
# Persona — Brad Sterling-Pinnacle, VP of Synergistic Empowerment.
# Over-the-top corporate-lingo manager. Porcupine hair, mid-meditation pose.
# ---------------------------------------------------------------------------

DEMO_CARD_DATA: dict = {
    "name": "Brad Sterling-Pinnacle",
    "title": "VP of Synergistic Empowerment",
    "industry": "Strategic Transformation Consulting",

    "strengths": [
        "Boils the ocean while keeping the lights on",
        "Moves needles, shifts paradigms, breaks silos",
        "Turns 1+1 into 3 (sometimes 4 on a good Friday)",
        "Champions radical candor in low-context rooms",
        "Operationalizes vibes into KPIs",
    ],
    "clifton_strengths": [
        "Strategic",
        "Activator",
        "Woo",
        "Maximizer",
        "Positivity",
    ],
    "inspirations": [
        "Simon Sinek — Start With Why (annotated, twice)",
        "An African proverb: 'go fast → alone, go far → together'",
        "Tony Robbins (the suit, the smile, the stage)",
        "His own LinkedIn carousel from Q3 2023",
    ],
    "aspirations": [
        "Build a self-managing org chart (no humans required)",
        "Coin a verb that ends up in the Harvard Business Review",
        "Deliver a TED talk barefoot, mid-pigeon-pose",
        "Achieve full-stack enlightenment by EOY",
    ],
    "learn_grow": [
        "Vipassana retreats (silent, but still posts a recap)",
        "Breathwork between back-to-back syncs",
        "Reading 'Atomic Habits' for the 4th time",
        "Mastering the conscious uncoupling of agendas",
        "Active listening — currently in beta",
    ],
    "accomplishments": [
        "Aligned 11 stakeholders on a single OKR (unprecedented)",
        "Reduced meeting count by 12% by adding a meta-meeting",
        "Personally onboarded the new fern in the WeWork",
        "Featured in 3 'Top Voices' lists he nominated himself for",
    ],

    "growth_focus": "Operationalize stillness — scale the inner game.",
    "flavor_text": (
        "If you want to go fast, go alone. If you want to go far, "
        "go together. If you want to go nowhere — schedule a sync."
    ),

    # Portrait override — drives the image-gen prompt for this card only.
    "portrait_hint": (
        "the subject has tall spiky porcupine-style hair sticking straight up "
        "in every direction, wears a sharp navy blazer over a white tee, sits "
        "cross-legged in a calm lotus meditation pose with eyes gently closed "
        "and a serene faint smile, hands resting on knees in a mudra; "
        "background: a sleek modern open-plan office softly out of focus with "
        "warm sunset light, a single potted bonsai on the desk"
    ),
}


@router.post("/demo")
async def demo_card_endpoint(
    user: dict = Depends(get_current_user),  # noqa: B008
) -> dict:
    """Return the demo persona card data (no image).

    Stateless. The image is generated separately via POST /api/demo/image so
    the frontend can render the card immediately and show a loader for the
    long-running portrait generation.
    """
    logger.info("POST /api/demo | user=%s", user.get("name", "anon"))
    card_data_public = {k: v for k, v in DEMO_CARD_DATA.items() if k != "portrait_hint"}
    return {"cardData": card_data_public}


@router.post("/demo/image")
async def demo_card_image_endpoint(
    user: dict = Depends(get_current_user),  # noqa: B008
) -> dict:
    """Generate the demo persona's card portrait image. Slow (~30-60s)."""
    from profile_agent.services.stateless_interview_service import _generate_card_image

    settings = get_settings()
    logger.info("POST /api/demo/image | user=%s", user.get("name", "anon"))

    image_result: dict | None = None
    try:
        result = await _generate_card_image(None, settings, DEMO_CARD_DATA)
        if result and "base64" in result:
            image_result = result
    except Exception:
        logger.exception("demo card image generation failed")

    return {"cardImage": image_result}
