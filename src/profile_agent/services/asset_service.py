"""Asset service — manages blob storage uploads and downloads."""

from __future__ import annotations

import logging
from typing import Any

from profile_agent.memory.base import AssetStore
from profile_agent.models.assets import GeneratedCard, UploadedImage

logger = logging.getLogger(__name__)


class AssetService:
    """High-level asset operations wrapping the store layer."""

    def __init__(self, asset_store: AssetStore) -> None:
        self._store = asset_store

    async def upload_profile_picture(
        self, session_id: str, filename: str, data: bytes, content_type: str
    ) -> UploadedImage:
        image = await self._store.upload_image(session_id, filename, data, content_type)
        logger.info("Uploaded profile picture: %s (%d bytes)", image.blob_path, image.size_bytes)
        return image

    async def save_card_image(
        self, session_id: str, image_data: bytes, metadata: dict[str, Any]
    ) -> GeneratedCard:
        card = await self._store.save_generated_card(
            session_id=session_id,
            image_data=image_data,
            content_type="image/png",
            metadata=metadata,
        )
        logger.info("Saved generated card: %s (%d bytes)", card.blob_path, card.size_bytes)
        return card

    async def get_profile_picture(self, session_id: str) -> UploadedImage | None:
        return await self._store.get_uploaded_image(session_id)

    async def get_card(self, session_id: str) -> GeneratedCard | None:
        return await self._store.get_generated_card(session_id)

    async def download(self, blob_path: str) -> bytes:
        return await self._store.download_asset(blob_path)
