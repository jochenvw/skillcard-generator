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

        {/* Quick-start hints */}
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 text-left space-y-2.5">
          <p className="text-[10px] font-mono uppercase tracking-widest text-cyan-400/70">
            Quick start
          </p>
          <ul className="space-y-2 text-xs text-zinc-400 leading-relaxed">
            <li className="flex gap-2">
              <span className="text-violet-400 shrink-0">📷</span>
              <span>
                <span className="text-zinc-200">Upload a profile picture</span>{" "}
                — used as the portrait reference for your AI-generated card.
              </span>
            </li>
            <li className="flex gap-2">
              <span className="text-violet-400 shrink-0">📄</span>
              <span>
                <span className="text-zinc-200">Drop in a CliftonStrengths PDF</span>{" "}
                — we extract your top themes locally; the file never leaves your browser.
              </span>
            </li>
            <li className="flex gap-2">
              <span className="text-violet-400 shrink-0">💬</span>
              <span>
                <span className="text-zinc-200">Or just start talking</span>{" "}
                — say hi and answer a few questions to build your deck.
              </span>
            </li>
          </ul>
        </div>

        {/* CTA Hint */}
        <p className="text-xs text-zinc-600 pt-2 animate-pulse">
          ↓ Use the buttons or type your first message below…
        </p>
      </div>
    </div>
  );
}
