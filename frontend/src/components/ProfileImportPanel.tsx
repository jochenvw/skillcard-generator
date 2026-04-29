/**
 * ProfileImportPanel — modal dialog for importing LinkedIn text or GitHub username.
 * Returns extracted skills via callbacks to the parent component.
 */

import { useState, useRef, useEffect, type FormEvent } from "react";
import {
  extractLinkedIn,
  extractGitHub,
  type ProfileResponse,
} from "../utils/profileClient";

type Tab = "linkedin" | "github";

interface ProfileImportPanelProps {
  open: boolean;
  onClose: () => void;
  onSkillsExtracted: (response: ProfileResponse) => void;
  getAuthHeaders: () => Promise<HeadersInit>;
}

export function ProfileImportPanel({
  open,
  onClose,
  onSkillsExtracted,
  getAuthHeaders,
}: ProfileImportPanelProps) {
  const [tab, setTab] = useState<Tab>("linkedin");
  const [linkedInInput, setLinkedInInput] = useState("");
  const [githubUsername, setGithubUsername] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const linkedinRef = useRef<HTMLInputElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Sync open state with dialog
  useEffect(() => {
    if (open) {
      dialogRef.current?.showModal();
      // Focus the active input
      setTimeout(() => {
        if (tab === "linkedin") linkedinRef.current?.focus();
        else inputRef.current?.focus();
      }, 50);
    } else {
      dialogRef.current?.close();
    }
  }, [open, tab]);

  // Close on backdrop click
  const handleDialogClick = (e: React.MouseEvent<HTMLDialogElement>) => {
    if (e.target === dialogRef.current) {
      onClose();
    }
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const authHeaders = await getAuthHeaders();
      let result: ProfileResponse;

      if (tab === "linkedin") {
        const input = linkedInInput.trim();
        if (!input) {
          setError("Please enter your LinkedIn profile URL or paste your profile text.");
          return;
        }
        result = await extractLinkedIn(input, authHeaders);
      } else {
        const username = githubUsername.trim().replace(/^@/, "");
        if (!username) {
          setError("Please enter a GitHub username.");
          return;
        }
        result = await extractGitHub(username, authHeaders);
      }

      if (!result.skills || result.skills.length === 0) {
        setError("No skills could be extracted. Please try with more detailed input.");
        return;
      }

      onSkillsExtracted(result);
      onClose();
      // Reset form
      setLinkedInInput("");
      setGithubUsername("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Extraction failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  if (!open) return null;

  return (
    <dialog
      ref={dialogRef}
      onClick={handleDialogClick}
      onCancel={onClose}
      className="fixed inset-0 z-50 m-auto w-full max-w-lg rounded-2xl border border-zinc-700 bg-zinc-900 p-0 text-zinc-200 shadow-2xl shadow-violet-500/10 backdrop:bg-black/60 backdrop:backdrop-blur-sm"
    >
      <div className="p-6 space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-mono text-cyan-400/90 tracking-tight">
            <span className="text-zinc-500">import</span>
            <span className="text-zinc-600">/</span>
            <span className="text-cyan-400/90">profile</span>
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
            aria-label="Close"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 rounded-xl bg-zinc-800/50 p-1">
          <button
            type="button"
            onClick={() => { setTab("linkedin"); setError(null); }}
            className={`flex-1 rounded-lg px-3 py-2 text-xs font-medium transition-colors ${
              tab === "linkedin"
                ? "bg-violet-600/80 text-white"
                : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700/50"
            }`}
          >
            <span className="mr-1.5">💼</span> LinkedIn
          </button>
          <button
            type="button"
            onClick={() => { setTab("github"); setError(null); }}
            className={`flex-1 rounded-lg px-3 py-2 text-xs font-medium transition-colors ${
              tab === "github"
                ? "bg-violet-600/80 text-white"
                : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700/50"
            }`}
          >
            <span className="mr-1.5">🐙</span> GitHub
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          {tab === "linkedin" ? (
            <div className="space-y-2">
              <label className="block text-xs text-zinc-400">
                Enter your LinkedIn profile URL
              </label>
              <p className="text-[10px] text-zinc-600 leading-relaxed">
                Paste your LinkedIn profile link (e.g. https://linkedin.com/in/yourname).
                We'll fetch and analyze your public profile to extract skills.
                You can also paste your full profile text directly.
              </p>
              <input
                ref={linkedinRef}
                type="text"
                value={linkedInInput}
                onChange={(e) => setLinkedInInput(e.target.value)}
                placeholder="https://linkedin.com/in/yourname or paste profile text…"
                maxLength={200000}
                disabled={loading}
                className="w-full rounded-xl bg-zinc-800 border border-zinc-700 px-4 py-3 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-violet-500 focus:border-violet-500 disabled:opacity-50"
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    e.currentTarget.closest("form")?.requestSubmit();
                  }
                }}
              />
            </div>
          ) : (
            <div className="space-y-2">
              <label className="block text-xs text-zinc-400">
                Enter a GitHub username
              </label>
              <p className="text-[10px] text-zinc-600 leading-relaxed">
                We analyze public repos, languages, and topics to identify technical strengths.
                Only public data is used — no authentication required.
              </p>
              <input
                ref={inputRef}
                type="text"
                value={githubUsername}
                onChange={(e) => setGithubUsername(e.target.value)}
                placeholder="e.g. octocat"
                maxLength={39}
                disabled={loading}
                className="w-full rounded-xl bg-zinc-800 border border-zinc-700 px-4 py-3 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-violet-500 focus:border-violet-500 disabled:opacity-50"
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    e.currentTarget.closest("form")?.requestSubmit();
                  }
                }}
              />
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="rounded-lg bg-red-950/40 border border-red-900/50 px-3 py-2 text-xs text-red-300">
              {error}
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-2 justify-end pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="rounded-xl px-4 py-2.5 text-sm text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || (tab === "linkedin" ? !linkedInInput.trim() : !githubUsername.trim())}
              className="rounded-xl bg-violet-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-40 disabled:hover:bg-violet-600 transition-colors flex items-center gap-2"
            >
              {loading ? (
                <>
                  <span className="animate-spin text-xs">⟳</span>
                  Analyzing…
                </>
              ) : (
                <>Extract Skills</>
              )}
            </button>
          </div>
        </form>
      </div>
    </dialog>
  );
}
