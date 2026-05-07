/**
 * Application Insights initialization for the React frontend.
 *
 * The connection string is fetched from the backend at boot via /api/telemetry/config.
 * Initialization is best-effort — if the SDK fails to load, the UI continues to work.
 *
 * Auto-collected:
 *  - Page views (history-based)
 *  - Unhandled exceptions
 *  - Fetch / XHR dependencies (with correlation headers to the backend)
 */

import { ApplicationInsights } from "@microsoft/applicationinsights-web";
import { ReactPlugin } from "@microsoft/applicationinsights-react-js";

import { getClientId } from "./clientId";
import { createLogger } from "./logger";

const log = createLogger("telemetry");

export const reactPlugin = new ReactPlugin();

let appInsights: ApplicationInsights | null = null;
let initialized = false;
let buildShaCache = "";
let buildTagCache = "";
let environmentCache = "dev";

export function getAppInsights(): ApplicationInsights | null {
  return appInsights;
}

export async function initTelemetry(buildSha?: string, buildTag?: string): Promise<void> {
  if (initialized) return;
  initialized = true;
  buildShaCache = buildSha ?? "";
  buildTagCache = buildTag ?? "";

  let connectionString = "";
  let roleName = "profile-agent-frontend";
  try {
    const res = await fetch("/api/telemetry/config");
    if (res.ok) {
      const cfg = await res.json();
      connectionString = cfg.connectionString ?? "";
      roleName = cfg.roleName ?? roleName;
      environmentCache = cfg.environment ?? environmentCache;
    }
  } catch (e) {
    log.warn("could not fetch telemetry config", e);
    return;
  }

  if (!connectionString) {
    log.info("telemetry disabled (no connection string)");
    return;
  }

  try {
    appInsights = new ApplicationInsights({
      config: {
        connectionString,
        extensions: [reactPlugin],
        // Chat-style SPA — no client-side routes worth tracking. We emit explicit custom events.
        enableAutoRouteTracking: false,
        autoTrackPageVisitTime: true,
        disableFetchTracking: false,
        enableCorsCorrelation: true,
        enableRequestHeaderTracking: true,
        enableResponseHeaderTracking: true,
      },
    });
    appInsights.loadAppInsights();
    const clientId = getClientId();
    appInsights.addTelemetryInitializer((envelope) => {
      envelope.tags = envelope.tags ?? {};
      envelope.tags["ai.cloud.role"] = roleName;
      const data = (envelope.data ??= {} as Record<string, unknown>);
      const baseData = (data as { baseData?: { properties?: Record<string, unknown> } }).baseData ?? {};
      baseData.properties = {
        ...(baseData.properties ?? {}),
        environment: environmentCache,
        buildSha: buildShaCache,
        buildTag: buildTagCache,
        client_id: clientId,
      };
    });
    appInsights.trackPageView();
    log.info("App Insights initialized", { roleName, environment: environmentCache, clientId });
  } catch (e) {
    log.warn("App Insights init failed", e);
    appInsights = null;
  }
}

/** Bind authenticated user once known. Use a stable opaque ID — never email/UPN. */
export function setUser(opaqueId: string, accountId?: string): void {
  if (!appInsights || !opaqueId) return;
  try {
    appInsights.setAuthenticatedUserContext(opaqueId, accountId, true);
  } catch (e) {
    log.warn("setAuthenticatedUserContext failed", e);
  }
}

export function clearUser(): void {
  if (!appInsights) return;
  try {
    appInsights.clearAuthenticatedUserContext();
  } catch {
    /* ignore */
  }
}

/** Emit a structured custom event (App Insights `customEvents` table). */
export function trackEvent(name: string, properties?: Record<string, unknown>): void {
  if (!appInsights) return;
  try {
    appInsights.trackEvent({ name }, properties as Record<string, string>);
  } catch (e) {
    log.warn("trackEvent failed", e);
  }
}

/** Forward a logger error/exception to App Insights. Safe to call before init (no-op). */
export function trackException(error: unknown, properties?: Record<string, unknown>): void {
  if (!appInsights) return;
  const err = error instanceof Error ? error : new Error(String(error));
  appInsights.trackException({ exception: err, properties });
}

/** Forward a structured trace message to App Insights. */
export function trackTrace(message: string, properties?: Record<string, unknown>): void {
  if (!appInsights) return;
  appInsights.trackTrace({ message, properties });
}

// ── apiFetch wrapper ────────────────────────────────────────────────────────

export type ApiContext = {
  sessionId?: string;
  /** Optional explicit request id; otherwise one is generated per call. */
  requestId?: string;
  /** Optional Authorization Bearer token. */
  authToken?: string;
};

/** fetch() wrapper that injects correlation headers + tracks the call as a custom event. */
export async function apiFetch(
  input: string,
  init: RequestInit = {},
  ctx: ApiContext = {},
): Promise<Response> {
  const requestId = ctx.requestId ?? (crypto.randomUUID?.() ?? Math.random().toString(36).slice(2));
  const headers = new Headers(init.headers ?? {});
  headers.set("X-Client-Id", getClientId());
  headers.set("X-Request-Id", requestId);
  if (ctx.sessionId) headers.set("X-Session-Id", ctx.sessionId);
  if (ctx.authToken && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${ctx.authToken}`);
  }

  const t0 = performance.now();
  let res: Response;
  try {
    res = await fetch(input, { ...init, headers });
  } catch (e) {
    trackException(e, {
      url: input,
      method: init.method ?? "GET",
      request_id: requestId,
      session_id: ctx.sessionId ?? "",
      duration_ms: Math.round(performance.now() - t0),
      outcome: "network_error",
    });
    throw e;
  }
  const duration = Math.round(performance.now() - t0);
  if (!res.ok) {
    trackEvent("api.request.failed", {
      url: input,
      method: init.method ?? "GET",
      status: String(res.status),
      request_id: requestId,
      session_id: ctx.sessionId ?? "",
      duration_ms: String(duration),
    });
  }
  return res;
}

