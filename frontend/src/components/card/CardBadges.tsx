import type { Rarity } from "../../types";
import { getRarityColors } from "./rarityTheme";

interface CardBadgesProps {
  rarity: Rarity;
  archetype: string;
  growthFocus: string;
  flavorText: string;
}

export function CardBadges({ rarity, growthFocus, flavorText }: CardBadgesProps) {
  const colors = getRarityColors(rarity);

  return (
    <div className="px-3 py-2 space-y-1.5">
      {/* Growth focus */}
      {growthFocus && (
        <div className="rounded-md bg-slate-800/60 border border-slate-700/30 px-2.5 py-1.5 flex items-center gap-1.5">
          <span className="text-[9px] font-black uppercase tracking-[0.15em] text-slate-500 shrink-0">
            Next →
          </span>
          <span className="text-[11px] font-bold text-slate-300 truncate">
            {growthFocus}
          </span>
        </div>
      )}

      {/* Flavor text */}
      {flavorText && (
        <div className="text-center px-4 py-1">
          <p className="text-[10px] italic text-slate-500 leading-snug">
            "{flavorText}"
          </p>
        </div>
      )}

      {/* Rarity stamp */}
      <div className="flex justify-center">
        <span className={`text-[8px] font-black uppercase tracking-[0.3em] ${colors.accent}`}>
          {colors.label}
        </span>
      </div>
    </div>
  );
}
