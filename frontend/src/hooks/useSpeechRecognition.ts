/**
 * useSpeechRecognition — browser Web Speech API hook.
 *
 * Exposes start/stop controls plus reactive state for the ChatPanel mic button.
 * No external dependencies — uses the native SpeechRecognition API.
 */

import { useState, useRef, useCallback, useEffect } from "react";

/* ── Web Speech API typings (not in lib.dom by default) ── */

interface SpeechRecognitionEvent extends Event {
  readonly resultIndex: number;
  readonly results: SpeechRecognitionResultList;
}

interface SpeechRecognitionErrorEvent extends Event {
  readonly error: string;
  readonly message: string;
}

interface SpeechRecognitionInstance extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((ev: SpeechRecognitionEvent) => void) | null;
  onerror: ((ev: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

type SpeechRecognitionCtor = new () => SpeechRecognitionInstance;

function getSpeechRecognitionCtor(): SpeechRecognitionCtor | null {
  const w = window as unknown as Record<string, unknown>;
  return (w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null) as SpeechRecognitionCtor | null;
}

/* ── Error classification ── */

/** Errors worth surfacing to the user. */
const USER_FACING_ERRORS: Record<string, string> = {
  "not-allowed": "Microphone permission denied. Please allow access in your browser settings.",
  "audio-capture": "No microphone found. Please connect a microphone and try again.",
  network: "Network error during speech recognition. Please check your connection.",
  "service-not-allowed": "Speech recognition service is not allowed in this browser.",
};

/** Errors that are silent / expected (e.g. user paused too long). */
const SILENT_ERRORS = new Set(["no-speech", "aborted"]);

/* ── Hook ── */

export interface UseSpeechRecognitionOptions {
  /** Called with the final transcript text. */
  onTranscript: (text: string) => void;
  /** BCP-47 language tag. @default "en-US" */
  lang?: string;
}

export interface UseSpeechRecognitionReturn {
  isSupported: boolean;
  isListening: boolean;
  error: string | null;
  startListening: () => void;
  stopListening: () => void;
  clearError: () => void;
}

export function useSpeechRecognition({
  onTranscript,
  lang = "en-US",
}: UseSpeechRecognitionOptions): UseSpeechRecognitionReturn {
  const [isListening, setIsListening] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Keep a stable ref to the latest callback to avoid stale closures.
  const onTranscriptRef = useRef(onTranscript);
  useEffect(() => {
    onTranscriptRef.current = onTranscript;
  }, [onTranscript]);

  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const mountedRef = useRef(true);

  const Ctor = getSpeechRecognitionCtor();
  const isSupported = Ctor !== null;

  // Cleanup on unmount
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (recognitionRef.current) {
        recognitionRef.current.onresult = null;
        recognitionRef.current.onerror = null;
        recognitionRef.current.onend = null;
        recognitionRef.current.onstart = null;
        recognitionRef.current.abort();
        recognitionRef.current = null;
      }
    };
  }, []);

  const startListening = useCallback(() => {
    if (!Ctor) return;

    // Stop any existing session
    if (recognitionRef.current) {
      recognitionRef.current.abort();
      recognitionRef.current = null;
    }

    setError(null);

    const recognition = new Ctor();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = lang;
    recognitionRef.current = recognition;

    recognition.onstart = () => {
      if (mountedRef.current) setIsListening(true);
    };

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      // Collect all final transcripts from this result batch.
      const parts: string[] = [];
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          parts.push(event.results[i][0].transcript);
        }
      }
      const transcript = parts.join(" ").trim();
      if (transcript && mountedRef.current) {
        onTranscriptRef.current(transcript);
      }
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      if (!mountedRef.current) return;
      if (SILENT_ERRORS.has(event.error)) return;
      const message = USER_FACING_ERRORS[event.error] ?? `Speech recognition error: ${event.error}`;
      setError(message);
    };

    recognition.onend = () => {
      if (mountedRef.current) setIsListening(false);
      recognitionRef.current = null;
    };

    try {
      recognition.start();
    } catch {
      setError("Failed to start speech recognition.");
      setIsListening(false);
      recognitionRef.current = null;
    }
  }, [Ctor, lang]);

  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
    }
  }, []);

  const clearError = useCallback(() => setError(null), []);

  return { isSupported, isListening, error, startListening, stopListening, clearError };
}
