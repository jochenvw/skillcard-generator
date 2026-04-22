import { useRef, useCallback } from "react";
import { toPng } from "html-to-image";
import type { SkillCardProfile } from "../types";
import { CardFrame } from "./card/CardFrame";
import { CardPortrait } from "./card/CardPortrait";
import { CardPanel } from "./card/CardPanel";

interface SkillCardProps {
  data: SkillCardProfile;
  photoBase64?: string | null;
}

export function SkillCard({ data, photoBase64 }: SkillCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);

  const subtitleParts = [data.title, data.industry].filter(Boolean);
  const subtitle = subtitleParts.join(" · ");

  const handleExport = useCallback(async () => {
    if (!cardRef.current) return;
    try {
      const dataUrl = await toPng(cardRef.current, { pixelRatio: 2, cacheBust: true });
      const link = document.createElement("a");
      link.download = `skill-deck-${data.name?.replace(/\s+/g, "-").toLowerCase() || "card"}.png`;
      link.href = dataUrl;
      link.click();
    } catch (err) {
      console.error("Card export failed:", err);
    }
  }, [data.name]);

  return (
    <div className="flex flex-col items-center gap-2">
      <div ref={cardRef}>
        <CardFrame>
          {/* Header bar */}
          <div className="flex items-center justify-between px-3 py-1.5 bg-gradient-to-r from-slate-800/90 via-slate-700/60 to-slate-800/90 border-b border-slate-600/30">
            <span className="text-[10px] font-black text-slate-400 uppercase tracking-[0.15em]">
              Skill Deck
            </span>
            <span className="text-base font-black text-white tracking-wide uppercase truncate max-w-[60%] text-center">
              {data.name}
            </span>
            <span className="text-[10px] font-black text-slate-400 uppercase tracking-[0.15em]">
              ◆
            </span>
          </div>

          <CardPortrait
            displayName={data.name}
            photoBase64={photoBase64}
            subtitle={subtitle}
          />

          {/* 6-panel grid */}
          <div className="border-t border-slate-700/30 px-3 py-2.5 grid grid-cols-2 gap-1.5">
            <CardPanel title="Strengths" items={data.strengths} accent="blue" />
            <CardPanel title="Clifton Strengths" items={data.clifton_strengths} accent="purple" />
            <CardPanel title="Inspirations" items={data.inspirations} />
            <CardPanel title="Aspirations" items={data.aspirations} />
            <CardPanel title="Learn / Grow" items={data.learn_grow} />
            <CardPanel title="Accomplishments" items={data.accomplishments} />
          </div>

          {/* Footer */}
          <div className="border-t border-slate-700/30 px-3 py-2 space-y-1.5 bg-gradient-to-r from-slate-800/60 via-slate-800/40 to-slate-800/60">
            {data.growth_focus && (
              <div className="rounded-md bg-slate-800/60 border border-slate-700/30 px-2.5 py-1.5 flex items-center gap-1.5">
                <span className="text-[9px] font-black uppercase tracking-[0.15em] text-slate-500 shrink-0">
                  Next →
                </span>
                <span className="text-[11px] font-bold text-slate-300 truncate">
                  {data.growth_focus}
                </span>
              </div>
            )}
            {data.flavor_text && (
              <div className="text-center px-4 py-1">
                <p className="text-[10px] italic text-slate-500 leading-snug">
                  &ldquo;{data.flavor_text}&rdquo;
                </p>
              </div>
            )}
          </div>
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
