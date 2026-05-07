"""Tests for the health API endpoints."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from profile_agent.api.health import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestHealthEndpoints:
    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"
        assert "version" in body

    def test_readiness(self, client):
        response = client.get("/readiness")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ready"
        assert "version" in body
