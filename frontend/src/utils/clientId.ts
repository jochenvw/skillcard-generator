/** Stable per-browser client identifier, persisted in localStorage. */

const KEY = "skillcard.clientId";

function uuid(): string {
  // crypto.randomUUID is available in all modern browsers we target.
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  // Fallback (very rare path)
  return "c" + Math.random().toString(36).slice(2) + Date.now().toString(36);
}

export function getClientId(): string {
  try {
    let id = localStorage.getItem(KEY);
    if (!id) {
      id = uuid();
      localStorage.setItem(KEY, id);
    }
    return id;
  } catch {
    // localStorage unavailable (private mode, blocked) — return a per-tab fallback
    return "ephemeral-" + uuid();
  }
}
