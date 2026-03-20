"""Evaluator agent — validates extraction quality and stage completion."""

from __future__ import annotations

import logging
from typing import Any

from agent_framework import BaseAgent, AgentContext, AgentResponse

logger = logging.getLogger(__name__)

EVALUATOR_SYSTEM_PROMPT = """\
You are an evaluator agent. Your job is to assess whether an interview stage \
has gathered enough information to meet its completion criteria.

You will receive:
- The stage's completion criteria
- The extracted facts so far
- The conversation transcript for this stage

Respond with a structured assessment:
1. Which criteria are met and which are not
2. What information is still missing
3. A suggested next question if the stage is not complete

Be precise and evidence-based. Cite specific parts of the transcript.
"""


class EvaluatorAgent(BaseAgent):
    """Sub-agent for evaluating extraction quality and stage completion."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    async def run(self, context: AgentContext) -> AgentResponse:
        messages = [
            {"role": "system", "content": EVALUATOR_SYSTEM_PROMPT},
        ]

        if hasattr(context, "input") and context.input:
            messages.append({"role": "user", "content": context.input})

        try:
            client = context.get_openai_client()
            response = await client.chat.completions.create(
                model=context.model_deployment or "gpt-4o",
                messages=messages,
                temperature=0.3,
                max_completion_tokens=800,
            )
            return AgentResponse(content=response.choices[0].message.content or "")
        except Exception as e:
            logger.error("Evaluator call failed: %s", e)
            return AgentResponse(content="Evaluation unavailable.")

    async def run_stream(self, context: AgentContext):
        result = await self.run(context)
        yield result.content
