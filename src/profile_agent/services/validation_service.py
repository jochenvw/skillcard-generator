"""Validation service — checks stage completion criteria."""

from __future__ import annotations

import json
import logging

from profile_agent.models.llm_contracts import ExtractedFact, StageValidationResult, ValidationIssue

logger = logging.getLogger(__name__)


class ValidationService:
    """Validates whether a stage's completion criteria have been met."""

    def __init__(self, model_client, model_deployment: str = "gpt-4o") -> None:
        self._client = model_client
        self._model = model_deployment

    async def validate(
        self,
        stage_id: str,
        completion_criteria: list[str],
        extracted_facts: list[ExtractedFact],
    ) -> StageValidationResult:
        """Check completion criteria against extracted facts."""
        prompt = self._build_validation_prompt(stage_id, completion_criteria, extracted_facts)

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "You evaluate whether interview stage completion criteria have been met based on extracted evidence. Return valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_completion_tokens=600,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            data = json.loads(content)

            issues = [ValidationIssue.model_validate(i) for i in data.get("issues", [])]

            return StageValidationResult(
                stage_id=stage_id,
                is_complete=data.get("is_complete", False),
                issues=issues,
                missing_information=data.get("missing_information", []),
                suggested_next_question=data.get("suggested_next_question", ""),
            )
        except Exception as e:
            logger.error("Validation failed for stage %s: %s", stage_id, e)
            return StageValidationResult(stage_id=stage_id, is_complete=False)

    def _build_validation_prompt(
        self,
        stage_id: str,
        criteria: list[str],
        facts: list[ExtractedFact],
    ) -> str:
        facts_text = "\n".join(f"- [{f.category}] {f.content}" for f in facts) if facts else "No facts extracted yet."
        criteria_text = "\n".join(f"- {c}" for c in criteria)

        return (
            f"Stage: {stage_id}\n\n"
            f"Completion criteria:\n{criteria_text}\n\n"
            f"Extracted facts so far:\n{facts_text}\n\n"
            "Evaluate each criterion. Return JSON:\n"
            '{"is_complete": true/false, "issues": [{"criterion": "...", "met": true/false, "detail": "..."}], '
            '"missing_information": ["..."], "suggested_next_question": "..."}'
        )
