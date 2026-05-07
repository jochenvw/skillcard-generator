import { useEffect, useState, useCallback } from "react";
import {
  GALLERY_CAPACITY,
  type GalleryCard,
  deleteCard,
  listCards,
} from "../utils/cardGallery";
import { trackEvent } from "../utils/telemetry";

interface GalleryModalProps {
  open: boolean;
  onClose: () => void;
  onRestore: (card: GalleryCard) => void;
}

function downloadCardImage(card: GalleryCard) {
  const a = document.createElement("a");
  a.href = card.imageDataUrl;
  const safeName = (card.name || "card").replace(/[^a-z0-9-_]+/gi, "_");
  a.download = `skillcard-${safeName}-${card.id.slice(0, 8)}.png`;
  a.click();
  trackEvent("gallery.downloaded", { card_id: card.id });
}

export function GalleryModal({ open, onClose, onRestore }: GalleryModalProps) {
  const [cards, setCards] = useState<GalleryCard[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setCards(await listCards());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    // Lazy-load gallery contents on open. setState inside is intentional —
    // this is the standard fetch-on-open pattern for a modal.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refresh();
    trackEvent("gallery.opened", {});
  }, [open, refresh]);

  if (!open) return null;

  const handleDelete = async (card: GalleryCard) => {
    if (!confirm(`Delete card for "${card.name}"?`)) return;
    await deleteCard(card.id);
    await refresh();
  };

  const handleRestore = (card: GalleryCard) => {
    trackEvent("gallery.restored", { card_id: card.id });
    onRestore(card);
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-4xl max-h-[85vh] overflow-hidden rounded-xl border border-zinc-700 bg-zinc-950 flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between border-b border-zinc-800 px-4 py-3 shrink-0">
          <h2 className="text-sm font-mono text-cyan-400/90 tracking-tight">
            <span className="text-zinc-500">~/</span>gallery
            <span className="text-zinc-600 ml-2 text-[11px]">
              ({cards.length}/{GALLERY_CAPACITY})
            </span>
          </h2>
          <button
            onClick={onClose}
            title="Close"
            className="rounded-lg p-1.5 text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </header>

        <div className="overflow-y-auto p-4">
          {loading && (
            <p className="text-center text-xs font-mono text-zinc-500 py-8">loading…</p>
          )}
          {!loading && cards.length === 0 && (
            <div className="text-center py-12 space-y-2">
              <p className="text-sm text-zinc-400">No saved cards yet.</p>
              <p className="text-xs text-zinc-600 font-mono">
                Generate a card and it will appear here automatically.
              </p>
            </div>
          )}
          {!loading && cards.length > 0 && (
            <ul className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
              {cards.map((card) => (
                <li
                  key={card.id}
                  className="group relative rounded-lg border border-zinc-800 bg-zinc-900 overflow-hidden hover:border-cyan-500/50 transition-colors"
                >
                  <button
                    type="button"
                    onClick={() => handleRestore(card)}
                    title={`Restore ${card.name}`}
                    className="block w-full aspect-[2/3] overflow-hidden cursor-pointer bg-zinc-950"
                  >
                    <img
                      src={card.imageDataUrl}
                      alt={card.name}
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform"
                      loading="lazy"
                    />
                  </button>
                  <div className="px-2 py-1.5 border-t border-zinc-800">
                    <p className="text-[11px] font-mono text-zinc-200 truncate" title={card.name}>
                      {card.name}
                    </p>
                    <p className="text-[10px] text-zinc-500 truncate" title={card.title}>
                      {card.title || "—"}
                    </p>
                    <p className="text-[10px] text-zinc-600 font-mono">
                      {new Date(card.createdAt).toLocaleString(undefined, {
                        year: "2-digit",
                        month: "short",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </p>
                  </div>
                  <div className="flex border-t border-zinc-800 text-[10px] font-mono">
                    <button
                      type="button"
                      onClick={() => downloadCardImage(card)}
                      title="Download PNG"
                      className="flex-1 px-2 py-1.5 text-zinc-400 hover:text-cyan-300 hover:bg-zinc-800 transition-colors"
                    >
                      download
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDelete(card)}
                      title="Delete"
                      className="flex-1 px-2 py-1.5 text-zinc-400 hover:text-red-400 hover:bg-zinc-800 border-l border-zinc-800 transition-colors"
                    >
                      delete
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
