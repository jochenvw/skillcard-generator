"""Profiler agent — skill matrix inference and profile synthesis."""

from __future__ import annotations

import logging
from typing import Any

from agent_framework import BaseAgent, AgentContext, AgentResponse

logger = logging.getLogger(__name__)

PROFILER_SYSTEM_PROMPT = """\
You are a profiler agent that infers a person's skills matrix and professional \
archetype from interview evidence.

Given a set of evidence records, stage summaries, and a profile draft, you will:
1. Score each skill dimension (unknown / emerging / working / strong / expert)
2. Assign confidence levels (low / medium / high)
3. Cite evidence for each assessment
4. Identify gaps where more information would help
5. Suggest an archetype/class from the evidence (e.g. "The Systems Architect", \
   "The Craft-Obsessed Builder", "The Bridge Builder")

Skill dimensions to assess:
- identity, networking, governance, infrastructure, application_development
- data, relational_databases, nosql, graph_databases, ai_ml_genai
- containers_orchestration, security, performance_optimization
- system_design, cloud_design_patterns, architecture_methods
- stakeholder_management, collaboration_influence, software_engineering_craftsmanship

Be evidence-based. Don't inflate scores without supporting quotes or examples.
"""


class ProfilerAgent(BaseAgent):
    """Sub-agent for skill matrix inference and profile synthesis."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    async def run(self, context: AgentContext) -> AgentResponse:
        messages = [
            {"role": "system", "content": PROFILER_SYSTEM_PROMPT},
        ]

        if hasattr(context, "input") and context.input:
            messages.append({"role": "user", "content": context.input})

        try:
            client = context.get_openai_client()
            response = await client.chat.completions.create(
                model=context.model_deployment or "gpt-4o",
                messages=messages,
                temperature=0.3,
                max_completion_tokens=1500,
            )
            return AgentResponse(content=response.choices[0].message.content or "")
        except Exception as e:
            logger.error("Profiler call failed: %s", e)
            return AgentResponse(content="Profile inference unavailable.")

    async def run_stream(self, context: AgentContext):
        result = await self.run(context)
        yield result.content
