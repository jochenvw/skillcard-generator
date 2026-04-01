import { useRef, useCallback } from "react";
import { toPng } from "html-to-image";
import type { CardData, Rarity, CardStat } from "../types";
import { CardFrame } from "./card/CardFrame";
import { CardPortrait } from "./card/CardPortrait";
import { CardStats } from "./card/CardStats";
import { CardAbilities } from "./card/CardAbilities";
import { CardProgress } from "./card/CardProgress";
import { CardBadges } from "./card/CardBadges";

interface SkillCardProps {
  data: CardData;
  photoBase64?: string | null;
}

/** Normalize data from old or new schema into consistent card props. */
function normalizeStats(data: CardData): CardStat[] {
  if (data.top_stats?.length) return data.top_stats;
  // Backward compat: map legacy top_expertise
  if (data.top_expertise?.length) {
    return data.top_expertise.map((e, i) => ({
      id: `stat_${i}`,
      label: e.label,
      value: e.score,
      icon: "cog",
    }));
  }
  return [];
}

export function SkillCard({ data, photoBase64 }: SkillCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const rarity: Rarity = data.rarity ?? "rare";
  const archetype = data.archetype ?? data.card_title ?? "Technologist";
  const stats = normalizeStats(data);
  const strengths = data.strengths?.length ? data.strengths : [];
  const weaknesses = data.weaknesses?.length ? data.weaknesses : [];
  const signatureAbility = data.signature_ability ?? null;
  const growthFocus = data.growth_focus || data.grow_into || "";
  const flavorText = data.flavor_text || "";
  const level = data.level ?? 7;
  const xp = data.xp ?? 5000;
  const xpNext = data.xp_to_next_level ?? 2000;

  const handleExport = useCallback(async () => {
    if (!cardRef.current) return;
    try {
      const dataUrl = await toPng(cardRef.current, { pixelRatio: 2, cacheBust: true });
      const link = document.createElement("a");
      link.download = `skill-deck-${data.display_name?.replace(/\s+/g, "-").toLowerCase() || "card"}.png`;
      link.href = dataUrl;
      link.click();
    } catch (err) {
      console.error("Card export failed:", err);
    }
  }, [data.display_name]);

  return (
    <div className="flex flex-col items-center gap-2">
      <div ref={cardRef}>
        <CardFrame rarity={rarity}>
      {/* Header bar */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-gradient-to-r from-slate-800/90 via-slate-700/60 to-slate-800/90 border-b border-slate-600/30">
        <span className="text-[10px] font-black text-slate-400 uppercase tracking-[0.15em]">
          Skill Deck
        </span>
        <span className="text-base font-black text-white tracking-wide uppercase">
          {data.display_name}
        </span>
        <span className="text-[10px] font-black text-slate-400 uppercase tracking-[0.15em]">
          #{String(level).padStart(2, "0")}
        </span>
      </div>

      <CardPortrait
        displayName={data.display_name}
        photoBase64={photoBase64}
        photoUrl={data.photo_url}
        archetype={archetype}
      />

      <div className="border-t border-slate-700/30">
        <CardStats stats={stats} />
      </div>

      <div className="border-t border-slate-700/20">
        <CardAbilities
          signatureAbility={signatureAbility}
          strengths={strengths}
          weaknesses={weaknesses}
        />
      </div>

      <div className="border-t border-slate-700/20">
        <CardBadges
          rarity={rarity}
          archetype={archetype}
          growthFocus={growthFocus}
          flavorText={flavorText}
        />
      </div>

      <CardProgress level={level} xp={xp} xpToNextLevel={xpNext} />
        </CardFrame>
      </div>

      {/* Export button */}
      <button
        onClick={handleExport}
        className="text-[10px] text-slate-500 hover:text-slate-300 font-mono uppercase tracking-wider flex items-center gap-1 transition-colors"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="7 10 12 15 17 10" />
          <line x1="12" y1="15" x2="12" y2="3" />
        </svg>
        Save as PNG
      </button>
    </div>
  );
}

