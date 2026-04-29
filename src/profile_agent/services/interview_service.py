"""Interview service — reusable interview pipeline extracted from Chainlit UI.

Manages per-turn interview logic: name/role extraction, stage commands,
LLM streaming, turn recording, and automatic stage transitions.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime

from openai import AsyncAzureOpenAI

from profile_agent.config.settings import Settings, get_settings
from profile_agent.models.conversation import Message, Role, Transcript
from profile_agent.models.llm_contracts import ImageGenerationRequest
from profile_agent.models.stage_state import StageState
from profile_agent.prompts import render_template
from profile_agent.services.image_service import ImageService
from profile_agent.stages.loader import load_stages
from profile_agent.stages.runner import StageRunner
from profile_agent.stages.transition_engine import TransitionEngine

logger = logging.getLogger(__name__)

FAST_STAGE_SOFT_TURN_LIMIT = 2
FAST_STAGE_HARD_TURN_LIMIT = 3
NEXT_STAGE_COMMANDS = ("next stage", "skip stage", "move on", "fasttrack", "fast track")
PROGRESS_COMMANDS = ("progress", "what stage", "where are we", "stage are we", "how far")
FINALIZE_COMMANDS = ("done", "finish", "generate card", "finalize", "complete")
START_OVER_COMMANDS = ("start over", "restart", "reset", "begin again", "start from scratch")


@dataclass
class InterviewSession:
    """In-memory state for one interview session."""

    session_id: str
    engine: TransitionEngine
    runner: StageRunner
    transcript: Transcript
    stage_state: StageState
    openai_client: AsyncAzureOpenAI
    identity_name: str = ""
    role_description: str = ""
    photo_status: str = "unknown"


@dataclass
class PanelData:
    """Structured panel data sent alongside chat responses."""

    stages: list[dict]
    current_stage_id: str
    completed_stage_ids: list[str]
    profile: dict

    def to_dict(self) -> dict:
        return {
            "stages": self.stages,
            "currentStageId": self.current_stage_id,
            "completedStageIds": self.completed_stage_ids,
            "profile": self.profile,
        }


@dataclass
class TurnResult:
    """Result of processing one user message."""

    text: str = ""
    panel_data: PanelData | None = None
    stage_advanced: bool = False
    interview_complete: bool = False
    session_reset: bool = False
    new_stage_title: str = ""
    new_stage_opening: str = ""
    completion_hint: str = ""


def _extract_name_and_role(user_text: str) -> tuple[str | None, str | None]:
    """Best-effort extraction for intro stage progression."""
    text = user_text.strip()
    lowered = text.lower()

    name: str | None = None
    role: str | None = None

    control_words = {"skip", "upload", "later", "no", "nope", "yes", "y", "n"}

    m = re.search(r"\bmy name is\s+([a-z][a-z\s\-']{1,80})", lowered)
    if m:
        candidate = m.group(1).strip(" .,")
        candidate = re.split(r"\b(?:and|i am|i'm)\b", candidate, maxsplit=1)[0].strip(" .,")
        if 1 <= len(candidate.split()) <= 4:
            name = " ".join(w.capitalize() for w in candidate.split())
    elif 1 <= len(text.split()) <= 4 and all(ch.isalpha() or ch.isspace() or ch in "-'" for ch in text):
        if lowered not in control_words:
            name = " ".join(w.capitalize() for w in text.split())

    if name is None:
        m2 = re.search(r"\b(?:i am|i'm)\s+([a-z][a-z\s\-']{1,30})\b", lowered)
        if m2:
            candidate2 = m2.group(1).strip(" .,")
            if not candidate2.startswith(("a ", "an ", "the ")) and 1 <= len(candidate2.split()) <= 3:
                if candidate2 not in control_words:
                    name = " ".join(w.capitalize() for w in candidate2.split())

    role_markers = (
        "i work", "i'm a", "i'm ", "i am a", "i am an", "i am ",
        "i'm an", "i usually tell people", "my role", "i do",
        "engineer", "architect", "developer", "consultant",
        "manager", "lead", "solution",
    )
    if any(marker in lowered for marker in role_markers) and len(text) >= 12:
        role = text

    return name, role


def _intro_missing(identity_name: str | None, role_description: str | None, photo_status: str) -> list[str]:
    missing: list[str] = []
    if not identity_name:
        missing.append("name")
    if not role_description:
        missing.append("what you do")
    if photo_status == "unknown":
        missing.append("photo decision (upload or skip)")
    return missing


def _completion_hint(runner: StageRunner, identity_name: str, role_description: str, photo_status: str) -> str:
    if runner.stage.next_stage is None:
        return "Final stage: share any last preference, then type `generate card` or `done` to complete."

    if runner.stage.id == "introduction":
        missing = _intro_missing(identity_name or None, role_description or None, photo_status)
        if missing:
            return "Needed to complete this stage: " + ", ".join(missing) + "."
        return "Stage completion criteria are met. You can type `next stage` to move on immediately."

    if runner.turns_in_stage < FAST_STAGE_SOFT_TURN_LIMIT:
        return "To complete this stage quickly: share one concrete example with outcome."
    if runner.turns_in_stage < FAST_STAGE_HARD_TURN_LIMIT:
        return "Almost done. Add one final concrete detail, or type `next stage` to fast-track."
    return "Fast-track threshold reached. Moving to the next stage."


def build_panel_data(engine: TransitionEngine, stage_state: StageState,
                     identity_name: str, role_description: str, photo_status: str) -> PanelData:
    """Build panel data for the current interview state."""
    stages = []
    for stage in engine._stages:
        progress = stage_state.get_progress(stage.id)
        stages.append({
            "id": stage.id,
            "title": stage.title,
            "turns": progress.turns_completed,
            "status": progress.status.value,
        })

    # Build photo URL when a picture has been uploaded
    photo_url = None
    if photo_status == "uploaded":
        photo_url = f"/api/sessions/{stage_state.session_id}/profile-picture"

    return PanelData(
        stages=stages,
        current_stage_id=stage_state.current_stage_id,
        completed_stage_ids=stage_state.completed_stage_ids,
        profile={
            "name": identity_name or None,
            "role": role_description or None,
            "photo": photo_status if photo_status != "unknown" else None,
            "photoUrl": photo_url,
        },
    )


class InterviewService:
    """Stateless service that processes interview turns.

    Each method takes an InterviewSession and returns results
    without depending on any UI framework.
    """

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()

    async def create_openai_client(self) -> tuple[AsyncAzureOpenAI, object | None, object | None]:
        """Create an Azure OpenAI client based on settings.

        Returns (client, project_client_or_none, credential_or_none).
        """
        settings = self._settings
        endpoint = settings.effective_azure_openai_endpoint
        project_client = None
        credential = None

        if endpoint and settings.azure_openai_key:
            client = AsyncAzureOpenAI(
                azure_endpoint=endpoint,
                api_key=settings.azure_openai_key,
                api_version=settings.azure_openai_api_version,
            )
        elif endpoint and settings.entra_tenant_id and settings.entra_client_id and settings.entra_client_secret:
            from azure.identity.aio import ClientSecretCredential, get_bearer_token_provider

            credential = ClientSecretCredential(
                tenant_id=settings.entra_tenant_id,
                client_id=settings.entra_client_id,
                client_secret=settings.entra_client_secret,
            )
            token_provider = get_bearer_token_provider(
                credential, "https://cognitiveservices.azure.com/.default",
            )
            client = AsyncAzureOpenAI(
                azure_endpoint=endpoint,
                azure_ad_token_provider=token_provider,
                api_version=settings.azure_openai_api_version,
            )
        else:
            from azure.ai.projects.aio import AIProjectClient
            from azure.identity.aio import DefaultAzureCredential

            credential = DefaultAzureCredential()
            project_client = AIProjectClient(
                endpoint=settings.foundry_project_endpoint,
                credential=credential,
            )
            client = project_client.get_openai_client()

        return client, project_client, credential

    async def init_session(self, session_id: str, openai_client: AsyncAzureOpenAI) -> InterviewSession:
        """Initialize a new or resumed interview session."""
        from profile_agent.memory.session_store import create_session_store
        from profile_agent.memory.transcript_store import create_transcript_store

        session_store = await create_session_store(self._settings)
        transcript_store = await create_transcript_store(self._settings)

        stage_state = await session_store.get_stage_state(session_id) or StageState(session_id=session_id)
        transcript = await transcript_store.get_transcript(session_id) or Transcript(session_id=session_id)

        stages = load_stages()
        engine = TransitionEngine(stages=stages, state=stage_state, transcript=transcript)
        runner = engine.start_interview()

        return InterviewSession(
            session_id=session_id,
            engine=engine,
            runner=runner,
            transcript=transcript,
            stage_state=stage_state,
            openai_client=openai_client,
        )

    def handle_stage_command(self, session: InterviewSession, user_text: str) -> TurnResult | None:
        """Check for stage commands and return a result if handled, or None to continue."""
        lowered = user_text.lower()
        runner = session.runner
        engine = session.engine
        panel = build_panel_data(engine, session.stage_state,
                                 session.identity_name, session.role_description, session.photo_status)

        # Next stage / skip / fast-track
        if any(cmd in lowered for cmd in NEXT_STAGE_COMMANDS):
            if runner.stage.next_stage is None:
                return TurnResult(
                    text="You're already in the final stage. Type `generate card` or `done` to finish.",
                    panel_data=panel,
                )
            runner.complete(summary=f"User fast-tracked from stage {runner.stage.id}.")
            next_runner = engine.advance()
            if next_runner is None:
                return TurnResult(text="Interview complete.", panel_data=panel, interview_complete=True)
            session.runner = next_runner
            panel = build_panel_data(engine, session.stage_state,
                                     session.identity_name, session.role_description, session.photo_status)
            return TurnResult(
                text=f"Next stage: {next_runner.stage.title}.",
                panel_data=panel,
                stage_advanced=True,
                new_stage_title=next_runner.stage.title,
                new_stage_opening=next_runner.stage.opening_prompt,
            )

        # Finalize last stage
        if runner.stage.next_stage is None and any(cmd in lowered for cmd in FINALIZE_COMMANDS):
            runner.complete(summary=f"User finalized final stage {runner.stage.id}.")
            panel = build_panel_data(engine, session.stage_state,
                                     session.identity_name, session.role_description, session.photo_status)
            return TurnResult(
                text="Interview complete. Generating your final strengths card output next.",
                panel_data=panel,
                interview_complete=True,
            )

        # Start over / reset
        if any(cmd in lowered for cmd in START_OVER_COMMANDS):
            session.stage_state = StageState(session_id=session.session_id)
            session.transcript = Transcript(session_id=session.session_id)
            session.engine = TransitionEngine(
                stages=load_stages(), state=session.stage_state, transcript=session.transcript,
            )
            session.runner = session.engine.start_interview()
            session.identity_name = ""
            session.role_description = ""
            session.photo_status = "unknown"
            panel = build_panel_data(engine, session.stage_state,
                                     session.identity_name, session.role_description, session.photo_status)
            return TurnResult(
                text="Starting over! Let's begin the interview from scratch.",
                panel_data=panel,
                session_reset=True,
                new_stage_opening=session.runner.stage.opening_prompt,
            )

        # Progress query
        if any(tok in lowered for tok in PROGRESS_COMMANDS):
            progress_summary = engine.get_progress_summary()
            completed = [sid for sid, st in progress_summary.items() if st == "completed"]
            insight_lines = [
                f"Current stage: {runner.stage.id} ({runner.stage.title})",
                f"Completed: {len(completed)}/{len(progress_summary)} stages",
                f"Turns in this stage: {runner.turns_in_stage}/{FAST_STAGE_HARD_TURN_LIMIT}",
            ]
            if runner.stage.id == "introduction":
                missing = _intro_missing(session.identity_name or None, session.role_description or None,
                                         session.photo_status)
                if missing:
                    insight_lines.append("To move on, I still need: " + ", ".join(missing) + ".")
                else:
                    insight_lines.append("Introduction criteria are met; I can move to the next stage now.")
            else:
                insight_lines.append(_completion_hint(runner, session.identity_name,
                                                      session.role_description, session.photo_status))
            return TurnResult(text="\n".join(insight_lines), panel_data=panel)

        return None

    def update_identity(self, session: InterviewSession, user_text: str, has_image: bool = False) -> None:
        """Update name, role, photo status from user text."""
        lowered = user_text.lower()

        if has_image:
            session.photo_status = "uploaded"

        extracted_name, extracted_role = _extract_name_and_role(user_text)
        if extracted_name and not session.identity_name:
            session.identity_name = extracted_name
        if extracted_role and not session.role_description:
            session.role_description = extracted_role

        # Intro fallback: substantive sentence → role description
        if (session.runner.stage.id == "introduction"
                and not session.role_description
                and len(user_text) >= 20
                and not any(tok in lowered for tok in ("skip", "upload", "next stage", "progress"))):
            session.role_description = user_text

        if session.photo_status == "unknown" and any(
            tok in lowered for tok in ("skip", "no photo", "no thanks", "later")
        ):
            session.photo_status = "skipped"

    def _build_evidence_summary(self, session: InterviewSession) -> str:
        """Build a text summary of all transcript turns for synthesis."""
        lines: list[str] = []
        for turn in session.transcript.turns:
            stage_id = turn.stage_id or "unknown"
            lines.append(f"[{stage_id}] User: {turn.user_message.content}")
            lines.append(f"[{stage_id}] Assistant: {turn.assistant_message.content}")
        return "\n".join(lines) if lines else "No conversation recorded yet."

    def _build_stage_summaries(self, session: InterviewSession) -> str:
        """Build per-stage summaries from completed stage progress."""
        lines: list[str] = []
        for stage_id in session.stage_state.completed_stage_ids:
            progress = session.stage_state.get_progress(stage_id)
            summary = progress.summary or f"Completed ({progress.turns_completed} turns)"
            lines.append(f"- **{stage_id}**: {summary}")
        return "\n".join(lines) if lines else "No stages completed yet."

    async def _run_synthesis(self, session: InterviewSession) -> str:
        """Run the synthesis LLM call and return the profile JSON."""
        prompt = render_template(
            "synthesis",
            session_id=session.session_id,
            evidence_summary=self._build_evidence_summary(session),
            stage_summaries=self._build_stage_summaries(session),
        )
        response = await session.openai_client.chat.completions.create(
            model=self._settings.effective_azure_openai_deployment,
            messages=[{"role": "system", "content": prompt}],
            temperature=0.4,
            max_completion_tokens=6000,
        )
        return response.choices[0].message.content or ""

    @staticmethod
    def _extract_json(text: str) -> dict | None:
        """Extract a JSON object from text that may contain markdown fences."""
        # Try direct parse first
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            pass
        # Strip markdown code fences
        import re
        m = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
        if m:
            try:
                return json.loads(m.group(1))
            except (json.JSONDecodeError, ValueError):
                pass
        # Find first { to last }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    async def _run_card_generation(
        self, session: InterviewSession, synthesis_json: str,
    ) -> dict:
        """Generate structured card data. Returns a dict with card fields."""
        display_name = session.identity_name or "Anonymous"
        archetype = "Technologist"
        top_strengths = "[]"
        skill_matrix = "[]"
        evidence_highlights = ""

        syn = self._extract_json(synthesis_json)
        if syn:
            archetype = syn.get("suggested_archetype", archetype)
            top_strengths = json.dumps(syn.get("top_strengths", []))
            skill_matrix = json.dumps(syn.get("dimensions", []), indent=2)
            evidence_highlights = "\n".join(
                f"- {d.get('name', '?')}: {d.get('evidence_summary', '')}"
                for d in syn.get("dimensions", [])
                if d.get("score") in ("strong", "leading")
            )
        else:
            logger.warning("Could not parse synthesis JSON for card generation")

        card_prompt = render_template(
            "card_generation",
            display_name=display_name,
            archetype=archetype,
            top_strengths=top_strengths,
            skill_matrix=skill_matrix,
            evidence_highlights=evidence_highlights or "No highlights available.",
        )
        card_response = await session.openai_client.chat.completions.create(
            model=self._settings.effective_azure_openai_deployment,
            messages=[
                {"role": "system", "content": "You are a JSON-only response bot. Output valid JSON with no markdown."},
                {"role": "user", "content": card_prompt},
            ],
            temperature=0.7,
            max_completion_tokens=6000,
        )
        card_text = card_response.choices[0].message.content or ""

        card_data = self._extract_json(card_text)
        if not card_data:
            logger.warning("Could not parse card spec JSON, using defaults")
            card_data = {
                "display_name": display_name,
                "card_title": "Skill Deck",
                "level": 5,
                "xp": 3000,
                "top_expertise": [
                    {"label": "Technology", "score": 7},
                    {"label": "Architecture", "score": 6},
                    {"label": "Leadership", "score": 5},
                ],
                "people_i_admire": [],
                "technical_accomplishments": [],
                "influential_ideas": [],
                "strategic_curiosities": [],
                "grow_into": "Growth",
                "xp_to_next_level": 2000,
                "flavor_text": "",
            }

        # Ensure display_name is set
        card_data["display_name"] = display_name

        # Include profile picture URL so the SkillCard can display it
        if session.photo_status == "uploaded":
            card_data["photo_url"] = f"/api/sessions/{session.session_id}/profile-picture"
        else:
            card_data["photo_url"] = None

        return card_data

    def _format_synthesis_for_display(self, synthesis_raw: str) -> str:
        """Format synthesis JSON into a human-readable markdown summary."""
        syn = self._extract_json(synthesis_raw)
        if not syn:
            return synthesis_raw

        lines: list[str] = []

        archetype = syn.get("suggested_archetype", "")
        if archetype:
            rationale = syn.get("archetype_rationale", "")
            lines.append(f"## Your Archetype: {archetype}")
            if rationale:
                lines.append(f"*{rationale}*\n")

        top = syn.get("top_strengths", [])
        if top:
            lines.append("### Top Strengths")
            for s in top:
                lines.append(f"- {s}")
            lines.append("")

        passion = syn.get("passion_markers", [])
        if passion:
            lines.append("### Passion Markers")
            for p in passion:
                lines.append(f"- {p}")
            lines.append("")

        unique = syn.get("unique_combination", "")
        if unique:
            lines.append(f"### What Makes You Distinctive\n{unique}\n")

        dims = syn.get("dimensions", [])
        observed = [d for d in dims if d.get("score") not in ("not_observed", None)]
        if observed:
            lines.append("### Skill Assessment")
            for d in observed:
                name = d.get("name", "?").replace("_", " ").title()
                score = d.get("score", "?")
                conf = d.get("confidence", "?")
                summary = d.get("evidence_summary", "")
                lines.append(f"- **{name}**: {score} (confidence: {conf})")
                if summary:
                    lines.append(f"  {summary}")
            lines.append("")

        return "\n".join(lines)

    def _format_card_for_display(self, card_text: str) -> str:
        """Format card spec JSON into a human-readable card display."""
        try:
            text = card_text
            if "{" in text:
                text = text[text.find("{"):text.rfind("}") + 1]
            card = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return card_text

        lines: list[str] = []

        title = card.get("card_title", "")
        if title:
            lines.append(f"# {title}")

        desc = card.get("card_description", "")
        if desc:
            lines.append(f"\n{desc}\n")

        abilities = card.get("abilities", [])
        if abilities:
            lines.append("### Abilities")
            for a in abilities:
                power = "⚡" * a.get("power_level", 1)
                lines.append(f"- **{a.get('name', '?')}** {power}")
                if a.get("description"):
                    lines.append(f"  {a['description']}")
            lines.append("")

        flavor = card.get("flavor_text", "")
        if flavor:
            lines.append(f"*\"{flavor}\"*\n")

        visual = card.get("visual_direction", {})
        if visual:
            mood = visual.get("mood", "")
            palette = visual.get("color_palette", "")
            if mood or palette:
                lines.append(f"🎨 *{mood}* — {palette}")

        return "\n".join(lines)

    async def process_turn_streaming(
        self, session: InterviewSession, user_text: str, has_image: bool = False,
    ) -> AsyncGenerator[str, None]:
        """Process a user message and yield AI SDK v6 UI Message Stream SSE events.

        Each yielded string is a complete SSE event: ``data: {json}\\n\\n``
        The stream uses the UI Message Chunk schema expected by DefaultChatTransport.
        """
        import uuid

        self.update_identity(session, user_text, has_image)

        # Check for stage commands first (non-streaming immediate responses)
        cmd_result = self.handle_stage_command(session, user_text)
        if cmd_result is not None:
            text_id = str(uuid.uuid4())
            full_text = cmd_result.text
            if cmd_result.new_stage_opening:
                full_text += "\n\n" + cmd_result.new_stage_opening

            yield f'data: {json.dumps({"type": "text-start", "id": text_id})}\n\n'
            yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": full_text})}\n\n'
            yield f'data: {json.dumps({"type": "text-end", "id": text_id})}\n\n'

            if cmd_result.panel_data:
                yield f'data: {json.dumps({"type": "data-panelUpdate", "data": cmd_result.panel_data.to_dict()})}\n\n'
            if cmd_result.session_reset:
                yield f'data: {json.dumps({"type": "data-sessionReset"})}\n\n'
            yield "data: [DONE]\n\n"
            return

        runner = session.runner
        stage = runner.stage

        # ── Validation stage: synthesize profile and present it ──
        if stage.id == "validation" and runner.turns_in_stage == 0:
            text_id = str(uuid.uuid4())
            yield f'data: {json.dumps({"type": "text-start", "id": text_id})}\n\n'

            preamble = stage.opening_prompt + "\n\nLet me synthesize your profile...\n\n"
            yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": preamble})}\n\n'

            synthesis_raw = await self._run_synthesis(session)
            # Store synthesis on the session for card generation later
            session._synthesis_json = synthesis_raw  # type: ignore[attr-defined]

            # Format synthesis for human-readable display
            display_text = self._format_synthesis_for_display(synthesis_raw)
            yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": display_text})}\n\n'

            closing = "\n\n**What did I get right? What did I miss or get wrong? Anything you want to add or emphasize?**"
            yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": closing})}\n\n'
            yield f'data: {json.dumps({"type": "text-end", "id": text_id})}\n\n'

            full_response = preamble + display_text + closing
            runner.record_turn(
                Message(role=Role.USER, content=user_text),
                Message(role=Role.ASSISTANT, content=full_response),
            )

            panel = build_panel_data(session.engine, session.stage_state,
                                     session.identity_name, session.role_description, session.photo_status)
            yield f'data: {json.dumps({"type": "data-panelUpdate", "data": panel.to_dict()})}\n\n'
            yield "data: [DONE]\n\n"
            return

        # ── Card generation stage: generate card spec + image ──
        if stage.id == "card_generation" and runner.turns_in_stage == 0:
            text_id = str(uuid.uuid4())
            yield f'data: {json.dumps({"type": "text-start", "id": text_id})}\n\n'

            preamble = stage.opening_prompt + "\n\n"
            yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": preamble})}\n\n'

            # Use stored synthesis or generate fresh
            synthesis_json = getattr(session, "_synthesis_json", None)
            if not synthesis_json:
                yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": "Synthesizing your profile first...\\n\\n"})}\n\n'
                synthesis_json = await self._run_synthesis(session)

            yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": "Generating your Skill Deck card...\\n\\n"})}\n\n'

            card_data = await self._run_card_generation(session, synthesis_json)

            status_msg = f"Your **{card_data.get('display_name', 'Skill')} Deck** card is ready! Check it out below."
            yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": status_msg})}\n\n'
            yield f'data: {json.dumps({"type": "text-end", "id": text_id})}\n\n'

            # Send structured card data to the frontend for rendering
            yield f'data: {json.dumps({"type": "data-cardData", "data": card_data})}\n\n'

            full_response = preamble + status_msg
            runner.record_turn(
                Message(role=Role.USER, content=user_text),
                Message(role=Role.ASSISTANT, content=full_response),
            )

            panel = build_panel_data(session.engine, session.stage_state,
                                     session.identity_name, session.role_description, session.photo_status)
            yield f'data: {json.dumps({"type": "data-panelUpdate", "data": panel.to_dict()})}\n\n'
            yield "data: [DONE]\n\n"
            return

        # ── Regular conversational stages ──
        context = {
            "stage_title": stage.title,
            "stage_purpose": stage.purpose,
            "opening_prompt": stage.opening_prompt,
            "context_summary": (
                f"Photo status: {session.photo_status}. "
                "If photo is uploaded or skipped, do not ask about photo again. "
                "Ask exactly one high-yield question at a time, keep response concise (2-4 sentences), "
                "and prefer concrete examples with outcomes."
            ),
            "extraction_targets": "\n".join(f"- {t}" for t in stage.extraction_targets),
            "follow_up_style": stage.follow_up_style if hasattr(stage, "follow_up_style") else "curious and warm",
            "completion_criteria": "\n".join(f"- {c}" for c in stage.completion_criteria),
        }

        if runner.turns_in_stage >= FAST_STAGE_SOFT_TURN_LIMIT:
            context["context_summary"] += " Stage is near completion; summarize signal and suggest moving on."
        system_prompt = render_template("interview_system", **context)

        history: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for turn in session.transcript.turns[-8:]:
            history.append({"role": "user", "content": turn.user_message.content})
            history.append({"role": "assistant", "content": turn.assistant_message.content})
        history.append({"role": "user", "content": user_text})

        # Stream from Azure OpenAI
        settings = self._settings
        full_response = ""
        text_id = str(uuid.uuid4())

        yield f'data: {json.dumps({"type": "text-start", "id": text_id})}\n\n'

        stream = await session.openai_client.chat.completions.create(
            model=settings.effective_azure_openai_deployment,
            messages=history,
            temperature=0.7,
            max_completion_tokens=280,
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                full_response += token
                yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": token})}\n\n'

        yield f'data: {json.dumps({"type": "text-end", "id": text_id})}\n\n'

        # Record turn
        runner.record_turn(
            Message(role=Role.USER, content=user_text),
            Message(role=Role.ASSISTANT, content=full_response),
        )

        # Check for automatic stage transitions
        advanced = False

        # Deterministic intro progression
        if runner.stage.id == "introduction":
            missing = _intro_missing(session.identity_name or None, session.role_description or None,
                                     session.photo_status)
            if not missing:
                runner.complete(
                    summary=f"Intro complete: name={session.identity_name}, role captured, "
                            f"photo_status={session.photo_status}."
                )
                next_runner = session.engine.advance()
                if next_runner is not None:
                    session.runner = next_runner
                    advanced = True
                    transition_id = str(uuid.uuid4())
                    transition_text = f"\n\nMoving to: {next_runner.stage.title}.\n{next_runner.stage.opening_prompt}"
                    yield f'data: {json.dumps({"type": "text-start", "id": transition_id})}\n\n'
                    yield f'data: {json.dumps({"type": "text-delta", "id": transition_id, "delta": transition_text})}\n\n'
                    yield f'data: {json.dumps({"type": "text-end", "id": transition_id})}\n\n'

        # Fast-track auto-advance
        if not advanced and runner.turns_in_stage >= FAST_STAGE_HARD_TURN_LIMIT:
            if runner.stage.next_stage is not None:
                runner.complete(summary=f"Auto-completed {runner.stage.id} at fast-track turn budget.")
                next_runner = session.engine.advance()
                if next_runner is not None:
                    session.runner = next_runner
                    advanced = True
                    transition_id = str(uuid.uuid4())
                    transition_text = f"\n\nFast-track: moving to {next_runner.stage.title}.\n{next_runner.stage.opening_prompt}"
                    yield f'data: {json.dumps({"type": "text-start", "id": transition_id})}\n\n'
                    yield f'data: {json.dumps({"type": "text-delta", "id": transition_id, "delta": transition_text})}\n\n'
                    yield f'data: {json.dumps({"type": "text-end", "id": transition_id})}\n\n'

        # Emit panel data as a data part
        panel = build_panel_data(session.engine, session.stage_state,
                                 session.identity_name, session.role_description, session.photo_status)
        yield f'data: {json.dumps({"type": "data-panelUpdate", "data": panel.to_dict()})}\n\n'
        yield "data: [DONE]\n\n"


def _escape_stream_text(text: str) -> str:
    """Escape text for AI SDK Data Stream Protocol JSON string values."""
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
