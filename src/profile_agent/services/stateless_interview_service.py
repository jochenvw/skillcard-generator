"""Stateless interview service — processes turns without server-side session state.

All conversation state is passed in the request and returned in the response.
The server only holds cached stage definitions and a reusable OpenAI client.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from functools import lru_cache

from openai import AsyncAzureOpenAI, RateLimitError

from pydantic import ValidationError

from profile_agent.config.settings import Settings, get_settings
from profile_agent.models.llm_contracts import CardStyle
from profile_agent.models.skill_card_profile import SkillCardProfile
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
REGENERATE_COMMANDS = (
    "regenerate", "regenerate card", "regen", "generate again", "rebuild",
    "redo card", "redo", "update card", "remake", "make it again",
)


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


_ROLE_STOP_WORDS = {
    "engineer", "architect", "developer", "consultant", "manager", "lead",
    "solution", "senior", "junior", "principal", "staff", "director", "head",
    "designer", "scientist", "analyst", "founder", "ceo", "cto", "cio", "vp",
    "for", "at", "from", "in", "of", "the", "a", "an", "and",
}

_NON_NAME_PHRASES = {
    "skip", "upload", "later", "no", "nope", "yes", "y", "n",
    "ok", "okay", "thanks", "thank you", "great", "perfect", "cool", "nice",
    "looks good", "sounds good", "looks great", "sounds great", "got it",
    "alright", "sure", "fine", "good", "awesome", "done",
}


_NAME_PARTICLES = {"van", "von", "de", "der", "den", "del", "della", "di", "da", "le", "la", "el", "bin", "ibn", "al"}


def _clean_name_candidate(raw: str) -> str | None:
    parts: list[str] = []
    for tok in raw.replace(",", " ").split():
        # Stop at first dash, role marker, or "is/am/work" verb
        low = tok.lower().strip(".,;:!?")
        if low in {"-", "—", "–"} or low in _ROLE_STOP_WORDS:
            break
        if not low or not all(ch.isalpha() or ch in "-'" for ch in low):
            break
        parts.append(low)
        if len(parts) >= 4:
            break
    if not parts:
        return None
    return " ".join(p if p in _NAME_PARTICLES else p.capitalize() for p in parts)


def _extract_title_from_role(role_text: str) -> str | None:
    """Pull a clean title like 'Senior Solution Engineer' from a free-form role sentence."""
    text = role_text.strip()
    if not text:
        return None
    # If there's a dash, prefer the chunk AFTER the first dash (typical "Name - Title for Company" form).
    dash_match = re.search(r"\s*[-–—]\s*", text)
    cleaned = text[dash_match.end():] if dash_match else text
    # Drop any leading "I'm a / I am / I work as / my role is"
    cleaned = re.sub(r"^(?:i['\u2019]m|i am|i work as|my role is)\s+(?:a |an )?", "", cleaned, flags=re.I)
    # Cut at "for ", "at ", connectors that introduce employer/team
    cleaned = re.split(r"\s+(?:for|at|with|in)\s+", cleaned, maxsplit=1, flags=re.I)[0]
    cleaned = cleaned.strip(" .,-—–")
    if 2 <= len(cleaned.split()) <= 8:
        return cleaned
    return None


def _extract_name_and_role(user_text: str) -> tuple[str | None, str | None]:
    text = user_text.strip()
    lowered = text.lower()
    name: str | None = None
    role: str | None = None

    m = re.search(r"\bmy name is\s+(.{1,80})", lowered)
    if m:
        name = _clean_name_candidate(m.group(1))

    if name is None:
        m2 = re.search(r"\b(?:i am|i'm)\s+([a-z][a-z\s\-']{1,30})", lowered)
        if m2:
            candidate2 = m2.group(1).strip(" .,")
            if not candidate2.startswith(("a ", "an ", "the ")):
                name = _clean_name_candidate(candidate2)

    if name is None and 1 <= len(text.split()) <= 4 \
            and all(ch.isalpha() or ch.isspace() or ch in "-'" for ch in text) \
            and lowered not in _NON_NAME_PHRASES \
            and not any(tok.lower() in _ROLE_STOP_WORDS for tok in text.split()):
        name = " ".join(w.capitalize() for w in text.split())

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
    title: str = ""
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
    bulk_extracted: dict | None = None

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
        if self.bulk_extracted is not None:
            d["bulkExtracted"] = self.bulk_extracted
        return d


def _identity_dict(ctx: IdentityContext) -> dict:
    return {"name": ctx.name, "role": ctx.role, "title": ctx.title, "photoStatus": ctx.photo_status}


_IDENTITY_EXTRACTION_PROMPT = """\
Extract the speaker's full name and current job title from the message below.

Rules:
- "name" = the person's full name only (no titles, no company). Use their original
  capitalization for particles ("van", "von", "de", "la", "der" stay lowercase).
- "title" = their job/role (e.g. "Senior Solution Engineer", "Staff Engineer",
  "Product Manager", "VP of Engineering"). Drop the company name ("at Microsoft NL"
  → just the title). Drop articles ("a", "an", "the"). 2–8 words.
- If a field is not stated or unclear, return null for that field.
- Do NOT invent. Do NOT use defaults. If the user just said "ok" or "looks good",
  return {"name": null, "title": null}.

Output **only** JSON: {"name": string|null, "title": string|null}

Message:
\"\"\"$message\"\"\"
"""


async def _extract_identity_with_llm(
    user_text: str,
    client: AsyncAzureOpenAI,
    settings: Settings,
) -> tuple[str | None, str | None]:
    """LLM-based name/title extraction. Returns (name, title) or (None, None)."""
    text = user_text.strip()
    if not text or len(text) < 2:
        return None, None
    try:
        prompt = _IDENTITY_EXTRACTION_PROMPT.replace("$message", text[:1000])
        resp = await client.chat.completions.create(
            model=settings.effective_azure_openai_deployment,
            messages=[
                {"role": "system", "content": "You are a strict JSON extractor. Output only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_completion_tokens=120,
        )
        raw = resp.choices[0].message.content or ""
        data = _extract_json(raw) or {}
        name = data.get("name")
        title = data.get("title")
        name = name.strip() or None if isinstance(name, str) else None
        title = title.strip() or None if isinstance(title, str) else None
        return name, title
    except Exception as exc:
        logger.warning("LLM identity extraction failed: %s", exc)
        return None, None


def update_identity(identity: IdentityContext, user_text: str, current_stage_id: str, has_image: bool = False) -> IdentityContext:
    """Return an updated copy of identity based on user text (regex fast path)."""
    new = IdentityContext(
        name=identity.name,
        role=identity.role,
        title=identity.title,
        photo_status=identity.photo_status,
    )
    lowered = user_text.lower()

    if has_image:
        new.photo_status = "uploaded"

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


async def update_identity_async(
    identity: IdentityContext,
    user_text: str,
    current_stage_id: str,
    has_image: bool,
    client: AsyncAzureOpenAI,
    settings: Settings,
) -> IdentityContext:
    """LLM-augmented identity update.

    Calls update_identity() for the cheap stuff (photo status, raw role text),
    then asks the LLM to extract name + title from the message — but only
    during the introduction stage and only if name or title are still missing.
    """
    new = update_identity(identity, user_text, current_stage_id, has_image)

    needs_extraction = (
        current_stage_id == "introduction"
        and (not new.name or not new.title)
        and len(user_text.strip()) >= 2
    )
    if not needs_extraction:
        return new

    extracted_name, extracted_title = await _extract_identity_with_llm(user_text, client, settings)
    if extracted_name and not new.name:
        new.name = extracted_name
    if extracted_title and not new.title:
        new.title = extracted_title
    return new


# ── Bulk profile text extraction ──

_BULK_TEXT_MIN_LENGTH = 200  # Minimum chars to trigger bulk extraction


def _is_bulk_profile_text(text: str) -> bool:
    """Detect if user input is a large block of profile/resume/bio text."""
    stripped = text.strip()
    if len(stripped) < _BULK_TEXT_MIN_LENGTH:
        return False
    # Must not be a command-only message
    lowered = stripped.lower()
    if lowered.startswith(("/", "!")):
        return False
    # Only reject if the ENTIRE message is a short command
    # (don't reject long text just because it contains words like "done" or "complete")
    if len(stripped) < 300 and any(cmd == lowered for cmd in NEXT_STAGE_COMMANDS + FINALIZE_COMMANDS + START_OVER_COMMANDS):
        return False
    return True


async def _extract_bulk_profile(
    user_text: str,
    client: AsyncAzureOpenAI,
    settings: Settings,
) -> dict | None:
    """Extract structured profile data from a large text block via LLM."""
    prompt = render_template("bulk_extraction", user_text=user_text[:50_000])

    try:
        response = await client.chat.completions.create(
            model=settings.effective_azure_openai_deployment,
            messages=[{"role": "system", "content": prompt}],
            temperature=0.2,
            max_completion_tokens=2000,
        )
    except Exception:
        logger.warning("Bulk profile extraction LLM call failed", exc_info=True)
        return None

    content = (response.choices[0].message.content or "") if response.choices else ""
    parsed = _extract_json(content)
    if not isinstance(parsed, dict):
        logger.warning("Bulk profile extraction: could not parse JSON")
        return None

    logger.info(
        "Bulk extraction success | name=%s title=%s skills=%d projects=%d",
        parsed.get("name"), parsed.get("title"),
        len(parsed.get("skills", [])), len(parsed.get("projects", [])),
    )
    return parsed


def _format_bulk_context(extracted: dict) -> str:
    """Format bulk-extracted profile data into a context block for the system prompt."""
    parts: list[str] = []
    parts.append("## Pre-extracted profile data (from user's pasted text)")
    parts.append("The user already provided the following information in a previous message. "
                 "DO NOT ask for any of this again. Only ask follow-up questions for items NOT listed here.\n")

    if extracted.get("name"):
        parts.append(f"**Name:** {extracted['name']}")
    if extracted.get("title"):
        parts.append(f"**Title/Role:** {extracted['title']}")
    if extracted.get("industry"):
        parts.append(f"**Industry:** {extracted['industry']}")

    skills = extracted.get("skills", [])
    if skills:
        skill_names = [s["name"] for s in skills if isinstance(s, dict) and s.get("name")]
        if skill_names:
            parts.append(f"**Skills:** {', '.join(skill_names)}")

    projects = extracted.get("projects", [])
    if projects:
        proj_names = [p["name"] for p in projects if isinstance(p, dict) and p.get("name")]
        if proj_names:
            parts.append(f"**Projects:** {', '.join(proj_names)}")

    if extracted.get("heroes"):
        parts.append(f"**Heroes/Role Models:** {', '.join(extracted['heroes'])}")
    if extracted.get("influences"):
        parts.append(f"**Influences:** {', '.join(extracted['influences'])}")
    if extracted.get("aspirations"):
        parts.append(f"**Aspirations:** {', '.join(extracted['aspirations'])}")
    if extracted.get("strengths"):
        parts.append(f"**Strengths:** {', '.join(extracted['strengths'])}")
    if extracted.get("collaboration_style"):
        parts.append(f"**Collaboration style:** {extracted['collaboration_style']}")
    if extracted.get("learning_interests"):
        parts.append(f"**Learning interests:** {', '.join(extracted['learning_interests'])}")
    if extracted.get("accomplishments"):
        parts.append(f"**Accomplishments:** {', '.join(extracted['accomplishments'])}")
    if extracted.get("education"):
        parts.append(f"**Education:** {', '.join(extracted['education'])}")

    parts.append("\n**Instruction:** Acknowledge what you already know from this data. "
                 "Do NOT re-ask for anything listed above. Only ask targeted follow-ups "
                 "for information that is genuinely missing for the current stage.")

    return "\n".join(parts)


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


def _is_regeneration_intent(text: str) -> bool:
    """Detect if the user wants to regenerate/update their card."""
    lowered = text.lower().strip()
    # Exact regeneration commands
    if any(cmd in lowered for cmd in REGENERATE_COMMANDS):
        return True
    # Edit/update patterns — "update this", "change X", "actually X", "add X to card"
    edit_patterns = (
        "update this", "update my", "change my", "change the", "change it",
        "actually change", "actually update", "add this", "add that",
        "fix my", "fix the", "edit my", "edit the", "modify",
        "to card", "to the card", "on my card", "on the card",
    )
    if any(p in lowered for p in edit_patterns):
        return True
    return False


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
        from profile_agent.config.settings import get_azure_credential

        _openai_credential = await get_azure_credential(settings)
        cred_type = type(_openai_credential).__name__
        logger.info("OpenAI client: using %s via Foundry project → %s",
                     cred_type, settings.foundry_project_endpoint)
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
    additional_context: str | None = None,
) -> str:
    evidence_lines: list[str] = []
    for s in completed_summaries:
        evidence_lines.append(f"[{s.id}]: {s.summary}")
    for msg in current_stage_messages:
        evidence_lines.append(f"[current] {msg.get('role', 'user')}: {msg.get('content', '')}")
    if additional_context:
        evidence_lines.append(f"[additional_context]: {additional_context}")

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
        max_completion_tokens=6000,
    )
    return response.choices[0].message.content or ""


async def _run_card_generation(
    client: AsyncAzureOpenAI,
    settings: Settings,
    synthesis_json: str,
    display_name: str,
    photo_status: str,
    clifton_strengths: list[str] | None = None,
    linkedin_skills: dict | None = None,
    github_skills: dict | None = None,
    completed_summaries: list[CompletedStageSummary] | None = None,
    role_text: str | None = None,
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

    clifton_list = [s for s in (clifton_strengths or []) if isinstance(s, str) and s.strip()]
    clifton_block = "\n".join(f"• {s.strip()}" for s in clifton_list) if clifton_list else ""

    # Format LinkedIn evidence
    linkedin_block = ""
    if linkedin_skills and (linkedin_skills.get("skills") or linkedin_skills.get("projects")):
        parts = [f"Summary: {linkedin_skills.get('summary', 'N/A')}"]
        for sk in linkedin_skills.get("skills", []):
            conf = sk.get("confidence", "?")
            parts.append(f"• {sk.get('name', '?')} ({sk.get('category', '?')}, confidence={conf}): {sk.get('evidence', '')}")
        if linkedin_skills.get("projects"):
            parts.append("\nProjects:")
            for proj in linkedin_skills["projects"]:
                techs = ", ".join(proj.get("technologies", [])) if proj.get("technologies") else "N/A"
                parts.append(f"  → {proj.get('name', '?')} [{techs}]: {proj.get('description', '')}")
        if linkedin_skills.get("highlights"):
            parts.append("Highlights: " + "; ".join(linkedin_skills["highlights"]))
        linkedin_block = "\n".join(parts)

    # Format GitHub evidence
    github_block = ""
    if github_skills and (github_skills.get("skills") or github_skills.get("projects")):
        parts = [f"Summary: {github_skills.get('summary', 'N/A')}"]
        for sk in github_skills.get("skills", []):
            conf = sk.get("confidence", "?")
            parts.append(f"• {sk.get('name', '?')} ({sk.get('category', '?')}, confidence={conf}): {sk.get('evidence', '')}")
        if github_skills.get("projects"):
            parts.append("\nNotable repositories:")
            for proj in github_skills["projects"]:
                techs = ", ".join(proj.get("technologies", [])) if proj.get("technologies") else "N/A"
                parts.append(f"  → {proj.get('name', '?')} [{techs}]: {proj.get('description', '')}")
        if github_skills.get("focus_areas"):
            parts.append("Focus areas: " + ", ".join(github_skills["focus_areas"]))
        if github_skills.get("highlights"):
            parts.append("Highlights: " + "; ".join(github_skills["highlights"]))
        github_block = "\n".join(parts)

    # Raw per-stage evidence — needed because the synthesis JSON above only
    # captures technical skill dimensions and drops the rich content about
    # heroes, books, aspirations etc.
    if completed_summaries:
        stage_evidence = "\n\n".join(
            f"### [{s.id}]\n{s.summary}" for s in completed_summaries if s.summary
        )
    else:
        stage_evidence = "(no stage summaries available)"

    card_prompt = render_template(
        "card_generation",
        display_name=display_name,
        display_title=_extract_title_from_role(role_text or "") or "",
        archetype=archetype,
        top_strengths=top_strengths,
        skill_matrix=skill_matrix,
        evidence_highlights=evidence_highlights or "No highlights available.",
        clifton_strengths=clifton_block,
        linkedin_evidence=linkedin_block,
        github_evidence=github_block,
        stage_evidence=stage_evidence,
    )
    card_response = await client.chat.completions.create(
        model=settings.effective_azure_openai_deployment,
        messages=[
            {"role": "system", "content": "You are a JSON-only response bot. Output valid JSON with no markdown."},
            {"role": "user", "content": card_prompt},
        ],
        temperature=0.7,
        max_completion_tokens=6000,
    )
    card_text = card_response.choices[0].message.content or ""

    card_data = _extract_json(card_text)
    if card_data is None:
        logger.warning("Could not parse SkillCardProfile JSON; using fallback")
        card_data = {}

    if not card_data.get("name"):
        card_data["name"] = display_name
    extracted_title = _extract_title_from_role(role_text or "") if role_text else None
    current_title = (card_data.get("title") or "").strip()
    # Force the parsed-from-introduction title to win over the LLM's generic
    # "Technologist" archetype when the user explicitly stated their title.
    if extracted_title and (not current_title or current_title.lower() in {"technologist", "technology"}):
        card_data["title"] = extracted_title
    if clifton_list and not card_data.get("clifton_strengths"):
        card_data["clifton_strengths"] = clifton_list

    try:
        profile = SkillCardProfile.model_validate(card_data)
    except ValidationError as ve:
        logger.warning("SkillCardProfile validation failed: %s", ve.errors())
        profile = SkillCardProfile(
            name=display_name or "Anonymous",
            title=str(card_data.get("title") or ""),
            industry=str(card_data.get("industry") or "Technology"),
            strengths=card_data.get("strengths") or ["—"],
            clifton_strengths=clifton_list,
            inspirations=card_data.get("inspirations") or [],
            aspirations=card_data.get("aspirations") or ["—"],
            learn_grow=card_data.get("learn_grow") or ["—"],
            accomplishments=card_data.get("accomplishments") or [],
            growth_focus=str(card_data.get("growth_focus") or ""),
            flavor_text=str(card_data.get("flavor_text") or ""),
        )

    result = profile.model_dump()
    # Photo metadata travels alongside the profile but is not part of the schema
    result["photo_url"] = None
    result["photo_status"] = photo_status
    return result


_image_client: AsyncAzureOpenAI | None = None


async def _get_image_client(settings: Settings) -> AsyncAzureOpenAI:
    """Separate client for image generation — AIProjectClient doesn't support images.generate()."""
    global _image_client
    if _image_client is not None:
        return _image_client

    from azure.identity.aio import get_bearer_token_provider
    from urllib.parse import urlparse
    from profile_agent.config.settings import get_azure_credential

    # Endpoint resolution:
    #   1. explicit override (e.g. APIM gateway in front of the AI Services resource)
    #   2. derive services.ai endpoint from the Foundry project endpoint
    if settings.foundry_image_endpoint_override:
        endpoint = settings.foundry_image_endpoint_override.rstrip("/")
        endpoint_source = "override"
    else:
        host = urlparse(settings.foundry_project_endpoint).hostname or ""
        resource_name = host.split(".")[0] if host else ""
        endpoint = f"https://{resource_name}.services.ai.azure.com" if resource_name else ""
        endpoint_source = "derived"

    if not endpoint:
        raise RuntimeError("Cannot derive image endpoint from Foundry project endpoint")

    # Auth: API key wins when paired with an override (typical APIM scenario);
    # otherwise fall back to AAD bearer tokens.
    if settings.foundry_image_api_key:
        _image_client = AsyncAzureOpenAI(
            azure_endpoint=endpoint,
            api_key=settings.foundry_image_api_key,
            api_version=settings.azure_openai_api_version,
        )
        auth_type = "api_key"
    else:
        cred = await get_azure_credential(settings)
        auth_type = type(cred).__name__
        token_provider = get_bearer_token_provider(cred, "https://cognitiveservices.azure.com/.default")
        _image_client = AsyncAzureOpenAI(
            azure_endpoint=endpoint,
            azure_ad_token_provider=token_provider,
            api_version=settings.azure_openai_api_version,
        )
    logger.info("Image client initialized → %s (endpoint=%s, auth=%s, deployment=%s)",
                endpoint, endpoint_source, auth_type, settings.foundry_image_deployment_name)
    return _image_client


def format_bullets(items: list[str]) -> str:
    if not items:
        return "• —"
    return "\n".join(f"• {item.strip()}" for item in items[:5])


# ── Card image prompt builder ──

# Default tokens — used when the user does not customize. These exact strings
# are what produced the "current look" before the customization feature, so
# any test that pins the no-style output should compare against them.
_DEFAULT_DESIGN_LINES = (
    "- metallic sci-fi frame with beveled edges\n"
    "- layered UI panels with depth and shadows\n"
    "- blue and cyan glowing accents\n"
    "- polished, sharp, AAA game UI quality\n"
    "- high contrast, crisp edges, no blur"
)
_DEFAULT_ACCENT_LINE = "- blue and cyan glowing accents"
_DEFAULT_STYLE_LINE = (
    "Style: clean structured UI, resembles a collectible card game interface, "
    "precise alignment, symmetrical layout, subtle gradients and metallic textures."
)

# Maps for known presets. Unknown values fall back to defaults (no-op).
_STYLE_PRESET_DESIGN: dict[str, str] = {
    "Cyberpunk Neon": (
        "- glitch-neon frame with chromatic aberration edges\n"
        "- layered UI panels lit by hot magenta and electric cyan signage\n"
        "- neon glow accents bleeding into rain-slick reflections\n"
        "- gritty cyberpunk holo-overlays, scanlines, AAA game UI quality\n"
        "- high contrast, crisp edges, no blur"
    ),
    "Pokémon TCG": (
        "- glossy holofoil frame in classic trading-card-game proportions\n"
        "- bold yellow border with energy-type icon corners\n"
        "- bright primary-color accents and starburst foil shimmer\n"
        "- clean cartoon-illustration UI, AAA card-game quality\n"
        "- high contrast, crisp edges, no blur"
    ),
    "Fantasy Trading Card": (
        "- ornate gold-filigree frame with hand-painted parchment panels\n"
        "- engraved scrollwork dividers and gemstone inlays at corners\n"
        "- warm amber and emerald glowing accents like enchanted runes\n"
        "- painterly fantasy-art UI, AAA collectible-card quality\n"
        "- high contrast, crisp edges, no blur"
    ),
    "Vaporwave": (
        "- pastel chrome frame with retro grid horizon lines\n"
        "- layered UI panels in soft pink, lavender, and teal\n"
        "- glowing magenta and cyan sunset-gradient accents\n"
        "- 80s-anime VHS aesthetic UI, AAA card-game quality\n"
        "- high contrast, crisp edges, no blur"
    ),
}

_STYLE_PRESET_OUTRO: dict[str, str] = {
    "Cyberpunk Neon": (
        "Style: gritty cyberpunk UI, neon-drenched holographic overlays, "
        "precise alignment, symmetrical layout, rain-slick reflective textures."
    ),
    "Pokémon TCG": (
        "Style: classic Pokémon-style trading card UI, holofoil shimmer, "
        "precise alignment, symmetrical layout, glossy cartoon textures."
    ),
    "Fantasy Trading Card": (
        "Style: high-fantasy collectible card UI, painterly textures, "
        "precise alignment, symmetrical layout, gold-filigree and parchment finishes."
    ),
    "Vaporwave": (
        "Style: vaporwave/retrofuture UI, pastel chrome and sunset gradients, "
        "precise alignment, symmetrical layout, soft VHS textures."
    ),
}

# A persona "Professional" (or None) keeps the original portrait line intact.
_PERSONA_PORTRAIT: dict[str, str] = {
    "Superhero": (
        "depicted as a confident superhero in a heroic stance, flowing cape, "
        "subtle emblem on the chest, retaining the facial likeness from the reference photo"
    ),
    "Wizard": (
        "depicted as a wise wizard in flowing robes holding a glowing artifact, "
        "retaining the facial likeness from the reference photo"
    ),
    "Astronaut": (
        "depicted as an astronaut in a sleek modern spacesuit with the helmet "
        "off or visor up, retaining the facial likeness from the reference photo"
    ),
    "Anime Hero": (
        "depicted in vibrant anime-hero style with dynamic pose and stylised hair, "
        "retaining the facial likeness from the reference photo"
    ),
    "Cybernetic Operative": (
        "depicted as a cybernetic operative in tactical gear with subtle augmentations "
        "and a heads-up visor, retaining the facial likeness from the reference photo"
    ),
}


def _build_card_image_prompt(card_data: dict, style: "CardStyle | None" = None) -> str:
    """Build the gpt-image prompt for the SkillCard.

    When ``style`` is None or all its fields are None/empty, the returned
    prompt is byte-identical to the prior hard-coded prompt — the "current
    look" is fully preserved for users who don't customize.
    """
    name = card_data.get("name") or card_data.get("display_name") or "Unknown"
    title = card_data.get("title") or ""
    industry = card_data.get("industry") or "Technology"
    strengths = card_data.get("strengths") or []
    clifton_strengths = card_data.get("clifton_strengths") or []
    inspirations = card_data.get("inspirations") or []
    aspirations = card_data.get("aspirations") or []
    learn_grow = card_data.get("learn_grow") or []
    accomplishments = card_data.get("accomplishments") or []
    growth_focus = card_data.get("growth_focus") or ""
    flavor_text = card_data.get("flavor_text") or ""
    portrait_hint = card_data.get("portrait_hint") or ""

    style_preset = (getattr(style, "style_preset", None) or "").strip()
    persona = (getattr(style, "persona_setting", None) or "").strip()
    accent_color = (getattr(style, "accent_color", None) or "").strip()

    # Design block: swap entire block for known non-default presets.
    if style_preset and style_preset != "Futuristic Metallic" and style_preset in _STYLE_PRESET_DESIGN:
        design_block = _STYLE_PRESET_DESIGN[style_preset]
        outro_style_line = _STYLE_PRESET_OUTRO[style_preset]
    else:
        design_block = _DEFAULT_DESIGN_LINES
        outro_style_line = _DEFAULT_STYLE_LINE

    # Accent color: replace the design-block bullet that mentions "accents"
    # (works for the default block and every preset block — they all have
    # exactly one such line as the 3rd bullet).
    if accent_color:
        accent_line = f"- {accent_color} glowing accents"
        new_lines = []
        replaced = False
        for line in design_block.split("\n"):
            if not replaced and "accents" in line.lower():
                new_lines.append(accent_line)
                replaced = True
            else:
                new_lines.append(line)
        design_block = "\n".join(new_lines)

    # Portrait persona line.
    if persona and persona != "Professional" and persona in _PERSONA_PORTRAIT:
        portrait_line = f"- the person is {_PERSONA_PORTRAIT[persona]}"
    else:
        portrait_line = f"- the person is a confident professional, {title} appearance"

    return f"""A premium, high-end digital trading card for a futuristic skill-based game. Full card layout, vertical orientation.

Design:
{design_block}

Top section:
- bold header bar reading "SKILL DECK"
- name plate reading "{name}" with subtitle "{title} · {industry}"

Portrait:
- centered character portrait inside a framed window
{portrait_line}
- {portrait_hint if portrait_hint else "background: blurred tech dashboards, code, holographic graphs"}
- cinematic lighting, rim light, sharp focus

Lower sections (six panels in a 2-column grid, consistent spacing, grid-aligned):
- left panel titled "STRENGTHS" (blue-themed):
{format_bullets(strengths)}

- right panel titled "CLIFTON STRENGTHS" (purple-themed):
{format_bullets(clifton_strengths)}

- next row left panel titled "INSPIRATIONS":
{format_bullets(inspirations)}

- next row right panel titled "ASPIRATIONS":
{format_bullets(aspirations)}

- next row left panel titled "LEARN / GROW":
{format_bullets(learn_grow)}

- next row right panel titled "ACCOMPLISHMENTS":
{format_bullets(accomplishments)}

- clean separation between all panels, grid-aligned, consistent spacing

Bottom section:
- growth focus tagline: "{growth_focus}"
- flavor text quote: "{flavor_text}"

{outro_style_line}
Quality: ultra detailed, sharp legible typography, no distortions, consistent spacing."""


async def _attempt_image_generation(
    image_client: AsyncAzureOpenAI,
    deployment: str,
    prompt: str,
    photo_bytes: bytes | None,
    size: str,
) -> dict | None:
    """Single attempt against one deployment. Raises on failure so the caller can fall back."""
    import io
    from profile_agent.config.events import wide_event

    mode = "edit" if photo_bytes else "generate"
    photo_size = len(photo_bytes) if photo_bytes else 0
    t0 = time.perf_counter()
    wide_event(
        "image.attempt.started",
        deployment=deployment,
        mode=mode,
        size=size,
        photo_bytes=photo_size,
        prompt_chars=len(prompt),
    )
    try:
        if photo_bytes:
            logger.info("Generating card image with reference photo (%d bytes) deployment=%s",
                        photo_size, deployment)
            buf = io.BytesIO(photo_bytes)
            buf.name = "photo.png"
            response = await image_client.images.edit(
                model=deployment,
                image=buf,
                prompt=prompt,
                size=size,
                n=1,
            )
        else:
            logger.info("Generating card image without reference photo deployment=%s", deployment)
            response = await image_client.images.generate(
                model=deployment,
                prompt=prompt,
                size=size,
                n=1,
            )
    except Exception as exc:
        wide_event(
            "image.attempt.completed",
            outcome="error",
            level=logging.WARNING,
            deployment=deployment,
            mode=mode,
            size=size,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            error_type=type(exc).__name__,
            error_message=str(exc)[:500],
        )
        raise

    duration_ms = int((time.perf_counter() - t0) * 1000)
    image_data = response.data[0]
    if getattr(image_data, "b64_json", None):
        logger.info("Card image generated successfully (base64, %d chars) deployment=%s in %dms",
                    len(image_data.b64_json), deployment, duration_ms)
        wide_event(
            "image.attempt.completed",
            outcome="ok",
            deployment=deployment,
            mode=mode,
            size=size,
            duration_ms=duration_ms,
            response_kind="base64",
            response_bytes=len(image_data.b64_json),
        )
        return {"base64": image_data.b64_json}
    if image_data.url:
        logger.info("Card image generated successfully (url) deployment=%s in %dms", deployment, duration_ms)
        wide_event(
            "image.attempt.completed",
            outcome="ok",
            deployment=deployment,
            mode=mode,
            size=size,
            duration_ms=duration_ms,
            response_kind="url",
        )
        return {"url": image_data.url}
    logger.warning("Card image response had no data deployment=%s", deployment)
    wide_event(
        "image.attempt.completed",
        outcome="empty",
        level=logging.WARNING,
        deployment=deployment,
        mode=mode,
        size=size,
        duration_ms=duration_ms,
    )
    return None


async def _generate_card_image(
    client,
    settings: Settings,
    card_data: dict,
    photo_base64: str | None = None,
    style: "CardStyle | None" = None,
) -> dict | None:
    """Generate a full trading card image using gpt-image-2, falling back to gpt-image-1."""
    import base64 as b64mod
    from profile_agent.config.events import wide_event

    prompt = _build_card_image_prompt(card_data, style)
    t0 = time.perf_counter()
    primary_ms = 0
    fallback_ms = 0
    used_deployment: str | None = None

    try:
        image_client = await _get_image_client(settings)
        primary = settings.foundry_image_deployment_name
        fallback = settings.foundry_image_fallback_deployment_name
        size = "1024x1536"

        photo_bytes = None
        if photo_base64:
            raw = photo_base64
            if "," in raw:
                raw = raw.split(",", 1)[1]
            try:
                photo_bytes = b64mod.b64decode(raw)
            except Exception:
                logger.warning("Could not decode photo base64, generating without reference")

        # Content-addressed cache lookup — same prompt+photo+model+size = cache hit.
        # Cache is keyed on the primary deployment so a successful fallback doesn't
        # poison the cache for users who later get the primary back.
        from profile_agent.services import image_cache
        cached = image_cache.get(prompt, photo_bytes, primary, size)
        if cached:
            wide_event(
                "image.generation.completed",
                outcome="ok",
                duration_ms=int((time.perf_counter() - t0) * 1000),
                cache_hit=True,
                used_deployment="cache",
                primary_deployment=primary,
                fallback_deployment=fallback,
                has_photo=bool(photo_bytes),
            )
            return {"base64": cached}

        rate_limit_info: dict | None = None
        primary_error: Exception | None = None

        # ── Primary attempt ──
        primary_t = time.perf_counter()
        try:
            result = await _attempt_image_generation(image_client, primary, prompt, photo_bytes, size)
            primary_ms = int((time.perf_counter() - primary_t) * 1000)
            if result and "base64" in result:
                image_cache.put(prompt, photo_bytes, primary, size, result["base64"])
            if result:
                used_deployment = primary
                wide_event(
                    "image.generation.completed",
                    outcome="ok",
                    duration_ms=int((time.perf_counter() - t0) * 1000),
                    cache_hit=False,
                    used_deployment=used_deployment,
                    primary_deployment=primary,
                    fallback_deployment=fallback,
                    primary_ms=primary_ms,
                    has_photo=bool(photo_bytes),
                )
                return result
        except RateLimitError as rle:
            primary_ms = int((time.perf_counter() - primary_t) * 1000)
            retry_after = None
            try:
                ra = rle.response.headers.get("retry-after") if getattr(rle, "response", None) else None
                if ra:
                    retry_after = int(float(ra))
            except (ValueError, AttributeError, TypeError):
                retry_after = None
            logger.warning("Primary image deployment %s rate-limited (retry_after=%s) — trying fallback %s",
                           primary, retry_after, fallback)
            rate_limit_info = {"error": "rate_limited", "retry_after": retry_after}
        except Exception as e:
            primary_ms = int((time.perf_counter() - primary_t) * 1000)
            logger.warning("Primary image deployment %s failed (%s: %s) — trying fallback %s",
                           primary, type(e).__name__, e, fallback)
            primary_error = e

        # ── Fallback attempt ──
        if fallback and fallback != primary:
            fallback_t = time.perf_counter()
            try:
                result = await _attempt_image_generation(image_client, fallback, prompt, photo_bytes, size)
                fallback_ms = int((time.perf_counter() - fallback_t) * 1000)
                if result and "base64" in result:
                    image_cache.put(prompt, photo_bytes, primary, size, result["base64"])
                if result:
                    used_deployment = fallback
                    logger.info("Card image succeeded via fallback deployment %s", fallback)
                    wide_event(
                        "image.generation.completed",
                        outcome="ok_fallback",
                        duration_ms=int((time.perf_counter() - t0) * 1000),
                        cache_hit=False,
                        used_deployment=used_deployment,
                        primary_deployment=primary,
                        fallback_deployment=fallback,
                        primary_ms=primary_ms,
                        fallback_ms=fallback_ms,
                        has_photo=bool(photo_bytes),
                    )
                    return result
            except RateLimitError as rle2:
                fallback_ms = int((time.perf_counter() - fallback_t) * 1000)
                retry_after = None
                try:
                    ra = rle2.response.headers.get("retry-after") if getattr(rle2, "response", None) else None
                    if ra:
                        retry_after = int(float(ra))
                except (ValueError, AttributeError, TypeError):
                    retry_after = None
                logger.warning("Fallback image deployment %s also rate-limited (retry_after=%s)",
                               fallback, retry_after)
                # Surface whichever retry-after we have
                if rate_limit_info is None:
                    rate_limit_info = {"error": "rate_limited", "retry_after": retry_after}
                elif retry_after and (not rate_limit_info.get("retry_after") or retry_after < rate_limit_info["retry_after"]):
                    rate_limit_info["retry_after"] = retry_after
            except Exception as e2:
                fallback_ms = int((time.perf_counter() - fallback_t) * 1000)
                logger.error("Fallback image deployment %s failed: %s", fallback, e2, exc_info=True)
                if primary_error is None:
                    primary_error = e2

        if rate_limit_info is not None:
            wide_event(
                "image.generation.completed",
                outcome="rate_limited",
                level=logging.WARNING,
                duration_ms=int((time.perf_counter() - t0) * 1000),
                cache_hit=False,
                primary_deployment=primary,
                fallback_deployment=fallback,
                primary_ms=primary_ms,
                fallback_ms=fallback_ms,
                retry_after=rate_limit_info.get("retry_after"),
                has_photo=bool(photo_bytes),
            )
            return rate_limit_info
        if primary_error is not None:
            wide_event(
                "image.generation.completed",
                outcome="failed",
                level=logging.ERROR,
                duration_ms=int((time.perf_counter() - t0) * 1000),
                cache_hit=False,
                primary_deployment=primary,
                fallback_deployment=fallback,
                primary_ms=primary_ms,
                fallback_ms=fallback_ms,
                error_type=type(primary_error).__name__,
                error_message=str(primary_error)[:500],
                has_photo=bool(photo_bytes),
            )
            return {"error": "failed", "message": str(primary_error)}
    except Exception as e:
        logger.error("Card image generation error: %s", e, exc_info=True)
        wide_event(
            "image.generation.completed",
            outcome="error",
            level=logging.ERROR,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            error_type=type(e).__name__,
            error_message=str(e)[:500],
        )
        return {"error": "failed", "message": str(e)}
    return None


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
    photo_base64: str | None = None,
    settings: Settings | None = None,
    clifton_strengths: list[str] | None = None,
    linkedin_skills: dict | None = None,
    github_skills: dict | None = None,
    bulk_extracted: dict | None = None,
    style: CardStyle | None = None,
) -> AsyncGenerator[str, None]:
    """Process a user turn statelessly and yield AI SDK SSE events.

    All state is received as arguments and a `data-stateUpdate` event
    is emitted at the end containing the updated state for the client.
    """
    import time
    _turn_start = time.monotonic()
    settings = settings or get_settings()
    client = await _get_openai_client(settings)

    logger.info(
        "TURN START | stage=%s user=%s msg_len=%d completed=%d has_photo=%s",
        current_stage_id,
        identity.name or "anon",
        len(user_text),
        len(completed_summaries),
        bool(photo_base64),
    )

    stage = get_stage(current_stage_id)
    if stage is None:
        stage = get_first_stage()
        current_stage_id = stage.id

    # ── Bulk profile text detection & extraction ──
    # Always extract from new long-form text; merge with any previously extracted data
    if _is_bulk_profile_text(user_text):
        logger.info("BULK TEXT detected | len=%d stage=%s", len(user_text), current_stage_id)
        fresh_extracted = await _extract_bulk_profile(user_text, client, settings)
        if fresh_extracted:
            if bulk_extracted:
                # Merge: new extraction wins for non-empty fields
                merged = dict(bulk_extracted)
                for key, val in fresh_extracted.items():
                    if val and (isinstance(val, str) or (isinstance(val, list) and len(val) > 0)):
                        merged[key] = val
                bulk_extracted = merged
            else:
                bulk_extracted = fresh_extracted

    # Update identity from bulk-extracted data
    # Fresh extraction from current message overrides empty fields;
    # if we just did a fresh extraction this turn, also allow overriding
    # existing values since the user is explicitly providing new info.
    _fresh_this_turn = _is_bulk_profile_text(user_text)
    if bulk_extracted:
        extracted_name = bulk_extracted.get("name")
        extracted_title = bulk_extracted.get("title")
        new_name = identity.name
        new_role = identity.role
        new_title = identity.title

        if extracted_name and (not new_name or _fresh_this_turn):
            new_name = extracted_name
        if extracted_title and (not new_title or _fresh_this_turn):
            new_title = extracted_title
        if extracted_title and (not new_role or _fresh_this_turn):
            new_role = extracted_title

        if (new_name != identity.name or new_role != identity.role
                or new_title != identity.title):
            identity = IdentityContext(
                name=new_name,
                role=new_role,
                title=new_title,
                photo_status=identity.photo_status,
            )

    # Update identity from user text (LLM-augmented during the intro stage)
    identity = await update_identity_async(
        identity, user_text, current_stage_id, has_image, client, settings,
    )

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
    # Also handle regeneration requests (turn_count > 0 with regen intent)
    is_card_stage = stage.id == "card_generation"
    is_regen = is_card_stage and turn_count > 0 and (
        _is_regeneration_intent(user_text)
        or any(cmd in lowered for cmd in FINALIZE_COMMANDS)
    )
    if is_card_stage and (turn_count == 0 or is_regen):
        text_id = str(uuid.uuid4())
        yield f'data: {json.dumps({"type": "text-start", "id": text_id})}\n\n'

        if is_regen:
            preamble = "♻️ Regenerating your card with the latest information...\n\n"
        else:
            preamble = stage.opening_prompt + "\n\n"
        yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": preamble})}\n\n'

        # Build additional context from post-generation edits + bulk extracted data
        additional_parts: list[str] = []
        if is_regen and user_text.strip():
            additional_parts.append(f"User's latest update/request: {user_text}")
        if bulk_extracted:
            additional_parts.append(f"Bulk-extracted profile data: {json.dumps(bulk_extracted)}")
        additional_context = "\n".join(additional_parts) if additional_parts else None

        try:
            yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": "Synthesizing your profile first...\\n\\n"})}\n\n'
            synthesis_json = await _run_synthesis(
                client, settings, completed_summaries, current_stage_messages,
                additional_context=additional_context,
            )

            yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": "Generating your Skill Deck card...\\n\\n"})}\n\n'
            display_name = identity.name or "Anonymous"
            card_data_result = await _run_card_generation(
                client,
                settings,
                synthesis_json,
                display_name,
                identity.photo_status,
                clifton_strengths=clifton_strengths,
                linkedin_skills=linkedin_skills,
                github_skills=github_skills,
                completed_summaries=completed_summaries,
                role_text=identity.title or identity.role,
            )

            status_msg = f"Your **{card_data_result.get('name', 'Skill')} Deck** card is ready! Check it out below."
            yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": status_msg})}\n\n'
            yield f'data: {json.dumps({"type": "text-end", "id": text_id})}\n\n'

            yield f'data: {json.dumps({"type": "data-cardData", "data": card_data_result})}\n\n'

            # Generate card image in parallel (non-blocking — card data already sent)
            yield f'data: {json.dumps({"type": "text-start", "id": text_id + "-img"})}\n\n'
            yield f'data: {json.dumps({"type": "text-delta", "id": text_id + "-img", "delta": "\\n\\n✨ Generating your AI card portrait..."})}\n\n'
            try:
                image_result = await _generate_card_image(client, settings, card_data_result, photo_base64, style=style)
                if image_result and "base64" in image_result:
                    yield f'data: {json.dumps({"type": "data-cardImage", "data": image_result})}\n\n'
                    yield f'data: {json.dumps({"type": "text-delta", "id": text_id + "-img", "delta": " Done!"})}\n\n'
                elif image_result and image_result.get("error") == "rate_limited":
                    ra = image_result.get("retry_after")
                    wait_hint = f" Please wait ~{ra}s and use /regenerate to try again." if ra else " Please wait a minute and use /regenerate to try again."
                    msg = f"\n\n⏳ The image service is rate-limited right now. Your card text is ready, but the portrait couldn't be generated.{wait_hint}"
                    yield f'data: {json.dumps({"type": "text-delta", "id": text_id + "-img", "delta": msg})}\n\n'
                elif image_result and image_result.get("error"):
                    yield f'data: {json.dumps({"type": "text-delta", "id": text_id + "-img", "delta": " (image generation failed — use /regenerate to retry)"})}\n\n'
                else:
                    yield f'data: {json.dumps({"type": "text-delta", "id": text_id + "-img", "delta": " (image generation unavailable)"})}\n\n'
            except Exception as img_err:
                logger.warning("Card image generation skipped: %s", img_err)
                yield f'data: {json.dumps({"type": "text-delta", "id": text_id + "-img", "delta": " (image generation skipped)"})}\n\n'
            yield f'data: {json.dumps({"type": "text-end", "id": text_id + "-img"})}\n\n'
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

    # Post-card-generation: let the LLM know it can accept edits
    if stage.id == "card_generation" and turn_count > 0:
        context["context_summary"] += (
            " A card has already been generated. The user may provide corrections or additions. "
            "Acknowledge their update and tell them you'll incorporate it — "
            "they can say 'regenerate' or 'generate again' to rebuild the card with the new info."
        )

    system_prompt = render_template("interview_system", **context)

    # Build LLM message history
    history: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]

    # Inject bulk-extracted profile context so the LLM avoids re-asking known info
    if bulk_extracted:
        bulk_ctx = _format_bulk_context(bulk_extracted)
        history.append({"role": "system", "content": bulk_ctx})

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
        bulk_extracted=bulk_extracted,
    )
    yield f'data: {json.dumps({"type": "data-stateUpdate", "data": state_update.to_dict()})}\n\n'
    yield "data: [DONE]\n\n"
