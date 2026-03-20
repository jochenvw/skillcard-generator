"""Pytest configuration and shared fixtures."""

import pytest


@pytest.fixture
def sample_session_id():
    return "test-session-001"


@pytest.fixture
def sample_user_id():
    return "test-user-001"
