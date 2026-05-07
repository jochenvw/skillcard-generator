import { useCallback } from "react";
import type { CardStyle } from "../types";

const STYLE_PRESETS = [
  "Futuristic Metallic",
  "Cyberpunk Neon",
  "Pokémon TCG",
  "Fantasy Trading Card",
  "Vaporwave",
] as const;

const PERSONA_PRESETS = [
  "Professional",
  "Superhero",
  "Wizard",
  "Astronaut",
  "Anime Hero",
  "Cybernetic Operative",
] as const;

interface AccentSwatch {
  label: string;
  value: string;
  css: string;
}

const ACCENT_SWATCHES: AccentSwatch[] = [
  { label: "Default", value: "", css: "linear-gradient(135deg,#22d3ee,#3b82f6)" },
  { label: "Hot pink", value: "hot pink", css: "#ec4899" },
  { label: "Gold", value: "gold", css: "#f5b700" },
  { label: "Emerald", value: "emerald green", css: "#10b981" },
  { label: "Violet", value: "violet", css: "#8b5cf6" },
  { label: "Crimson", value: "crimson red", css: "#dc2626" },
  { label: "Amber", value: "amber orange", css: "#f59e0b" },
  { label: "Slate", value: "cool slate grey", css: "#64748b" },
];

interface CustomizeLookPanelProps {
  style: CardStyle;
  onChange: (next: CardStyle) => void;
  onRegenerate: () => void;
  regenerating?: boolean;
  disabled?: boolean;
}

export function CustomizeLookPanel({
  style,
  onChange,
  onRegenerate,
  regenerating,
  disabled,
}: CustomizeLookPanelProps) {
  const update = useCallback(
    (patch: Partial<CardStyle>) => onChange({ ...style, ...patch }),
    [style, onChange],
  );

  const isDisabled = disabled || regenerating;

  const currentAccent = style.accentColor ?? "";

  return (
    <div className="w-[280px] shrink-0 rounded-2xl border border-violet-500/20 bg-zinc-900/60 p-4 space-y-4 text-zinc-200">
      <div>
        <h3 className="text-xs font-mono uppercase tracking-wider text-cyan-400/80">
          Customize look
        </h3>
        <p className="text-[10px] text-zinc-500 mt-0.5">
          Layout stays the same — only the art style changes.
        </p>
      </div>

      <label className="block space-y-1">
        <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400">
          Style
        </span>
        <select
          value={style.stylePreset ?? ""}
          onChange={(e) =>
            update({ stylePreset: e.target.value || null })
          }
          disabled={isDisabled}
          className="w-full rounded-md bg-zinc-950 border border-zinc-700 text-xs px-2 py-1.5 focus:outline-none focus:border-cyan-400/60 disabled:opacity-50"
        >
          <option value="">Default (Futuristic Metallic)</option>
          {STYLE_PRESETS.filter((p) => p !== "Futuristic Metallic").map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </label>

      <label className="block space-y-1">
        <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400">
          Depict me as
        </span>
        <select
          value={style.personaSetting ?? ""}
          onChange={(e) =>
            update({ personaSetting: e.target.value || null })
          }
          disabled={isDisabled}
          className="w-full rounded-md bg-zinc-950 border border-zinc-700 text-xs px-2 py-1.5 focus:outline-none focus:border-cyan-400/60 disabled:opacity-50"
        >
          <option value="">Default (Professional)</option>
          {PERSONA_PRESETS.filter((p) => p !== "Professional").map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </label>

      <div className="space-y-1.5">
        <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400 block">
          Accent color
        </span>
        <div className="grid grid-cols-8 gap-1.5">
          {ACCENT_SWATCHES.map((s) => {
            const selected = currentAccent === s.value;
            return (
              <button
                key={s.label}
                type="button"
                title={s.label}
                onClick={() => update({ accentColor: s.value || null })}
                disabled={isDisabled}
                className={`h-6 w-6 rounded-full border transition-all ${
                  selected
                    ? "border-cyan-300 ring-2 ring-cyan-400/50"
                    : "border-zinc-700 hover:border-zinc-500"
                } disabled:opacity-50`}
                style={{ background: s.css }}
              />
            );
          })}
        </div>
        <input
          type="text"
          value={
            currentAccent &&
            !ACCENT_SWATCHES.some((s) => s.value === currentAccent)
              ? currentAccent
              : ""
          }
          onChange={(e) =>
            update({ accentColor: e.target.value.trim() || null })
          }
          placeholder="…or describe a color"
          disabled={isDisabled}
          className="w-full rounded-md bg-zinc-950 border border-zinc-700 text-[11px] px-2 py-1 mt-1 placeholder:text-zinc-600 focus:outline-none focus:border-cyan-400/60 disabled:opacity-50"
        />
      </div>

      <button
        type="button"
        onClick={onRegenerate}
        disabled={isDisabled}
        className="w-full rounded-lg border border-violet-500/40 bg-violet-600/20 hover:bg-violet-600/30 text-xs font-mono uppercase tracking-wider py-2 text-violet-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {regenerating ? "⟳ Regenerating…" : "✨ Regenerate card"}
      </button>
      <p className="text-[10px] text-zinc-500 leading-relaxed mt-1.5">
        ⏱ Portrait generation takes <span className="text-zinc-400 font-medium">~5 minutes</span>.
        The image service is rate-limited to <span className="text-zinc-400 font-medium">~2 requests/minute</span>,
        so try not to spam the button.
      </p>
    </div>
  );
}
