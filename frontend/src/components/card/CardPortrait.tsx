interface CardPortraitProps {
  displayName: string;
  photoBase64?: string | null;
  subtitle?: string;
}

export function CardPortrait({ displayName, photoBase64, subtitle }: CardPortraitProps) {
  const src = photoBase64 || undefined;
  const initial = displayName?.charAt(0)?.toUpperCase() || "?";

  return (
    <div className="relative h-40 bg-gradient-to-br from-indigo-950/80 via-slate-900 to-cyan-950/60 flex items-center justify-center overflow-hidden">
      {/* Ambient glow spots */}
      <div className="absolute inset-0 opacity-30 bg-[radial-gradient(circle_at_25%_35%,rgba(99,102,241,0.4),transparent_50%),radial-gradient(circle_at_75%_65%,rgba(6,182,212,0.3),transparent_50%)]" />

      {/* Portrait */}
      {src ? (
        <img
          src={src}
          alt={displayName}
          className="w-28 h-28 rounded-full object-cover border-2 border-white/10 shadow-lg shadow-black/40 relative z-10"
        />
      ) : (
        <div className="w-28 h-28 rounded-full bg-slate-800/80 border-2 border-white/10 flex items-center justify-center text-4xl font-bold text-slate-400 relative z-10">
          {initial}
        </div>
      )}

      {/* Subtitle badge overlay */}
      {subtitle && (
        <div className="absolute bottom-2 left-1/2 -translate-x-1/2 z-20 max-w-[90%]">
          <span className="text-[9px] font-black uppercase tracking-[0.2em] text-white/70 bg-black/50 backdrop-blur-sm px-3 py-1 rounded-full border border-white/10 truncate inline-block max-w-full">
            {subtitle}
          </span>
        </div>
      )}
    </div>
  );
}
