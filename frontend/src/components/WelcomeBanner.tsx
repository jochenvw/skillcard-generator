export function WelcomeBanner() {
  return (
    <div className="flex items-center justify-center h-full px-4">
      <div className="max-w-lg w-full space-y-6 text-center">
        {/* ASCII Art Logo */}
        <div className="relative">
          <pre
            className="font-mono text-xs sm:text-sm leading-tight inline-block text-left bg-gradient-to-r from-cyan-400 via-violet-400 to-cyan-400 bg-clip-text text-transparent select-none"
            style={{
              filter: "drop-shadow(0 0 8px rgba(139, 92, 246, 0.3))",
            }}
          >
            {[
              "┌─────────────────────────┐",
              "│  ╔═╗╦╔═╦╦  ╦    ┌───┐  │",
              "│  ╚═╗╠╩╗║║  ║    │ ♦ │  │",
              "│  ╚═╝╩ ╩╩╩═╝╩═╝  └───┘  │",
              "│     D · E · C · K       │",
              "└─────────────────────────┘",
            ].join("\n")}
          </pre>
        </div>

        {/* Description */}
        <div className="space-y-1.5">
          <p className="text-sm text-zinc-300 leading-relaxed">
            An AI-powered interview that discovers your tech strengths
            <br className="hidden sm:inline" /> and generates a personalized
            skill card.
          </p>
          <p className="text-sm text-zinc-500">
            Answer a few questions, get a card. Simple.
          </p>
        </div>

        {/* Privacy Notice */}
        <div className="inline-flex items-start gap-2.5 rounded-lg border border-emerald-800/50 bg-emerald-950/30 px-4 py-3 text-left">
          <span className="shrink-0 text-base leading-none mt-0.5">🔒</span>
          <div className="space-y-1 text-xs leading-relaxed">
            <p className="text-emerald-300/90">
              Your data stays in <span className="font-semibold">your</span>{" "}
              browser. We store nothing server-side.
            </p>
            <p className="text-emerald-400/60">
              You can export, import, or delete your session anytime.
            </p>
          </div>
        </div>

        {/* CTA Hint */}
        <p className="text-xs text-zinc-600 pt-2 animate-pulse">
          ↓ Type your first message below to begin…
        </p>
      </div>
    </div>
  );
}
