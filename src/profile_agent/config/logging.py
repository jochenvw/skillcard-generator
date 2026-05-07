"""Structured logging configuration."""

from __future__ import annotations

import json
import logging
import sys
from typing import TYPE_CHECKING

from profile_agent.config.context import context_snapshot

if TYPE_CHECKING:
    from profile_agent.config.settings import Settings


# Reserved LogRecord attributes — anything not in here that's set on the record
# is treated as a structured "extra" field and copied into customDimensions.
_RESERVED_LOGRECORD_ATTRS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName", "message", "asctime",
    # Custom additions we always inject below — already top-level fields in our JSON output.
    "request_id", "session_id", "client_id", "user_id",
    "trace_id", "span_id",
}


def _install_record_factory() -> None:
    """Wrap the default LogRecord factory to inject request context + OTel trace ids.

    Using a factory (not a Filter) is the only reliable way to enrich every
    record — including those emitted by 3rd-party child loggers that propagate.
    """
    base_factory = logging.getLogRecordFactory()

    def factory(*args, **kwargs):  # noqa: ANN002, ANN003
        record = base_factory(*args, **kwargs)

        # Per-request context (no-op when called outside a request)
        ctx = context_snapshot()
        for key in ("request_id", "session_id", "client_id", "user_id"):
            setattr(record, key, ctx.get(key, ""))

        # OTel trace correlation — best effort
        try:
            from opentelemetry.trace import get_current_span

            span_ctx = get_current_span().get_span_context()
            if span_ctx and span_ctx.is_valid:
                record.trace_id = format(span_ctx.trace_id, "032x")
                record.span_id = format(span_ctx.span_id, "016x")
            else:
                record.trace_id = ""
                record.span_id = ""
        except Exception:  # noqa: BLE001
            record.trace_id = ""
            record.span_id = ""

        return record

    logging.setLogRecordFactory(factory)


class _JsonFormatter(logging.Formatter):
    """Emit JSON lines with all known context fields plus any extra= fields.

    The OTel logging handler reads `LogRecord.__dict__`, so extras automatically
    flow into Azure Monitor `customDimensions`. This formatter is just for
    stdout (which the Container App ships to Log Analytics).
    """

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload: dict[str, object] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", ""),
            "session_id": getattr(record, "session_id", ""),
            "client_id": getattr(record, "client_id", ""),
            "user_id": getattr(record, "user_id", ""),
            "trace_id": getattr(record, "trace_id", ""),
            "span_id": getattr(record, "span_id", ""),
        }
        # Anything else attached via `extra={...}` becomes a top-level field.
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOGRECORD_ATTRS or key in payload:
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = repr(value)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def configure_logging(settings: Settings) -> None:
    """Set up root logger with appropriate handler/format for the environment."""
    _install_record_factory()

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Remove existing handlers to avoid duplicate output
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)

    if settings.is_dev:
        # Human-friendly with key context fields visible
        formatter = logging.Formatter(
            fmt="%(asctime)s %(levelname)-8s [%(name)s] req=%(request_id).8s sess=%(session_id).8s | %(message)s",
            datefmt="%H:%M:%S",
        )
    else:
        formatter = _JsonFormatter()

    handler.setFormatter(formatter)
    root.addHandler(handler)

    # Quiet noisy libraries
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("opentelemetry").setLevel(logging.WARNING)
