import { useState, useEffect, useRef } from "react";

interface CardGeneratingIndicatorProps {
  active: boolean;
  variant?: "card" | "image";
  /** When the image job is sitting in the server-side throttle queue.
   *  When set, overrides the running indicator with a queued-state UI. */
  queueInfo?: { position: number; etaSec: number } | null;
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
    // Foundry image generation is throttled (~2 req/min) and a single render
    // typically lands between 3 and 6 minutes. Pace the bar over 7 minutes so
    // it doesn't sit pinned at 92% for ages.
    durationMs: 420000,
    progressTarget: 92,
    finishMsg: "Portrait rendered \u2713",
    messages: [
      "Booting image diffusion stack...",
      "Composing card frame & metallic bezels...",
      "Painting subject portrait...",
      "Lighting the scene...",
      "Engraving panel typography...",
      "Polishing holographic accents...",
      "Image service is rate-limited (~2 req/min) — hang tight...",
      "Foundry image gen typically takes 3–6 minutes — still working...",
      "Final pass — sharpening details...",
    ],
  },
} as const;

const FADE_OUT_DELAY_MS = 600;

export function CardGeneratingIndicator({ active, variant = "card", queueInfo = null }: CardGeneratingIndicatorProps) {
  const cfg = VARIANTS[variant];
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState<string>(cfg.messages[0]);
  const [finishing, setFinishing] = useState(false);
  const [prevActive, setPrevActive] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);
  const rafRef = useRef<number | null>(null);
  const messageIdxRef = useRef(0);

  if (active !== prevActive) {
    setPrevActive(active);
    if (active) {
      setProgress(0);
      setFinishing(false);
      setElapsedMs(0);
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
      setElapsedMs(elapsed);
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

  // Queued state — overrides the regular running UI. The throttle queue is a
  // server-side construct; show position + ETA so the user knows we haven't
  // forgotten about them.
  if (active && queueInfo) {
    const etaMin = Math.floor(queueInfo.etaSec / 60);
    const etaSec = queueInfo.etaSec % 60;
    return (
      <div className="mx-auto w-full max-w-sm transition-all duration-500 my-3 opacity-100">
        <div className="compaction-terminal relative overflow-hidden rounded-lg border font-mono text-xs">
          <div className="compaction-scanlines pointer-events-none absolute inset-0 z-10" />
          <div className="flex items-center gap-2 border-b border-amber-900/50 bg-black/60 px-3 py-1.5">
            <span className="inline-block h-2 w-2 rounded-full bg-amber-400 compaction-pulse" />
            <span className="text-amber-300 tracking-wider text-[10px] uppercase font-bold">Queued</span>
            <span className="ml-auto text-amber-800 text-[10px]">img.queue</span>
          </div>
          <div className="px-3 py-2.5 space-y-2 text-amber-200/90">
            <div className="flex items-center gap-1.5">
              <span className="text-amber-400 text-sm">{"\u23F3"}</span>
              <span>
                Position <span className="font-bold text-amber-100">{queueInfo.position}</span> in queue
              </span>
            </div>
            <div className="text-[11px] text-amber-300/70">
              We pace requests so the AI service doesn&apos;t get overwhelmed.
              <br />
              Starting in ~{etaMin > 0 ? `${etaMin}m ${etaSec.toString().padStart(2, "0")}s` : `${etaSec}s`}
            </div>
            <div className="text-[10px] text-amber-500/60 pt-0.5 border-t border-amber-900/30 mt-1">
              Each card takes ~5 minutes once it starts.
            </div>
          </div>
        </div>
      </div>
    );
  }

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
            {variant === "image" && active && (
              <div className="flex justify-between text-[10px] text-violet-500/80 pt-0.5 border-t border-violet-900/30 mt-1">
                <span className="tabular-nums">
                  elapsed: {Math.floor(elapsedMs / 60000)}m {Math.floor((elapsedMs % 60000) / 1000).toString().padStart(2, "0")}s
                </span>
                <span>ETA ~5 min</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
