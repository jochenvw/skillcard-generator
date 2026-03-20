"""Conversation and transcript models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Message(BaseModel):
    """A single message in the conversation."""

    role: Role
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, str] = Field(default_factory=dict)


class Turn(BaseModel):
    """A user message + assistant response pair."""

    turn_number: int
    user_message: Message
    assistant_message: Message
    stage_id: str = ""
    extraction_applied: bool = False


class Transcript(BaseModel):
    """Full ordered transcript for a session."""

    session_id: str
    turns: list[Turn] = Field(default_factory=list)

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    def append_turn(self, user_msg: Message, assistant_msg: Message, stage_id: str) -> Turn:
        turn = Turn(
            turn_number=self.turn_count + 1,
            user_message=user_msg,
            assistant_message=assistant_msg,
            stage_id=stage_id,
        )
        self.turns.append(turn)
        return turn

    def turns_for_stage(self, stage_id: str) -> list[Turn]:
        return [t for t in self.turns if t.stage_id == stage_id]
