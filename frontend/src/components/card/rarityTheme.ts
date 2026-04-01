import type { Rarity } from "../../types";

const RARITY_COLORS: Record<Rarity, { accent: string; label: string; badgeBg: string }> = {
  common:    { accent: "text-zinc-400",   label: "COMMON",    badgeBg: "bg-zinc-600" },
  rare:      { accent: "text-blue-400",   label: "RARE",      badgeBg: "bg-blue-600" },
  epic:      { accent: "text-purple-400", label: "EPIC",      badgeBg: "bg-purple-600" },
  legendary: { accent: "text-amber-400",  label: "LEGENDARY", badgeBg: "bg-amber-600" },
};

export function getRarityColors(rarity: Rarity) {
  return RARITY_COLORS[rarity] || RARITY_COLORS.common;
}

export function getRarityClass(rarity: Rarity) {
  return `rarity-${rarity}`;
}
