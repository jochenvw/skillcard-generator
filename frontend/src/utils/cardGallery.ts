// Card gallery — keeps the last N generated cards in IndexedDB.
//
// Why IndexedDB and not localStorage?
//   localStorage caps at ~5 MB per origin; a single base64 PNG can be 1-2 MB,
//   so only a handful of cards would fit. IndexedDB gives ~50 MB to unlimited
//   (browser/disk-quota dependent) and handles larger payloads gracefully.
//
// Records are keyed by a content hash of (cardData + style), so saving the
// same card twice is a no-op (it just refreshes the timestamp).

import type { CardData, CardStyle } from "../types";
import { trackEvent } from "./telemetry";

const DB_NAME = "skillcard-gallery";
const DB_VERSION = 1;
const STORE = "cards";
export const GALLERY_CAPACITY = 10;

export interface GalleryCard {
  id: string;             // content hash
  createdAt: number;      // epoch ms
  name: string;
  title: string;
  cardData: CardData;
  style: CardStyle | null;
  imageDataUrl: string;   // data:image/png;base64,... or remote URL
}

let _dbPromise: Promise<IDBDatabase> | null = null;

function openDB(): Promise<IDBDatabase> {
  if (_dbPromise) return _dbPromise;
  _dbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, { keyPath: "id" });
        store.createIndex("createdAt", "createdAt");
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return _dbPromise;
}

async function sha256Hex(input: string): Promise<string> {
  const buf = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest("SHA-256", buf);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export async function computeCardId(
  cardData: CardData,
  style: CardStyle | null,
): Promise<string> {
  const payload = JSON.stringify({ cardData, style: style ?? null });
  return sha256Hex(payload);
}

function txStore(db: IDBDatabase, mode: IDBTransactionMode): IDBObjectStore {
  return db.transaction(STORE, mode).objectStore(STORE);
}

export async function listCards(): Promise<GalleryCard[]> {
  try {
    const db = await openDB();
    return await new Promise<GalleryCard[]>((resolve, reject) => {
      const store = txStore(db, "readonly");
      const req = store.getAll();
      req.onsuccess = () => {
        const cards = (req.result as GalleryCard[]) ?? [];
        cards.sort((a, b) => b.createdAt - a.createdAt);
        resolve(cards);
      };
      req.onerror = () => reject(req.error);
    });
  } catch {
    return [];
  }
}

export async function saveCard(input: {
  cardData: CardData;
  style: CardStyle | null;
  imageDataUrl: string;
}): Promise<GalleryCard | null> {
  try {
    const id = await computeCardId(input.cardData, input.style);
    const record: GalleryCard = {
      id,
      createdAt: Date.now(),
      name:
        (input.cardData as { name?: string; display_name?: string }).name ||
        (input.cardData as { name?: string; display_name?: string }).display_name ||
        "Unknown",
      title: (input.cardData as { title?: string }).title || "",
      cardData: input.cardData,
      style: input.style,
      imageDataUrl: input.imageDataUrl,
    };
    const db = await openDB();
    await new Promise<void>((resolve, reject) => {
      const store = txStore(db, "readwrite");
      const req = store.put(record);
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error);
    });
    await evictOldest();
    trackEvent("gallery.saved", {
      card_id: id,
      name: record.name,
      has_style: String(Boolean(input.style)),
    });
    return record;
  } catch (err) {
    // Quota exceeded or storage disabled — fail silently, gallery is best-effort.
    if (typeof console !== "undefined") {
      console.warn("[gallery] saveCard failed", err);
    }
    return null;
  }
}

export async function deleteCard(id: string): Promise<void> {
  try {
    const db = await openDB();
    await new Promise<void>((resolve, reject) => {
      const store = txStore(db, "readwrite");
      const req = store.delete(id);
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error);
    });
    trackEvent("gallery.deleted", { card_id: id });
  } catch {
    /* ignore */
  }
}

async function evictOldest(): Promise<void> {
  const cards = await listCards();
  if (cards.length <= GALLERY_CAPACITY) return;
  const toRemove = cards.slice(GALLERY_CAPACITY);
  const db = await openDB();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    const store = tx.objectStore(STORE);
    for (const c of toRemove) store.delete(c.id);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function clearAll(): Promise<void> {
  try {
    const db = await openDB();
    await new Promise<void>((resolve, reject) => {
      const store = txStore(db, "readwrite");
      const req = store.clear();
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error);
    });
  } catch {
    /* ignore */
  }
}

export async function importCards(cards: GalleryCard[]): Promise<number> {
  if (!Array.isArray(cards) || !cards.length) return 0;
  let imported = 0;
  try {
    const db = await openDB();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      const store = tx.objectStore(STORE);
      for (const c of cards) {
        if (!c || typeof c.id !== "string" || !c.imageDataUrl) continue;
        store.put(c);
        imported += 1;
      }
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    await evictOldest();
  } catch (err) {
    if (typeof console !== "undefined") {
      console.warn("[gallery] importCards failed", err);
    }
  }
  return imported;
}
