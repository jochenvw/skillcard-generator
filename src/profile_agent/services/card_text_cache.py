"""In-process cache for generated card *text* (the cardData JSON).

Mirrors ``image_cache`` for the text side of regeneration. The /api/regenerate
endpoint hits OpenAI twice (synthesis + card generation, ~25-30s combined) with
``temperature=0.4`` — so identical re-clicks would otherwise produce slightly
different cards every time AND incur full LLM cost. This cache short-circuits
that for byte-identical inputs.

Storage: ``<repo>/.cache/card_text/<sha256>.json`` — single JSON document
(the cardData dict). The directory is created lazily and is gitignored.
The cache lives only for the lifetime of the container's filesystem, so a
restart wipes it — exactly the behaviour the user asked for.

Cache key inputs (must be free of timestamps / random values, audited
2026-05-07):

* identity name + role + title + photoStatus
* sorted (id, summary) tuples of completed stage summaries
* sorted clifton strengths
* canonical-JSON (sort_keys=True) dumps of linkedin_skills, github_skills,
  bulk_extracted, style
* model deployment name (so a model upgrade busts the cache)

The reference photo is **not** part of the key — the photo only affects the
generated image, never the text card.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Same parents-up depth as image_cache.py so both caches sit next to each other.
_CACHE_DIR = Path(__file__).resolve().parents[3] / ".cache" / "card_text"


def _canonical(value: Any) -> str:
    """Deterministic JSON for any JSON-able input — keys sorted, no whitespace."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_key(
    *,
    deployment: str,
    identity: dict[str, Any],
    completed_stages: list[dict[str, str]],
    clifton_strengths: list[str],
    linkedin_skills: dict | None,
    github_skills: dict | None,
    bulk_extracted: dict | None,
    style: dict | None,
) -> str:
    """SHA-256 of every input that influences the cardData output."""
    payload = {
        "deployment": deployment,
        "identity": {
            "name": (identity.get("name") or "").strip(),
            "role": (identity.get("role") or "").strip(),
            "title": (identity.get("title") or "").strip(),
            "photoStatus": (identity.get("photoStatus") or "").strip(),
        },
        # Sort by id so client-side reordering doesn't bust the cache.
        "stages": sorted(
            ({"id": s.get("id", ""), "summary": s.get("summary", "")} for s in completed_stages),
            key=lambda x: x["id"],
        ),
        "clifton": sorted(s.strip() for s in clifton_strengths if isinstance(s, str) and s.strip()),
        "linkedin": linkedin_skills or None,
        "github": github_skills or None,
        "bulk": bulk_extracted or None,
        "style": style or None,
    }
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _path_for(key: str) -> Path:
    return _CACHE_DIR / f"{key}.json"


def get(key: str) -> dict | None:
    """Return cached cardData dict, or None on miss / corrupt entry."""
    p = _path_for(key)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        logger.info("Card text cache HIT key=%s", key[:12])
        return data
    except Exception:
        logger.exception("Failed to read card text cache key=%s", key[:12])
        return None


def put(key: str, card_data: dict) -> None:
    """Persist cardData under the content-addressed key."""
    if not isinstance(card_data, dict) or not card_data:
        return
    p = _path_for(key)
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        p.write_text(_canonical(card_data), encoding="utf-8")
        logger.info("Card text cache STORE key=%s (%d bytes)", key[:12], p.stat().st_size)
    except Exception:
        logger.exception("Failed to write card text cache key=%s", key[:12])
