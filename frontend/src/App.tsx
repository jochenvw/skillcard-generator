import { useRef, useCallback, useState, useEffect } from "react";
import type { UIMessage } from "ai";
import { useLocalSession } from "./hooks/useLocalSession";
import { useAuth } from "./auth";
import { ProgressPanel } from "./components/ProgressPanel";
import { ChatPanel } from "./components/ChatPanel";
import { SummaryPanel } from "./components/SummaryPanel";
import type { CardData, StateUpdate, ClientSession, CardStyle } from "./types";
import { EMPTY_CARD_STYLE } from "./types";
import type { StrengthsResponse } from "./utils/strengthsClient";
import { createLogger } from "./utils/logger";
import { apiFetch, trackEvent } from "./utils/telemetry";

const log = createLogger("app");

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
  const { user, getAuthHeaders, signOut } = useAuth();

  // Display messages — seeded from currentStageMessages on first render
  const [messages, setMessages] = useState<UIMessage[]>(() =>
    session ? toUIMessages(session.currentStageMessages) : [],
  );
  const [isStreaming, setIsStreaming] = useState(false);
  const [cardData, setCardData] = useState<CardData | null>(
    session?.cardData ?? null,
  );
  const [cardImageSrc, setCardImageSrcState] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    try {
      return localStorage.getItem("skillcard-image") || null;
    } catch {
      return null;
    }
  });
  // Explicit lifecycle for the portrait so the spinner only ever shows while we
  // are *actually* generating, and clears on success or failure.
  // 'idle'    — no generation in flight; show whatever cardImageSrc holds (incl. null)
  // 'loading' — request in flight; show the forging spinner
  // 'ready'   — image arrived; show it
  // 'error'   — generation failed/timed out; show retry tile
  type ImageStatus = "idle" | "loading" | "ready" | "error";
  const [imageStatus, setImageStatus] = useState<ImageStatus>(() =>
    typeof window !== "undefined" && localStorage.getItem("skillcard-image") ? "ready" : "idle",
  );
  const [imageError, setImageError] = useState<string | null>(null);
  // Safety-net: if a generation gets stuck (network drop, server crash with no
  // response), force back to 'error' after this many ms so the UI never spins
  // forever. Cleared on success, error, or new generation.
  const imageTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const clearImageTimeout = useCallback(() => {
    if (imageTimeoutRef.current) {
      clearTimeout(imageTimeoutRef.current);
      imageTimeoutRef.current = null;
    }
  }, []);
  const startImageGeneration = useCallback(() => {
    clearImageTimeout();
    setImageError(null);
    setImageStatus("loading");
    imageTimeoutRef.current = setTimeout(() => {
      log.warn("Image generation timed out client-side after 5min");
      setImageStatus("error");
      setImageError("Timed out waiting for the portrait. Try regenerating.");
    }, 5 * 60 * 1000);
  }, [clearImageTimeout]);
  const finishImageGeneration = useCallback(
    (outcome: "ready" | "error", message?: string) => {
      clearImageTimeout();
      setImageStatus(outcome);
      setImageError(outcome === "error" ? (message ?? "Portrait generation failed.") : null);
    },
    [clearImageTimeout],
  );
  useEffect(() => () => clearImageTimeout(), [clearImageTimeout]);
  const setCardImageSrc = useCallback((src: string | null) => {
    setCardImageSrcState(src);
    try {
      if (src) localStorage.setItem("skillcard-image", src);
      else localStorage.removeItem("skillcard-image");
    } catch (err) {
      // QuotaExceeded for very large data URLs — log but don't crash.
      log.warn("Could not cache card image to localStorage", err);
    }
  }, []);
  const [compacting, setCompacting] = useState(false);

  // Track whether the next send should include hasImage
  const hasImageRef = useRef(false);

  // ── /demo route — fetch a pre-baked persona + generated card image ──────
  const demoFetchedRef = useRef(false);
  useEffect(() => {
    if (demoFetchedRef.current) return;
    if (typeof window === "undefined") return;
    if (window.location.pathname !== "/demo") return;
    demoFetchedRef.current = true;

    (async () => {
      try {
        const headers: Record<string, string> = { "Content-Type": "application/json" };
        Object.assign(headers, await getAuthHeaders());

        // 1) Fetch card data immediately so the SkillCard renders.
        const res = await fetch("/api/demo", { method: "POST", headers });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = (await res.json()) as { cardData: CardData };
        setCardData(body.cardData);

        // 2) Kick off the slow image generation. The image-loader in
        // ChatPanel becomes visible as soon as cardData is set & no image yet.
        startImageGeneration();
        const imgRes = await fetch("/api/demo/image", { method: "POST", headers });
        if (!imgRes.ok) throw new Error(`Image HTTP ${imgRes.status}`);
        const imgBody = (await imgRes.json()) as {
          cardImage: { url?: string; base64?: string } | null;
        };
        if (imgBody.cardImage?.url) {
          setCardImageSrc(imgBody.cardImage.url);
          finishImageGeneration("ready");
        } else if (imgBody.cardImage?.base64) {
          setCardImageSrc(`data:image/png;base64,${imgBody.cardImage.base64}`);
          finishImageGeneration("ready");
        } else {
          finishImageGeneration("error", "Demo portrait was not produced.");
        }
      } catch (err) {
        log.error("Demo card load failed", err);
        finishImageGeneration("error", err instanceof Error ? err.message : "Demo failed");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Regenerate card from existing session state (no interview re-run) ─────
  const [regenerating, setRegenerating] = useState(false);
  const regenerateCard = useCallback(async () => {
    if (!session || regenerating) return;
    if (!session.completedStages?.length) {
      log.warn("Regenerate skipped — no completed stages in session");
      return;
    }
    setRegenerating(true);
    setCardImageSrc(null);
    startImageGeneration();
    try {
      const payload = {
        identity: session.identity,
        completedStageSummaries: session.completedStages.map((s) => ({
          id: s.id,
          summary: s.summary,
        })),
        cliftonStrengths: session.cliftonStrengths || [],
        photoBase64: session.photoBase64,
        includeImage: true,
        style: session.style ?? EMPTY_CARD_STYLE,
      };
      log.info("regenerate → POST /api/regenerate", { stages: session.completedStages.length });
      const t0 = performance.now();
      const tokenHeaders = await getAuthHeaders();
      const authToken = tokenHeaders.Authorization?.replace(/^Bearer\s+/i, "");
      trackEvent("regenerate.started", {
        session_id: session.sessionId,
        num_stages: String(session.completedStages.length),
        has_clifton: String(Boolean(session.cliftonStrengths?.length)),
        has_photo: String(Boolean(session.photoBase64)),
      });
      const res = await apiFetch(
        "/api/regenerate",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
        { sessionId: session.sessionId, authToken },
      );
      if (!res.ok) {
        let detail = "";
        try {
          const text = await res.text();
          detail = text.slice(0, 500);
        } catch {
          // body may be unreadable on gateway timeouts
        }
        const err = new Error(`POST /api/regenerate failed: HTTP ${res.status}${detail ? ` — ${detail}` : ""}`);
        log.error("Regenerate request failed", err, { status: res.status, detail });
        if (res.status === 504 || res.status === 502 || res.status === 503) {
          alert(
            "The server took too long to respond (gateway timeout). " +
            "This sometimes happens on a cold start or when image generation is slow. " +
            "Please wait ~30 seconds and try again.",
          );
        } else {
          alert(`Regeneration failed (HTTP ${res.status}). Please try again in a moment.`);
        }
        throw err;
      }
      const body = (await res.json()) as {
        cardData: CardData;
        cardImage?: { url?: string; base64?: string } | null;
        cardImageError?: string;
        cardImageRetryAfter?: number;
      };
      setCardData(body.cardData);
      updateSession({ cardData: body.cardData });
      const imageOutcome = body.cardImage?.url
        ? "url"
        : body.cardImage?.base64
        ? "base64"
        : body.cardImageError === "rate_limited"
        ? "rate_limited"
        : body.cardImageError
        ? "failed"
        : "missing";
      trackEvent("regenerate.completed", {
        session_id: session.sessionId,
        num_stages: String(session.completedStages.length),
        duration_ms: String(Math.round(performance.now() - t0)),
        image_outcome: imageOutcome,
      });
      if (body.cardImage?.url) {
        log.info("regenerate ✓ image (url)");
        setCardImageSrc(body.cardImage.url);
        finishImageGeneration("ready");
      } else if (body.cardImage?.base64) {
        log.info("regenerate ✓ image (base64)", { bytes: body.cardImage.base64.length });
        setCardImageSrc(`data:image/png;base64,${body.cardImage.base64}`);
        finishImageGeneration("ready");
      } else if (body.cardImageError === "rate_limited") {
        log.warn("regenerate image rate-limited", { retryAfter: body.cardImageRetryAfter });
        const wait = body.cardImageRetryAfter
          ? `Please wait ~${body.cardImageRetryAfter}s and try again.`
          : "Please wait a minute and try again.";
        finishImageGeneration("error", `Image service is rate-limited. ${wait}`);
        alert(`Image service is rate-limited right now. Card text was regenerated, but the portrait could not be created. ${wait}`);
      } else if (body.cardImageError) {
        log.warn("regenerate image failed", { error: body.cardImageError });
        finishImageGeneration("error", "Image generation failed. Try regenerating again.");
        alert("Image generation failed. Card text was regenerated. Try again in a moment.");
      } else {
        // Card text came back but no image and no explicit error — treat as failure.
        finishImageGeneration("error", "Portrait was not produced. Try regenerating.");
      }
    } catch (err) {
      log.error("Regenerate failed", err);
      finishImageGeneration("error", err instanceof Error ? err.message : "Regeneration failed");
      // If we haven't already alerted (i.e. this was a non-HTTP error like network failure), notify the user.
      if (err instanceof Error && !err.message.startsWith("POST /api/regenerate failed")) {
        alert(`Could not regenerate: ${err.message}. Check your connection and try again.`);
      }
    } finally {
      setRegenerating(false);
    }
  }, [session, regenerating, getAuthHeaders, updateSession, setCardImageSrc, startImageGeneration, finishImageGeneration]);

  // Expose for quick manual triggering from devtools.
  useEffect(() => {
    (window as unknown as { regenerateCard?: () => void }).regenerateCard = regenerateCard;
  }, [regenerateCard]);

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
          title: session.identity.title || "",
          photoStatus: session.identity.photoStatus,
        },
        hasImage,
        photoBase64: session.photoBase64 || undefined,
        clifton_strengths: session.cliftonStrengths || [],
        linkedin_skills: session.linkedinSkills || undefined,
        github_skills: session.githubSkills || undefined,
        bulk_extracted: session.bulkExtracted || undefined,
        style: session.style ?? EMPTY_CARD_STYLE,
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
        const authHeaders = await getAuthHeaders();
        const res = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders },
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
                  // Card text just arrived — backend will produce an image next.
                  // Begin loading state so the spinner appears (and clears on
                  // success/error/timeout instead of indefinitely).
                  if (imageStatus !== "loading") startImageGeneration();
                  break;
                }
                case "data-cardImage": {
                  const img = evt.data as { url?: string; base64?: string; error?: string };
                  if (img.url) {
                    setCardImageSrc(img.url);
                    finishImageGeneration("ready");
                  } else if (img.base64) {
                    setCardImageSrc(`data:image/png;base64,${img.base64}`);
                    finishImageGeneration("ready");
                  } else {
                    finishImageGeneration(
                      "error",
                      img.error ? `Portrait failed: ${img.error}` : "Portrait was not produced.",
                    );
                  }
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
            finishImageGeneration("ready"); // tear down spinner; ready+null = nothing rendered
            setImageStatus("idle");
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
        log.error("Chat stream error", err);
        const errText =
          assistantText || "Sorry, something went wrong. Please try again.";
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId
              ? { ...m, parts: [{ type: "text" as const, text: errText }] }
              : m,
          ),
        );
        // Stream died — if we'd kicked off an image expectation, mark it failed
        // so the spinner clears.
        if (imageStatus === "loading") {
          finishImageGeneration("error", "Connection lost while generating portrait.");
        }
      } finally {
        setIsStreaming(false);
      }
    },
    [session, isStreaming, handleStateUpdate, updateSession, resetSession, cardData, getAuthHeaders, setCardImageSrc, imageStatus, startImageGeneration, finishImageGeneration],
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

  // ── PDF strengths handlers ──────────────────────────────────────────────
  const handlePdfProcessingStart = useCallback((filename: string) => {
    const ts = Date.now();
    setMessages((prev) => [
      ...prev,
      {
        id: `u-pdf-${ts}`,
        role: "user" as const,
        parts: [{ type: "text" as const, text: `📄 Uploaded: ${filename}` }],
      },
      {
        id: `a-pdf-${ts}`,
        role: "assistant" as const,
        parts: [
          {
            type: "text" as const,
            text: "Analyzing your document for strengths…",
          },
        ],
      },
    ]);
  }, []);

  const handlePdfStrengths = useCallback(
    (resp: StrengthsResponse) => {
      const names = resp.strengths.map((s) => s.name);
      updateSession({ cliftonStrengths: names });

      const summary = `Captured ${names.length} Clifton Strengths from your PDF: ${names.join(", ")}.`;
      setMessages((prev) => [
        ...prev,
        {
          id: `a-pdf-result-${Date.now()}`,
          role: "assistant" as const,
          parts: [{ type: "text" as const, text: summary }],
        },
      ]);
    },
    [updateSession],
  );

  const handlePdfError = useCallback((msg: string) => {
    setMessages((prev) => [
      ...prev,
      {
        id: `a-pdf-err-${Date.now()}`,
        role: "assistant" as const,
        parts: [
          {
            type: "text" as const,
            text: `Sorry, I couldn't analyze that PDF: ${msg}`,
          },
        ],
      },
    ]);
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
        if (!Array.isArray(imported.cliftonStrengths)) {
          imported.cliftonStrengths = [];
        }
        updateSession(imported);
        setMessages(toUIMessages(imported.currentStageMessages));
        setCardData(imported.cardData);
        setCardImageSrc(null);
        clearImageTimeout();
        setImageStatus("idle");
        setImageError(null);
      } catch {
        alert("Failed to parse session file.");
      }
    };
    input.click();
  }, [updateSession, setCardImageSrc, clearImageTimeout]);

  // ── Reset session ───────────────────────────────────────────────────────
  const handleReset = useCallback(() => {
    if (!confirm("Reset session? All interview progress will be lost.")) return;
    resetSession();
    setMessages([]);
    setCardData(null);
    setCardImageSrc(null);
    clearImageTimeout();
    setImageStatus("idle");
    setImageError(null);
  }, [resetSession, setCardImageSrc, clearImageTimeout]);

  // ── Customize-look handler ──────────────────────────────────────────────
  const handleCardStyleChange = useCallback(
    (next: CardStyle) => {
      updateSession({ style: next });
    },
    [updateSession],
  );

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
        <ProgressPanel
          data={session.panelData}
          totalTurns={
            session.completedStages.reduce(
              (sum, s) => sum + Math.ceil((s.turnCount ?? 0) / 2),
              0,
            ) +
            session.currentStageMessages.filter((m) => m.role === "user").length
          }
        />
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
            {/* User info */}
            {user && (
              <span className="text-[11px] text-zinc-500 font-mono mr-2 hidden sm:inline truncate max-w-[160px]" title={user.email}>
                {user.email}
              </span>
            )}

            {/* Sign out */}
            {user && (
              <button
                onClick={signOut}
                title="Sign out"
                className="rounded-lg p-1.5 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                  <polyline points="16 17 21 12 16 7" />
                  <line x1="21" y1="12" x2="9" y2="12" />
                </svg>
              </button>
            )}

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
          imageStatus={imageStatus}
          imageError={imageError}
          onDismissImageError={() => {
            setImageStatus("idle");
            setImageError(null);
          }}
          photoBase64={session.photoBase64}
          getAuthHeaders={getAuthHeaders}
          onPdfProcessingStart={handlePdfProcessingStart}
          onPdfStrengths={handlePdfStrengths}
          onPdfError={handlePdfError}
          onRegenerateCard={regenerateCard}
          regenerating={regenerating}
          cardStyle={session.style ?? EMPTY_CARD_STYLE}
          onCardStyleChange={handleCardStyleChange}
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