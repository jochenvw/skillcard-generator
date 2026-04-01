import { useRef, useCallback, useState } from "react";
import type { UIMessage } from "ai";
import { useLocalSession } from "./hooks/useLocalSession";
import { ProgressPanel } from "./components/ProgressPanel";
import { ChatPanel } from "./components/ChatPanel";
import { SummaryPanel } from "./components/SummaryPanel";
import type { CardData, StateUpdate, ClientSession } from "./types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build UIMessage objects from persisted ChatMessage array. */
function toUIMessages(
  msgs: { role: "user" | "assistant"; content: string }[],
): UIMessage[] {
  return msgs.map((m, i) => ({
    id: `restored-${i}`,
    role: m.role,
    parts: [{ type: "text" as const, text: m.content }],
  }));
}

/** Parse a single SSE `data:` payload into a typed event, or null. */
function parseSSEData(
  raw: string,
): { type: string; id?: string; delta?: string; data?: unknown } | null {
  if (raw === "[DONE]") return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

export default function App() {
  const {
    session,
    loading,
    updateSession,
    handleStateUpdate,
    resetSession,
    exportSession,
  } = useLocalSession();

  // Display messages — seeded from currentStageMessages on first render
  const [messages, setMessages] = useState<UIMessage[]>(() =>
    session ? toUIMessages(session.currentStageMessages) : [],
  );
  const [isStreaming, setIsStreaming] = useState(false);
  const [cardData, setCardData] = useState<CardData | null>(
    session?.cardData ?? null,
  );
  const [cardImageSrc, setCardImageSrc] = useState<string | null>(null);
  const [compacting, setCompacting] = useState(false);

  // Track whether the next send should include hasImage
  const hasImageRef = useRef(false);

  // ── Send a chat message via the stateless endpoint ──────────────────────
  const sendMessage = useCallback(
    async (text: string) => {
      if (!session || isStreaming) return;

      const hasImage = hasImageRef.current;
      hasImageRef.current = false;

      // Optimistically add the user bubble
      const userMsg: UIMessage = {
        id: `u-${Date.now()}`,
        role: "user",
        parts: [{ type: "text" as const, text }],
      };
      setMessages((prev) => [...prev, userMsg]);
      setIsStreaming(true);

      const payload = {
        message: text,
        currentStageId: session.currentStageId,
        completedStageSummaries: session.completedStages.map((s) => ({
          id: s.id,
          summary: s.summary,
        })),
        currentStageMessages: session.currentStageMessages,
        identity: {
          name: session.identity.name || "",
          role: session.identity.role || "",
          photoStatus: session.identity.photoStatus,
        },
        hasImage,
      };

      const assistantMsgId = `a-${Date.now()}`;
      let assistantText = "";
      let receivedStateUpdate: StateUpdate | null = null;

      // Add an empty assistant bubble we will fill progressively
      setMessages((prev) => [
        ...prev,
        {
          id: assistantMsgId,
          role: "assistant" as const,
          parts: [{ type: "text" as const, text: "" }],
        },
      ]);

      try {
        const res = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        if (!res.ok) {
          throw new Error(`Chat request failed (${res.status})`);
        }

        const reader = res.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        // Read SSE chunks
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          // Process complete events (separated by double-newline)
          let boundary: number;
          while ((boundary = buffer.indexOf("\n\n")) !== -1) {
            const block = buffer.slice(0, boundary);
            buffer = buffer.slice(boundary + 2);

            for (const line of block.split("\n")) {
              if (!line.startsWith("data: ")) continue;
              const evt = parseSSEData(line.slice(6));
              if (!evt) continue;

              switch (evt.type) {
                case "text-delta": {
                  assistantText += evt.delta ?? "";
                  const snapshot = assistantText;
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantMsgId
                        ? {
                            ...m,
                            parts: [{ type: "text" as const, text: snapshot }],
                          }
                        : m,
                    ),
                  );
                  break;
                }
                case "data-stateUpdate":
                  receivedStateUpdate = evt.data as StateUpdate;
                  if (receivedStateUpdate.stageAdvanced) {
                    setCompacting(true);
                  }
                  break;
                case "data-cardData": {
                  const cd = evt.data as CardData;
                  setCardData(cd);
                  updateSession({ cardData: cd });
                  break;
                }
                case "data-cardImage": {
                  const img = evt.data as { url?: string; base64?: string };
                  if (img.url) setCardImageSrc(img.url);
                  else if (img.base64)
                    setCardImageSrc(`data:image/png;base64,${img.base64}`);
                  break;
                }
                // text-start / text-end are informational — no action needed
              }
            }
          }
        }

        // Persist state after the stream completes
        if (receivedStateUpdate) {
          if (
            (receivedStateUpdate as StateUpdate & { sessionReset?: boolean })
              .sessionReset
          ) {
            setCompacting(false);
            resetSession();
            setMessages([]);
            setCardData(null);
            setCardImageSrc(null);
            return;
          }
          handleStateUpdate(receivedStateUpdate, assistantText, text);

          // End compaction indicator after stage advance settles
          if (receivedStateUpdate.stageAdvanced) {
            setTimeout(() => setCompacting(false), 2500);
          }

          // Card data may also be embedded in the state update
          const embedded = (
            receivedStateUpdate as StateUpdate & { cardData?: CardData }
          ).cardData;
          if (embedded && !cardData) {
            setCardData(embedded);
            updateSession({ cardData: embedded });
          }
        } else if (!assistantText) {
          // Stream ended without content or state update — surface the error
          const errText = "Something went wrong — no response received. Please try again.";
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? { ...m, parts: [{ type: "text" as const, text: errText }] }
                : m,
            ),
          );
        }
      } catch (err) {
        console.error("Chat stream error:", err);
        const errText =
          assistantText || "Sorry, something went wrong. Please try again.";
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId
              ? { ...m, parts: [{ type: "text" as const, text: errText }] }
              : m,
          ),
        );
      } finally {
        setIsStreaming(false);
      }
    },
    [session, isStreaming, handleStateUpdate, updateSession, resetSession, cardData],
  );

  // ── Photo selected in ChatPanel ─────────────────────────────────────────
  const handlePhotoSelected = useCallback(
    (base64: string) => {
      if (!session) return;
      updateSession({
        photoBase64: base64,
        identity: { ...session.identity, photoStatus: "uploaded" },
      });
    },
    [session, updateSession],
  );

  const handleImageUploaded = useCallback(() => {
    hasImageRef.current = true;
  }, []);

  // ── Import session from JSON file ───────────────────────────────────────
  const handleImport = useCallback(() => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".json";
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      try {
        const raw = await file.text();
        const imported = JSON.parse(raw) as ClientSession;
        if (!imported.sessionId || !imported.currentStageId) {
          alert("Invalid session file.");
          return;
        }
        updateSession(imported);
        setMessages(toUIMessages(imported.currentStageMessages));
        setCardData(imported.cardData);
        setCardImageSrc(null);
      } catch {
        alert("Failed to parse session file.");
      }
    };
    input.click();
  }, [updateSession]);

  // ── Reset session ───────────────────────────────────────────────────────
  const handleReset = useCallback(() => {
    if (!confirm("Reset session? All interview progress will be lost.")) return;
    resetSession();
    setMessages([]);
    setCardData(null);
    setCardImageSrc(null);
  }, [resetSession]);

  // ── Loading state ───────────────────────────────────────────────────────
  if (loading || !session) {
    return (
      <div className="flex items-center justify-center h-full bg-zinc-950 text-zinc-400 bg-grid-pattern">
        <div className="text-center space-y-3">
          <p className="text-sm font-mono text-cyan-400/70">
            <span className="text-zinc-500">[</span>
            initializing
            <span className="text-zinc-500">]</span>
            <span className="terminal-cursor text-cyan-400 ml-0.5">▌</span>
          </p>
        </div>
      </div>
    );
  }

  // ── Main layout ─────────────────────────────────────────────────────────
  return (
    <div className="flex h-full bg-zinc-950 text-zinc-200 bg-grid-pattern">
      {/* Left panel — Progress */}
      <aside className="w-64 shrink-0 border-r border-zinc-800 p-4 overflow-hidden hidden lg:block">
        <ProgressPanel data={session.panelData} />
      </aside>

      {/* Centre panel — Chat */}
      <main className="flex-1 flex flex-col min-w-0">
        <header className="border-b border-zinc-800 px-4 py-3 flex items-center justify-between shrink-0 header-scanline">
          <h1 className="text-sm font-mono text-cyan-400/80 tracking-tight">
            <span className="text-zinc-500">skill-deck</span>
            <span className="text-zinc-600">@</span>
            <span className="text-zinc-500">v0.1</span>
            <span className="text-zinc-600 mx-1">~/</span>
            <span className="text-cyan-400/90">interview</span>
            <span className="terminal-cursor text-cyan-400 ml-0.5">▌</span>
          </h1>
          <div className="flex items-center gap-1.5">
            {/* Export */}
            <button
              onClick={exportSession}
              title="Export session"
              className="rounded-lg p-1.5 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
            </button>

            {/* Import */}
            <button
              onClick={handleImport}
              title="Import session"
              className="rounded-lg p-1.5 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
            </button>

            {/* Reset */}
            <button
              onClick={handleReset}
              title="Reset session"
              className="rounded-lg p-1.5 text-zinc-500 hover:text-red-400 hover:bg-zinc-800 transition-colors"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                <path d="M10 11v6" />
                <path d="M14 11v6" />
              </svg>
            </button>

            <span className="text-[10px] text-zinc-600 font-mono ml-1">
              {session.sessionId.slice(0, 8)}
            </span>
          </div>
        </header>

        <ChatPanel
          messages={messages}
          isLoading={isStreaming}
          compacting={compacting}
          onSendMessage={sendMessage}
          onImageUploaded={handleImageUploaded}
          onPhotoSelected={handlePhotoSelected}
          cardImageSrc={cardImageSrc}
          cardData={cardData}
          photoBase64={session.photoBase64}
        />
      </main>

      {/* Right panel — Summary */}
      <aside className="w-72 shrink-0 border-l border-zinc-800 p-4 overflow-hidden hidden xl:block">
        <SummaryPanel
          data={session.panelData}
          photoBase64={session.photoBase64}
          completedStages={session.completedStages}
        />
      </aside>
      {/* Version badge */}
      <div className="fixed bottom-2 right-2 font-mono text-[10px] text-zinc-600 opacity-50 hover:opacity-100 transition-opacity select-none pointer-events-auto z-50">
        {__GIT_TAG__ ? `${__GIT_TAG__} · ${__GIT_SHA__}` : __GIT_SHA__}
      </div>
    </div>
  );
}