import type { CardAbility } from "../../types";

interface CardAbilitiesProps {
  signatureAbility: CardAbility | null;
  strengths: string[];
  weaknesses: string[];
}

export function CardAbilities({ signatureAbility, strengths, weaknesses }: CardAbilitiesProps) {
  return (
    <div className="px-3 py-2 space-y-2">
      {/* Signature Ability */}
      {signatureAbility && (
        <div className="rounded-lg bg-gradient-to-r from-amber-950/50 via-amber-900/30 to-amber-950/50 border border-amber-500/20 px-3 py-2">
          <div className="text-[9px] font-black uppercase tracking-[0.2em] text-amber-500/80 mb-0.5">
            Signature Ability
          </div>
          <div className="text-sm font-black text-amber-400 tracking-wide">
            {signatureAbility.name}
          </div>
          <div className="text-[10px] text-slate-400 mt-0.5 italic leading-snug">
            {signatureAbility.description}
          </div>
        </div>
      )}

      {/* Strengths & Weaknesses side by side */}
      <div className="grid grid-cols-2 gap-1.5">
        <div className="bg-emerald-950/30 rounded-lg px-2.5 py-2 border border-emerald-500/10">
          <div className="text-[8px] font-black uppercase tracking-[0.2em] text-emerald-500/70 mb-1">
            Strengths
          </div>
          <div className="space-y-0.5">
            {strengths.slice(0, 3).map((s, i) => (
              <div key={i} className="text-[10px] text-slate-300 flex items-start gap-1">
                <span className="text-emerald-500/60 text-[8px] mt-0.5">▸</span>
                <span className="leading-snug">{s}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="bg-red-950/20 rounded-lg px-2.5 py-2 border border-red-500/10">
          <div className="text-[8px] font-black uppercase tracking-[0.2em] text-red-400/70 mb-1">
            Growth Areas
          </div>
          <div className="space-y-0.5">
            {weaknesses.slice(0, 2).map((w, i) => (
              <div key={i} className="text-[10px] text-slate-400 flex items-start gap-1">
                <span className="text-red-400/50 text-[8px] mt-0.5">▸</span>
                <span className="leading-snug">{w}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
