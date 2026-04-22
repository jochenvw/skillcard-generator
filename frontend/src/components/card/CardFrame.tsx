interface CardFrameProps {
  children: React.ReactNode;
}

export function CardFrame({ children }: CardFrameProps) {
  return (
    <div className="w-[420px] mx-auto select-none">
      <div className="skillcard-frame relative rounded-2xl border-2 p-[3px] rarity-rare">
        <div className="relative rounded-xl border border-slate-700/40 bg-slate-900/95 overflow-hidden">
          {children}
        </div>
      </div>
    </div>
  );
}
