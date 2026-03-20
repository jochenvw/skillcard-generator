"""Tool: Present a stage summary for user confirmation."""

from __future__ import annotations

import logging

from profile_agent.stages.runner import StageRunner

logger = logging.getLogger(__name__)


def format_confirmation_prompt(runner: StageRunner, summary: str) -> str:
    """Build a confirmation message to present to the user."""
    stage = runner.stage
    return (
        f"**{stage.title} — Summary**\n\n"
        f"{summary}\n\n"
        "---\n"
        "Does this capture things accurately? You can:\n"
        "- Say **\"yes\"** or **\"looks good\"** to confirm and move on\n"
        "- Tell me what I got wrong or missed, and I'll update it\n"
    )


def process_confirmation_response(runner: StageRunner, user_response: str) -> bool:
    """Process the user's confirmation response. Returns True if confirmed."""
    positive_signals = ["yes", "looks good", "correct", "confirmed", "that's right", "accurate", "good", "perfect"]
    normalized = user_response.strip().lower()

    if any(signal in normalized for signal in positive_signals):
        runner.accept_confirmation()
        logger.info("Stage %s confirmed by user", runner.stage.id)
        return True
    else:
        runner.reject_confirmation()
        logger.info("Stage %s confirmation rejected — user wants changes", runner.stage.id)
        return False
