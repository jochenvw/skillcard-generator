/**
 * Lightweight structured logger for the React frontend.
 *
 * Why not just `console.log`?
 *  - Consistent module prefixes for grep/filter in DevTools.
 *  - Debug-level messages are suppressed in production builds (Vite tree-shakes
 *    the body via `import.meta.env.DEV`).
 *  - Single point to wire up remote sinks (Application Insights, etc.) later
 *    without touching every call site.
 *
 * Usage:
 *   import { createLogger } from "../utils/logger";
 *   const log = createLogger("chat");
 *   log.info("send message", { len: text.length });
 *   log.error("stream failed", err);
 */

const IS_DEV = import.meta.env.DEV;

// Color the module tag in the console for quick visual scanning.
const STYLE_TAG = "color:#67e8f9;font-weight:600";
const STYLE_LEVEL_INFO = "color:#a3e635";
const STYLE_LEVEL_WARN = "color:#fbbf24";
const STYLE_LEVEL_ERROR = "color:#f87171";
const STYLE_LEVEL_DEBUG = "color:#94a3b8";

export interface Logger {
  debug: (msg: string, ...args: unknown[]) => void;
  info: (msg: string, ...args: unknown[]) => void;
  warn: (msg: string, ...args: unknown[]) => void;
  error: (msg: string, ...args: unknown[]) => void;
}

function format(level: string, levelStyle: string, tag: string, msg: string): [string, string, string, string] {
  return [`%c[${tag}]%c ${level} %c${msg}`, STYLE_TAG, levelStyle, "color:inherit"];
}

export function createLogger(tag: string): Logger {
  return {
    debug: (msg, ...args) => {
      if (!IS_DEV) return;
      console.debug(...format("DBG", STYLE_LEVEL_DEBUG, tag, msg), ...args);
    },
    info: (msg, ...args) => {
      console.info(...format("INF", STYLE_LEVEL_INFO, tag, msg), ...args);
    },
    warn: (msg, ...args) => {
      console.warn(...format("WRN", STYLE_LEVEL_WARN, tag, msg), ...args);
    },
    error: (msg, ...args) => {
      console.error(...format("ERR", STYLE_LEVEL_ERROR, tag, msg), ...args);
    },
  };
}
