"""Summarizer agent — guided compression and stage summarization."""

from __future__ import annotations

import logging
from typing import Any

from agent_framework import BaseAgent, AgentContext, AgentResponse

logger = logging.getLogger(__name__)

SUMMARIZER_SYSTEM_PROMPT = """\
You are a summarization agent that performs GUIDED compression of interview \
transcripts. You do NOT produce generic summaries.

You MUST preserve:
- Concrete examples and specific project/tool names
- Motivations and stated values
- Technical domains mentioned
- Inferred strengths with supporting evidence
- Unresolved ambiguities that need follow-up
- Direct quotes that are especially revealing

You MUST discard:
- Filler conversation
- Repeated information
- Pleasantries and small talk

Output format: Return a structured summary with clearly labeled sections \
for preserved_examples, preserved_motivations, preserved_domains, \
evidence_snippets, unresolved_ambiguities, and open_questions.
"""


class SummarizerAgent(BaseAgent):
    """Sub-agent for guided compression and stage summarization."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    async def run(self, context: AgentContext) -> AgentResponse:
        messages = [
            {"role": "system", "content": SUMMARIZER_SYSTEM_PROMPT},
        ]

        if hasattr(context, "input") and context.input:
            messages.append({"role": "user", "content": context.input})

        try:
            client = context.get_openai_client()
            response = await client.chat.completions.create(
                model=context.model_deployment or "gpt-4o",
                messages=messages,
                temperature=0.2,
                max_completion_tokens=1000,
            )
            return AgentResponse(content=response.choices[0].message.content or "")
        except Exception as e:
            logger.error("Summarizer call failed: %s", e)
            return AgentResponse(content="Summarization unavailable.")

    async def run_stream(self, context: AgentContext):
        result = await self.run(context)
        yield result.content
