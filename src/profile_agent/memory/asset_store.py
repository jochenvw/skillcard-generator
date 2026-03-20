"""Asset store facade — returns the configured implementation."""

from __future__ import annotations

from profile_agent.config.settings import Settings
from profile_agent.memory.base import AssetStore


async def create_asset_store(settings: Settings) -> AssetStore:
    if settings.is_dev and settings.dev_mock_blob:
        from profile_agent.memory.implementations.sqlite_store import SQLiteAssetStore

        return SQLiteAssetStore()
    else:
        from azure.storage.blob.aio import BlobServiceClient

        from profile_agent.config.settings import get_azure_credential
        from profile_agent.memory.implementations.blob_store import BlobAssetStore

        credential = await get_azure_credential(settings)
        blob_client = BlobServiceClient(
            account_url=settings.azure_storage_account_url,
            credential=credential,
        )
        return BlobAssetStore(
            blob_service_client=blob_client,
            uploads_container=settings.blob_container_uploads,
            cards_container=settings.blob_container_cards,
        )
