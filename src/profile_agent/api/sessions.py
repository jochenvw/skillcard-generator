"""Session management API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from profile_agent.api.auth import get_current_user

router = APIRouter(tags=["sessions"])


@router.post("/sessions")
async def create_session(user: dict = Depends(get_current_user)):
    """Create a new interview session."""
    from profile_agent.api.dependencies import get_session_service

    svc = get_session_service()
    session = await svc.create_session(user["user_id"])
    return {"session_id": session.session_id, "status": "created"}


@router.get("/sessions")
async def list_sessions(user: dict = Depends(get_current_user)):
    """List sessions for the current user."""
    from profile_agent.api.dependencies import get_session_service

    svc = get_session_service()
    sessions = await svc.list_sessions(user["user_id"])
    return {"sessions": [s.model_dump() for s in sessions]}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, user: dict = Depends(get_current_user)):
    """Get session details."""
    from profile_agent.api.dependencies import get_session_service

    svc = get_session_service()
    session = await svc.get_session(session_id)
    if not session:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Session not found")
    return session.model_dump()


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, user: dict = Depends(get_current_user)):
    """Delete a session and its associated data."""
    from profile_agent.api.dependencies import get_session_service

    svc = get_session_service()
    await svc.delete_session(session_id)
    return {"status": "deleted"}


@router.get("/sessions/{session_id}/state")
async def get_session_state(session_id: str, user: dict = Depends(get_current_user)):
    """Return full interview state for panel rendering.

    Includes stage progress, current stage, completed stages, profile info,
    and transcript history.
    """
    from profile_agent.api.dependencies import get_session_service
    from profile_agent.config.settings import get_settings
    from profile_agent.memory.session_store import create_session_store
    from profile_agent.memory.transcript_store import create_transcript_store
    from profile_agent.models.stage_state import StageState
    from profile_agent.models.conversation import Transcript
    from profile_agent.stages.loader import load_stages
    from profile_agent.stages.transition_engine import TransitionEngine
    from profile_agent.services.interview_service import build_panel_data
    from fastapi import HTTPException

    svc = get_session_service()
    session = await svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    settings = get_settings()
    session_store = await create_session_store(settings)
    transcript_store = await create_transcript_store(settings)

    stage_state = await session_store.get_stage_state(session_id) or StageState(session_id=session_id)
    transcript = await transcript_store.get_transcript(session_id) or Transcript(session_id=session_id)

    stages = load_stages()
    engine = TransitionEngine(stages=stages, state=stage_state, transcript=transcript)

    panel = build_panel_data(engine, stage_state, "", "", "unknown")

    # Build transcript history for chat replay
    messages = []
    for turn in transcript.turns:
        messages.append({"role": "user", "content": turn.user_message.content})
        messages.append({"role": "assistant", "content": turn.assistant_message.content})

    return {
        "sessionId": session_id,
        "panelData": panel.to_dict(),
        "messages": messages,
        "turnCount": transcript.turn_count,
    }
