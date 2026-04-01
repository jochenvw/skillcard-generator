import type { Rarity } from "../../types";
import { getRarityClass } from "./rarityTheme";

interface CardFrameProps {
  rarity: Rarity;
  children: React.ReactNode;
}

export function CardFrame({ rarity, children }: CardFrameProps) {
  const hasShimmer = rarity === "epic" || rarity === "legendary";

  return (
    <div className="w-[420px] mx-auto select-none">
      <div
        className={`skillcard-frame relative rounded-2xl border-2 p-[3px] ${getRarityClass(rarity)}`}
      >
        {hasShimmer && <div className="card-shimmer rounded-2xl" />}
        <div className="relative rounded-xl border border-slate-700/40 bg-slate-900/95 overflow-hidden">
          {children}
        </div>
      </div>
    </div>
  );
}
