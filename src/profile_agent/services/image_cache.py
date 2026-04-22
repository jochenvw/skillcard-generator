"""Local content-addressed cache for generated card images.

The cache key is a SHA-256 of the exact image-gen inputs (prompt + reference
photo bytes + deployment name + size). Any change → new key → cache miss →
re-generation. Cache hits return instantly without calling the model.

Storage: <repo>/.cache/card_images/<sha256>.b64 — plain base64 string (PNG).
The directory is created lazily and is gitignored.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Cache lives at the repo root (3 levels up from this file:
# src/profile_agent/services/image_cache.py).
_CACHE_DIR = Path(__file__).resolve().parents[3] / ".cache" / "card_images"


def _key(prompt: str, photo_bytes: bytes | None, deployment: str, size: str) -> str:
    h = hashlib.sha256()
    h.update(deployment.encode("utf-8"))
    h.update(b"\x00")
    h.update(size.encode("utf-8"))
    h.update(b"\x00")
    h.update(prompt.encode("utf-8"))
    h.update(b"\x00")
    if photo_bytes:
        h.update(photo_bytes)
    return h.hexdigest()


def _path_for(key: str) -> Path:
    return _CACHE_DIR / f"{key}.b64"


def get(prompt: str, photo_bytes: bytes | None, deployment: str, size: str) -> str | None:
    """Return cached base64 PNG if present, else None."""
    key = _key(prompt, photo_bytes, deployment, size)
    p = _path_for(key)
    if not p.exists():
        return None
    try:
        data = p.read_text(encoding="utf-8").strip()
        if not data:
            return None
        logger.info("Card image cache HIT key=%s (%d chars)", key[:12], len(data))
        return data
    except Exception:
        logger.exception("Failed to read card image cache key=%s", key[:12])
        return None


def put(prompt: str, photo_bytes: bytes | None, deployment: str, size: str, b64: str) -> None:
    """Persist base64 PNG under the content-addressed key."""
    if not b64:
        return
    key = _key(prompt, photo_bytes, deployment, size)
    p = _path_for(key)
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        p.write_text(b64, encoding="utf-8")
        logger.info("Card image cache STORE key=%s (%d chars)", key[:12], len(b64))
    except Exception:
        logger.exception("Failed to write card image cache key=%s", key[:12])
