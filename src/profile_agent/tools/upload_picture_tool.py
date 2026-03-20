"""Tool: Handle profile picture upload to storage."""

from __future__ import annotations

import logging
from typing import BinaryIO

from profile_agent.memory.base import AssetStore
from profile_agent.models.assets import UploadedImage

logger = logging.getLogger(__name__)

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


async def upload_profile_picture(
    asset_store: AssetStore,
    session_id: str,
    filename: str,
    data: bytes,
    content_type: str,
) -> UploadedImage | str:
    """Upload a profile picture. Returns UploadedImage on success, error string on failure."""
    if content_type not in ALLOWED_CONTENT_TYPES:
        return f"Unsupported image type: {content_type}. Accepted: JPEG, PNG, WebP, GIF."

    if len(data) > MAX_SIZE_BYTES:
        return f"Image too large ({len(data) / 1024 / 1024:.1f} MB). Maximum: 10 MB."

    if len(data) == 0:
        return "Empty file received."

    image = await asset_store.upload_image(session_id, filename, data, content_type)
    logger.info("Uploaded profile picture for session %s: %s (%d bytes)", session_id, filename, len(data))
    return image
