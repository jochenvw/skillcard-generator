"""Upload API endpoints — profile pictures and other assets."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response

from profile_agent.api.auth import get_current_user

router = APIRouter(tags=["uploads"])

_MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB
_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}


@router.post("/sessions/{session_id}/upload-picture")
async def upload_picture(
    session_id: str,
    file: UploadFile,
    user: dict = Depends(get_current_user),
):
    """Upload a profile picture for card generation."""
    if file.content_type not in _ALLOWED_TYPES:
        raise HTTPException(400, f"Unsupported image type: {file.content_type}. Use JPEG, PNG, or WebP.")

    data = await file.read()
    if len(data) > _MAX_IMAGE_SIZE:
        raise HTTPException(400, f"Image too large ({len(data)} bytes). Max {_MAX_IMAGE_SIZE} bytes.")

    from profile_agent.api.dependencies import get_asset_service

    svc = get_asset_service()
    image = await svc.upload_profile_picture(
        session_id=session_id,
        filename=file.filename or "profile.jpg",
        data=data,
        content_type=file.content_type or "image/jpeg",
    )
    return {"blob_path": image.blob_path, "size_bytes": image.size_bytes}


@router.get("/sessions/{session_id}/profile-picture")
async def get_profile_picture(
    session_id: str,
    user: dict = Depends(get_current_user),
):
    """Serve the uploaded profile picture for display in the UI."""
    from profile_agent.api.dependencies import get_asset_service

    svc = get_asset_service()
    image = await svc.get_profile_picture(session_id)
    if not image:
        raise HTTPException(404, "No profile picture uploaded for this session")

    data = await svc.download(image.blob_path)
    return Response(
        content=data,
        media_type=image.content_type or "image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )
