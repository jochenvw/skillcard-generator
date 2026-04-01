interface CardProgressProps {
  level: number;
  xp: number;
  xpToNextLevel: number;
}

export function CardProgress({ level, xp, xpToNextLevel }: CardProgressProps) {
  const xpTotal = xp + xpToNextLevel;
  const xpPercent = Math.round((xp / xpTotal) * 100);

  return (
    <div className="px-3 py-2 bg-gradient-to-r from-slate-800/80 via-slate-800/60 to-slate-800/80 border-t border-slate-700/30">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-1.5">
          <span className="bg-amber-500 text-black text-[9px] font-black px-1.5 py-0.5 rounded uppercase tracking-wider">
            Lv {level}
          </span>
          <span className="text-[10px] text-slate-500 font-medium">
            {xp.toLocaleString()} XP
          </span>
        </div>
        <span className="text-[9px] text-slate-600">
          {xpToNextLevel.toLocaleString()} to next
        </span>
      </div>
      <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-amber-500 via-orange-500 to-red-500 rounded-full xp-bar-fill"
          style={{ "--xp-width": `${xpPercent}%` } as React.CSSProperties}
        />
      </div>
    </div>
  );
}
