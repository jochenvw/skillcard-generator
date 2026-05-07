import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

export type ToastKind = "info" | "success" | "warning" | "error";

export interface Toast {
  id: string;
  kind: ToastKind;
  title?: string;
  message: string;
  /** ms before auto-dismiss; 0 means sticky */
  duration?: number;
  action?: { label: string; onClick: () => void };
}

interface ToastContextValue {
  show: (toast: Omit<Toast, "id">) => string;
  dismiss: (id: string) => void;
  info: (message: string, opts?: Partial<Toast>) => string;
  success: (message: string, opts?: Partial<Toast>) => string;
  warning: (message: string, opts?: Partial<Toast>) => string;
  error: (message: string, opts?: Partial<Toast>) => string;
}

const ToastContext = createContext<ToastContextValue | null>(null);

// eslint-disable-next-line react-refresh/only-export-components
export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counterRef = useRef(0);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const show = useCallback(
    (input: Omit<Toast, "id">): string => {
      counterRef.current += 1;
      const id = `t-${Date.now()}-${counterRef.current}`;
      const toast: Toast = { duration: 6000, ...input, id };
      setToasts((prev) => [...prev, toast]);
      return id;
    },
    [],
  );

  const value = useMemo<ToastContextValue>(
    () => ({
      show,
      dismiss,
      info: (message, opts) => show({ kind: "info", message, ...opts }),
      success: (message, opts) => show({ kind: "success", message, ...opts }),
      warning: (message, opts) => show({ kind: "warning", message, ...opts }),
      error: (message, opts) => show({ kind: "error", message, duration: 0, ...opts }),
    }),
    [show, dismiss],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastViewport toasts={toasts} dismiss={dismiss} />
    </ToastContext.Provider>
  );
}

function ToastViewport({ toasts, dismiss }: { toasts: Toast[]; dismiss: (id: string) => void }) {
  return (
    <div
      aria-live="polite"
      aria-atomic="true"
      className="fixed top-4 right-4 z-[1000] flex flex-col gap-2 w-[min(420px,calc(100vw-2rem))] pointer-events-none"
    >
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} onDismiss={() => dismiss(t.id)} />
      ))}
    </div>
  );
}

const KIND_STYLES: Record<ToastKind, { ring: string; bg: string; iconBg: string; icon: string; title: string }> = {
  info:    { ring: "ring-sky-500/40",    bg: "bg-slate-900/95", iconBg: "bg-sky-500/20",    icon: "ℹ", title: "text-sky-200" },
  success: { ring: "ring-emerald-500/40",bg: "bg-slate-900/95", iconBg: "bg-emerald-500/20",icon: "✓", title: "text-emerald-200" },
  warning: { ring: "ring-amber-500/40",  bg: "bg-slate-900/95", iconBg: "bg-amber-500/20",  icon: "!", title: "text-amber-200" },
  error:   { ring: "ring-red-500/40",    bg: "bg-slate-900/95", iconBg: "bg-red-500/20",    icon: "⚠", title: "text-red-200" },
};

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) {
  const styles = KIND_STYLES[toast.kind];
  useEffect(() => {
    if (!toast.duration) return;
    const t = setTimeout(onDismiss, toast.duration);
    return () => clearTimeout(t);
  }, [toast.duration, onDismiss]);

  return (
    <div
      role={toast.kind === "error" || toast.kind === "warning" ? "alert" : "status"}
      className={`pointer-events-auto flex gap-3 items-start rounded-lg border border-white/10 ${styles.bg} ${styles.ring} ring-1 shadow-lg shadow-black/30 backdrop-blur p-3 animate-[slide-in_0.18s_ease-out]`}
    >
      <span className={`shrink-0 mt-0.5 inline-flex items-center justify-center w-6 h-6 rounded-full ${styles.iconBg} text-sm font-bold`}>
        {styles.icon}
      </span>
      <div className="flex-1 min-w-0">
        {toast.title && (
          <p className={`text-xs font-mono uppercase tracking-wider mb-0.5 ${styles.title}`}>{toast.title}</p>
        )}
        <p className="text-sm text-slate-100 break-words">{toast.message}</p>
        {toast.action && (
          <button
            type="button"
            onClick={() => {
              toast.action?.onClick();
              onDismiss();
            }}
            className="mt-2 px-2.5 py-1 rounded-md bg-violet-600 hover:bg-violet-500 text-white text-xs font-mono uppercase tracking-wider transition"
          >
            {toast.action.label}
          </button>
        )}
      </div>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss notification"
        className="shrink-0 text-slate-400 hover:text-slate-100 text-lg leading-none px-1 -mt-1 -mr-1"
      >
        ×
      </button>
    </div>
  );
}
