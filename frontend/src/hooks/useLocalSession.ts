import { useState, useCallback } from 'react';
import type { ClientSession, StateUpdate, ChatMessage } from '../types';
import { EMPTY_CARD_STYLE } from '../types';

const STORAGE_KEY = 'skillcard-session';

function createFreshSession(): ClientSession {
  return {
    sessionId: crypto.randomUUID(),
    currentStageId: 'introduction',
    completedStages: [],
    currentStageMessages: [],
    identity: { name: null, role: null, title: null, photoStatus: 'unknown' },
    photoBase64: null,
    cliftonStrengths: [],
    linkedinSkills: null,
    githubSkills: null,
    bulkExtracted: null,
    panelData: {
      stages: [],
      currentStageId: 'introduction',
      completedStageIds: [],
      profile: { name: null, role: null, photo: null, photoUrl: null },
    },
    cardData: null,
    style: { ...EMPTY_CARD_STYLE },
    createdAt: new Date().toISOString(),
  };
}

function persist(session: ClientSession) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function useLocalSession() {
  // Tracks whether this hook initialized with a brand-new session (no prior
  // localStorage). Stored in state alongside the session so we don't write a
  // ref during render. Consumers call consumeFreshFlag() once on mount to
  // fire `session.started` telemetry without re-firing on remount.
  const [{ session: initialSession, wasFresh }] = useState<{
    session: ClientSession;
    wasFresh: boolean;
  }>(() => {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as ClientSession;
        if (!Array.isArray(parsed.cliftonStrengths)) parsed.cliftonStrengths = [];
        if (!parsed.linkedinSkills) parsed.linkedinSkills = null;
        if (!parsed.githubSkills) parsed.githubSkills = null;
        if (parsed.bulkExtracted === undefined) parsed.bulkExtracted = null;
        if (parsed.identity && parsed.identity.title === undefined) {
          parsed.identity = { ...parsed.identity, title: null };
        }
        if (parsed.cardData && !Array.isArray((parsed.cardData as { strengths?: unknown }).strengths)) {
          parsed.cardData = null;
        }
        if (!parsed.style || typeof parsed.style !== 'object') {
          parsed.style = { ...EMPTY_CARD_STYLE };
        } else {
          parsed.style = {
            stylePreset: parsed.style.stylePreset ?? null,
            personaSetting: parsed.style.personaSetting ?? null,
            accentColor: parsed.style.accentColor ?? null,
          };
        }
        return { session: parsed, wasFresh: false };
      } catch {
        const fresh = createFreshSession();
        persist(fresh);
        return { session: fresh, wasFresh: true };
      }
    }
    const fresh = createFreshSession();
    persist(fresh);
    return { session: fresh, wasFresh: true };
  });
  const [session, setSession] = useState<ClientSession | null>(initialSession);
  const [freshFlag, setFreshFlag] = useState<boolean>(wasFresh);
  const consumeFreshFlag = useCallback(() => {
    if (!freshFlag) return false;
    setFreshFlag(false);
    return true;
  }, [freshFlag]);
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
          // Persist bulk-extracted profile data (first extraction wins)
          bulkExtracted: update.bulkExtracted ?? prev.bulkExtracted,
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

  return { session, loading, updateSession, handleStateUpdate, resetSession, exportSession, consumeFreshFlag };
}
