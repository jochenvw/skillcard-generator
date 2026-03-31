import type { CardData } from "../types";

interface SkillCardProps {
  data: CardData;
  photoBase64?: string | null;
}

export function SkillCard({ data, photoBase64 }: SkillCardProps) {
  const level = data.level ?? 7;
  const xp = data.xp ?? 5120;
  const xpNext = data.xp_to_next_level ?? 2880;
  const xpTotal = xp + xpNext;
  const xpPercent = Math.round((xp / xpTotal) * 100);

  return (
    <div className="w-[420px] mx-auto select-none">
      {/* Card outer frame */}
      <div className="relative rounded-2xl border-2 border-cyan-500/60 bg-gradient-to-b from-slate-900 via-slate-800 to-slate-900 p-1 shadow-[0_0_30px_rgba(6,182,212,0.15)]">
        <div className="rounded-xl border border-slate-700/50 bg-slate-900/90 overflow-hidden">

          {/* Top bar: Level + Title + XP */}
          <div className="flex items-center justify-between px-3 py-2 bg-gradient-to-r from-slate-800 via-slate-700 to-slate-800 border-b border-slate-600/50">
            <span className="flex items-center gap-1">
              <span className="bg-amber-500 text-black text-[10px] font-black px-1.5 py-0.5 rounded uppercase tracking-wider">
                Lvl {level}
              </span>
            </span>
            <span className="text-lg font-black text-white tracking-wide uppercase">
              Skill Deck
            </span>
            <span className="bg-amber-600 text-white text-[10px] font-bold px-2 py-0.5 rounded">
              XP {xp.toLocaleString()}
            </span>
          </div>

          {/* Name banner */}
          <div className="text-center py-1.5 bg-gradient-to-r from-slate-800 via-slate-700 to-slate-800 border-b border-slate-600/30">
            <span className="text-base font-semibold text-slate-200 tracking-wide">
              {data.display_name}
            </span>
          </div>

          {/* Photo area */}
          <div className="relative h-44 bg-gradient-to-br from-indigo-900/80 via-slate-800 to-cyan-900/60 flex items-center justify-center overflow-hidden">
            <div className="absolute inset-0 opacity-20 bg-[radial-gradient(circle_at_30%_40%,rgba(99,102,241,0.4),transparent_50%),radial-gradient(circle_at_70%_60%,rgba(6,182,212,0.3),transparent_50%)]" />
            {(photoBase64 || data.photo_url) ? (
              <img
                src={photoBase64 || data.photo_url || undefined}
                alt={data.display_name || "Profile"}
                className="w-28 h-28 rounded-full object-cover border-2 border-cyan-500/30 shadow-lg shadow-cyan-500/20 relative z-10"
              />
            ) : (
              <div className="w-28 h-28 rounded-full bg-slate-700/60 border-2 border-cyan-500/30 flex items-center justify-center text-4xl">
                {data.display_name?.charAt(0) || "?"}
              </div>
            )}
          </div>

          {/* Top Expertise */}
          <div className="px-3 py-2 bg-gradient-to-r from-amber-900/30 via-slate-800 to-amber-900/30 border-y border-amber-500/20">
            <div className="text-center text-[10px] font-bold text-amber-400 uppercase tracking-widest mb-1.5">
              Top Expertise
            </div>
            <div className="flex justify-around">
              {(data.top_expertise ?? []).map((skill, i) => (
                <div key={i} className="text-center">
                  <div className="text-xl font-black text-white">{skill.score}</div>
                  <div className="text-[9px] text-slate-400 font-medium mt-0.5 max-w-[80px]">
                    {skill.label}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 4-quadrant grid */}
          <div className="grid grid-cols-2 gap-px bg-slate-700/30 mx-2 my-2 rounded-lg overflow-hidden">
            {/* People I Admire */}
            <QuadrantSection
              title="People I Admire"
              items={data.people_i_admire ?? []}
              color="red"
              icon="▸"
            />
            {/* Technical Accomplishments */}
            <QuadrantSection
              title="Technical Accomplishments"
              items={data.technical_accomplishments ?? []}
              color="teal"
              icon="◆"
            />
            {/* Influential Ideas */}
            <QuadrantSection
              title="Influential Ideas"
              items={data.influential_ideas ?? []}
              color="amber"
              icon="▸"
            />
            {/* Strategic Curiosities */}
            <QuadrantSection
              title="Strategic Curiosities"
              items={data.strategic_curiosities ?? []}
              color="indigo"
              icon="▸"
            />
          </div>

          {/* Learn / Grow Into */}
          <div className="mx-2 mb-2 rounded-lg bg-gradient-to-r from-amber-900/40 via-amber-800/30 to-amber-900/40 border border-amber-500/20 px-3 py-2">
            <div className="text-[9px] font-bold text-slate-400 uppercase tracking-widest mb-1">
              Learn / Grow Into
            </div>
            <div className="text-sm font-bold text-amber-400 italic">
              {data.grow_into || "Expanding horizons"}
            </div>
          </div>

          {/* XP bar at bottom */}
          <div className="px-3 py-2 bg-gradient-to-r from-slate-800 via-slate-700 to-slate-800 border-t border-slate-600/30">
            <div className="flex items-center justify-between text-[9px] text-slate-500 mb-1">
              <span className="uppercase tracking-wider font-medium">XP to next Lv</span>
              <span className="font-bold text-amber-400">{xpNext.toLocaleString()}</span>
            </div>
            <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-amber-500 via-orange-500 to-red-500 rounded-full transition-all duration-1000"
                style={{ width: `${xpPercent}%` }}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function QuadrantSection({
  title,
  items,
  color,
  icon,
}: {
  title: string;
  items: string[];
  color: string;
  icon: string;
}) {
  const colorMap: Record<string, string> = {
    red: "from-red-900/40 to-red-950/20 border-red-500/20 text-red-400",
    teal: "from-teal-900/40 to-teal-950/20 border-teal-500/20 text-teal-400",
    amber: "from-amber-900/40 to-amber-950/20 border-amber-500/20 text-amber-400",
    indigo: "from-indigo-900/40 to-indigo-950/20 border-indigo-500/20 text-indigo-400",
  };
  const cls = colorMap[color] || colorMap.teal;
  const [gradientCls, , titleCls] = cls.split(" ");
  const borderCls = cls.split(" ")[1];

  return (
    <div className={`bg-gradient-to-b ${gradientCls} ${borderCls} p-2`}>
      <div className={`text-[8px] font-black uppercase tracking-widest mb-1.5 ${titleCls}`}>
        {title}
      </div>
      <div className="space-y-0.5">
        {items.slice(0, 3).map((item, i) => (
          <div key={i} className="text-[10px] text-slate-300 flex items-start gap-1">
            <span className="text-[8px] mt-0.5 opacity-60">{icon}</span>
            <span>{item}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
