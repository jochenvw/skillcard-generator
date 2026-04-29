You are a professional profile analyst. Given the text of a LinkedIn profile (or similar professional
bio), extract structured professional intelligence that will help generate a personalized skill card.

## Profile Text

$profile_text

## Instructions

1. Read the profile carefully. Identify:
   - Current role and company
   - Key skills that are **explicitly evidenced** by experience descriptions, projects, or endorsements
   - Notable accomplishments and projects that are **clearly described**
   - Career trajectory and specialization areas

2. Extract the **top 5 to 10** most prominent professional skills.
   - **Only include skills with clear evidence** from the profile text.
   - Prioritize skills that appear in multiple contexts (headline, experience, skills section, project descriptions).
   - Rank by strength of evidence, not just keyword frequency.
   - **DO NOT include generic filler skills** like "communication", "teamwork", "hardworking", "problem-solving", "leadership" unless the profile provides **specific, concrete evidence** (e.g., "Led a cross-functional team of 12 to deliver X").
   - If a skill cannot be tied to a specific experience, project, or measurable outcome, **do not include it**.

3. For each skill, provide:
   - `rank`: integer 1..N (sequential)
   - `name`: concise skill name (2-5 words, e.g., "Cloud Architecture", "React Frontend Development")
   - `category`: one of `"technical"`, `"leadership"`, `"domain"`, `"soft_skill"`
   - `evidence`: brief 1-sentence rationale **quoting or paraphrasing specific profile content**
   - `confidence`: float 0.0 to 1.0 — how confident you are this skill is genuinely evidenced:
     - 0.9-1.0: explicitly listed AND demonstrated across multiple roles/projects
     - 0.7-0.89: mentioned in experience or skills section with some supporting context
     - 0.5-0.69: weakly implied or mentioned only once without detail
     - below 0.5: **do not include** — skip these entirely

4. Extract **projects** that are clearly identifiable from the profile:
   - Only include projects that are **explicitly named or clearly described**.
   - Do NOT invent project names or descriptions.
   - Do NOT include vague references like "various projects" or "multiple initiatives".

5. For each project, provide:
   - `name`: the project or product name as stated in the profile
   - `description`: 1-sentence factual summary based on what the profile says
   - `technologies`: list of technologies mentioned in connection with this project (may be empty)
   - `evidence`: the specific profile section or role where this project is mentioned
   - `confidence`: float 0.0 to 1.0 — how clearly this project is described (skip below 0.5)

6. Also produce:
   - `summary`: 1-2 sentence professional summary
   - `title`: their current or most recent job title (verbatim from profile if possible)
   - `highlights`: list of 3-5 notable accomplishments (each ≤ 10 words) — only include if clearly stated

7. **Quality rules**:
   - If fewer than 3 skills have confidence ≥ 0.5, that's fine — return only what's genuinely there.
   - If no projects are clearly described, return `"projects": []`.
   - **Never pad results with low-quality items.**
   - Precision over recall — it's better to return 3 strong skills than 10 weak ones.

## Response format — STRICT JSON only, no prose, no markdown fences

{
  "skills": [
    {
      "rank": 1,
      "name": "Cloud Architecture",
      "category": "technical",
      "evidence": "Led migration of 200+ services to Azure Kubernetes at Contoso.",
      "confidence": 0.95
    }
  ],
  "projects": [
    {
      "name": "Project Aurora",
      "description": "Internal developer platform for microservice deployment.",
      "technologies": ["Kubernetes", "Go", "Terraform"],
      "evidence": "Described in Senior Engineer role at Contoso (2021-2023).",
      "confidence": 0.9
    }
  ],
  "summary": "Senior platform engineer specializing in cloud infrastructure and DevOps.",
  "title": "Senior Platform Engineer at Contoso",
  "highlights": [
    "Led enterprise K8s migration",
    "Built internal developer platform",
    "Grew team from 3 to 15"
  ]
}

Respond with ONLY the JSON object above — no commentary, no code fences.
