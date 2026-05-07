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

import { createLogger } from "./logger";

const log = createLogger("telemetry");

export const reactPlugin = new ReactPlugin();

let appInsights: ApplicationInsights | null = null;
let initialized = false;

export function getAppInsights(): ApplicationInsights | null {
  return appInsights;
}

export async function initTelemetry(buildSha?: string, buildTag?: string): Promise<void> {
  if (initialized) return;
  initialized = true;

  let connectionString = "";
  let roleName = "profile-agent-frontend";
  let environment = "dev";
  try {
    const res = await fetch("/api/telemetry/config");
    if (res.ok) {
      const cfg = await res.json();
      connectionString = cfg.connectionString ?? "";
      roleName = cfg.roleName ?? roleName;
      environment = cfg.environment ?? environment;
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
        enableAutoRouteTracking: true,
        autoTrackPageVisitTime: true,
        disableFetchTracking: false,
        enableCorsCorrelation: true,
        enableRequestHeaderTracking: true,
        enableResponseHeaderTracking: true,
        // Same App Insights resource as the backend — distinguish by cloud_RoleName.
      },
    });
    appInsights.loadAppInsights();
    appInsights.addTelemetryInitializer((envelope) => {
      envelope.tags = envelope.tags ?? {};
      envelope.tags["ai.cloud.role"] = roleName;
      const props = (envelope.data ??= {} as Record<string, unknown>);
      const baseData = (props as { baseData?: { properties?: Record<string, unknown> } }).baseData ?? {};
      baseData.properties = {
        ...(baseData.properties ?? {}),
        environment,
        buildSha: buildSha ?? "",
        buildTag: buildTag ?? "",
      };
    });
    appInsights.trackPageView();
    log.info("App Insights initialized", { roleName, environment });
  } catch (e) {
    log.warn("App Insights init failed", e);
    appInsights = null;
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
