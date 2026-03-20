"""Asset models for uploaded images and generated cards."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AssetMetadata(BaseModel):
    """Common metadata for any stored asset."""

    asset_id: str = ""
    session_id: str = ""
    blob_path: str = ""
    blob_url: str = ""
    content_type: str = ""
    size_bytes: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class UploadedImage(AssetMetadata):
    """Metadata for a user-uploaded profile picture."""

    original_filename: str = ""
    thumbnail_blob_path: str = ""


class GeneratedCard(AssetMetadata):
    """Metadata for a generated strengths card image."""

    prompt_used: str = ""
    model_deployment: str = ""
    generation_params: dict[str, str] = Field(default_factory=dict)
    card_spec_snapshot: dict = Field(default_factory=dict)
