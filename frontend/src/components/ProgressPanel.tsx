import type { PanelData } from "../types";

const STATUS_STYLES: Record<string, { dot: string; text: string }> = {
  completed: { dot: "bg-emerald-400", text: "text-emerald-400" },
  in_progress: { dot: "bg-violet-400 animate-pulse", text: "text-violet-300" },
  not_started: { dot: "bg-zinc-600", text: "text-zinc-500" },
  skipped: { dot: "bg-yellow-500", text: "text-yellow-500" },
  awaiting_confirmation: { dot: "bg-amber-400 animate-pulse", text: "text-amber-300" },
  confirmed: { dot: "bg-emerald-400", text: "text-emerald-400" },
  failed: { dot: "bg-red-500", text: "text-red-400" },
};

export function ProgressPanel({ data }: { data: PanelData | null }) {
  if (!data) {
    return (
      <div className="flex items-center justify-center h-full text-zinc-500 text-sm">
        Loading stages...
      </div>
    );
  }

  const completedCount = data.completedStageIds.length;
  const totalCount = data.stages.length;
  const pct = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;

  return (
    <div className="flex flex-col h-full">
      <h2 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider mb-4">
        Progress
      </h2>

      {/* Progress bar */}
      <div className="mb-5">
        <div className="flex justify-between text-xs text-zinc-500 mb-1">
          <span>{completedCount} / {totalCount} stages</span>
          <span>{pct}%</span>
        </div>
        <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
          <div
            className="h-full bg-violet-500 rounded-full transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {/* Stage list */}
      <div className="flex-1 overflow-y-auto space-y-1">
        {data.stages.map((stage) => {
          const style = STATUS_STYLES[stage.status] || STATUS_STYLES.not_started;
          const isCurrent = stage.id === data.currentStageId;

          return (
            <div
              key={stage.id}
              className={`flex items-center gap-2.5 px-3 py-2 rounded-lg transition-colors ${
                isCurrent
                  ? "bg-violet-500/10 border border-violet-500/30"
                  : "hover:bg-zinc-800/50"
              }`}
            >
              <div className={`w-2 h-2 rounded-full shrink-0 ${style.dot}`} />
              <div className="min-w-0 flex-1">
                <div className={`text-sm truncate ${isCurrent ? "text-violet-200 font-medium" : style.text}`}>
                  {stage.title}
                </div>
                {stage.turns > 0 && (
                  <div className="text-[10px] text-zinc-600">
                    {stage.turns} turn{stage.turns > 1 ? "s" : ""}
                  </div>
                )}
              </div>
              {stage.status === "completed" && (
                <svg className="w-3.5 h-3.5 text-emerald-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
