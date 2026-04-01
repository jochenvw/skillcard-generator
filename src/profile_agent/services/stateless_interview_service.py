"""Stateless interview service — processes turns without server-side session state.

All conversation state is passed in the request and returned in the response.
The server only holds cached stage definitions and a reusable OpenAI client.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from functools import lru_cache

from openai import AsyncAzureOpenAI

from profile_agent.config.settings import Settings, get_settings
from profile_agent.prompts import render_template
from profile_agent.stages.loader import build_stage_index, load_stages
from profile_agent.stages.models import StageDefinition

logger = logging.getLogger(__name__)

FAST_STAGE_SOFT_TURN_LIMIT = 2
FAST_STAGE_HARD_TURN_LIMIT = 3
NEXT_STAGE_COMMANDS = ("next stage", "skip stage", "move on", "fasttrack", "fast track")
PROGRESS_COMMANDS = ("progress", "what stage", "where are we", "stage are we", "how far")
FINALIZE_COMMANDS = ("done", "finish", "generate card", "finalize", "complete")
START_OVER_COMMANDS = ("start over", "restart", "reset", "begin again", "start from scratch")
JUMP_TO_CARD_COMMANDS = ("/card", "/generate")


@lru_cache(maxsize=1)
def _cached_stages() -> list[StageDefinition]:
    return load_stages()


@lru_cache(maxsize=1)
def _cached_stage_index() -> dict[str, StageDefinition]:
    return build_stage_index(_cached_stages())


def get_stage(stage_id: str) -> StageDefinition | None:
    return _cached_stage_index().get(stage_id)


def get_all_stages() -> list[StageDefinition]:
    return _cached_stages()


def get_next_stage(current_stage_id: str) -> StageDefinition | None:
    """Determine the next stage after the given one."""
    index = _cached_stage_index()
    current = index.get(current_stage_id)
    if current and current.next_stage:
        return index.get(current.next_stage)
    stages = _cached_stages()
    for i, stage in enumerate(stages):
        if stage.id == current_stage_id and i + 1 < len(stages):
            return stages[i + 1]
    return None


def get_first_stage() -> StageDefinition:
    return _cached_stages()[0]


# ── Identity extraction (same as interview_service) ──


def _extract_name_and_role(user_text: str) -> tuple[str | None, str | None]:
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


@dataclass
class IdentityContext:
    name: str = ""
    role: str = ""
    photo_status: str = "unknown"


@dataclass
class CompletedStageSummary:
    id: str
    summary: str


@dataclass
class StateUpdate:
    """Return payload for the state update SSE event."""
    current_stage_id: str
    identity: dict
    stage_advanced: bool = False
    stage_summary: str | None = None
    new_stage_opening: str | None = None
    panel_data: dict = field(default_factory=dict)
    session_reset: bool = False
    card_data: dict | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "currentStageId": self.current_stage_id,
            "identity": self.identity,
            "stageAdvanced": self.stage_advanced,
            "stageSummary": self.stage_summary,
            "newStageOpening": self.new_stage_opening,
            "panelData": self.panel_data,
        }
        if self.session_reset:
            d["sessionReset"] = True
        if self.card_data is not None:
            d["cardData"] = self.card_data
        return d


def _identity_dict(ctx: IdentityContext) -> dict:
    return {"name": ctx.name, "role": ctx.role, "photoStatus": ctx.photo_status}


def update_identity(identity: IdentityContext, user_text: str, current_stage_id: str, has_image: bool = False) -> IdentityContext:
    """Return an updated copy of identity based on user text."""
    new = IdentityContext(name=identity.name, role=identity.role, photo_status=identity.photo_status)
    lowered = user_text.lower()

    if has_image:
        new.photo_status = "uploaded"

    extracted_name, extracted_role = _extract_name_and_role(user_text)
    if extracted_name and not new.name:
        new.name = extracted_name
    if extracted_role and not new.role:
        new.role = extracted_role

    if (current_stage_id == "introduction"
            and not new.role
            and len(user_text) >= 20
            and not any(tok in lowered for tok in ("skip", "upload", "next stage", "progress"))):
        new.role = user_text

    if new.photo_status == "unknown" and any(
        tok in lowered for tok in ("skip", "no photo", "no thanks", "later")
    ):
        new.photo_status = "skipped"

    return new


def _intro_missing(identity: IdentityContext) -> list[str]:
    missing: list[str] = []
    if not identity.name:
        missing.append("name")
    if not identity.role:
        missing.append("what you do")
    if identity.photo_status == "unknown":
        missing.append("photo decision (upload or skip)")
    return missing


def _completion_hint(stage: StageDefinition, turn_count: int, identity: IdentityContext) -> str:
    if stage.next_stage is None:
        return "Final stage: share any last preference, then type `generate card` or `done` to complete."
    if stage.id == "introduction":
        missing = _intro_missing(identity)
        if missing:
            return "Needed to complete this stage: " + ", ".join(missing) + "."
        return "Stage completion criteria are met. You can type `next stage` to move on immediately."
    if turn_count < FAST_STAGE_SOFT_TURN_LIMIT:
        return "To complete this stage quickly: share one concrete example with outcome."
    if turn_count < FAST_STAGE_HARD_TURN_LIMIT:
        return "Almost done. Add one final concrete detail, or type `next stage` to fast-track."
    return "Fast-track threshold reached. Moving to the next stage."


def _build_panel_data(current_stage_id: str, completed_ids: list[str],
                      identity: IdentityContext) -> dict:
    """Build panel data from stage definitions + completed info."""
    stages_list = []
    completed_set = set(completed_ids)
    for stage in get_all_stages():
        if stage.id in completed_set:
            status = "completed"
        elif stage.id == current_stage_id:
            status = "in_progress"
        else:
            status = "not_started"
        stages_list.append({
            "id": stage.id,
            "title": stage.title,
            "status": status,
        })

    return {
        "stages": stages_list,
        "currentStageId": current_stage_id,
        "completedStageIds": list(completed_ids),
        "profile": {
            "name": identity.name or None,
            "role": identity.role or None,
            "photo": identity.photo_status if identity.photo_status != "unknown" else None,
        },
    }


def _build_context_message(completed_summaries: list[CompletedStageSummary]) -> str | None:
    """Join completed stage summaries into a single context message."""
    if not completed_summaries:
        return None
    lines = [f"[{s.id}]: {s.summary}" for s in completed_summaries]
    return "Previously completed stages:\n" + "\n".join(lines)


# ── OpenAI client cache ──

_openai_client: AsyncAzureOpenAI | None = None
_openai_credential: object | None = None


async def _get_openai_client(settings: Settings | None = None) -> AsyncAzureOpenAI:
    global _openai_client, _openai_credential
    if _openai_client is not None:
        return _openai_client

    settings = settings or get_settings()
    endpoint = settings.effective_azure_openai_endpoint

    if endpoint and settings.azure_openai_key:
        logger.info("OpenAI client: using API key auth → %s", endpoint)
        _openai_client = AsyncAzureOpenAI(
            azure_endpoint=endpoint,
            api_key=settings.azure_openai_key,
            api_version=settings.azure_openai_api_version,
        )
    elif endpoint and settings.entra_tenant_id and settings.entra_client_id and settings.entra_client_secret:
        from azure.identity.aio import ClientSecretCredential, get_bearer_token_provider

        logger.info("OpenAI client: using Entra client-secret auth → %s", endpoint)
        _openai_credential = ClientSecretCredential(
            tenant_id=settings.entra_tenant_id,
            client_id=settings.entra_client_id,
            client_secret=settings.entra_client_secret,
        )
        token_provider = get_bearer_token_provider(
            _openai_credential, "https://cognitiveservices.azure.com/.default",
        )
        _openai_client = AsyncAzureOpenAI(
            azure_endpoint=endpoint,
            azure_ad_token_provider=token_provider,
            api_version=settings.azure_openai_api_version,
        )
    else:
        from azure.ai.projects.aio import AIProjectClient
        from azure.identity.aio import DefaultAzureCredential

        logger.info("OpenAI client: using DefaultAzureCredential via Foundry project → %s",
                     settings.foundry_project_endpoint)
        _openai_credential = DefaultAzureCredential()
        project_client = AIProjectClient(
            endpoint=settings.foundry_project_endpoint,
            credential=_openai_credential,
        )
        _openai_client = project_client.get_openai_client()

    logger.info("OpenAI client initialized (deployment=%s)", settings.effective_azure_openai_deployment)
    return _openai_client


# ── JSON extraction helper ──

def _extract_json(text: str) -> dict | None:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    m = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError):
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except (json.JSONDecodeError, ValueError):
            pass
    return None


# ── Synthesis / Card generation ──

async def _run_synthesis(
    client: AsyncAzureOpenAI,
    settings: Settings,
    completed_summaries: list[CompletedStageSummary],
    current_stage_messages: list[dict],
) -> str:
    evidence_lines: list[str] = []
    for s in completed_summaries:
        evidence_lines.append(f"[{s.id}]: {s.summary}")
    for msg in current_stage_messages:
        evidence_lines.append(f"[current] {msg.get('role', 'user')}: {msg.get('content', '')}")

    stage_summary_lines = [f"- **{s.id}**: {s.summary}" for s in completed_summaries]

    prompt = render_template(
        "synthesis",
        session_id="stateless",
        evidence_summary="\n".join(evidence_lines) if evidence_lines else "No conversation recorded yet.",
        stage_summaries="\n".join(stage_summary_lines) if stage_summary_lines else "No stages completed yet.",
    )
    response = await client.chat.completions.create(
        model=settings.effective_azure_openai_deployment,
        messages=[{"role": "system", "content": prompt}],
        temperature=0.4,
        max_completion_tokens=2000,
    )
    return response.choices[0].message.content or ""


async def _run_card_generation(
    client: AsyncAzureOpenAI,
    settings: Settings,
    synthesis_json: str,
    display_name: str,
    photo_status: str,
) -> dict:
    archetype = "Technologist"
    top_strengths = "[]"
    skill_matrix = "[]"
    evidence_highlights = ""

    syn = _extract_json(synthesis_json)
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
    card_response = await client.chat.completions.create(
        model=settings.effective_azure_openai_deployment,
        messages=[
            {"role": "system", "content": "You are a JSON-only response bot. Output valid JSON with no markdown."},
            {"role": "user", "content": card_prompt},
        ],
        temperature=0.7,
        max_completion_tokens=2000,
    )
    card_text = card_response.choices[0].message.content or ""

    card_data = _extract_json(card_text)
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

    card_data["display_name"] = display_name
    card_data["photo_url"] = None
    return card_data


def _format_synthesis_for_display(synthesis_raw: str) -> str:
    syn = _extract_json(synthesis_raw)
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
            name_val = d.get("name", "?").replace("_", " ").title()
            score = d.get("score", "?")
            conf = d.get("confidence", "?")
            summary = d.get("evidence_summary", "")
            lines.append(f"- **{name_val}**: {score} (confidence: {conf})")
            if summary:
                lines.append(f"  {summary}")
        lines.append("")
    return "\n".join(lines)


# ── Stage summarization ──


async def _generate_stage_summary(
    stage_title: str,
    stage_purpose: str,
    messages: list[dict],
    client: AsyncAzureOpenAI,
    settings: Settings,
) -> str:
    """Generate a concise LLM summary of a completed stage's conversation."""
    conversation_lines = [
        f"{m.get('role', 'user').upper()}: {m.get('content', '')}"
        for m in messages
    ]
    prompt = render_template(
        "stage_summary",
        stage_title=stage_title,
        stage_purpose=stage_purpose,
        conversation="\n".join(conversation_lines),
    )
    try:
        resp = await client.chat.completions.create(
            model=settings.effective_azure_openai_deployment,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_completion_tokens=200,
        )
        summary = (resp.choices[0].message.content or "").strip()
        if summary:
            return summary
    except Exception:
        logger.warning("Stage summary generation failed; using fallback", exc_info=True)
    return f"Completed stage: {stage_title}."


# ── Main stateless turn processor ──

async def process_stateless_turn(
    user_text: str,
    current_stage_id: str,
    completed_summaries: list[CompletedStageSummary],
    current_stage_messages: list[dict],
    identity: IdentityContext,
    has_image: bool = False,
    settings: Settings | None = None,
) -> AsyncGenerator[str, None]:
    """Process a user turn statelessly and yield AI SDK SSE events.

    All state is received as arguments and a `data-stateUpdate` event
    is emitted at the end containing the updated state for the client.
    """
    settings = settings or get_settings()
    client = await _get_openai_client(settings)

    stage = get_stage(current_stage_id)
    if stage is None:
        stage = get_first_stage()
        current_stage_id = stage.id

    # Update identity from user text
    identity = update_identity(identity, user_text, current_stage_id, has_image)

    # Count turns in the current stage (each pair of user+assistant = 1 turn)
    turn_count = len([m for m in current_stage_messages if m.get("role") == "assistant"])

    lowered = user_text.lower()
    completed_ids = [s.id for s in completed_summaries]
    stage_advanced = False
    stage_summary: str | None = None
    new_stage_opening: str | None = None
    session_reset = False
    card_data_result: dict | None = None

    # ── Stage commands ──

    # Next stage / skip
    if any(cmd in lowered for cmd in NEXT_STAGE_COMMANDS):
        next_stage = get_next_stage(current_stage_id)
        if next_stage is None:
            text_id = str(uuid.uuid4())
            msg = "You're already in the final stage. Type `generate card` or `done` to finish."
            yield f'data: {json.dumps({"type": "text-start", "id": text_id})}\n\n'
            yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": msg})}\n\n'
            yield f'data: {json.dumps({"type": "text-end", "id": text_id})}\n\n'
        else:
            stage_summary = await _generate_stage_summary(
                stage.title, stage.purpose, current_stage_messages, client, settings,
            )
            completed_summaries = completed_summaries + [CompletedStageSummary(id=current_stage_id, summary=stage_summary)]
            completed_ids = [s.id for s in completed_summaries]
            current_stage_id = next_stage.id
            stage = next_stage
            stage_advanced = True
            new_stage_opening = next_stage.opening_prompt
            text_id = str(uuid.uuid4())
            msg = f"Next stage: {next_stage.title}.\n\n{next_stage.opening_prompt}"
            yield f'data: {json.dumps({"type": "text-start", "id": text_id})}\n\n'
            yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": msg})}\n\n'
            yield f'data: {json.dumps({"type": "text-end", "id": text_id})}\n\n'

        panel = _build_panel_data(current_stage_id, completed_ids, identity)
        state_update = StateUpdate(
            current_stage_id=current_stage_id,
            identity=_identity_dict(identity),
            stage_advanced=stage_advanced,
            stage_summary=stage_summary,
            new_stage_opening=new_stage_opening,
            panel_data=panel,
        )
        yield f'data: {json.dumps({"type": "data-stateUpdate", "data": state_update.to_dict()})}\n\n'
        yield "data: [DONE]\n\n"
        return

    # Finalize (final stage only) — at card_generation, actually generate the card
    if stage.next_stage is None and any(cmd in lowered for cmd in FINALIZE_COMMANDS):
        if stage.id == "card_generation":
            # Fall through to the card generation handler below by treating this as turn 0
            turn_count = 0
        else:
            text_id = str(uuid.uuid4())
            msg = "Interview complete. Generating your final strengths card output next."
            yield f'data: {json.dumps({"type": "text-start", "id": text_id})}\n\n'
            yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": msg})}\n\n'
            yield f'data: {json.dumps({"type": "text-end", "id": text_id})}\n\n'

            panel = _build_panel_data(current_stage_id, completed_ids, identity)
            state_update = StateUpdate(
                current_stage_id=current_stage_id,
                identity=_identity_dict(identity),
                panel_data=panel,
            )
            yield f'data: {json.dumps({"type": "data-stateUpdate", "data": state_update.to_dict()})}\n\n'
            yield "data: [DONE]\n\n"
            return

    # Start over
    if any(cmd in lowered for cmd in START_OVER_COMMANDS):
        first = get_first_stage()
        identity = IdentityContext()
        current_stage_id = first.id
        session_reset = True
        text_id = str(uuid.uuid4())
        msg = "Starting over! Let's begin the interview from scratch.\n\n" + first.opening_prompt
        yield f'data: {json.dumps({"type": "text-start", "id": text_id})}\n\n'
        yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": msg})}\n\n'
        yield f'data: {json.dumps({"type": "text-end", "id": text_id})}\n\n'

        panel = _build_panel_data(current_stage_id, [], identity)
        state_update = StateUpdate(
            current_stage_id=current_stage_id,
            identity=_identity_dict(identity),
            stage_advanced=True,
            new_stage_opening=first.opening_prompt,
            panel_data=panel,
            session_reset=True,
        )
        yield f'data: {json.dumps({"type": "data-stateUpdate", "data": state_update.to_dict()})}\n\n'
        yield "data: [DONE]\n\n"
        return

    # Jump to card generation (/card shortcut)
    if any(lowered.strip() == cmd for cmd in JUMP_TO_CARD_COMMANDS):
        # Summarize current stage before jumping
        if current_stage_id != "card_generation":
            stage_summary = await _generate_stage_summary(
                stage.title, stage.purpose, current_stage_messages, client, settings,
            )
            completed_summaries = completed_summaries + [CompletedStageSummary(id=current_stage_id, summary=stage_summary)]
            # Also mark any skipped stages between current and card_generation
            all_stages = get_all_stages()
            completed_set = {s.id for s in completed_summaries}
            for s in all_stages:
                if s.id == "card_generation":
                    break
                if s.id not in completed_set:
                    completed_summaries = completed_summaries + [CompletedStageSummary(id=s.id, summary=f"Skipped stage: {s.title}")]
            completed_ids = [s.id for s in completed_summaries]

        card_stage = get_stage("card_generation")
        if card_stage:
            current_stage_id = card_stage.id
            stage = card_stage
            stage_advanced = True
            # Force turn_count=0 so card generation handler fires
            turn_count = 0

    # Progress query
    if any(tok in lowered for tok in PROGRESS_COMMANDS):
        all_stages = get_all_stages()
        completed_set = set(completed_ids)
        insight_lines = [
            f"Current stage: {current_stage_id} ({stage.title})",
            f"Completed: {len(completed_ids)}/{len(all_stages)} stages",
            f"Turns in this stage: {turn_count}/{FAST_STAGE_HARD_TURN_LIMIT}",
        ]
        if current_stage_id == "introduction":
            missing = _intro_missing(identity)
            if missing:
                insight_lines.append("To move on, I still need: " + ", ".join(missing) + ".")
            else:
                insight_lines.append("Introduction criteria are met; I can move to the next stage now.")
        else:
            insight_lines.append(_completion_hint(stage, turn_count, identity))

        text_id = str(uuid.uuid4())
        msg = "\n".join(insight_lines)
        yield f'data: {json.dumps({"type": "text-start", "id": text_id})}\n\n'
        yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": msg})}\n\n'
        yield f'data: {json.dumps({"type": "text-end", "id": text_id})}\n\n'

        panel = _build_panel_data(current_stage_id, completed_ids, identity)
        state_update = StateUpdate(
            current_stage_id=current_stage_id,
            identity=_identity_dict(identity),
            panel_data=panel,
        )
        yield f'data: {json.dumps({"type": "data-stateUpdate", "data": state_update.to_dict()})}\n\n'
        yield "data: [DONE]\n\n"
        return

    # ── Validation stage: synthesize profile on first turn ──
    if stage.id == "validation" and turn_count == 0:
        text_id = str(uuid.uuid4())
        yield f'data: {json.dumps({"type": "text-start", "id": text_id})}\n\n'

        preamble = stage.opening_prompt + "\n\nLet me synthesize your profile...\n\n"
        yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": preamble})}\n\n'

        try:
            synthesis_raw = await _run_synthesis(client, settings, completed_summaries, current_stage_messages)
            display_text = _format_synthesis_for_display(synthesis_raw)
            yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": display_text})}\n\n'

            closing = "\n\n**What did I get right? What did I miss or get wrong? Anything you want to add or emphasize?**"
            yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": closing})}\n\n'
        except Exception as e:
            logger.error("Synthesis failed: %s", e, exc_info=True)
            error_msg = f"I couldn't synthesize your profile right now. ({type(e).__name__}: {e})"
            yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": error_msg})}\n\n'

        yield f'data: {json.dumps({"type": "text-end", "id": text_id})}\n\n'

        panel = _build_panel_data(current_stage_id, completed_ids, identity)
        state_update = StateUpdate(
            current_stage_id=current_stage_id,
            identity=_identity_dict(identity),
            panel_data=panel,
        )
        yield f'data: {json.dumps({"type": "data-stateUpdate", "data": state_update.to_dict()})}\n\n'
        yield "data: [DONE]\n\n"
        return

    # ── Card generation stage: generate card spec on first turn ──
    if stage.id == "card_generation" and turn_count == 0:
        text_id = str(uuid.uuid4())
        yield f'data: {json.dumps({"type": "text-start", "id": text_id})}\n\n'

        preamble = stage.opening_prompt + "\n\n"
        yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": preamble})}\n\n'

        try:
            yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": "Synthesizing your profile first...\\n\\n"})}\n\n'
            synthesis_json = await _run_synthesis(client, settings, completed_summaries, current_stage_messages)

            yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": "Generating your Skill Deck card...\\n\\n"})}\n\n'
            display_name = identity.name or "Anonymous"
            card_data_result = await _run_card_generation(client, settings, synthesis_json, display_name, identity.photo_status)

            status_msg = f"Your **{card_data_result.get('display_name', 'Skill')} Deck** card is ready! Check it out below."
            yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": status_msg})}\n\n'
            yield f'data: {json.dumps({"type": "text-end", "id": text_id})}\n\n'

            yield f'data: {json.dumps({"type": "data-cardData", "data": card_data_result})}\n\n'
        except Exception as e:
            logger.error("Card generation failed: %s", e, exc_info=True)
            error_msg = f"I couldn't generate your card right now. ({type(e).__name__}: {e})"
            yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": error_msg})}\n\n'
            yield f'data: {json.dumps({"type": "text-end", "id": text_id})}\n\n'
            card_data_result = None

        panel = _build_panel_data(current_stage_id, completed_ids, identity)
        state_update = StateUpdate(
            current_stage_id=current_stage_id,
            identity=_identity_dict(identity),
            panel_data=panel,
            card_data=card_data_result,
        )
        yield f'data: {json.dumps({"type": "data-stateUpdate", "data": state_update.to_dict()})}\n\n'
        yield "data: [DONE]\n\n"
        return

    # ── Regular conversational turn ──
    context = {
        "stage_title": stage.title,
        "stage_purpose": stage.purpose,
        "opening_prompt": stage.opening_prompt,
        "context_summary": (
            f"Photo status: {identity.photo_status}. "
            "If photo is uploaded or skipped, do not ask about photo again. "
            "Ask exactly one high-yield question at a time, keep response concise (2-4 sentences), "
            "and prefer concrete examples with outcomes."
        ),
        "extraction_targets": "\n".join(f"- {t}" for t in stage.extraction_targets),
        "follow_up_style": stage.follow_up_style,
        "completion_criteria": "\n".join(f"- {c}" for c in stage.completion_criteria),
    }

    if turn_count >= FAST_STAGE_SOFT_TURN_LIMIT:
        context["context_summary"] += " Stage is near completion; summarize signal and suggest moving on."

    system_prompt = render_template("interview_system", **context)

    # Build LLM message history
    history: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]

    # Add context from completed stages
    context_msg = _build_context_message(completed_summaries)
    if context_msg:
        history.append({"role": "system", "content": context_msg})

    # Add current stage messages (last 8 turns = 16 messages max)
    recent = current_stage_messages[-16:]
    for msg in recent:
        history.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})

    # Add new user message
    history.append({"role": "user", "content": user_text})

    # Stream from Azure OpenAI
    full_response = ""
    text_id = str(uuid.uuid4())

    yield f'data: {json.dumps({"type": "text-start", "id": text_id})}\n\n'

    try:
        stream = await client.chat.completions.create(
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
    except Exception as e:
        logger.error("LLM streaming call failed: %s", e, exc_info=True)
        error_msg = f"I couldn't reach the AI model. Please check your Azure credentials and try again. ({type(e).__name__})"
        yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": error_msg})}\n\n'
        full_response = error_msg

    yield f'data: {json.dumps({"type": "text-end", "id": text_id})}\n\n'

    # ── Automatic stage transitions ──

    # Deterministic intro progression
    if stage.id == "introduction":
        missing = _intro_missing(identity)
        if not missing:
            stage_summary = await _generate_stage_summary(
                stage.title, stage.purpose, current_stage_messages, client, settings,
            )
            completed_summaries = completed_summaries + [CompletedStageSummary(id=current_stage_id, summary=stage_summary)]
            completed_ids = [s.id for s in completed_summaries]
            next_s = get_next_stage(current_stage_id)
            if next_s is not None:
                current_stage_id = next_s.id
                stage = next_s
                stage_advanced = True
                new_stage_opening = next_s.opening_prompt
                transition_id = str(uuid.uuid4())
                transition_text = f"\n\nMoving to: {next_s.title}.\n{next_s.opening_prompt}"
                yield f'data: {json.dumps({"type": "text-start", "id": transition_id})}\n\n'
                yield f'data: {json.dumps({"type": "text-delta", "id": transition_id, "delta": transition_text})}\n\n'
                yield f'data: {json.dumps({"type": "text-end", "id": transition_id})}\n\n'

    # Fast-track auto-advance (turn_count + 1 because we just did a turn)
    effective_turns = turn_count + 1
    if not stage_advanced and effective_turns >= FAST_STAGE_HARD_TURN_LIMIT:
        if stage.next_stage is not None:
            stage_summary = await _generate_stage_summary(
                stage.title, stage.purpose, current_stage_messages, client, settings,
            )
            completed_summaries = completed_summaries + [CompletedStageSummary(id=current_stage_id, summary=stage_summary)]
            completed_ids = [s.id for s in completed_summaries]
            next_s = get_next_stage(current_stage_id)
            if next_s is not None:
                current_stage_id = next_s.id
                stage = next_s
                stage_advanced = True
                new_stage_opening = next_s.opening_prompt
                transition_id = str(uuid.uuid4())
                transition_text = f"\n\nFast-track: moving to {next_s.title}.\n{next_s.opening_prompt}"
                yield f'data: {json.dumps({"type": "text-start", "id": transition_id})}\n\n'
                yield f'data: {json.dumps({"type": "text-delta", "id": transition_id, "delta": transition_text})}\n\n'
                yield f'data: {json.dumps({"type": "text-end", "id": transition_id})}\n\n'

    # ── Emit state update ──
    panel = _build_panel_data(current_stage_id, completed_ids, identity)
    state_update = StateUpdate(
        current_stage_id=current_stage_id,
        identity=_identity_dict(identity),
        stage_advanced=stage_advanced,
        stage_summary=stage_summary,
        new_stage_opening=new_stage_opening,
        panel_data=panel,
    )
    yield f'data: {json.dumps({"type": "data-stateUpdate", "data": state_update.to_dict()})}\n\n'
    yield "data: [DONE]\n\n"
