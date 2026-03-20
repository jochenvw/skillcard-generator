"""OpenTelemetry setup — traces, metrics, and logs to Azure Monitor."""

from __future__ import annotations

import logging

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)

_configured = False


def configure_telemetry(
    connection_string: str | None = None,
    service_name: str = "profile-agent",
    service_version: str = "0.1.0",
) -> None:
    """Configure OpenTelemetry with Azure Monitor exporter.

    Safe to call multiple times — subsequent calls are no-ops.
    """
    global _configured
    if _configured:
        return

    resource = Resource.create({
        "service.name": service_name,
        "service.version": service_version,
    })

    if connection_string:
        try:
            from azure.monitor.opentelemetry.exporter import (
                AzureMonitorLogExporter,
                AzureMonitorMetricExporter,
                AzureMonitorTraceExporter,
            )

            # Traces
            trace_exporter = AzureMonitorTraceExporter(connection_string=connection_string)
            tracer_provider = TracerProvider(resource=resource)
            tracer_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
            trace.set_tracer_provider(tracer_provider)

            # Metrics
            metric_exporter = AzureMonitorMetricExporter(connection_string=connection_string)
            metric_reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=60000)
            meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
            metrics.set_meter_provider(meter_provider)

            logger.info("Telemetry configured with Azure Monitor")
        except ImportError:
            logger.warning("azure-monitor-opentelemetry-exporter not installed — telemetry disabled")
            _setup_noop_providers(resource)
    else:
        logger.info("No Application Insights connection string — telemetry in console-only mode")
        _setup_noop_providers(resource)

    _configured = True


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
