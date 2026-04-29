/** Client helpers for LinkedIn + GitHub profile extraction endpoints. */

export interface ExtractedSkill {
  rank: number;
  name: string;
  category: string;
  evidence: string;
  confidence: number;
}

export interface ExtractedProject {
  name: string;
  description: string;
  technologies?: string[];
  evidence: string;
  confidence: number;
}

export interface LinkedInResponse {
  skills: ExtractedSkill[];
  projects: ExtractedProject[];
  summary: string;
  title: string;
  highlights: string[];
  source: "linkedin";
}

export interface GitHubResponse {
  skills: ExtractedSkill[];
  projects: ExtractedProject[];
  summary: string;
  highlights: string[];
  focus_areas: string[];
  source: "github";
}

export type ProfileResponse = LinkedInResponse | GitHubResponse;

export async function extractLinkedIn(
  input: string,
  authHeaders: HeadersInit,
): Promise<LinkedInResponse> {
  // Detect if input is a URL or pasted text
  const isUrl = /linkedin\.com\/in\//i.test(input.trim());
  const body = isUrl ? { url: input.trim() } : { text: input };

  const res = await fetch("/api/extract-linkedin", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `LinkedIn extraction failed (${res.status})`);
  }
  return res.json();
}

export async function extractGitHub(
  username: string,
  authHeaders: HeadersInit,
): Promise<GitHubResponse> {
  const res = await fetch("/api/extract-github", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders },
    body: JSON.stringify({ username }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `GitHub extraction failed (${res.status})`);
  }
  return res.json();
}
