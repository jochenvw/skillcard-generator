import { useState, useCallback } from 'react';
import type { ClientSession, StateUpdate, ChatMessage } from '../types';

const STORAGE_KEY = 'skillcard-session';

function createFreshSession(): ClientSession {
  return {
    sessionId: crypto.randomUUID(),
    currentStageId: 'introduction',
    completedStages: [],
    currentStageMessages: [],
    identity: { name: null, role: null, photoStatus: 'unknown' },
    photoBase64: null,
    cliftonStrengths: [],
    panelData: {
      stages: [],
      currentStageId: 'introduction',
      completedStageIds: [],
      profile: { name: null, role: null, photo: null, photoUrl: null },
    },
    cardData: null,
    createdAt: new Date().toISOString(),
  };
}

function persist(session: ClientSession) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function useLocalSession() {
  const [session, setSession] = useState<ClientSession | null>(() => {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as ClientSession;
        // Backfill fields added in later versions
        if (!Array.isArray(parsed.cliftonStrengths)) {
          parsed.cliftonStrengths = [];
        }
        // Discard cardData persisted under the legacy gamey schema
        // (top_stats / weaknesses / signature_ability / level / xp / rarity).
        // It would crash the new SkillCard which expects strengths/inspirations/etc.
        if (parsed.cardData && !Array.isArray((parsed.cardData as { strengths?: unknown }).strengths)) {
          parsed.cardData = null;
        }
        return parsed;
      } catch {
        const fresh = createFreshSession();
        persist(fresh);
        return fresh;
      }
    }
    const fresh = createFreshSession();
    persist(fresh);
    return fresh;
  });
  const loading = session === null;

  const updateSession = useCallback((updates: Partial<ClientSession>) => {
    setSession((prev) => {
      if (!prev) return prev;
      const next = { ...prev, ...updates };
      persist(next);
      return next;
    });
  }, []);

  const handleStateUpdate = useCallback(
    (update: StateUpdate, assistantMessage: string, userMessage: string) => {
      setSession((prev) => {
        if (!prev) return prev;

        const userMsg: ChatMessage = { role: 'user', content: userMessage };
        const assistantMsg: ChatMessage = { role: 'assistant', content: assistantMessage };
        const updatedMessages = [...prev.currentStageMessages, userMsg, assistantMsg];

        let next: ClientSession = {
          ...prev,
          currentStageMessages: updatedMessages,
          identity: update.identity,
          panelData: update.panelData,
          currentStageId: update.currentStageId,
        };

        if (update.stageAdvanced) {
          const completedStage = {
            id: prev.currentStageId,
            title:
              prev.panelData.stages.find((s) => s.id === prev.currentStageId)?.title ??
              prev.currentStageId,
            summary: update.stageSummary ?? '',
            turnCount: updatedMessages.length,
          };

          next = {
            ...next,
            completedStages: [...prev.completedStages, completedStage],
            currentStageMessages: [],
            currentStageId: update.currentStageId,
          };
        }

        persist(next);
        return next;
      });
    },
    [],
  );

  const resetSession = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    const fresh = createFreshSession();
    persist(fresh);
    setSession(fresh);
  }, []);

  const exportSession = useCallback(() => {
    if (!session) return;
    const blob = new Blob([JSON.stringify(session, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `skillcard-session-${session.sessionId.slice(0, 8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [session]);

  return { session, loading, updateSession, handleStateUpdate, resetSession, exportSession };
}
