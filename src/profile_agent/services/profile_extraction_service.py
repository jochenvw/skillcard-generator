"""Profile extraction service — LinkedIn text + GitHub profile analysis via LLM."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from bs4 import BeautifulSoup

from profile_agent.config.settings import get_settings
from profile_agent.prompts import render_template
from profile_agent.services.stateless_interview_service import _extract_json, _get_openai_client

logger = logging.getLogger(__name__)

_VALID_CATEGORIES_LINKEDIN = {"technical", "leadership", "domain", "soft_skill"}
_VALID_CATEGORIES_GITHUB = {"language", "framework", "infrastructure", "domain", "practice"}
_MAX_SKILLS = 10
_MAX_PROJECTS = 8
_CONFIDENCE_THRESHOLD = 0.5
_MAX_REPOS_TO_ANALYZE = 20
_GITHUB_API_BASE = "https://api.github.com"
_GITHUB_TIMEOUT = 15.0
_LINKEDIN_TIMEOUT = 20.0

# Generic filler skills to filter out unless confidence is very high
_GENERIC_SKILL_BLOCKLIST = {
    "communication", "teamwork", "hardworking", "problem solving",
    "problem-solving", "time management", "critical thinking",
    "adaptability", "creativity", "work ethic", "self-motivated",
    "detail oriented", "detail-oriented", "multitasking",
    "interpersonal skills", "organizational skills",
    "version control", "git", "documentation", "open source",
}

_LINKEDIN_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?linkedin\.com/in/([a-zA-Z0-9\-_%]+)",
    re.IGNORECASE,
)


class ProfileExtractionError(RuntimeError):
    """Raised when profile extraction fails."""


# ── Shared helpers ──


def _normalize_skills(
    parsed: dict[str, Any],
    valid_categories: set[str],
    source: str,
) -> dict[str, Any]:
    """Validate, filter, and normalize LLM JSON output for profile extraction."""
    raw_skills = parsed.get("skills")
    summary = parsed.get("summary", "")
    if not isinstance(raw_skills, list) or not isinstance(summary, str):
        return {"skills": [], "projects": [], "summary": "", "highlights": [], "source": source}

    # ── Skills: filter by confidence and blocklist ──
    cleaned_skills: list[dict[str, Any]] = []
    for item in raw_skills:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        category = item.get("category")
        evidence = item.get("evidence", "")
        confidence = item.get("confidence", 0.7)

        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(category, str) or category.lower() not in valid_categories:
            category = "technical"
        if not isinstance(evidence, str):
            evidence = str(evidence)
        if not isinstance(confidence, (int, float)):
            try:
                confidence = float(confidence)
            except (ValueError, TypeError):
                confidence = 0.5

        # Filter out low-confidence skills
        if confidence < _CONFIDENCE_THRESHOLD:
            logger.debug("skill filtered (low confidence): %s (%.2f)", name, confidence)
            continue

        # Filter generic filler skills unless confidence is very high
        if name.strip().lower() in _GENERIC_SKILL_BLOCKLIST and confidence < 0.85:
            logger.debug("skill filtered (generic blocklist): %s (%.2f)", name, confidence)
            continue

        cleaned_skills.append({
            "rank": len(cleaned_skills) + 1,
            "name": name.strip(),
            "category": category.lower(),
            "evidence": evidence.strip(),
            "confidence": round(confidence, 2),
        })

    # Sort by confidence descending, then cap
    cleaned_skills.sort(key=lambda s: -s["confidence"])
    cleaned_skills = cleaned_skills[:_MAX_SKILLS]
    for i, item in enumerate(cleaned_skills, start=1):
        item["rank"] = i

    # ── Projects: filter by confidence and quality ──
    raw_projects = parsed.get("projects", [])
    cleaned_projects: list[dict[str, Any]] = []
    if isinstance(raw_projects, list):
        for proj in raw_projects:
            if not isinstance(proj, dict):
                continue
            pname = proj.get("name")
            pdesc = proj.get("description", "")
            ptechs = proj.get("technologies", [])
            pevidence = proj.get("evidence", "")
            pconfidence = proj.get("confidence", 0.7)

            if not isinstance(pname, str) or not pname.strip():
                continue
            if not isinstance(pdesc, str):
                pdesc = str(pdesc)
            if not isinstance(ptechs, list):
                ptechs = []
            ptechs = [str(t).strip() for t in ptechs if isinstance(t, str) and t.strip()][:10]
            if not isinstance(pevidence, str):
                pevidence = str(pevidence)
            if not isinstance(pconfidence, (int, float)):
                try:
                    pconfidence = float(pconfidence)
                except (ValueError, TypeError):
                    pconfidence = 0.5

            if pconfidence < _CONFIDENCE_THRESHOLD:
                logger.debug("project filtered (low confidence): %s (%.2f)", pname, pconfidence)
                continue

            cleaned_projects.append({
                "name": pname.strip(),
                "description": pdesc.strip(),
                "technologies": ptechs,
                "evidence": pevidence.strip(),
                "confidence": round(pconfidence, 2),
            })

    cleaned_projects.sort(key=lambda p: -p["confidence"])
    cleaned_projects = cleaned_projects[:_MAX_PROJECTS]

    highlights = parsed.get("highlights", [])
    if not isinstance(highlights, list):
        highlights = []
    highlights = [str(h).strip() for h in highlights if isinstance(h, str) and h.strip()][:5]

    result: dict[str, Any] = {
        "skills": cleaned_skills,
        "projects": cleaned_projects,
        "summary": summary.strip(),
        "highlights": highlights,
        "source": source,
    }

    # Pass through extra fields depending on source
    if source == "linkedin":
        result["title"] = str(parsed.get("title", "")).strip()
    elif source == "github":
        focus = parsed.get("focus_areas", [])
        if isinstance(focus, list):
            result["focus_areas"] = [str(f).strip() for f in focus if isinstance(f, str) and f.strip()][:3]

    return result


# ── LinkedIn extraction ──


async def fetch_linkedin_profile_text(url: str) -> str:
    """Fetch a public LinkedIn profile page and extract visible text content."""
    match = _LINKEDIN_URL_PATTERN.match(url.strip())
    if not match:
        raise ProfileExtractionError("Invalid LinkedIn URL format")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=_LINKEDIN_TIMEOUT
        ) as client:
            resp = await client.get(url.strip(), headers=headers)
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise ProfileExtractionError("LinkedIn profile not found") from exc
        if exc.response.status_code == 999:
            raise ProfileExtractionError(
                "LinkedIn blocked the request. Please paste your profile text manually instead."
            ) from exc
        raise ProfileExtractionError(
            f"Failed to fetch LinkedIn profile (HTTP {exc.response.status_code})"
        ) from exc
    except httpx.TimeoutException as exc:
        raise ProfileExtractionError("LinkedIn request timed out") from exc
    except Exception as exc:
        raise ProfileExtractionError(f"Could not reach LinkedIn: {exc}") from exc

    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    # Remove script/style/nav elements
    for tag in soup(["script", "style", "nav", "footer", "noscript", "svg", "img"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)

    # Clean up excessive whitespace
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    text = "\n".join(lines)

    if len(text) < 50:
        raise ProfileExtractionError(
            "Could not extract enough content from the LinkedIn page. "
            "LinkedIn may have blocked the request — please paste your profile text manually."
        )

    logger.info("fetched linkedin profile | url=%s text_len=%d", url, len(text))
    return text[:200_000]


async def extract_linkedin_skills(text: str) -> dict[str, Any]:
    """Extract professional skills from LinkedIn profile text via LLM."""
    if not isinstance(text, str) or not text.strip():
        raise ProfileExtractionError("text must be a non-empty string")

    text = text.strip()[:200_000]  # cap input

    settings = get_settings()
    client = await _get_openai_client(settings)

    prompt = render_template("linkedin_extraction", profile_text=text)

    logger.info("linkedin extraction request | text_len=%d", len(text))

    try:
        response = await client.chat.completions.create(
            model=settings.effective_azure_openai_deployment,
            messages=[{"role": "system", "content": prompt}],
            temperature=0.2,
            max_completion_tokens=2500,
        )
    except Exception as exc:
        logger.exception("linkedin extraction LLM call failed")
        raise ProfileExtractionError("LLM request failed") from exc

    content = (response.choices[0].message.content or "") if response.choices else ""
    parsed = _extract_json(content)
    if parsed is None or not isinstance(parsed, dict):
        logger.warning("linkedin extraction parse failed")
        return {"skills": [], "projects": [], "summary": "", "highlights": [], "source": "linkedin", "title": ""}

    result = _normalize_skills(parsed, _VALID_CATEGORIES_LINKEDIN, "linkedin")
    logger.info("linkedin extraction success | skills_count=%d", len(result["skills"]))
    return result


# ── GitHub extraction ──


async def _fetch_github_data(username: str) -> dict[str, Any]:
    """Fetch public GitHub profile and repo data (unauthenticated)."""
    async with httpx.AsyncClient(
        timeout=_GITHUB_TIMEOUT,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "SkillCard-Generator/1.0"},
    ) as client:
        # Fetch user profile
        user_resp = await client.get(f"{_GITHUB_API_BASE}/users/{username}")
        if user_resp.status_code == 404:
            raise ProfileExtractionError(f"GitHub user '{username}' not found")
        if user_resp.status_code == 403:
            raise ProfileExtractionError("GitHub API rate limit exceeded. Please try again later.")
        user_resp.raise_for_status()
        user_data = user_resp.json()

        # Fetch repos (sorted by recent push, exclude forks, cap at top N)
        repos_resp = await client.get(
            f"{_GITHUB_API_BASE}/users/{username}/repos",
            params={"sort": "pushed", "direction": "desc", "per_page": 100, "type": "owner"},
        )
        repos_resp.raise_for_status()
        all_repos = repos_resp.json()

    # Filter repos: exclude forks, archived, and trivial repos
    _TRIVIAL_REPO_PATTERNS = re.compile(
        r"^(hello[-_]?world|test[-_]?repo|my[-_]?dotfiles|\.dotfiles|"
        r"\.github|config[-_]?files|notes|scratch|temp|tmp|tutorial|"
        r"learning[-_]|practice[-_]|homework|assignment)$",
        re.IGNORECASE,
    )

    repos = []
    for r in all_repos:
        if r.get("fork") or r.get("archived"):
            continue
        name = r.get("name", "")
        # Skip trivial-looking repos
        if _TRIVIAL_REPO_PATTERNS.match(name):
            continue
        # Skip repos with zero substance: no description, no stars, no topics, no language
        has_substance = (
            r.get("description")
            or r.get("stargazers_count", 0) > 0
            or r.get("topics")
            or r.get("language")
        )
        if not has_substance:
            continue
        repos.append(r)

    repos = repos[:_MAX_REPOS_TO_ANALYZE]

    return {"user": user_data, "repos": repos}


def _format_github_data(data: dict[str, Any]) -> dict[str, str]:
    """Format raw GitHub API data into prompt-friendly strings."""
    user = data["user"]
    repos = data["repos"]

    bio = user.get("bio") or "(no bio)"
    public_repos = str(user.get("public_repos", 0))

    created = user.get("created_at", "")
    if created:
        try:
            created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            years = (datetime.now(timezone.utc) - created_dt).days // 365
            account_age = f"{years} years"
        except (ValueError, TypeError):
            account_age = "unknown"
    else:
        account_age = "unknown"

    # Format repo data
    repo_lines = []
    for r in repos:
        name = r.get("name", "?")
        desc = r.get("description") or "(no description)"
        lang = r.get("language") or "unknown"
        stars = r.get("stargazers_count", 0)
        forks = r.get("forks_count", 0)
        topics = ", ".join(r.get("topics", [])[:5]) or "none"
        pushed = (r.get("pushed_at") or "unknown")[:10]
        repo_lines.append(
            f"- **{name}** [{lang}] ⭐{stars} 🍴{forks} | topics: {topics} | "
            f"last push: {pushed}\n  {desc}"
        )
    repo_data = "\n".join(repo_lines) if repo_lines else "(no public repos found)"

    # Aggregate languages
    lang_counts: dict[str, int] = {}
    for r in repos:
        lang = r.get("language")
        if lang:
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
    sorted_langs = sorted(lang_counts.items(), key=lambda x: -x[1])
    lang_lines = [f"- {lang}: {count} repos" for lang, count in sorted_langs[:15]]
    language_data = "\n".join(lang_lines) if lang_lines else "(no language data)"

    return {
        "bio": bio,
        "public_repos": public_repos,
        "account_age": account_age,
        "repo_data": repo_data,
        "language_data": language_data,
    }


async def extract_github_skills(username: str) -> dict[str, Any]:
    """Extract technical skills from a public GitHub profile."""
    username = username.strip().lstrip("@")
    if not username or len(username) > 39:
        raise ProfileExtractionError("Invalid GitHub username")
    if "/" in username or " " in username:
        raise ProfileExtractionError("Invalid GitHub username — provide just the username, not a URL")

    logger.info("github extraction request | username=%s", username)

    try:
        raw_data = await _fetch_github_data(username)
    except ProfileExtractionError:
        raise
    except Exception as exc:
        logger.exception("github API fetch failed | username=%s", username)
        raise ProfileExtractionError(f"Failed to fetch GitHub data: {exc}") from exc

    formatted = _format_github_data(raw_data)

    settings = get_settings()
    client = await _get_openai_client(settings)

    prompt = render_template(
        "github_extraction",
        username=username,
        bio=formatted["bio"],
        public_repos=formatted["public_repos"],
        account_age=formatted["account_age"],
        repo_data=formatted["repo_data"],
        language_data=formatted["language_data"],
    )

    try:
        response = await client.chat.completions.create(
            model=settings.effective_azure_openai_deployment,
            messages=[{"role": "system", "content": prompt}],
            temperature=0.2,
            max_completion_tokens=2500,
        )
    except Exception as exc:
        logger.exception("github extraction LLM call failed | username=%s", username)
        raise ProfileExtractionError("LLM request failed") from exc

    content = (response.choices[0].message.content or "") if response.choices else ""
    parsed = _extract_json(content)
    if parsed is None or not isinstance(parsed, dict):
        logger.warning("github extraction parse failed | username=%s", username)
        return {"skills": [], "projects": [], "summary": "", "highlights": [], "focus_areas": [], "source": "github"}

    result = _normalize_skills(parsed, _VALID_CATEGORIES_GITHUB, "github")
    logger.info("github extraction success | username=%s skills_count=%d", username, len(result["skills"]))
    return result
