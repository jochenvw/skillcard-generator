import { useState } from "react";
import type { PanelData, CompletedStage } from "../types";

interface SummaryPanelProps {
  data: PanelData | null;
  photoBase64?: string | null;
  completedStages?: CompletedStage[];
}

function PhotoStatusBadge({ status }: { status: string | null }) {
  const label =
    status === "uploaded"
      ? "Photo ✓"
      : status === "skipped"
        ? "Skipped"
        : "Pending";
  const color =
    status === "uploaded"
      ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
      : status === "skipped"
        ? "bg-zinc-700/50 text-zinc-400 border-zinc-600/30"
        : "bg-amber-500/15 text-amber-300 border-amber-500/30";

  return (
    <span
      className={`inline-flex items-center text-[10px] font-medium px-1.5 py-0.5 rounded-full border ${color}`}
    >
      {label}
    </span>
  );
}

function StageCard({ stage }: { stage: CompletedStage }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-lg border border-cyan-500/10 bg-zinc-800/40 overflow-hidden transition-colors hover:border-cyan-500/25">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-2 px-3 py-2.5 text-left cursor-pointer"
      >
        <div className="flex items-center gap-2 min-w-0">
          <svg
            className="w-3 h-3 text-emerald-400 shrink-0"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2.5}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M5 13l4 4L19 7"
            />
          </svg>
          <span className="text-xs font-medium text-zinc-200 truncate">
            {stage.title}
          </span>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <span className="text-[10px] font-mono text-cyan-400/70 bg-cyan-500/10 px-1.5 py-0.5 rounded">
            {stage.turnCount}t
          </span>
          <svg
            className={`w-3 h-3 text-zinc-500 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M19 9l-7 7-7-7"
            />
          </svg>
        </div>
      </button>

      <div
        className={`grid transition-[grid-template-rows] duration-200 ease-in-out ${open ? "grid-rows-[1fr]" : "grid-rows-[0fr]"}`}
      >
        <div className="overflow-hidden">
          <p className="px-3 pb-3 text-[11px] leading-relaxed text-zinc-400 border-t border-zinc-700/40 pt-2">
            {stage.summary || "No summary available."}
          </p>
        </div>
      </div>
    </div>
  );
}

export function SummaryPanel({
  data,
  photoBase64,
  completedStages = [],
}: SummaryPanelProps) {
  if (!data) {
    return (
      <div className="flex items-center justify-center h-full text-zinc-500 text-sm">
        Waiting for data…
      </div>
    );
  }

  const { profile } = data;
  const initial = profile.name ? profile.name[0].toUpperCase() : "?";

  return (
    <div className="flex flex-col h-full gap-4">
      {/* ── Profile card ─────────────────────────────────── */}
      <div className="flex flex-col items-center text-center pt-2">
        {/* Glow ring around photo */}
        <div className="relative mb-3">
          <div className="absolute -inset-1 rounded-full bg-gradient-to-br from-cyan-500/30 to-violet-500/30 blur-sm" />
          {photoBase64 ? (
            <img
              src={photoBase64}
              alt={profile.name || "Profile"}
              className="relative w-20 h-20 rounded-full object-cover border-2 border-cyan-500/40 shadow-lg shadow-violet-500/10"
            />
          ) : (
            <div className="relative w-20 h-20 rounded-full bg-zinc-800 border-2 border-violet-500/30 flex items-center justify-center text-violet-300 text-2xl font-bold shadow-lg shadow-violet-500/10">
              {initial}
            </div>
          )}
        </div>

        <h2 className="text-sm font-bold text-zinc-100 leading-tight">
          {profile.name || "Name pending…"}
        </h2>
        {profile.role && (
          <p className="text-[11px] text-zinc-500 mt-0.5 line-clamp-2 max-w-[14rem]">
            {profile.role}
          </p>
        )}
        <div className="mt-1.5">
          <PhotoStatusBadge status={profile.photo} />
        </div>
      </div>

      {/* ── Identity section ─────────────────────────────── */}
      {(profile.name || profile.role) && (
        <div className="rounded-lg bg-zinc-800/50 border border-zinc-700/40 px-3 py-2.5">
          <h3 className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider mb-1.5">
            Identity
          </h3>
          {profile.name && (
            <p className="text-xs text-zinc-200 font-semibold">
              {profile.name}
            </p>
          )}
          {profile.role && (
            <p className="text-[11px] text-zinc-400 mt-0.5 leading-relaxed">
              {profile.role.length > 200
                ? profile.role.slice(0, 200) + "…"
                : profile.role}
            </p>
          )}
        </div>
      )}

      {/* ── Completed stage summaries ────────────────────── */}
      {completedStages.length > 0 ? (
        <div className="flex-1 min-h-0 flex flex-col">
          <h3 className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider mb-2">
            Completed Stages
          </h3>
          <div className="flex-1 overflow-y-auto space-y-1.5 pr-0.5">
            {completedStages.map((stage) => (
              <StageCard key={stage.id} stage={stage} />
            ))}
          </div>
        </div>
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center text-center px-4">
          <div className="text-2xl mb-2 animate-pulse">◇</div>
          <p className="text-xs text-zinc-500 leading-relaxed">
            Complete stages to build your profile here
          </p>
          <p className="text-[10px] text-zinc-600 mt-1">
            Each stage reveals a new facet of your skill card
          </p>
        </div>
      )}
    </div>
  );
}
