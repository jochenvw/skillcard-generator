"""OpenTelemetry setup — traces, metrics, logs, and Live Metrics to Azure Monitor.

Uses the azure-monitor-opentelemetry distro so Live Metrics (QuickPulse) is
supported out of the box. The distro also installs a logging handler on the
root logger that flows LogRecord extras to App Insights customDimensions, and
auto-instruments FastAPI / httpx / requests / urllib3.
"""

from __future__ import annotations

import logging

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

from profile_agent.config.version import get_app_git_tag, get_app_version

logger = logging.getLogger(__name__)

_configured = False
_app_instrumented = False


def configure_telemetry(
    connection_string: str | None = None,
    service_name: str = "profile-agent",
    service_version: str | None = None,
) -> None:
    """Configure OpenTelemetry with Azure Monitor + Live Metrics.

    ``service_version`` defaults to the resolved app version (git SHA from the
    container build), so AppInsights ``cloud_RoleVersion`` is populated on
    every span / log / metric without any extra plumbing.

    Safe to call multiple times — subsequent calls are no-ops.
    """
    global _configured
    if _configured:
        return

    if service_version is None:
        service_version = get_app_version()

    resource_attrs: dict = {
        "service.name": service_name,
        "service.version": service_version,
    }
    git_tag = get_app_git_tag()
    if git_tag:
        resource_attrs["service.git_tag"] = git_tag
    resource = Resource.create(resource_attrs)
    logger.info("Telemetry resource: service.name=%s service.version=%s", service_name, service_version)

    if connection_string:
        try:
            from azure.monitor.opentelemetry import configure_azure_monitor

            # Distro wires up:
            #   - traces  → AzureMonitorTraceExporter
            #   - metrics → AzureMonitorMetricExporter (60s)
            #   - logs    → AzureMonitorLogExporter + LoggingHandler on root logger
            #   - live metrics (QuickPulse) when enable_live_metrics=True
            #   - auto-instrumentation for fastapi, httpx, requests, urllib(3), psycopg, etc.
            configure_azure_monitor(
                connection_string=connection_string,
                resource=resource,
                enable_live_metrics=True,
                logger_name="profile_agent",  # root logger for App Insights log flow
            )
            logger.info("Telemetry configured with Azure Monitor distro (traces, metrics, logs, Live Metrics)")
        except ImportError:
            logger.warning("azure-monitor-opentelemetry distro not installed — telemetry disabled")
            _setup_noop_providers(resource)
        except Exception as e:  # noqa: BLE001 — telemetry must never break the app
            logger.warning("Telemetry setup failed (%s: %s) — falling back to noop", type(e).__name__, e)
            _setup_noop_providers(resource)
    else:
        logger.info("No Application Insights connection string — telemetry in console-only mode")
        _setup_noop_providers(resource)

    _configured = True


def instrument_app(app) -> None:  # noqa: ANN001 — FastAPI app type avoided to keep import light
    """Enable any extra instrumentation not auto-wired by the distro.

    The distro auto-instruments fastapi/httpx/requests/urllib via entry points
    when configure_azure_monitor() runs. We additionally enable the OpenAI v2
    instrumentor so LLM calls show up in App Insights with proper gen_ai.*
    semantic attributes (model, input/output tokens, finish reasons) instead
    of opaque HTTP dependency rows.
    """
    global _app_instrumented
    if _app_instrumented:
        return
    _app_instrumented = True
    try:
        from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

        OpenAIInstrumentor().instrument()
        logger.info("OpenAI v2 instrumentation enabled (gen_ai.* semantic attributes on LLM dependency spans)")
    except ImportError:
        logger.warning("opentelemetry-instrumentation-openai-v2 not installed — LLM calls will appear as raw HTTP")
    except Exception as e:  # noqa: BLE001
        logger.warning("OpenAI instrumentation failed: %s", e)


def _setup_noop_providers(resource: Resource) -> None:
    """Set up providers without exporters for local dev."""
    tracer_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(tracer_provider)

    meter_provider = MeterProvider(resource=resource)
    metrics.set_meter_provider(meter_provider)


def get_tracer(name: str = "profile_agent") -> trace.Tracer:
    return trace.get_tracer(name)


def get_meter(name: str = "profile_agent") -> metrics.Meter:
    return metrics.get_meter(name)


# Pre-defined custom metrics
_meter = metrics.get_meter("profile_agent")

interview_turn_counter = _meter.create_counter(
    "interview.turns",
    description="Total interview turns processed",
)

stage_completion_counter = _meter.create_counter(
    "interview.stage_completions",
    description="Stage completions",
)

extraction_latency = _meter.create_histogram(
    "interview.extraction_latency_ms",
    description="Extraction service call latency in milliseconds",
)

validation_latency = _meter.create_histogram(
    "interview.validation_latency_ms",
    description="Validation service call latency in milliseconds",
)

compression_latency = _meter.create_histogram(
    "interview.compression_latency_ms",
    description="Compression service call latency in milliseconds",
)

image_generation_latency = _meter.create_histogram(
    "interview.image_generation_latency_ms",
    description="Image generation call latency in milliseconds",
)

session_counter = _meter.create_counter(
    "interview.sessions_created",
    description="Total sessions created",
)

