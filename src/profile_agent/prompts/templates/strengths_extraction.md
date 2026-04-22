You are a CliftonStrengths (Gallup) analyst. Given the text of a personal/professional document
(resume, bio, narrative, performance review, or similar), identify the person's most prominent
CliftonStrengths themes that are evidenced by the text.

## Document text

$document_text

## Instructions

1. Read the document carefully and identify behavioral, motivational, and cognitive signals.
2. Select the **top 5 to 10** CliftonStrengths themes most strongly evidenced by the text.
3. Order them by `rank`, where `rank: 1` is the strongest signal in the text.
4. For each strength, provide:
   - `rank`: integer 1..N (sequential, no gaps)
   - `name`: the official CliftonStrengths theme name (e.g., "Achiever", "Strategic", "Learner",
     "Relator", "Communication", "Maximizer", "Responsibility", "Input", "Ideation", "Activator",
     "Command", "Empathy", "Developer", "Focus", "Futuristic", "Harmony", "Includer", "Individualization",
     "Intellection", "Positivity", "Restorative", "Self-Assurance", "Significance", "Woo", "Adaptability",
     "Analytical", "Arranger", "Belief", "Connectedness", "Consistency", "Context", "Deliberative",
     "Discipline").
   - `theme`: exactly one of `"executing"`, `"influencing"`, `"relationship"`, `"strategic"` —
     the four CliftonStrengths domains. Map each theme to its correct domain:
       * **executing**: Achiever, Arranger, Belief, Consistency, Deliberative, Discipline, Focus,
         Responsibility, Restorative
       * **influencing**: Activator, Command, Communication, Competition, Maximizer, Self-Assurance,
         Significance, Woo
       * **relationship**: Adaptability, Connectedness, Developer, Empathy, Harmony, Includer,
         Individualization, Positivity, Relator
       * **strategic**: Analytical, Context, Futuristic, Ideation, Input, Intellection, Learner,
         Strategic
   - `description`: a brief 1-2 sentence rationale grounded in the text (do not invent facts).
5. Also produce a 1-2 sentence overall `summary` of the document.

## Response format — STRICT JSON only, no prose, no markdown fences

{
  "strengths": [
    {
      "rank": 1,
      "name": "Achiever",
      "theme": "executing",
      "description": "Brief 1-2 sentence rationale grounded in the text."
    }
  ],
  "summary": "1-2 sentence overall summary of the document."
}

Respond with ONLY the JSON object above — no commentary, no code fences.
