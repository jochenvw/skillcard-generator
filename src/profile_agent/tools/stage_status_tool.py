"""Tool: Get current stage status and interview progress."""

from __future__ import annotations

from profile_agent.stages.loader import load_stages
from profile_agent.models.stage_state import StageState


def get_stage_status(state: StageState) -> dict:
    """Return a summary of interview progress for display."""
    stages = load_stages()
    progress_list = []
    for stage in stages:
        p = state.get_progress(stage.id)
        progress_list.append({
            "stage_id": stage.id,
            "title": stage.title,
            "status": p.status.value,
            "turns": p.turns_completed,
        })

    return {
        "current_stage": state.current_stage_id,
        "stages": progress_list,
        "completed_count": len(state.completed_stage_ids),
        "total_count": len(stages),
    }
