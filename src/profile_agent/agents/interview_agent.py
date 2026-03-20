"""Interview agent — main conversational agent using Microsoft Agent Framework."""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator

from agent_framework import BaseAgent, AgentContext, AgentResponse

from profile_agent.stages.loader import load_stages, build_stage_index
from profile_agent.stages.models import StageDefinition

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a thoughtful, playful, and perceptive interview agent building a \
strengths profile for the person you're talking to.

Your style:
- Intelligent and reflective, never robotic or HR-ish
- Story-driven: you ask for stories, examples, and specifics — not abstract self-assessments
- "Show, don't tell" — you encourage people to demonstrate their strengths through anecdotes
- Warm but not sycophantic
- You notice patterns others miss and reflect them back
- You're genuinely curious and a great listener

You are currently in stage: {stage_title}
Stage purpose: {stage_purpose}
Follow-up style: {follow_up_style}
Extraction targets: {extraction_targets}
Completion criteria: {completion_criteria}
Turns so far in this stage: {turns_completed}

Guidelines for this turn:
- If this is the first turn in the stage, use the opening prompt provided
- Ask follow-up questions that go deeper into specifics
- Avoid yes/no questions — ask for stories, examples, names, and details
- When you have enough information for the stage's extraction targets, \
  signal readiness to move on by summarizing what you've learned
- Never break character or discuss the system's internals
"""


class InterviewAgent(BaseAgent):
    """Main interview agent — orchestrates the multi-stage strengths interview.

    This agent is designed to be wrapped with the Foundry hosting adapter
    for deployment, or used directly in local dev mode via Chainlit.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._stages = load_stages()
        self._stage_index = build_stage_index(self._stages)

    async def run(self, context: AgentContext) -> AgentResponse:
        """Handle a single turn (non-streaming)."""
        stage_context = self._get_stage_context(context)
        system_prompt = SYSTEM_PROMPT.format(**stage_context)

        # Build messages for the LLM call
        messages = [
            {"role": "system", "content": system_prompt},
        ]

        # Add conversation history from context
        if hasattr(context, "messages") and context.messages:
            for msg in context.messages:
                messages.append({"role": msg.role, "content": msg.content})

        # Add current user input
        if hasattr(context, "input") and context.input:
            messages.append({"role": "user", "content": context.input})

        response_text = await self._call_model(messages, context)

        return AgentResponse(content=response_text)

    async def run_stream(self, context: AgentContext) -> AsyncGenerator[str, None]:
        """Handle a single turn (streaming)."""
        stage_context = self._get_stage_context(context)
        system_prompt = SYSTEM_PROMPT.format(**stage_context)

        messages = [
            {"role": "system", "content": system_prompt},
        ]

        if hasattr(context, "messages") and context.messages:
            for msg in context.messages:
                messages.append({"role": msg.role, "content": msg.content})

        if hasattr(context, "input") and context.input:
            messages.append({"role": "user", "content": context.input})

        async for chunk in self._stream_model(messages, context):
            yield chunk

    async def _call_model(self, messages: list[dict], context: AgentContext) -> str:
        """Call the LLM and return the full response."""
        # Uses the model client provided by the framework / hosting adapter
        try:
            client = context.get_openai_client()
            response = await client.chat.completions.create(
                model=context.model_deployment or "gpt-4o",
                messages=messages,
                temperature=0.8,
                max_completion_tokens=1024,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error("Model call failed: %s", e)
            return "I'm having trouble thinking right now — can you give me a moment and try again?"

    async def _stream_model(self, messages: list[dict], context: AgentContext) -> AsyncGenerator[str, None]:
        """Stream the LLM response."""
        try:
            client = context.get_openai_client()
            stream = await client.chat.completions.create(
                model=context.model_deployment or "gpt-4o",
                messages=messages,
                temperature=0.8,
                max_completion_tokens=1024,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error("Model stream failed: %s", e)
            yield "I'm having trouble thinking right now — can you give me a moment and try again?"

    def _get_stage_context(self, context: AgentContext) -> dict[str, str]:
        """Extract current stage context for prompt interpolation."""
        # Default to introduction stage
        stage_id = getattr(context, "stage_id", None) or "introduction"
        stage = self._stage_index.get(stage_id, self._stages[0])

        return {
            "stage_title": stage.title,
            "stage_purpose": stage.purpose,
            "follow_up_style": stage.follow_up_style,
            "extraction_targets": ", ".join(stage.extraction_targets),
            "completion_criteria": ", ".join(stage.completion_criteria),
            "turns_completed": str(getattr(context, "turns_completed", 0)),
        }
