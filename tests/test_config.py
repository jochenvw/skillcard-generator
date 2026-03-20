"""Tests for the settings configuration."""

import pytest

from profile_agent.config.settings import Settings


class TestSettings:
    def test_default_settings(self):
        settings = Settings()
        assert settings.environment.value == "dev"
        assert settings.run_mode.value == "web"

    def test_production_settings(self):
        settings = Settings(
            environment="prod",
            run_mode="foundry",
        )
        assert settings.environment.value == "prod"
        assert settings.run_mode.value == "foundry"
