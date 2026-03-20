"""Extraction service — LLM-powered fact extraction from conversation turns."""

from __future__ import annotations

import json
import logging

from profile_agent.models.llm_contracts import ExtractedFact, StageExtractionResult

logger = logging.getLogger(__name__)


class ExtractionService:
    """Extracts structured facts from conversation turns using LLM calls."""

    def __init__(self, model_client, model_deployment: str = "gpt-4o") -> None:
        self._client = model_client
        self._model = model_deployment

    async def extract(
        self,
        user_text: str,
        assistant_text: str,
        stage_id: str,
        extraction_targets: list[str],
    ) -> StageExtractionResult:
        """Extract structured facts from a turn."""
        prompt = self._build_extraction_prompt(user_text, assistant_text, stage_id, extraction_targets)

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "You are a precise information extraction agent. Extract structured facts from conversation turns. Return valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_completion_tokens=800,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            data = json.loads(content)

            facts = [ExtractedFact.model_validate(f) for f in data.get("facts", [])]
            open_questions = data.get("open_questions", [])

            return StageExtractionResult(
                facts=facts,
                open_questions=open_questions,
                stage_id=stage_id,
            )
        except Exception as e:
            logger.error("Extraction failed for stage %s: %s", stage_id, e)
            return StageExtractionResult(stage_id=stage_id)

    def _build_extraction_prompt(
        self,
        user_text: str,
        assistant_text: str,
        stage_id: str,
        targets: list[str],
    ) -> str:
        return (
            f"Stage: {stage_id}\n"
            f"Extraction targets: {', '.join(targets)}\n\n"
            f"Assistant said: {assistant_text}\n\n"
            f"User responded: {user_text}\n\n"
            "Extract all relevant facts from the user's response. "
            "Return JSON with this schema:\n"
            '{"facts": [{"category": "...", "content": "...", "source_quote": "...", '
            '"confidence": "low|medium|high", "skill_dimensions": ["..."]}], '
            '"open_questions": ["..."]}'
        )
