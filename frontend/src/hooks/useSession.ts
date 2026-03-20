import { useState, useCallback, useEffect } from "react";
import type { UIMessage } from "ai";
import type { PanelData, SessionState } from "../types";

export function useSession() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [panelData, setPanelData] = useState<PanelData | null>(null);
  const [initialMessages, setInitialMessages] = useState<UIMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const initSession = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      // Try to find an existing session
      const listRes = await fetch("/api/sessions");
      if (!listRes.ok) throw new Error("Failed to list sessions");
      const { sessions } = await listRes.json();

      let sid: string;

      if (sessions && sessions.length > 0) {
        // Resume the most recent session
        const latest = sessions.reduce(
          (a: { updated_at: string }, b: { updated_at: string }) =>
            a.updated_at > b.updated_at ? a : b
        );
        sid = latest.session_id;
      } else {
        // Create a new session
        const createRes = await fetch("/api/sessions", { method: "POST" });
        if (!createRes.ok) throw new Error("Failed to create session");
        const { session_id } = await createRes.json();
        sid = session_id;
      }

      setSessionId(sid);

      // Load session state (stages, transcript, profile)
      const stateRes = await fetch(`/api/sessions/${sid}/state`);
      if (stateRes.ok) {
        const state: SessionState = await stateRes.json();
        setPanelData(state.panelData);
        if (state.messages && state.messages.length > 0) {
          setInitialMessages(
            state.messages.map((m, i) => ({
              id: `history-${i}`,
              role: m.role as "user" | "assistant",
              parts: [{ type: "text" as const, text: m.content }],
            }))
          );
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Session init failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    initSession();
  }, [initSession]);

  const createNewSession = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const createRes = await fetch("/api/sessions", { method: "POST" });
      if (!createRes.ok) throw new Error("Failed to create session");
      const { session_id } = await createRes.json();
      setSessionId(session_id);
      setPanelData(null);
      setInitialMessages([]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Session creation failed");
    } finally {
      setLoading(false);
    }
  }, []);

  const resetSession = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      await fetch(`/api/sessions/${sessionId}`, { method: "DELETE" });
      const createRes = await fetch("/api/sessions", { method: "POST" });
      if (!createRes.ok) throw new Error("Failed to create session");
      const { session_id } = await createRes.json();
      setSessionId(session_id);
      setPanelData(null);
      setInitialMessages([]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Reset failed");
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  return {
    sessionId,
    panelData,
    setPanelData,
    initialMessages,
    loading,
    error,
    createNewSession,
    resetSession,
  };
}
