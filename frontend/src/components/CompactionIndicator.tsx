import { useState, useEffect, useRef, useCallback } from "react";

interface CompactionIndicatorProps {
  active: boolean;
}

const MESSAGES = [
  "Compacting stage memory...",
  "Synthesizing context...",
  "Consolidating knowledge graph...",
  "Distilling conversation essence...",
];

const PROGRESS_DURATION_MS = 2500;
const PROGRESS_TARGET = 92;
const FADE_OUT_DELAY_MS = 600;

export function CompactionIndicator({ active }: CompactionIndicatorProps) {
  const [visible, setVisible] = useState(false);
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState(MESSAGES[0]);
  const [finishing, setFinishing] = useState(false);
  const rafRef = useRef<number | null>(null);
  const startTimeRef = useRef<number>(0);
  const messageIdxRef = useRef(0);

  const animateProgress = useCallback(() => {
    const elapsed = performance.now() - startTimeRef.current;
    const t = Math.min(elapsed / PROGRESS_DURATION_MS, 1);
    // Ease-out curve: fast start, slow toward target
    const eased = 1 - Math.pow(1 - t, 3);
    setProgress(Math.round(eased * PROGRESS_TARGET));

    if (t < 1) {
      rafRef.current = requestAnimationFrame(animateProgress);
    }
  }, []);

  // Rotate messages while active
  useEffect(() => {
    if (!visible || finishing) return;
    const iv = setInterval(() => {
      messageIdxRef.current = (messageIdxRef.current + 1) % MESSAGES.length;
      setMessage(MESSAGES[messageIdxRef.current]);
    }, 900);
    return () => clearInterval(iv);
  }, [visible, finishing]);

  // Start animation when active
  useEffect(() => {
    if (active) {
      setVisible(true);
      setFinishing(false);
      setProgress(0);
      messageIdxRef.current = Math.floor(Math.random() * MESSAGES.length);
      setMessage(MESSAGES[messageIdxRef.current]);
      startTimeRef.current = performance.now();
      rafRef.current = requestAnimationFrame(animateProgress);
    } else if (visible) {
      // Done — jump to 100% then fade out
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      setProgress(100);
      setFinishing(true);
      setMessage("Context synchronized ✓");
      const timeout = setTimeout(() => setVisible(false), FADE_OUT_DELAY_MS);
      return () => clearTimeout(timeout);
    }
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [active, visible, animateProgress]);

  if (!visible) return null;

  const barWidth = `${progress}%`;
  const barChar = "█";
  const emptyChar = "░";
  const totalBlocks = 20;
  const filledBlocks = Math.round((progress / 100) * totalBlocks);
  const barText =
    barChar.repeat(filledBlocks) + emptyChar.repeat(totalBlocks - filledBlocks);

  return (
    <div
      className={`mx-auto w-full max-w-sm transition-all duration-500 ${
        finishing ? "opacity-0 translate-y-2" : "opacity-100 translate-y-0"
      }`}
    >
      <div className="compaction-terminal relative overflow-hidden rounded-lg border font-mono text-xs">
        {/* Scan-line overlay */}
        <div className="compaction-scanlines pointer-events-none absolute inset-0 z-10" />

        {/* Title bar */}
        <div className="flex items-center gap-2 border-b border-cyan-900/50 bg-black/60 px-3 py-1.5">
          <span className="inline-block h-2 w-2 rounded-full bg-cyan-400 compaction-pulse" />
          <span className="text-cyan-300 tracking-wider text-[10px] uppercase font-bold">
            Memory Compaction
          </span>
          <span className="ml-auto text-cyan-800 text-[10px]">sys.proc</span>
        </div>

        {/* Body */}
        <div className="px-3 py-2.5 space-y-2">
          {/* Status message */}
          <div className="flex items-center gap-1.5">
            <span className="text-yellow-400 text-sm compaction-bolt">⚡</span>
            <span className="text-cyan-200/90 truncate">{message}</span>
          </div>

          {/* Progress bar */}
          <div className="space-y-1">
            <div className="relative h-4 rounded bg-cyan-950/40 overflow-hidden border border-cyan-900/30">
              <div
                className="absolute inset-y-0 left-0 rounded transition-all duration-200 ease-out compaction-bar-glow"
                style={{
                  width: barWidth,
                  background:
                    "linear-gradient(90deg, #0e7490, #06b6d4, #22d3ee)",
                }}
              />
              {/* ASCII bar overlay */}
              <div className="absolute inset-0 flex items-center px-1.5 text-[10px] leading-none">
                <span className="text-cyan-300/60 tracking-[1px]">
                  {barText}
                </span>
              </div>
            </div>
            <div className="flex justify-between text-[10px] text-cyan-600">
              <span>
                {progress < 100 ? "processing" : "done"}{" "}
                <span className="compaction-blink">_</span>
              </span>
              <span className="text-cyan-400 tabular-nums font-bold">
                {progress}%
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
