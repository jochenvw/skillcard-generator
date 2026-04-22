"""CliftonStrengths extraction service — stateless LLM call against arbitrary document text."""

from __future__ import annotations

import logging
from typing import Any

from profile_agent.config.settings import get_settings
from profile_agent.prompts import render_template
from profile_agent.services.stateless_interview_service import _extract_json, _get_openai_client

logger = logging.getLogger(__name__)

_VALID_THEMES = {"executing", "influencing", "relationship", "strategic"}
_MIN_STRENGTHS = 5
_MAX_STRENGTHS = 10


class StrengthsExtractionError(RuntimeError):
    """Raised when the strengths extraction LLM call or parsing fails."""


def _fallback_payload() -> dict[str, Any]:
    return {"strengths": [], "summary": ""}


def _normalize(parsed: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize the LLM JSON output to the expected shape."""
    raw_strengths = parsed.get("strengths")
    summary = parsed.get("summary", "")
    if not isinstance(raw_strengths, list) or not isinstance(summary, str):
        return _fallback_payload()

    cleaned: list[dict[str, Any]] = []
    for item in raw_strengths:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        theme = item.get("theme")
        description = item.get("description", "")
        rank = item.get("rank")
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(theme, str) or theme.lower() not in _VALID_THEMES:
            continue
        if not isinstance(description, str):
            description = str(description)
        try:
            rank_int = int(rank)
        except (TypeError, ValueError):
            rank_int = len(cleaned) + 1
        cleaned.append({
            "rank": rank_int,
            "name": name.strip(),
            "theme": theme.lower(),
            "description": description.strip(),
        })

    cleaned.sort(key=lambda s: s["rank"])
    cleaned = cleaned[:_MAX_STRENGTHS]
    for i, item in enumerate(cleaned, start=1):
        item["rank"] = i

    return {"strengths": cleaned, "summary": summary.strip()}


async def extract_strengths(text: str) -> dict[str, Any]:
    """Extract top CliftonStrengths themes from arbitrary document text.

    Stateless — does not persist or cache the input. Returns a dict with shape:
        {"strengths": [{"rank", "name", "theme", "description"}, ...], "summary": str}
    """
    if not isinstance(text, str) or not text.strip():
        raise StrengthsExtractionError("text must be a non-empty string")

    settings = get_settings()
    client = await _get_openai_client(settings)

    prompt = render_template("strengths_extraction", document_text=text)

    text_len = len(text)
    logger.info("strengths extraction request | text_len=%d", text_len)

    try:
        response = await client.chat.completions.create(
            model=settings.effective_azure_openai_deployment,
            messages=[{"role": "system", "content": prompt}],
            temperature=0.2,
            max_completion_tokens=1500,
        )
    except Exception as exc:
        logger.exception("strengths extraction LLM call failed | text_len=%d", text_len)
        raise StrengthsExtractionError("LLM request failed") from exc

    content = (response.choices[0].message.content or "") if response.choices else ""
    parsed = _extract_json(content)
    if parsed is None or not isinstance(parsed, dict):
        logger.warning("strengths extraction parse failed | text_len=%d", text_len)
        return _fallback_payload()

    result = _normalize(parsed)
    if len(result["strengths"]) < _MIN_STRENGTHS:
        logger.warning(
            "strengths extraction returned fewer than %d strengths | text_len=%d count=%d",
            _MIN_STRENGTHS, text_len, len(result["strengths"]),
        )

    logger.info(
        "strengths extraction success | text_len=%d strengths_count=%d",
        text_len, len(result["strengths"]),
    )
    return result
