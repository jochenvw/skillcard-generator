export type StrengthTheme =
  | "executing"
  | "influencing"
  | "relationship"
  | "strategic";

export interface Strength {
  rank: number;
  name: string;
  theme: StrengthTheme;
  description: string;
}

export interface StrengthsResponse {
  strengths: Strength[];
  summary: string;
}

export async function extractStrengths(
  text: string,
  authHeaders: HeadersInit,
): Promise<StrengthsResponse> {
  const res = await fetch("/api/extract-strengths", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders },
    body: JSON.stringify({ text }),
  });

  if (!res.ok) {
    let detail = "";
    try {
      const body = (await res.json()) as { detail?: string; error?: string };
      detail = body.detail ?? body.error ?? "";
    } catch {
      // ignore
    }
    throw new Error(
      `Strengths extraction failed (${res.status})${detail ? `: ${detail}` : ""}`,
    );
  }

  return (await res.json()) as StrengthsResponse;
}
