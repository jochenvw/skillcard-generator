import { useMemo, useRef, useCallback, useState } from "react";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import type { UIMessage } from "ai";
import { useSession } from "./hooks/useSession";
import { ProgressPanel } from "./components/ProgressPanel";
import { ChatPanel } from "./components/ChatPanel";
import { SummaryPanel } from "./components/SummaryPanel";
import type { PanelData, CardData } from "./types";

/**
 * Inner component that only mounts once sessionId is available.
 * This ensures the Chat instance is always created with a valid transport.
 */
function InterviewChat({
  sessionId,
  panelData,
  setPanelData,
  initialMessages,
}: {
  sessionId: string;
  panelData: PanelData | null;
  setPanelData: (d: PanelData) => void;
  initialMessages: UIMessage[];
}) {
  const imageUploadedRef = useRef(false);
  const [cardImageSrc, setCardImageSrc] = useState<string | null>(null);
  const [cardData, setCardData] = useState<CardData | null>(null);

  const transport = useMemo(
    () =>
      new DefaultChatTransport({
        api: `/api/sessions/${sessionId}/chat`,
      }),
    [sessionId]
  );

  const { messages, sendMessage, status } = useChat({
    transport,
    messages: initialMessages.length > 0 ? initialMessages : undefined,
    onData: (part: { type: string; data?: unknown }) => {
      if (part.type === "data-panelUpdate" && part.data) {
        setPanelData(part.data as PanelData);
      }
      if (part.type === "data-cardImage" && part.data) {
        const img = part.data as { url?: string; base64?: string };
        if (img.url) {
          setCardImageSrc(img.url);
        } else if (img.base64) {
          setCardImageSrc(`data:image/png;base64,${img.base64}`);
        }
      }
      if (part.type === "data-cardData" && part.data) {
        setCardData(part.data as CardData);
      }
      if (part.type === "data-sessionReset") {
        // Reload to get a clean chat state
        window.location.reload();
      }
    },
  });

  const chatLoading = status === "submitted" || status === "streaming";

  const handleSendMessage = useCallback(
    (text: string) => {
      const hasImage = imageUploadedRef.current;
      imageUploadedRef.current = false;
      sendMessage(
        { text },
        hasImage ? { body: { hasImage: true } } : undefined,
      );
    },
    [sendMessage],
  );

  const handleImageUploaded = useCallback(() => {
    imageUploadedRef.current = true;
  }, []);

  return (
    <div className="flex h-screen bg-zinc-950 text-zinc-200">
      {/* Left panel — Progress */}
      <aside className="w-64 shrink-0 border-r border-zinc-800 p-4 overflow-hidden hidden lg:block">
        <ProgressPanel data={panelData} />
      </aside>

      {/* Center panel — Chat */}
      <main className="flex-1 flex flex-col min-w-0">
        <header className="border-b border-zinc-800 px-4 py-3 flex items-center justify-between shrink-0">
          <h1 className="text-sm font-semibold text-zinc-300">
            Skill Card Interview
          </h1>
          <span className="text-[10px] text-zinc-600 font-mono">
            {sessionId.slice(0, 8)}
          </span>
        </header>
        <ChatPanel
          messages={messages}
          isLoading={chatLoading}
          onSendMessage={handleSendMessage}
          onImageUploaded={handleImageUploaded}
          cardImageSrc={cardImageSrc}
          cardData={cardData}
        />
      </main>

      {/* Right panel — Summary */}
      <aside className="w-72 shrink-0 border-l border-zinc-800 p-4 overflow-hidden hidden xl:block">
        <SummaryPanel data={panelData} />
      </aside>
    </div>
  );
}

export default function App() {
  const { sessionId, panelData, setPanelData, initialMessages, loading, error } =
    useSession();

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-zinc-950 text-zinc-400">
        <div className="text-center space-y-3">
          <div className="w-8 h-8 border-2 border-violet-500 border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-sm">Initializing session...</p>
        </div>
      </div>
    );
  }

  if (error || !sessionId) {
    return (
      <div className="flex items-center justify-center h-screen bg-zinc-950 text-red-400">
        <div className="text-center space-y-2">
          <p className="text-sm font-medium">Error</p>
          <p className="text-xs text-zinc-500">
            {error ?? "Failed to initialize session"}
          </p>
        </div>
      </div>
    );
  }

  return (
    <InterviewChat
      sessionId={sessionId}
      panelData={panelData}
      setPanelData={setPanelData}
      initialMessages={initialMessages}
    />
  );
}
