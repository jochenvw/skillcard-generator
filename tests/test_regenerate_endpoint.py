"""Tests for the /api/regenerate endpoint.

Verifies that regeneration re-synthesizes the profile from stage summaries
AND generates fresh card data before regenerating the card visuals (image).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

SAMPLE_CARD_DATA = {
    "name": "Jane Doe",
    "title": "Senior Engineer",
    "industry": "Technology",
    "strengths": ["Systems thinking", "Mentorship"],
    "clifton_strengths": ["Achiever", "Learner"],
    "inspirations": ["Richard Feynman"],
    "aspirations": ["Build impactful tools"],
    "learn_grow": ["Distributed systems"],
    "accomplishments": ["Led migration to cloud"],
    "growth_focus": "Broadening technical leadership.",
    "flavor_text": "A builder at heart.",
    "photo_url": None,
    "photo_status": "skipped",
}

SAMPLE_SYNTHESIS = (
    '{"suggested_archetype": "Platform Alchemist",'
    ' "top_strengths": ["Systems thinking"], "dimensions": []}'
)


@pytest.fixture
def client():
    from profile_agent.api.auth import get_current_user
    from profile_agent.api.regenerate import router

    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "test",
        "name": "Tester",
        "email": "t@e.com",
    }
    return TestClient(app)


@pytest.fixture
def valid_payload():
    return {
        "identity": {
            "name": "Jane Doe",
            "role": "Senior Engineer at Acme",
            "title": "Senior Engineer",
            "photoStatus": "skipped",
        },
        "completedStageSummaries": [
            {"id": "introduction", "summary": "Jane is a Senior Engineer at Acme."},
            {"id": "expertise", "summary": "She specializes in distributed systems."},
        ],
        "cliftonStrengths": ["Achiever", "Learner"],
        "photoBase64": None,
        "includeImage": False,
    }


class TestRegenerateEndpoint:
    def test_returns_card_data_with_synthesis_and_card_generation(self, client, valid_payload):
        """Regenerate must call synthesis AND card generation, then return cardData."""
        with (
            patch(
                "profile_agent.services.stateless_interview_service._run_synthesis",
                new=AsyncMock(return_value=SAMPLE_SYNTHESIS),
            ) as mock_synthesis,
            patch(
                "profile_agent.services.stateless_interview_service._run_card_generation",
                new=AsyncMock(return_value=SAMPLE_CARD_DATA),
            ) as mock_card_gen,
            patch(
                "profile_agent.services.stateless_interview_service._get_openai_client",
                new=AsyncMock(return_value=MagicMock()),
            ),
        ):
            response = client.post("/api/regenerate", json=valid_payload)

        assert response.status_code == 200
        body = response.json()
        assert "cardData" in body
        assert body["cardData"]["name"] == "Jane Doe"

        # Both synthesis and card generation must have been invoked
        mock_synthesis.assert_awaited_once()
        mock_card_gen.assert_awaited_once()

    def test_synthesis_result_is_passed_to_card_generation(self, client, valid_payload):
        """The synthesis JSON output must be forwarded to _run_card_generation."""
        synthesis_output = SAMPLE_SYNTHESIS
        card_gen_received: list[str] = []

        async def capture_card_gen(client, settings, synthesis_json, *args, **kwargs):
            card_gen_received.append(synthesis_json)
            return SAMPLE_CARD_DATA

        with (
            patch(
                "profile_agent.services.stateless_interview_service._run_synthesis",
                new=AsyncMock(return_value=synthesis_output),
            ),
            patch(
                "profile_agent.services.stateless_interview_service._run_card_generation",
                new=capture_card_gen,
            ),
            patch(
                "profile_agent.services.stateless_interview_service._get_openai_client",
                new=AsyncMock(return_value=MagicMock()),
            ),
        ):
            response = client.post("/api/regenerate", json=valid_payload)

        assert response.status_code == 200
        assert card_gen_received == [synthesis_output]

    def test_image_generated_when_include_image_true(self, client, valid_payload):
        """When includeImage=True the image generation step must run."""
        valid_payload["includeImage"] = True
        with (
            patch(
                "profile_agent.services.stateless_interview_service._run_synthesis",
                new=AsyncMock(return_value=SAMPLE_SYNTHESIS),
            ),
            patch(
                "profile_agent.services.stateless_interview_service._run_card_generation",
                new=AsyncMock(return_value=SAMPLE_CARD_DATA),
            ),
            patch(
                "profile_agent.services.stateless_interview_service._generate_card_image",
                new=AsyncMock(return_value={"base64": "abc123"}),
            ) as mock_img,
            patch(
                "profile_agent.services.stateless_interview_service._get_openai_client",
                new=AsyncMock(return_value=MagicMock()),
            ),
        ):
            response = client.post("/api/regenerate", json=valid_payload)

        assert response.status_code == 200
        body = response.json()
        assert "cardData" in body
        assert body["cardImage"]["base64"] == "abc123"
        mock_img.assert_awaited_once()

    def test_image_skipped_when_include_image_false(self, client, valid_payload):
        """When includeImage=False the image generation step must be skipped."""
        valid_payload["includeImage"] = False
        with (
            patch(
                "profile_agent.services.stateless_interview_service._run_synthesis",
                new=AsyncMock(return_value=SAMPLE_SYNTHESIS),
            ),
            patch(
                "profile_agent.services.stateless_interview_service._run_card_generation",
                new=AsyncMock(return_value=SAMPLE_CARD_DATA),
            ),
            patch(
                "profile_agent.services.stateless_interview_service._generate_card_image",
                new=AsyncMock(return_value={"base64": "abc123"}),
            ) as mock_img,
            patch(
                "profile_agent.services.stateless_interview_service._get_openai_client",
                new=AsyncMock(return_value=MagicMock()),
            ),
        ):
            response = client.post("/api/regenerate", json=valid_payload)

        assert response.status_code == 200
        body = response.json()
        assert "cardData" in body
        assert "cardImage" not in body
        mock_img.assert_not_awaited()

    def test_missing_stage_summaries_returns_400(self, client):
        """Regenerate without any stage summaries must return 400."""
        payload = {
            "identity": {"name": "Test", "role": "", "title": None, "photoStatus": "unknown"},
            "completedStageSummaries": [],
            "cliftonStrengths": [],
            "includeImage": False,
        }
        response = client.post("/api/regenerate", json=payload)
        assert response.status_code == 400

    def test_stage_summaries_forwarded_to_synthesis(self, client, valid_payload):
        """The completed stage summaries from the request must reach _run_synthesis."""
        synthesis_received: list = []

        async def capture_synthesis(client, settings, completed_summaries, current_messages):
            synthesis_received.extend(completed_summaries)
            return SAMPLE_SYNTHESIS

        with (
            patch(
                "profile_agent.services.stateless_interview_service._run_synthesis",
                new=capture_synthesis,
            ),
            patch(
                "profile_agent.services.stateless_interview_service._run_card_generation",
                new=AsyncMock(return_value=SAMPLE_CARD_DATA),
            ),
            patch(
                "profile_agent.services.stateless_interview_service._get_openai_client",
                new=AsyncMock(return_value=MagicMock()),
            ),
        ):
            response = client.post("/api/regenerate", json=valid_payload)

        assert response.status_code == 200
        assert len(synthesis_received) == 2
        assert synthesis_received[0].id == "introduction"
        assert synthesis_received[1].id == "expertise"

    def test_image_generation_failure_does_not_break_card_data(self, client, valid_payload):
        """If image generation fails, cardData must still be returned."""
        valid_payload["includeImage"] = True
        with (
            patch(
                "profile_agent.services.stateless_interview_service._run_synthesis",
                new=AsyncMock(return_value=SAMPLE_SYNTHESIS),
            ),
            patch(
                "profile_agent.services.stateless_interview_service._run_card_generation",
                new=AsyncMock(return_value=SAMPLE_CARD_DATA),
            ),
            patch(
                "profile_agent.services.stateless_interview_service._generate_card_image",
                new=AsyncMock(side_effect=RuntimeError("DALL-E unavailable")),
            ),
            patch(
                "profile_agent.services.stateless_interview_service._get_openai_client",
                new=AsyncMock(return_value=MagicMock()),
            ),
        ):
            response = client.post("/api/regenerate", json=valid_payload)

        assert response.status_code == 200
        body = response.json()
        assert "cardData" in body
        assert body["cardData"]["name"] == "Jane Doe"
        assert body.get("cardImageError") == "image generation failed"
        assert "cardImage" not in body
