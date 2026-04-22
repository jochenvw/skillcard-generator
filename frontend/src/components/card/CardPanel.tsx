type Accent = "blue" | "purple" | "default";

interface CardPanelProps {
  title: string;
  items: string[];
  accent?: Accent;
}

const ACCENT_STYLES: Record<Accent, { bg: string; border: string; label: string; bullet: string }> = {
  blue: {
    bg: "bg-blue-950/30",
    border: "border-blue-500/15",
    label: "text-blue-400/80",
    bullet: "text-blue-400/60",
  },
  purple: {
    bg: "bg-violet-950/30",
    border: "border-violet-500/15",
    label: "text-violet-400/80",
    bullet: "text-violet-400/60",
  },
  default: {
    bg: "bg-slate-800/50",
    border: "border-slate-700/30",
    label: "text-slate-500",
    bullet: "text-slate-500",
  },
};

export function CardPanel({ title, items, accent = "default" }: CardPanelProps) {
  const styles = ACCENT_STYLES[accent];
  const display = items.slice(0, 5);

  return (
    <div className={`rounded-lg ${styles.bg} border ${styles.border} px-2.5 py-2 min-h-[88px]`}>
      <div className={`text-[8px] font-black uppercase tracking-[0.2em] ${styles.label} mb-1`}>
        {title}
      </div>
      {display.length === 0 ? (
        <div className="text-[10px] text-slate-600 italic leading-snug">—</div>
      ) : (
        <div className="space-y-0.5">
          {display.map((item, i) => (
            <div key={i} className="text-[10px] text-slate-300 flex items-start gap-1">
              <span className={`${styles.bullet} text-[8px] mt-0.5`}>▸</span>
              <span className="leading-snug">{item}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
