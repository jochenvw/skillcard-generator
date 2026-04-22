import { useState, useEffect, useRef } from "react";

interface CardGeneratingIndicatorProps {
  active: boolean;
  variant?: "card" | "image";
}

const VARIANTS = {
  card: {
    label: "Card Forge",
    procTag: "gen.proc",
    durationMs: 12000,
    progressTarget: 88,
    finishMsg: "Card generated \u2713",
    messages: [
      "Analyzing your strengths profile...",
      "Determining your archetype...",
      "Distilling top abilities...",
      "Crafting flavor text...",
      "Rendering card layout...",
      "Applying holographic finish...",
    ],
  },
  image: {
    label: "Portrait Forge",
    procTag: "img.gen",
    // Image generation is slow (~30-60s) — pace the bar accordingly
    durationMs: 50000,
    progressTarget: 92,
    finishMsg: "Portrait rendered \u2713",
    messages: [
      "Booting image diffusion stack...",
      "Composing card frame & metallic bezels...",
      "Painting subject portrait...",
      "Lighting the scene...",
      "Engraving panel typography...",
      "Polishing holographic accents...",
      "Final pass — sharpening details...",
    ],
  },
} as const;

const FADE_OUT_DELAY_MS = 600;

export function CardGeneratingIndicator({ active, variant = "card" }: CardGeneratingIndicatorProps) {
  const cfg = VARIANTS[variant];
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState<string>(cfg.messages[0]);
  const [finishing, setFinishing] = useState(false);
  const [prevActive, setPrevActive] = useState(false);
  const rafRef = useRef<number | null>(null);
  const messageIdxRef = useRef(0);

  if (active !== prevActive) {
    setPrevActive(active);
    if (active) {
      setProgress(0);
      setFinishing(false);
      setMessage(cfg.messages[0]);
    } else if (prevActive) {
      setProgress(100);
      setFinishing(true);
      setMessage(cfg.finishMsg);
    }
  }

  const visible = active || finishing;

  useEffect(() => {
    if (!active) return;
    const start = performance.now();
    const tick = () => {
      const elapsed = performance.now() - start;
      const t = Math.min(elapsed / cfg.durationMs, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      setProgress(Math.round(eased * cfg.progressTarget));
      if (t < 1) {
        rafRef.current = requestAnimationFrame(tick);
      }
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [active, cfg.durationMs, cfg.progressTarget]);

  useEffect(() => {
    if (!active || finishing) return;
    const iv = setInterval(() => {
      messageIdxRef.current = (messageIdxRef.current + 1) % cfg.messages.length;
      setMessage(cfg.messages[messageIdxRef.current]);
    }, 2000);
    return () => clearInterval(iv);
  }, [active, finishing, cfg.messages]);

  useEffect(() => {
    if (!finishing) return;
    const t = setTimeout(() => setFinishing(false), FADE_OUT_DELAY_MS);
    return () => clearTimeout(t);
  }, [finishing]);

  if (!visible) return null;

  const totalBlocks = 20;
  const filledBlocks = Math.round((progress / 100) * totalBlocks);
  const barText =
    "\u2588".repeat(filledBlocks) + "\u2591".repeat(totalBlocks - filledBlocks);

  return (
    <div
      className={`mx-auto w-full max-w-sm transition-all duration-500 my-3 ${
        finishing ? "opacity-0 translate-y-2" : "opacity-100 translate-y-0"
      }`}
    >
      <div className="compaction-terminal relative overflow-hidden rounded-lg border font-mono text-xs">
        <div className="compaction-scanlines pointer-events-none absolute inset-0 z-10" />

        <div className="flex items-center gap-2 border-b border-violet-900/50 bg-black/60 px-3 py-1.5">
          <span className="inline-block h-2 w-2 rounded-full bg-violet-400 compaction-pulse" />
          <span className="text-violet-300 tracking-wider text-[10px] uppercase font-bold">
            {cfg.label}
          </span>
          <span className="ml-auto text-violet-800 text-[10px]">{cfg.procTag}</span>
        </div>

        <div className="px-3 py-2.5 space-y-2">
          <div className="flex items-center gap-1.5">
            <span className="text-yellow-400 text-sm compaction-bolt">
              {"\u2728"}
            </span>
            <span className="text-violet-200/90 truncate">{message}</span>
          </div>

          <div className="space-y-1">
            <div className="relative h-4 rounded bg-violet-950/40 overflow-hidden border border-violet-900/30">
              <div
                className="absolute inset-y-0 left-0 rounded transition-all duration-200 ease-out"
                style={{
                  width: `${progress}%`,
                  background:
                    "linear-gradient(90deg, #6d28d9, #8b5cf6, #a78bfa)",
                  boxShadow: "0 0 6px rgba(139, 92, 246, 0.4)",
                }}
              />
              <div className="absolute inset-0 flex items-center px-1.5 text-[10px] leading-none">
                <span className="text-violet-300/60 tracking-[1px]">
                  {barText}
                </span>
              </div>
            </div>
            <div className="flex justify-between text-[10px] text-violet-600">
              <span>
                {progress < 100 ? "forging" : "complete"}{" "}
                <span className="compaction-blink">_</span>
              </span>
              <span className="text-violet-400 tabular-nums font-bold">
                {progress}%
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
