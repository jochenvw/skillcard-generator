"""Compression service — guided context compression for long stages."""

from __future__ import annotations

import json
import logging

from profile_agent.models.llm_contracts import GuidedCompressionResult

logger = logging.getLogger(__name__)


class CompressionService:
    """Performs guided compression of stage transcripts.

    Preserves:
    - Concrete examples, project names, tool names
    - Motivations and stated values
    - Technical domains mentioned
    - Inferred strengths with evidence
    - Unresolved ambiguities
    - Direct quotes

    Discards:
    - Filler, pleasantries, repeated information
    """

    def __init__(self, model_client, model_deployment: str = "gpt-4o") -> None:
        self._client = model_client
        self._model = model_deployment

    async def compress(
        self,
        stage_id: str,
        transcript_text: str,
        extraction_targets: list[str],
    ) -> GuidedCompressionResult:
        """Perform guided compression of a stage transcript."""
        prompt = self._build_compression_prompt(stage_id, transcript_text, extraction_targets)

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": (
                        "You are a precision summarization agent. You perform GUIDED compression "
                        "that preserves concrete examples, motivations, technical domains, evidence, "
                        "and unresolved questions. You discard filler and repetition. Return valid JSON."
                    )},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_completion_tokens=1000,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            data = json.loads(content)
            data["stage_id"] = stage_id
            return GuidedCompressionResult.model_validate(data)
        except Exception as e:
            logger.error("Compression failed for stage %s: %s", stage_id, e)
            return GuidedCompressionResult(stage_id=stage_id, distilled_summary=transcript_text[:500])

    def _build_compression_prompt(self, stage_id: str, transcript: str, targets: list[str]) -> str:
        return (
            f"Stage: {stage_id}\n"
            f"Extraction targets: {', '.join(targets)}\n\n"
            f"Transcript:\n{transcript}\n\n"
            "Compress this transcript using guided compression. Return JSON:\n"
            '{"distilled_summary": "...", "preserved_examples": ["..."], '
            '"preserved_motivations": ["..."], "preserved_domains": ["..."], '
            '"evidence_snippets": ["..."], "unresolved_ambiguities": ["..."], '
            '"open_questions": ["..."]}'
        )
