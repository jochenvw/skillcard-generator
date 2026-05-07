"""Single-process throttle + queue for image generation.

WHY:
    Azure OpenAI gpt-image-* models have a low rate limit (~2 req/min observed).
    Bursts produce 429s + cascading regenerate failures.

DESIGN:
    - Token-bucket admitter: pops one job every ``ADMIT_INTERVAL_S`` seconds.
    - Hard concurrency cap via ``Semaphore(MAX_INFLIGHT)`` — defends against
      long-tail jobs (we observed 590s outliers) overflowing steady-state.
    - Queue depth cap (``MAX_DEPTH``) — fail fast instead of promising waits
      longer than the frontend polling tolerance.
    - Honors upstream ``Retry-After``: ``pause_admission(seconds)`` shifts the
      next admit time forward globally.

CONSTRAINTS:
    - This is an **in-process** queue. ``maxReplicas=1`` is required in
      Container Apps — multiple replicas would each run their own queue and
      defeat the throttle. ``minReplicas=1`` ensures the admitter is always
      running (no scale-to-zero).
    - Single uvicorn worker required for the same reason.
    - In-flight jobs die on container restart. Frontend handles 404 / cancelled
      states with a clear "server restarted" toast.

ETA REPORTED TO CLIENT:
    estimated_wait_s ≈ (queue_position + 1) * ADMIT_INTERVAL_S + RUN_P50_S
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.trace import Link, SpanContext, SpanKind, Status, StatusCode

from profile_agent.config.events import wide_event

logger = logging.getLogger(__name__)

# ── OpenTelemetry instrumentation ───────────────────────────────────────────
# We follow the OTel messaging semantic conventions
# (https://opentelemetry.io/docs/specs/semconv/messaging/) so APM tools can
# render produce → process flows for each image job.
#
# Spans:
#   image_queue.publish   kind=PRODUCER  emitted at enqueue()
#   image_queue.process   kind=CONSUMER  emitted around the worker call;
#                                        linked to the producer span so the
#                                        async hop is visible in App Insights'
#                                        end-to-end transaction view.
#
# Metrics (azure-monitor-opentelemetry exports these as customMetrics):
#   image_queue.queue_wait_s    histogram (s)   how long jobs wait for admission
#   image_queue.run_duration_s  histogram (s)   how long the worker took
#   image_queue.depth           updown counter  current queue depth
#   image_queue.in_flight       updown counter  current concurrency
#   image_queue.jobs            counter         outcome-tagged job count
_tracer = trace.get_tracer("profile_agent.image_queue")
_meter = metrics.get_meter("profile_agent.image_queue")

_metric_queue_wait = _meter.create_histogram(
    "image_queue.queue_wait_s",
    unit="s",
    description="Time a job spent waiting in the throttle queue before admission",
)
_metric_run_duration = _meter.create_histogram(
    "image_queue.run_duration_s",
    unit="s",
    description="Time the worker spent producing the image",
)
_metric_depth = _meter.create_up_down_counter(
    "image_queue.depth",
    unit="{job}",
    description="Current depth of the throttle queue",
)
_metric_in_flight = _meter.create_up_down_counter(
    "image_queue.in_flight",
    unit="{job}",
    description="Current number of in-flight image jobs",
)
_metric_jobs = _meter.create_counter(
    "image_queue.jobs",
    unit="{job}",
    description="Image jobs by outcome (queued / completed / failed / cancelled / rejected)",
)
_MESSAGING_DESTINATION = "image-generation"
_MESSAGING_SYSTEM = "image_queue"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


# Knobs (env-overridable for ops + tests). 40s admit interval gives headroom
# over the observed 2-req/min ceiling. 8 in-flight covers the 5-min p50 with
# safety margin against 10-min outliers. 12 max depth keeps worst-case wait
# under the frontend's 15-min polling budget.
ADMIT_INTERVAL_S: float = float(_env_int("IMAGE_QUEUE_ADMIT_INTERVAL_S", 40))
MAX_INFLIGHT: int = _env_int("IMAGE_QUEUE_MAX_INFLIGHT", 8)
MAX_DEPTH: int = _env_int("IMAGE_QUEUE_MAX_DEPTH", 12)
JOB_TTL_S: int = _env_int("IMAGE_JOB_TTL_S", 1800)
JOB_HARD_TIMEOUT_S: int = _env_int("IMAGE_JOB_HARD_TIMEOUT_S", 600)
RUN_P50_S: int = _env_int("IMAGE_RUN_P50_S", 300)

# State values exposed to clients.
STATE_QUEUED = "queued"
STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_FAILED = "failed"
STATE_CANCELLED = "cancelled"


class QueueFullError(Exception):
    """Raised when the queue depth cap is reached."""

    def __init__(self, depth: int, retry_after_s: int):
        super().__init__(f"image queue full (depth={depth})")
        self.depth = depth
        self.retry_after_s = retry_after_s


# Worker signature: (payload) -> result_dict | None.
# Result dict shape: {"base64": "..."} on success or {"error": "...", ...} on failure.
ImageWorker = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]


@dataclass
class _Job:
    job_id: str
    user_hash: str
    payload: dict[str, Any]
    enqueued_at: float  # monotonic
    enqueued_wall: datetime
    state: str = STATE_QUEUED
    started_at: float | None = None
    finished_at: float | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    error_type: str | None = None
    retry_after: int | None = None
    queue_position: int = 0  # snapshot at enqueue time
    enqueue_in_flight: int = 0  # snapshot at enqueue time
    enqueue_depth: int = 0  # snapshot at enqueue time
    has_photo: bool = False
    cache_key_prefix: str = ""
    # Owning task — kept so we can cancel on shutdown.
    task: asyncio.Task | None = field(default=None, repr=False)
    # OpenTelemetry SpanContext from the producer (enqueue) span. The
    # consumer span links to it so the async hop is visible end-to-end.
    producer_span_context: SpanContext | None = field(default=None, repr=False)
    # Hex trace id of the producer span — surfaced to the API client + in all
    # wide events for this job so a support engineer can pivot from a job_id
    # to the corresponding distributed trace in App Insights.
    trace_id: str = ""


class ImageQueue:
    """Single-process image-generation queue.

    Lifecycle: ``await start(worker)`` once at app startup, ``await stop()``
    on shutdown. Submit work via ``enqueue(...)`` and poll via ``status(...)``.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[_Job] = asyncio.Queue()
        self._sem = asyncio.Semaphore(MAX_INFLIGHT)
        self._jobs: dict[str, _Job] = {}
        self._admitter_task: asyncio.Task | None = None
        self._running_tasks: set[asyncio.Task] = set()
        self._worker: ImageWorker | None = None
        self._accepting: bool = False
        # Monotonic timestamps. ``_next_admit_at`` enforces start-rate.
        # ``_paused_until`` lets upstream 429s globally extend it.
        self._next_admit_at: float = 0.0
        self._paused_until: float = 0.0
        self._in_flight: int = 0
        # When the admitter has pulled a job from the queue but is still waiting
        # for the cadence delay or in-flight semaphore, the job is in limbo:
        # it's no longer "queued" and not yet "running". Track it so stop() can
        # cancel it cleanly.
        self._admitting: _Job | None = None
        self._lock = asyncio.Lock()  # guards _next_admit_at + _paused_until reads in stats

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def start(self, worker: ImageWorker) -> None:
        if self._admitter_task is not None:
            return
        self._worker = worker
        self._accepting = True
        self._admitter_task = asyncio.create_task(self._admitter_loop(), name="image-queue-admitter")
        wide_event(
            "image_queue.startup",
            outcome="ok",
            admit_interval_s=ADMIT_INTERVAL_S,
            max_inflight=MAX_INFLIGHT,
            max_depth=MAX_DEPTH,
        )
        logger.info(
            "image queue started: admit_interval=%.1fs max_inflight=%d max_depth=%d",
            ADMIT_INTERVAL_S, MAX_INFLIGHT, MAX_DEPTH,
        )

    async def stop(self, drain_timeout_s: float = 5.0) -> None:
        """Stop accepting work, drain briefly, then cancel."""
        if self._admitter_task is None:
            return
        self._accepting = False
        # Mark all queued jobs cancelled — they never started.
        cancelled_queued = 0
        while not self._queue.empty():
            try:
                job = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            job.state = STATE_CANCELLED
            job.error = "server_shutdown"
            job.error_type = "shutdown"
            cancelled_queued += 1
            _metric_depth.add(-1)
            _metric_jobs.add(1, {"outcome": "cancelled", "reason": "shutdown"})
        # Cancel admitter.
        self._admitter_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await self._admitter_task
        self._admitter_task = None
        # Wait briefly for in-flight tasks. Most image jobs run for minutes,
        # so we expect to cancel — drain time is intentionally short.
        if self._running_tasks:
            done, pending = await asyncio.wait(self._running_tasks, timeout=drain_timeout_s)
            for t in pending:
                t.cancel()
        wide_event(
            "image_queue.shutdown",
            outcome="ok",
            cancelled_queued=cancelled_queued,
            cancelled_running=len(self._running_tasks),
        )

    # ── Public API ─────────────────────────────────────────────────────────

    def enqueue(
        self,
        *,
        user_hash: str,
        payload: dict[str, Any],
        has_photo: bool = False,
        cache_key_prefix: str = "",
    ) -> _Job:
        """Reject if queue is full or shutting down. Returns the created job."""
        if not self._accepting:
            _metric_jobs.add(1, {"outcome": "rejected", "reason": "shutting_down"})
            raise QueueFullError(depth=0, retry_after_s=30)
        depth = self._queue.qsize()
        if depth >= MAX_DEPTH:
            wide_event(
                "image_queue.rejected_full",
                outcome="error",
                level=logging.WARNING,
                queue_depth=depth,
                in_flight=self._in_flight,
            )
            _metric_jobs.add(1, {"outcome": "rejected", "reason": "queue_full"})
            raise QueueFullError(depth=depth, retry_after_s=max(1, int(ADMIT_INTERVAL_S * 2)))

        job_id = uuid.uuid4().hex
        position = depth + 1  # 1-indexed for display
        # PRODUCER span — encloses the enqueue work and seeds trace context that
        # the consumer span will link to. SpanKind.PRODUCER + messaging.* attrs
        # follow the OpenTelemetry messaging semantic conventions.
        with _tracer.start_as_current_span(
            "image_queue.publish",
            kind=SpanKind.PRODUCER,
            attributes={
                "messaging.system": _MESSAGING_SYSTEM,
                "messaging.operation.type": "publish",
                "messaging.operation.name": "publish",
                "messaging.destination.name": _MESSAGING_DESTINATION,
                "messaging.message.id": job_id,
                "messaging.batch.message_count": 1,
                "image_queue.position": position,
                "image_queue.depth_after_publish": position,
                "image_queue.in_flight": self._in_flight,
                "image_queue.estimated_wait_s": self.estimate_wait_s(position),
                "image_queue.has_photo": has_photo,
            },
        ) as span:
            span_ctx = span.get_span_context()
            trace_hex = format(span_ctx.trace_id, "032x") if span_ctx.is_valid else ""
            job = _Job(
                job_id=job_id,
                user_hash=user_hash,
                payload=payload,
                enqueued_at=time.monotonic(),
                enqueued_wall=datetime.now(UTC),
                queue_position=position,
                enqueue_in_flight=self._in_flight,
                enqueue_depth=depth,
                has_photo=has_photo,
                cache_key_prefix=cache_key_prefix[:12],
                producer_span_context=span_ctx if span_ctx.is_valid else None,
                trace_id=trace_hex,
            )
            self._jobs[job_id] = job
            self._queue.put_nowait(job)
            _metric_depth.add(1)
            _metric_jobs.add(1, {"outcome": "enqueued"})
            self._evict_expired()
            wide_event(
                "image_job.enqueued",
                outcome="ok",
                job_id=job_id,
                trace_id=trace_hex,
                queue_depth=position,
                in_flight=self._in_flight,
                queue_position=position,
                estimated_wait_s=self.estimate_wait_s(position),
                has_photo=has_photo,
                cache_key_prefix=cache_key_prefix[:12] or None,
            )
            span.set_status(Status(StatusCode.OK))
            return job

    def status(self, job_id: str, user_hash: str) -> dict[str, Any] | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        if job.user_hash != user_hash:
            # Caller treats this the same as not-found to avoid leaking existence.
            return None
        position = self._current_position(job)
        out: dict[str, Any] = {
            "state": job.state,
            "queue_depth": self._queue.qsize(),
            "in_flight": self._in_flight,
        }
        if job.trace_id:
            out["trace_id"] = job.trace_id
        if job.state == STATE_QUEUED:
            out["queue_position"] = position
            out["estimated_wait_s"] = self.estimate_wait_s(position)
        elif job.state == STATE_RUNNING:
            out["queue_position"] = 0
            out["estimated_wait_s"] = max(
                0,
                int(RUN_P50_S - (time.monotonic() - (job.started_at or time.monotonic()))),
            )
        elif job.state == STATE_DONE:
            out["result"] = job.result
        elif job.state in (STATE_FAILED, STATE_CANCELLED):
            out["error"] = job.error
            out["error_type"] = job.error_type
            if job.retry_after:
                out["retry_after"] = job.retry_after
        return out

    def estimate_wait_s(self, position: int) -> int:
        """ETA = (position) * admit_interval + RUN_P50.

        position is 1-indexed; the front of the queue has position=1 meaning
        ~one admit interval until it starts.
        """
        return int(position * ADMIT_INTERVAL_S + RUN_P50_S)

    def stats(self) -> dict[str, Any]:
        return {
            "queue_depth": self._queue.qsize(),
            "in_flight": self._in_flight,
            "max_inflight": MAX_INFLIGHT,
            "max_depth": MAX_DEPTH,
            "admit_interval_s": ADMIT_INTERVAL_S,
            "paused_until_in_s": max(0, int(self._paused_until - time.monotonic())),
            "jobs_tracked": len(self._jobs),
        }

    def pause_admission(self, seconds: float, reason: str = "upstream_429") -> None:
        target = time.monotonic() + seconds
        if target > self._paused_until:
            self._paused_until = target
            wide_event(
                "image_queue.upstream_429",
                outcome="error",
                level=logging.WARNING,
                retry_after_s=int(seconds),
                paused_for_s=int(seconds),
                reason=reason,
            )

    # ── Internals ──────────────────────────────────────────────────────────

    def _current_position(self, job: _Job) -> int:
        """Snapshot 1-indexed position. Recomputed by walking the queue's
        internal deque — this is O(N) but N≤MAX_DEPTH (12)."""
        if job.state != STATE_QUEUED:
            return 0
        try:
            # asyncio.Queue exposes ._queue as a deque on CPython. Documented
            # nowhere as public, but stable in 3.12. Fallback returns the
            # snapshot taken at enqueue.
            for idx, q_job in enumerate(self._queue._queue, start=1):  # type: ignore[attr-defined]
                if q_job.job_id == job.job_id:
                    return idx
        except Exception:  # noqa: BLE001
            pass
        return job.queue_position

    def _evict_expired(self) -> None:
        cutoff = time.monotonic() - JOB_TTL_S
        expired = [jid for jid, j in self._jobs.items()
                   if j.state in (STATE_DONE, STATE_FAILED, STATE_CANCELLED)
                   and (j.finished_at or j.enqueued_at) < cutoff]
        for jid in expired:
            self._jobs.pop(jid, None)
        if expired:
            wide_event("image_queue.jobs_evicted", outcome="ok", count=len(expired))

    async def _admitter_loop(self) -> None:
        """Single background task. Pops one job per admit interval, throttled."""
        logger.info("image queue admitter loop started")
        try:
            while self._accepting:
                job: _Job = await self._queue.get()
                self._admitting = job
                if not self._accepting:
                    job.state = STATE_CANCELLED
                    job.error = "server_shutdown"
                    job.error_type = "shutdown"
                    self._admitting = None
                    break

                # Wait until admit cadence + global pause both allow.
                now = time.monotonic()
                wait_until = max(self._next_admit_at, self._paused_until)
                if wait_until > now:
                    sleep_s = wait_until - now
                    logger.debug("admitter sleeping %.1fs until next slot", sleep_s)
                    await asyncio.sleep(sleep_s)

                # Hard concurrency cap. May block if all slots are in flight.
                await self._sem.acquire()

                # Slot reserved; record next admit time.
                self._next_admit_at = time.monotonic() + ADMIT_INTERVAL_S

                # Dispatch in its own task so the admitter loop continues.
                task = asyncio.create_task(self._run_job(job), name=f"image-job-{job.job_id}")
                self._running_tasks.add(task)
                task.add_done_callback(self._on_job_done)
                job.task = task
                self._admitting = None
        except asyncio.CancelledError:
            logger.info("admitter cancelled")
            # The job we were about to dispatch never ran — mark it cancelled.
            if self._admitting is not None and self._admitting.state == STATE_QUEUED:
                self._admitting.state = STATE_CANCELLED
                self._admitting.error = "server_shutdown"
                self._admitting.error_type = "shutdown"
                self._admitting = None
            raise
        except Exception:  # noqa: BLE001
            logger.exception("admitter loop crashed")
            wide_event("image_queue.admitter_crashed", outcome="error", level=logging.ERROR)
            raise

    def _on_job_done(self, task: asyncio.Task) -> None:
        self._running_tasks.discard(task)
        # Surface unexpected exceptions so we don't get "Task exception was
        # never retrieved" warnings hiding real bugs.
        if not task.cancelled():
            exc = task.exception()
            if exc is not None and not isinstance(exc, asyncio.CancelledError):
                logger.exception("image job task ended with unhandled exception", exc_info=exc)

    async def _run_job(self, job: _Job) -> None:
        """Execute the worker, update state, release semaphore, emit telemetry."""
        from profile_agent.config.context import user_id_var

        user_id_var.set(job.user_hash)
        job.state = STATE_RUNNING
        job.started_at = time.monotonic()
        queue_wait_s = job.started_at - job.enqueued_at
        in_flight_after = MAX_INFLIGHT - self._sem._value  # type: ignore[attr-defined]
        self._in_flight = in_flight_after
        _metric_depth.add(-1)
        _metric_in_flight.add(1)
        _metric_queue_wait.record(queue_wait_s, {"has_photo": str(job.has_photo).lower()})

        # CONSUMER span linked to the producer span so the async hop renders
        # as a connected end-to-end transaction in App Insights.
        links = []
        if job.producer_span_context is not None:
            links.append(Link(job.producer_span_context))

        with _tracer.start_as_current_span(
            "image_queue.process",
            kind=SpanKind.CONSUMER,
            links=links,
            attributes={
                "messaging.system": _MESSAGING_SYSTEM,
                "messaging.operation.type": "process",
                "messaging.operation.name": "process",
                "messaging.destination.name": _MESSAGING_DESTINATION,
                "messaging.message.id": job.job_id,
                "image_queue.queue_wait_s": round(queue_wait_s, 3),
                "image_queue.queue_depth_at_admit": self._queue.qsize(),
                "image_queue.in_flight_after": in_flight_after,
                "image_queue.has_photo": job.has_photo,
                "image_queue.producer_trace_id": job.trace_id,
            },
        ) as span:
            wide_event(
                "image_job.admitted",
                outcome="ok",
                job_id=job.job_id,
                trace_id=job.trace_id,
                queue_wait_s=round(queue_wait_s, 2),
                queue_depth_at_admit=self._queue.qsize(),
                in_flight_after=in_flight_after,
                has_photo=job.has_photo,
            )
            try:
                assert self._worker is not None  # noqa: S101
                result = await asyncio.wait_for(self._worker(job.payload), timeout=JOB_HARD_TIMEOUT_S)
                job.finished_at = time.monotonic()
                run_s = job.finished_at - (job.started_at or job.finished_at)
                total_s = job.finished_at - job.enqueued_at
                _metric_run_duration.record(run_s, {"outcome": "ok" if result and "base64" in result else "error"})
                if result and "base64" in result:
                    job.state = STATE_DONE
                    job.result = result
                    span.set_attribute("image_queue.outcome", "completed")
                    span.set_attribute("image_queue.run_s", round(run_s, 3))
                    span.set_attribute("image_queue.total_s", round(total_s, 3))
                    span.set_status(Status(StatusCode.OK))
                    _metric_jobs.add(1, {"outcome": "completed"})
                    wide_event(
                        "image_job.completed",
                        outcome="ok",
                        job_id=job.job_id,
                        trace_id=job.trace_id,
                        queue_wait_s=round(queue_wait_s, 2),
                        run_s=round(run_s, 2),
                        total_s=round(total_s, 2),
                    )
                elif result and result.get("error") == "rate_limited":
                    ra = result.get("retry_after")
                    if isinstance(ra, (int, float)) and ra > 0:
                        self.pause_admission(float(ra), reason="upstream_429")
                        job.retry_after = int(ra)
                    job.state = STATE_FAILED
                    job.error = "rate_limited"
                    job.error_type = "rate_limited"
                    span.set_attribute("image_queue.outcome", "rate_limited")
                    span.set_attribute("image_queue.retry_after_s", job.retry_after or 0)
                    span.set_status(Status(StatusCode.ERROR, "upstream rate limited"))
                    _metric_jobs.add(1, {"outcome": "failed", "error_type": "rate_limited"})
                    wide_event(
                        "image_job.failed",
                        outcome="error",
                        level=logging.WARNING,
                        job_id=job.job_id,
                        trace_id=job.trace_id,
                        error_type="rate_limited",
                        retry_after_s=job.retry_after,
                        queue_wait_s=round(queue_wait_s, 2),
                        run_s=round(run_s, 2),
                    )
                else:
                    err_kind = (result or {}).get("error", "generation_failed") if result else "no_image"
                    job.state = STATE_FAILED
                    job.error = str(err_kind)[:500]
                    job.error_type = "generation_failed"
                    span.set_attribute("image_queue.outcome", "failed")
                    span.set_attribute("image_queue.error_type", str(err_kind)[:100])
                    span.set_status(Status(StatusCode.ERROR, str(err_kind)[:200]))
                    _metric_jobs.add(1, {"outcome": "failed", "error_type": "generation_failed"})
                    wide_event(
                        "image_job.failed",
                        outcome="error",
                        level=logging.ERROR,
                        job_id=job.job_id,
                        trace_id=job.trace_id,
                        error_type=str(err_kind)[:100],
                        queue_wait_s=round(queue_wait_s, 2),
                        run_s=round(run_s, 2),
                    )
            except TimeoutError as exc:
                job.finished_at = time.monotonic()
                job.state = STATE_FAILED
                job.error = f"image generation exceeded {JOB_HARD_TIMEOUT_S}s timeout"
                job.error_type = "TimeoutError"
                run_s = job.finished_at - (job.started_at or job.finished_at)
                _metric_run_duration.record(run_s, {"outcome": "timeout"})
                _metric_jobs.add(1, {"outcome": "failed", "error_type": "TimeoutError"})
                span.record_exception(exc)
                span.set_attribute("image_queue.outcome", "timeout")
                span.set_status(Status(StatusCode.ERROR, "worker timeout"))
                wide_event(
                    "image_job.failed",
                    outcome="error",
                    level=logging.ERROR,
                    job_id=job.job_id,
                    trace_id=job.trace_id,
                    error_type="TimeoutError",
                    run_s=round(run_s, 2),
                )
                logger.error("image job %s timed out after %ds", job.job_id, JOB_HARD_TIMEOUT_S)
            except asyncio.CancelledError:
                job.finished_at = time.monotonic()
                job.state = STATE_CANCELLED
                job.error = "cancelled"
                job.error_type = "cancelled"
                _metric_jobs.add(1, {"outcome": "cancelled"})
                span.set_attribute("image_queue.outcome", "cancelled")
                span.set_status(Status(StatusCode.ERROR, "cancelled"))
                wide_event(
                    "image_job.cancelled",
                    outcome="error",
                    level=logging.WARNING,
                    job_id=job.job_id,
                    trace_id=job.trace_id,
                    reason="task_cancelled",
                )
                raise
            except Exception as exc:  # noqa: BLE001
                job.finished_at = time.monotonic()
                job.state = STATE_FAILED
                job.error = str(exc)[:500]
                job.error_type = type(exc).__name__
                run_s = (job.finished_at or 0) - (job.started_at or 0)
                _metric_run_duration.record(run_s, {"outcome": "error"})
                _metric_jobs.add(1, {"outcome": "failed", "error_type": type(exc).__name__})
                span.record_exception(exc)
                span.set_attribute("image_queue.outcome", "failed")
                span.set_attribute("image_queue.error_type", type(exc).__name__)
                span.set_status(Status(StatusCode.ERROR, str(exc)[:200]))
                wide_event(
                    "image_job.failed",
                    outcome="error",
                    level=logging.ERROR,
                    job_id=job.job_id,
                    trace_id=job.trace_id,
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:500],
                    run_s=round(run_s, 2),
                )
                logger.exception("image job %s failed", job.job_id)
            finally:
                self._sem.release()
                self._in_flight = max(0, MAX_INFLIGHT - self._sem._value)  # type: ignore[attr-defined]
                _metric_in_flight.add(-1)


# Module-level singleton. ``maxReplicas=1`` + single uvicorn worker are
# enforced so this is the only instance per cluster.
_QUEUE: ImageQueue | None = None


def get_queue() -> ImageQueue:
    global _QUEUE
    if _QUEUE is None:
        _QUEUE = ImageQueue()
    return _QUEUE


def reset_queue_for_tests() -> None:
    """Test-only: drop the singleton so each test gets a fresh queue."""
    global _QUEUE
    _QUEUE = None
