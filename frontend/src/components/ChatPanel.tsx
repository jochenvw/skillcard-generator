import { useState, useRef, useEffect, useCallback, type FormEvent } from "react";
import type { UIMessage } from "ai";
import type { CardData } from "../types";
import { SkillCard } from "./SkillCard";
import { WelcomeBanner } from "./WelcomeBanner";
import { CompactionIndicator } from "./CompactionIndicator";

interface SlashCommand {
  command: string;
  label: string;
  description: string;
}

const SLASH_COMMANDS: SlashCommand[] = [
  { command: "/next",     label: "Next stage",   description: "Move on to the next interview stage" },
  { command: "/skip",     label: "Skip stage",   description: "Skip the current stage" },
  { command: "/progress", label: "Progress",     description: "See where you are in the interview" },
  { command: "/done",     label: "Done",         description: "Finalize and generate your skill card" },
  { command: "/restart",  label: "Start over",   description: "Reset and start from the beginning" },
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
}: ChatPanelProps) {
  const [input, setInputRaw] = useState("");
  const [pendingImage, setPendingImage] = useState<File | null>(null);
  const [slashMenuDismissed, setSlashMenuDismissed] = useState(false);
  const [slashMenuIndex, setSlashMenuIndex] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

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
    <div className="flex flex-col h-full">
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
                <div className="whitespace-pre-wrap">{text}</div>
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

        {cardData && (
          <div className="flex justify-center py-4">
            <SkillCard data={cardData} photoBase64={photoBase64} />
          </div>
        )}

        {cardImageSrc && !cardData && (
          <div className="flex justify-start">
            <div className="max-w-[90%] rounded-2xl rounded-bl-md overflow-hidden border border-violet-500/30 shadow-lg shadow-violet-500/10">
              <img
                src={cardImageSrc}
                alt="Your generated skill card"
                className="w-full max-w-md rounded-t-2xl"
              />
              <div className="bg-zinc-800 px-4 py-2 text-xs text-zinc-400 text-center">
                Your Skill Card
              </div>
            </div>
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
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={isLoading}
            className="shrink-0 rounded-xl bg-zinc-800 border border-zinc-700 p-2.5 text-zinc-400 hover:text-zinc-200 hover:border-zinc-600 disabled:opacity-40 transition-colors"
            title="Upload profile photo"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
            </svg>
          </button>
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message or / for commands…"
            rows={1}
            disabled={isLoading}
            className="flex-1 resize-none overflow-hidden rounded-xl bg-zinc-800 border border-zinc-700 px-4 py-2.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-violet-500 focus:border-violet-500 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={isLoading || (!input.trim() && !pendingImage)}
            className="shrink-0 rounded-xl bg-violet-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-40 disabled:hover:bg-violet-600 transition-colors"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
