"""Tests for the CliftonStrengths extraction endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from profile_agent.api.auth import get_current_user
    from profile_agent.api.strengths import router

    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "test", "name": "Tester", "email": "t@e.com",
    }
    return TestClient(app)


@pytest.fixture
def mock_service_result():
    return {
        "strengths": [
            {"rank": 1, "name": "Achiever", "theme": "executing", "description": "Always shipping."},
            {"rank": 2, "name": "Learner", "theme": "strategic", "description": "Reads constantly."},
            {"rank": 3, "name": "Relator", "theme": "relationship", "description": "Deep 1:1 bonds."},
            {"rank": 4, "name": "Communication", "theme": "influencing", "description": "Clear writer."},
            {"rank": 5, "name": "Focus", "theme": "executing", "description": "Stays on target."},
        ],
        "summary": "A driven, curious engineer who builds trusted relationships.",
    }


class TestStrengthsEndpoint:
    def test_happy_path(self, client, mock_service_result):
        with patch(
            "profile_agent.services.strengths_extraction_service.extract_strengths",
            new=AsyncMock(return_value=mock_service_result),
        ):
            response = client.post("/api/extract-strengths", json={"text": "Some bio text."})
        assert response.status_code == 200
        body = response.json()
        assert "strengths" in body and "summary" in body
        assert len(body["strengths"]) == 5
        assert body["strengths"][0]["rank"] == 1
        assert body["strengths"][0]["theme"] in {"executing", "influencing", "relationship", "strategic"}

    def test_empty_text_rejected(self, client):
        response = client.post("/api/extract-strengths", json={"text": ""})
        # Pydantic min_length=1 → 422; whitespace-only → 400 from handler
        assert response.status_code == 422

    def test_whitespace_only_rejected(self, client):
        response = client.post("/api/extract-strengths", json={"text": "   \n\t  "})
        assert response.status_code == 400

    def test_oversize_text_rejected(self, client):
        oversized = "x" * 200_001
        response = client.post("/api/extract-strengths", json={"text": oversized})
        # Pydantic max_length validation kicks in first → 422
        assert response.status_code == 422

    def test_service_error_returns_500(self, client):
        from profile_agent.services.strengths_extraction_service import StrengthsExtractionError

        with patch(
            "profile_agent.services.strengths_extraction_service.extract_strengths",
            new=AsyncMock(side_effect=StrengthsExtractionError("boom")),
        ):
            response = client.post("/api/extract-strengths", json={"text": "Some bio text."})
        assert response.status_code == 500
        assert "boom" not in response.text  # generic message, no leak

    def test_missing_text_field(self, client):
        response = client.post("/api/extract-strengths", json={})
        assert response.status_code == 422
