"""Azure Blob Storage implementation for binary assets."""

from __future__ import annotations

import uuid
from typing import Any

from azure.storage.blob.aio import BlobServiceClient

from profile_agent.memory.base import AssetStore
from profile_agent.models.assets import GeneratedCard, UploadedImage


class BlobAssetStore(AssetStore):
    """Stores uploaded images and generated card images in Azure Blob Storage."""

    def __init__(
        self,
        blob_service_client: BlobServiceClient,
        uploads_container: str = "uploads",
        cards_container: str = "cards",
    ) -> None:
        self._blob = blob_service_client
        self._uploads_container = uploads_container
        self._cards_container = cards_container

    async def upload_image(self, session_id: str, filename: str, data: bytes, content_type: str) -> UploadedImage:
        asset_id = str(uuid.uuid4())
        blob_path = f"{session_id}/{asset_id}_{filename}"
        container = self._blob.get_container_client(self._uploads_container)
        await container.upload_blob(name=blob_path, data=data, content_settings=_content_settings(content_type))

        return UploadedImage(
            asset_id=asset_id,
            session_id=session_id,
            blob_path=blob_path,
            blob_url=f"{container.url}/{blob_path}",
            content_type=content_type,
            size_bytes=len(data),
            original_filename=filename,
        )

    async def save_generated_card(
        self, session_id: str, image_data: bytes, content_type: str, metadata: dict[str, Any]
    ) -> GeneratedCard:
        asset_id = str(uuid.uuid4())
        blob_path = f"{session_id}/{asset_id}.png"
        container = self._blob.get_container_client(self._cards_container)
        await container.upload_blob(name=blob_path, data=image_data, content_settings=_content_settings(content_type))

        return GeneratedCard(
            asset_id=asset_id,
            session_id=session_id,
            blob_path=blob_path,
            blob_url=f"{container.url}/{blob_path}",
            content_type=content_type,
            size_bytes=len(image_data),
            prompt_used=metadata.get("prompt_used", ""),
            model_deployment=metadata.get("model_deployment", ""),
        )

    async def get_uploaded_image(self, session_id: str) -> UploadedImage | None:
        # Metadata lookup should come from Cosmos/SQLite — this store handles bytes only.
        return None

    async def get_generated_card(self, session_id: str) -> GeneratedCard | None:
        return None

    async def download_asset(self, blob_path: str) -> bytes:
        # Determine container from path convention
        if "/uploads/" in blob_path or self._uploads_container in blob_path:
            container = self._blob.get_container_client(self._uploads_container)
        else:
            container = self._blob.get_container_client(self._cards_container)
        blob = container.get_blob_client(blob_path.split("/", 1)[-1] if "/" in blob_path else blob_path)
        download = await blob.download_blob()
        return await download.readall()


def _content_settings(content_type: str):
    from azure.storage.blob import ContentSettings

    return ContentSettings(content_type=content_type)
