"""Application settings loaded from environment variables and .env files."""

from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from urllib.parse import urlparse
from typing import TYPE_CHECKING

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from azure.core.credentials_async import AsyncTokenCredential


class Environment(str, Enum):
    DEV = "dev"
    TEST = "test"
    PROD = "prod"


class RunMode(str, Enum):
    WEB = "web"
    FOUNDRY = "foundry"


class Settings(BaseSettings):
    """Central configuration — reads from env vars / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Runtime
    environment: Environment = Environment.DEV
    run_mode: RunMode = RunMode.WEB

    # Azure AI Foundry
    foundry_project_endpoint: str = ""
    foundry_model_deployment_name: str = "gpt-5.4"
    foundry_image_deployment_name: str = "gpt-image-2-1"
    foundry_image_fallback_deployment_name: str = "gpt-image-1.5"
    # Optional: route image generation through an APIM gateway (or any custom endpoint).
    # When set, the image client uses this endpoint instead of the derived AI Services URL.
    # If foundry_image_api_key is also set, API-key auth is used; otherwise AAD is used.
    foundry_image_endpoint_override: str = ""
    foundry_image_api_key: str = ""

    # Azure OpenAI direct/model endpoint settings
    azure_openai_endpoint: str = ""
    azure_openai_key: str = ""
    azure_openai_deployment: str = ""
    azure_openai_api_version: str = "2025-04-01-preview"

    # Application Insights
    # Bicep injects APPLICATIONINSIGHTS_CONNECTION_STRING; legacy env var is APPINSIGHTS_CONNECTION_STRING.
    appinsights_connection_string: str = Field(
        default="",
        validation_alias=AliasChoices(
            "APPLICATIONINSIGHTS_CONNECTION_STRING",
            "APPINSIGHTS_CONNECTION_STRING",
            "appinsights_connection_string",
        ),
    )

    # Microsoft Entra ID
    entra_client_id: str = ""
    entra_tenant_id: str = ""
    entra_client_secret: str = ""
    entra_redirect_uri: str = "http://localhost:8000/api/auth/callback"

    # Managed identity override (user-assigned)
    azure_client_id: str = ""

    # Local dev flags
    dev_auth_bypass: bool = False

    # Server
    host: str = "0.0.0.0"
    web_port: int = Field(default=8000, alias="PORT")
    foundry_port: int = 8088

    @property
    def is_dev(self) -> bool:
        return self.environment == Environment.DEV

    @property
    def is_prod(self) -> bool:
        return self.environment == Environment.PROD

    @property
    def effective_azure_openai_endpoint(self) -> str:
        if self.azure_openai_endpoint:
            return self.azure_openai_endpoint
        if not self.foundry_project_endpoint:
            return ""

        host = urlparse(self.foundry_project_endpoint).hostname or ""
        if host.endswith(".services.ai.azure.com"):
            resource_name = host.removesuffix(".services.ai.azure.com")
            return f"https://{resource_name}.openai.azure.com"
        return ""

    @property
    def effective_azure_openai_deployment(self) -> str:
        return self.azure_openai_deployment or self.foundry_model_deployment_name


async def get_azure_credential(settings: Settings) -> AsyncTokenCredential:
    """Return the appropriate async Azure credential for the current environment.

    Local dev → DefaultAzureCredential (chains CLI / VS Code / env).
    Production → ManagedIdentityCredential (deterministic, no fallback chain).
    """
    if settings.is_dev:
        from azure.identity.aio import DefaultAzureCredential

        return DefaultAzureCredential()
    else:
        from azure.identity.aio import ManagedIdentityCredential

        kwargs = {}
        if settings.azure_client_id:
            kwargs["client_id"] = settings.azure_client_id
        return ManagedIdentityCredential(**kwargs)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton settings instance."""
    # Ensure .env is loaded before Pydantic reads env vars
    try:
        from dotenv import load_dotenv

        load_dotenv(override=False)
    except ImportError:
        pass
    return Settings()  # type: ignore[call-arg]
