import type { PanelData, StageInfo } from "../types";

/* ------------------------------------------------------------------ */
/*  Radial progress gauge using conic-gradient (cyan -> violet fill)   */
/* ------------------------------------------------------------------ */

function RadialGauge({ completed, total }: { completed: number; total: number }) {
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
  const deg = total > 0 ? (completed / total) * 360 : 0;

  return (
    <div className="flex flex-col items-center gap-2 mb-5">
      <div
        className="relative w-28 h-28 rounded-full transition-all duration-700"
        style={{
          background:
            deg > 0
              ? `conic-gradient(from 220deg, #06b6d4 0deg, #8b5cf6 ${deg}deg, #27272a ${deg}deg, #27272a 360deg)`
              : "#27272a",
        }}
      >
        <div className="absolute inset-[10px] rounded-full bg-zinc-950 flex flex-col items-center justify-center">
          <span className="text-2xl font-bold font-mono bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text text-transparent">
            {pct}%
          </span>
          <span className="text-[10px] text-zinc-500 tracking-wide">
            {completed}/{total}
          </span>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Individual stage row                                              */
/* ------------------------------------------------------------------ */

function StageRow({ stage, isCurrent }: { stage: StageInfo; isCurrent: boolean }) {
  const isCompleted = stage.status === "completed" || stage.status === "confirmed";
  const isActive =
    isCurrent || stage.status === "in_progress" || stage.status === "awaiting_confirmation";
  const isFailed = stage.status === "failed";
  const isSkipped = stage.status === "skipped";

  let rowClass =
    "flex items-center gap-2.5 px-3 py-2 rounded-lg transition-all duration-300 ";
  if (isActive) {
    rowClass += "bg-cyan-500/8 border border-cyan-500/25";
  } else if (isCompleted) {
    rowClass += "hover:bg-zinc-800/40";
  } else {
    rowClass += "opacity-50";
  }

  let titleClass = "text-sm truncate transition-colors duration-300 ";
  if (isActive) titleClass += "text-cyan-200 font-medium";
  else if (isCompleted) titleClass += "text-emerald-400";
  else if (isFailed) titleClass += "text-red-400";
  else if (isSkipped) titleClass += "text-yellow-500";
  else titleClass += "text-zinc-500";

  return (
    <div className={rowClass}>
      <span className="shrink-0 w-5 text-center text-sm leading-none">
        {isCompleted && <span className="text-emerald-400">{"\u2705"}</span>}
        {isActive && (
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse shadow-[0_0_6px_rgba(6,182,212,0.6)]" />
        )}
        {isFailed && <span className="text-red-400">{"\u2717"}</span>}
        {isSkipped && <span className="text-yellow-500">{"\u23ED"}</span>}
        {!isCompleted && !isActive && !isFailed && !isSkipped && (
          <span className="text-zinc-600">{"\u2014"}</span>
        )}
      </span>

      <div className="min-w-0 flex-1">
        <div className={titleClass}>{stage.title}</div>
        {isActive && (
          <div className="text-[10px] text-cyan-500/70 font-mono tracking-wide">
            in progress
          </div>
        )}
      </div>

      {isCompleted && stage.turns > 0 && (
        <span className="shrink-0 text-[10px] font-mono bg-zinc-800 text-zinc-400 px-1.5 py-0.5 rounded">
          {stage.turns}t
        </span>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  XP-style footer counter                                          */
/* ------------------------------------------------------------------ */

function XpCounter({ turns, completed, total }: { turns: number; completed: number; total: number }) {
  return (
    <div className="mt-auto pt-3 border-t border-zinc-800">
      <div className="flex justify-between text-[11px] font-mono text-zinc-500 tracking-wider">
        <span>
          TURNS <span className="text-cyan-400">{turns}</span>
        </span>
        <span>
          STAGES{" "}
          <span className="text-violet-400">
            {completed}/{total}
          </span>
        </span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main panel                                                       */
/* ------------------------------------------------------------------ */

export function ProgressPanel({ data }: { data: PanelData | null }) {
  if (!data) {
    return (
      <div className="flex items-center justify-center h-full text-zinc-500 text-sm font-mono animate-pulse">
        Loading stages...
      </div>
    );
  }

  const completedCount = data.completedStageIds.length;
  const totalCount = data.stages.length;
  const totalTurns = data.stages.reduce((sum: number, s: StageInfo) => sum + s.turns, 0);

  return (
    <div className="flex flex-col h-full">
      <h2 className="text-xs font-semibold text-zinc-400 uppercase tracking-widest mb-4 font-mono">
        {"\u27D0"} Progress
      </h2>

      <RadialGauge completed={completedCount} total={totalCount} />

      <div className="flex-1 overflow-y-auto space-y-1 pr-0.5">
        {data.stages.map((stage) => (
          <StageRow
            key={stage.id}
            stage={stage}
            isCurrent={stage.id === data.currentStageId}
          />
        ))}
      </div>

      <XpCounter turns={totalTurns} completed={completedCount} total={totalCount} />
    </div>
  );
}