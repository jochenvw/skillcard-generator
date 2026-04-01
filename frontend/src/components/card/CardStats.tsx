import type { CardStat } from "../../types";

const ICONS: Record<string, string> = {
  cog: "⚙",
  brain: "🧠",
  shield: "🛡",
  cloud: "☁",
  code: "⟨⟩",
  chart: "📊",
  users: "🤝",
  lightning: "⚡",
  database: "🗄",
  globe: "🌐",
};

interface CardStatsProps {
  stats: CardStat[];
}

export function CardStats({ stats }: CardStatsProps) {
  const display = stats.slice(0, 5);

  return (
    <div className="px-3 py-2.5 space-y-1.5">
      <div className="text-[9px] font-black uppercase tracking-[0.2em] text-slate-500 mb-2">
        Core Stats
      </div>
      {display.map((stat) => (
        <div key={stat.id} className="flex items-center gap-2">
          <span className="w-4 text-center text-xs shrink-0" title={stat.icon}>
            {ICONS[stat.icon ?? "cog"] ?? "⚙"}
          </span>
          <span className="text-[10px] text-slate-400 w-20 shrink-0 truncate font-medium uppercase tracking-wider">
            {stat.label}
          </span>
          <div className="flex-1 h-2.5 bg-slate-800 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full stat-bar-fill"
              style={{
                width: `${(stat.value / 10) * 100}%`,
                background: barGradient(stat.value),
              }}
            />
          </div>
          <span className="text-[11px] font-black text-white w-5 text-right tabular-nums">
            {stat.value}
          </span>
        </div>
      ))}
    </div>
  );
}

function barGradient(value: number): string {
  if (value >= 9) return "linear-gradient(90deg, #f59e0b, #ef4444)";
  if (value >= 7) return "linear-gradient(90deg, #3b82f6, #8b5cf6)";
  if (value >= 5) return "linear-gradient(90deg, #06b6d4, #3b82f6)";
  return "linear-gradient(90deg, #6b7280, #9ca3af)";
}
