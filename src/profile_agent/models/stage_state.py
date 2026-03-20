"""Stage state and progress tracking models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class StageStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class StageProgress(BaseModel):
    """Tracks progress within a single stage."""

    stage_id: str
    status: StageStatus = StageStatus.NOT_STARTED
    turns_completed: int = 0
    extraction_count: int = 0
    compression_count: int = 0
    entered_at: datetime | None = None
    completed_at: datetime | None = None
    summary: str = ""
    confirmation_accepted: bool | None = None


class StageState(BaseModel):
    """Overall interview state across all stages."""

    session_id: str
    current_stage_id: str = ""
    stage_progress: dict[str, StageProgress] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def get_progress(self, stage_id: str) -> StageProgress:
        if stage_id not in self.stage_progress:
            self.stage_progress[stage_id] = StageProgress(stage_id=stage_id)
        return self.stage_progress[stage_id]

    def enter_stage(self, stage_id: str) -> None:
        self.current_stage_id = stage_id
        progress = self.get_progress(stage_id)
        progress.status = StageStatus.IN_PROGRESS
        progress.entered_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def complete_stage(self, stage_id: str, summary: str) -> None:
        progress = self.get_progress(stage_id)
        progress.status = StageStatus.COMPLETED
        progress.completed_at = datetime.utcnow()
        progress.summary = summary
        self.updated_at = datetime.utcnow()

    @property
    def completed_stage_ids(self) -> list[str]:
        return [
            sid
            for sid, p in self.stage_progress.items()
            if p.status == StageStatus.COMPLETED
        ]
