import type { PanelData } from "../types";

export function SummaryPanel({ data }: { data: PanelData | null }) {
  if (!data) {
    return (
      <div className="flex items-center justify-center h-full text-zinc-500 text-sm">
        Waiting for data...
      </div>
    );
  }

  const { profile, completedStageIds, stages } = data;

  // Gather completed stage summaries
  const completedStages = stages.filter((s) =>
    completedStageIds.includes(s.id)
  );

  return (
    <div className="flex flex-col h-full">
      <h2 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider mb-4">
        Profile Summary
      </h2>

      {/* Identity card */}
      <div className="bg-zinc-800/50 rounded-xl p-4 mb-4 border border-zinc-700/50">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-full bg-violet-500/20 flex items-center justify-center text-violet-300 text-lg font-semibold">
            {profile.name ? profile.name[0].toUpperCase() : "?"}
          </div>
          <div>
            <div className="text-sm font-medium text-zinc-200">
              {profile.name || "Name pending..."}
            </div>
            <div className="text-xs text-zinc-500">
              {profile.photo === "uploaded"
                ? "Photo uploaded"
                : profile.photo === "skipped"
                  ? "Photo skipped"
                  : "Photo pending"}
            </div>
          </div>
        </div>

        {profile.role && (
          <p className="text-xs text-zinc-400 leading-relaxed border-t border-zinc-700/50 pt-3">
            {profile.role.length > 200
              ? profile.role.slice(0, 200) + "..."
              : profile.role}
          </p>
        )}
      </div>

      {/* Completed stages summary */}
      {completedStages.length > 0 && (
        <div className="flex-1 overflow-y-auto">
          <h3 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-2">
            Completed Topics
          </h3>
          <div className="space-y-1.5">
            {completedStages.map((stage) => (
              <div
                key={stage.id}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-500/5 border border-emerald-500/10"
              >
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
                <span className="text-xs text-emerald-300">{stage.title}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {completedStages.length === 0 && (
        <p className="text-xs text-zinc-600 italic">
          Complete interview stages to build your profile here.
        </p>
      )}
    </div>
  );
}
