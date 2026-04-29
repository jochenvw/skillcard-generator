import { useState, useRef, useEffect, useCallback, type FormEvent } from "react";
import type { UIMessage } from "ai";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { CardData, CardStyle } from "../types";
import { SkillCard } from "./SkillCard";
import { WelcomeBanner } from "./WelcomeBanner";
import { CompactionIndicator } from "./CompactionIndicator";
import { CardGeneratingIndicator } from "./CardGeneratingIndicator";
import { CustomizeLookPanel } from "./CustomizeLookPanel";
import { extractPdfText } from "../utils/pdfExtract";
import { extractStrengths, type StrengthsResponse } from "../utils/strengthsClient";
import { useSpeechRecognition } from "../hooks/useSpeechRecognition";
import { createLogger } from "../utils/logger";

const log = createLogger("chat-panel");

interface SlashCommand {
  command: string;
  label: string;
  description: string;
}

const SLASH_COMMANDS: SlashCommand[] = [
  { command: "/next",       label: "Next stage",     description: "Move on to the next interview stage" },
  { command: "/skip",       label: "Skip stage",     description: "Skip the current stage" },
  { command: "/progress",   label: "Progress",       description: "See where you are in the interview" },
  { command: "/card",       label: "Generate card",  description: "Skip ahead and generate your skill card now" },
  { command: "/regenerate", label: "Regenerate card", description: "Re-run card generation from your existing answers" },
  { command: "/demo",       label: "Demo persona",   description: "Open the over-the-top corporate demo card" },
  { command: "/done",       label: "Done",           description: "Finalize and generate your skill card" },
  { command: "/restart",    label: "Start over",     description: "Reset and start from the beginning" },
];

interface ChatPanelProps {
  messages: UIMessage[];
  isLoading: boolean;
  compacting?: boolean;
  onSendMessage: (text: string) => void;
  onImageUploaded?: () => void;
  onPhotoSelected?: (base64: string) => void;
  cardImageSrc?: string | null;
  cardData?: CardData | null;
  photoBase64?: string | null;
  getAuthHeaders?: () => Promise<HeadersInit>;
  onPdfProcessingStart?: (filename: string) => void;
  onPdfStrengths?: (resp: StrengthsResponse) => void;
  onPdfError?: (msg: string) => void;
  onRegenerateCard?: () => void;
  regenerating?: boolean;
  cardStyle?: CardStyle;
  onCardStyleChange?: (next: CardStyle) => void;
}

function getMessageText(message: UIMessage): string {
  return message.parts
    .filter((p): p is Extract<typeof p, { type: "text" }> => p.type === "text")
    .map((p) => p.text)
    .join("");
}

export function ChatPanel({
  messages,
  isLoading,
  compacting,
  onSendMessage,
  onImageUploaded,
  onPhotoSelected,
  cardImageSrc,
  cardData,
  photoBase64,
  getAuthHeaders,
  onPdfProcessingStart,
  onPdfStrengths,
  onPdfError,
  onRegenerateCard,
  regenerating,
  cardStyle,
  onCardStyleChange,
}: ChatPanelProps) {
  const [input, setInputRaw] = useState("");
  const [pendingImage, setPendingImage] = useState<File | null>(null);
  const [slashMenuDismissed, setSlashMenuDismissed] = useState(false);
  const [slashMenuIndex, setSlashMenuIndex] = useState(0);
  const [pdfProcessing, setPdfProcessing] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pdfInputRef = useRef<HTMLInputElement>(null);

  // ── Voice input ──
  const inputRef = useRef(input);
  useEffect(() => { inputRef.current = input; }, [input]);
  const {
    isSupported: speechSupported,
    isListening,
    error: speechError,
    startListening,
    stopListening,
    clearError: clearSpeechError,
  } = useSpeechRecognition({
    onTranscript: (text) => {
      const prev = inputRef.current;
      setInput(prev ? prev + " " + text : text);
      textareaRef.current?.focus();
    },
  });

  // Auto-clear speech error after 5 seconds
  useEffect(() => {
    if (!speechError) return;
    const timer = setTimeout(clearSpeechError, 5000);
    return () => clearTimeout(timer);
  }, [speechError, clearSpeechError]);

  // Wrap setInput to reset slash menu state on every input change
  const setInput = useCallback((value: string) => {
    setInputRaw(value);
    setSlashMenuDismissed(false);
    setSlashMenuIndex(0);
  }, []);

  // Auto-scroll to the latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 120)}px`;
    }
  }, [input]);

  // Re-focus the textarea when streaming finishes — guarantees the user can
  // keep typing without reaching for the mouse after a response arrives.
  const prevLoadingRef = useRef(isLoading);
  useEffect(() => {
    if (prevLoadingRef.current && !isLoading) {
      textareaRef.current?.focus();
    }
    prevLoadingRef.current = isLoading;
  }, [isLoading]);

  // Derive slash menu state from input (no effects needed)
  const slashFilter = input.startsWith("/") ? input.toLowerCase() : "";
  const filteredCommands = slashFilter
    ? SLASH_COMMANDS.filter((c) => c.command.startsWith(slashFilter))
    : [];
  const slashMenuOpen = filteredCommands.length > 0 && !slashMenuDismissed;

  const acceptSlashCommand = useCallback((cmd: SlashCommand) => {
    setInput(cmd.command + " ");
    setSlashMenuDismissed(true);
    textareaRef.current?.focus();
  }, [setInput]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if ((!text && !pendingImage) || isLoading) return;

    // Client-side slash commands — handled locally, not sent to the backend.
    const firstWord = text.split(/\s+/, 1)[0].toLowerCase();
    if (firstWord === "/demo") {
      setInput("");
      setSlashMenuDismissed(false);
      window.location.assign("/demo");
      return;
    }
    if (firstWord === "/regenerate") {
      setInput("");
      setSlashMenuDismissed(false);
      textareaRef.current?.focus();
      onRegenerateCard?.();
      return;
    }

    if (pendingImage) {
      onImageUploaded?.();
      onSendMessage(text || "I've uploaded my photo.");
      setPendingImage(null);
    } else {
      onSendMessage(text);
    }
    setInput("");
    setSlashMenuDismissed(false);
    // Keep focus in the textarea after sending
    textareaRef.current?.focus();
  };

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const allowed = ["image/jpeg", "image/png", "image/webp"];
    if (!allowed.includes(file.type)) {
      alert("Please select a JPEG, PNG, or WebP image.");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      alert("Image must be under 5 MB.");
      return;
    }
    setPendingImage(file);

    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        onPhotoSelected?.(reader.result);
      }
    };
    reader.readAsDataURL(file);

    e.target.value = "";
  }, [onPhotoSelected]);

  const handlePdfSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (file.type !== "application/pdf") {
      alert("Please select a PDF file.");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      alert("PDF must be under 10 MB.");
      return;
    }
    if (!getAuthHeaders) {
      alert("Authentication is not available.");
      return;
    }

    setPdfProcessing(true);
    setPdfError(null);
    onPdfProcessingStart?.(file.name);

    try {
      const text = await extractPdfText(file);
      if (!text) {
        throw new Error("No selectable text found in PDF.");
      }
      log.info("pdf extracted", { length: text.length });
      const authHeaders = await getAuthHeaders();
      const response = await extractStrengths(text, authHeaders);
      log.info("pdf strengths extracted", { count: response.strengths.length });
      onPdfStrengths?.(response);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to process PDF.";
      log.error("pdf processing failed", msg);
      setPdfError(msg);
      onPdfError?.(msg);
    } finally {
      setPdfProcessing(false);
    }
  }, [getAuthHeaders, onPdfProcessingStart, onPdfStrengths, onPdfError]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Navigate slash command menu
    if (slashMenuOpen && filteredCommands.length > 0) {
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setSlashMenuIndex((i) => (i - 1 + filteredCommands.length) % filteredCommands.length);
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSlashMenuIndex((i) => (i + 1) % filteredCommands.length);
        return;
      }
      if (e.key === "Tab" || e.key === "Enter") {
        e.preventDefault();
        acceptSlashCommand(filteredCommands[slashMenuIndex]);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setSlashMenuDismissed(true);
        return;
      }
    }

    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      const form = e.currentTarget.closest("form");
      if (form) form.requestSubmit();
    }
  };

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.length === 0 && <WelcomeBanner />}

        {messages.map((message) => {
          const text = getMessageText(message);
          if (!text) return null;

          return (
            <div
              key={message.id}
              className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                  message.role === "user"
                    ? "bg-violet-600 text-white rounded-br-md"
                    : "bg-zinc-800/80 text-zinc-200 rounded-bl-md border border-zinc-700/50 border-l-2 border-l-cyan-500/40"
                }`}
              >
                {message.role === "user" ? (
                  <div className="whitespace-pre-wrap">{text}</div>
                ) : (
                  <div className="markdown-message">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {isLoading && messages[messages.length - 1]?.role !== "assistant" && (
          <div className="flex justify-start">
            <div className="bg-zinc-800/80 text-cyan-400/70 rounded-2xl rounded-bl-md px-4 py-2.5 text-sm font-mono border border-zinc-700/50 border-l-2 border-l-cyan-500/40">
              <span className="terminal-cursor">▌</span>
            </div>
          </div>
        )}

        <CardGeneratingIndicator
          active={isLoading && !cardData && (() => {
            const lastMsg = messages[messages.length - 1];
            if (!lastMsg || lastMsg.role !== "assistant") return false;
            const text = getMessageText(lastMsg).toLowerCase();
            return text.includes("synthesizing") || text.includes("generating your skill deck") || text.includes("card forge");
          })()}
        />

        {(cardData || cardImageSrc) && (
          <div className="py-4">
            <div className="flex flex-col md:flex-row flex-wrap items-center md:items-start justify-center gap-6">
              {cardData && (
                <SkillCard data={cardData} photoBase64={photoBase64} />
              )}
              {cardImageSrc ? (
                <div className="flex flex-col items-center gap-2">
                  <div className="w-[420px] rounded-2xl overflow-hidden border-2 border-violet-500/30 shadow-lg shadow-violet-500/10 skillcard-frame rarity-epic">
                    <img
                      src={cardImageSrc}
                      alt="AI-generated card portrait"
                      className="w-full"
                    />
                  </div>
                  <span className="text-[10px] text-slate-500 font-mono uppercase tracking-wider">
                    ✨ AI-Generated Portrait
                  </span>
                </div>
              ) : cardData ? (
                <div className="flex flex-col items-center gap-2">
                  <div className="w-[420px] aspect-[2/3] rounded-2xl border-2 border-violet-500/30 shadow-lg shadow-violet-500/10 skillcard-frame rarity-epic bg-gradient-to-br from-slate-900 via-violet-950/40 to-slate-900 flex items-center justify-center p-4 relative overflow-hidden">
                    <div className="absolute inset-0 opacity-30 bg-[radial-gradient(circle_at_50%_50%,rgba(139,92,246,0.25),transparent_60%)] animate-pulse" />
                    <div className="relative z-10 w-full">
                      <CardGeneratingIndicator active variant="image" />
                    </div>
                  </div>
                  <span className="text-[10px] text-violet-400/70 font-mono uppercase tracking-wider">
                    ✨ Forging AI Portrait...
                  </span>
                </div>
              ) : null}
              {cardData && cardStyle && onCardStyleChange && onRegenerateCard && (
                <CustomizeLookPanel
                  style={cardStyle}
                  onChange={onCardStyleChange}
                  onRegenerate={onRegenerateCard}
                  regenerating={regenerating}
                />
              )}
            </div>
            {regenerating && (
              <div className="mt-3 text-center text-xs font-mono uppercase tracking-wider text-violet-300/80">
                ⟳ Regenerating card…
              </div>
            )}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Compaction indicator — between messages and input */}
      {!!compacting && (
        <div className="px-4 py-2">
          <CompactionIndicator active={!!compacting} />
        </div>
      )}

      {/* Input */}
      <div className="border-t border-zinc-800 p-4">
        {pdfError && (
          <div className="mb-2 rounded-lg bg-red-950/40 border border-red-900/50 px-3 py-2 text-xs text-red-300">
            {pdfError}
          </div>
        )}
        {speechError && (
          <div className="mb-2 rounded-lg bg-red-950/40 border border-red-900/50 px-3 py-2 text-xs text-red-300 flex items-center justify-between">
            <span>{speechError}</span>
            <button type="button" onClick={clearSpeechError} className="ml-2 text-red-400 hover:text-red-200" aria-label="Dismiss">✕</button>
          </div>
        )}
        {pdfProcessing && (
          <div className="mb-2 rounded-lg bg-zinc-800 px-3 py-2 text-xs text-cyan-400/80 font-mono">
            <span className="terminal-cursor">▌</span> Analyzing PDF…
          </div>
        )}
        {pendingImage && (
          <div className="mb-2 flex items-center gap-2 rounded-lg bg-zinc-800 px-3 py-2 text-xs text-zinc-300">
            <span className="truncate max-w-[200px]">{pendingImage.name}</span>
            <span className="text-zinc-500">({(pendingImage.size / 1024).toFixed(0)} KB)</span>
            <button
              type="button"
              onClick={() => setPendingImage(null)}
              className="ml-auto text-zinc-500 hover:text-zinc-300"
              aria-label="Remove image"
            >
              ✕
            </button>
          </div>
        )}

        {/* Slash command menu */}
        {slashMenuOpen && filteredCommands.length > 0 && (
          <div className="mb-2 rounded-xl border border-zinc-700 bg-zinc-900 shadow-xl overflow-hidden">
            <div className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-zinc-500 border-b border-zinc-800">
              Commands
            </div>
            {filteredCommands.map((cmd, idx) => (
              <button
                key={cmd.command}
                type="button"
                onMouseDown={(e) => {
                  // Use onMouseDown + preventDefault to avoid blur on textarea
                  e.preventDefault();
                  acceptSlashCommand(cmd);
                }}
                className={`w-full text-left px-3 py-2 flex items-center gap-3 text-sm transition-colors ${
                  idx === slashMenuIndex
                    ? "bg-violet-600/30 text-zinc-100"
                    : "text-zinc-300 hover:bg-zinc-800"
                }`}
              >
                <span className="font-mono text-violet-400 text-xs w-20 shrink-0">{cmd.command}</span>
                <span className="font-medium text-xs">{cmd.label}</span>
                <span className="text-zinc-500 text-xs ml-auto">{cmd.description}</span>
              </button>
            ))}
            <div className="px-3 py-1 text-[10px] text-zinc-600 border-t border-zinc-800 flex gap-3">
              <span>↑↓ navigate</span>
              <span>↵ / Tab select</span>
              <span>Esc dismiss</span>
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="flex gap-2 items-end">
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={handleFileSelect}
            className="hidden"
          />
          <input
            ref={pdfInputRef}
            type="file"
            accept="application/pdf"
            onChange={handlePdfSelect}
            className="hidden"
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={isLoading || pdfProcessing}
            className="shrink-0 rounded-xl bg-zinc-800 border border-zinc-700 p-2.5 text-zinc-400 hover:text-zinc-200 hover:border-zinc-600 disabled:opacity-40 transition-colors"
            title="Upload profile photo"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
            </svg>
          </button>
          <button
            type="button"
            onClick={() => pdfInputRef.current?.click()}
            disabled={isLoading || pdfProcessing}
            className="shrink-0 rounded-xl bg-zinc-800 border border-zinc-700 p-2.5 text-zinc-400 hover:text-zinc-200 hover:border-zinc-600 disabled:opacity-40 transition-colors"
            title="Upload CliftonStrengths PDF"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="9" y1="13" x2="15" y2="13" />
              <line x1="9" y1="17" x2="15" y2="17" />
            </svg>
          </button>
          {speechSupported && (
            <button
              type="button"
              onClick={isListening ? stopListening : startListening}
              disabled={isLoading || pdfProcessing}
              className={`shrink-0 rounded-xl border p-2.5 transition-colors ${
                isListening
                  ? "bg-red-600/80 border-red-500 text-white animate-pulse"
                  : "bg-zinc-800 border-zinc-700 text-zinc-400 hover:text-zinc-200 hover:border-zinc-600"
              } disabled:opacity-40`}
              title={isListening ? "Stop listening" : "Voice input"}
              aria-label={isListening ? "Stop voice input" : "Start voice input"}
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                <line x1="12" y1="19" x2="12" y2="23" />
                <line x1="8" y1="23" x2="16" y2="23" />
              </svg>
            </button>
          )}
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isListening ? "🎤 Listening…" : "Type a message or / for commands…"}
            rows={1}
            className="flex-1 resize-none overflow-hidden rounded-xl bg-zinc-800 border border-zinc-700 px-4 py-2.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-violet-500 focus:border-violet-500"
          />
          <button
            type="submit"
            disabled={isLoading || pdfProcessing || (!input.trim() && !pendingImage)}
            className="shrink-0 rounded-xl bg-violet-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-40 disabled:hover:bg-violet-600 transition-colors"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
