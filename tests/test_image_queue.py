"""Tests for the in-process image throttle/queue.

These tests use very short admit intervals via monkeypatch so the suite stays
fast while still exercising the real cadence logic.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from profile_agent.services import image_queue as iq


@pytest.fixture(autouse=True)
def _reset_queue_singleton():
    iq.reset_queue_for_tests()
    yield
    iq.reset_queue_for_tests()


@pytest.fixture
def fast_queue(monkeypatch):
    """Compress the admit interval and queue caps so tests run fast."""
    monkeypatch.setattr(iq, "ADMIT_INTERVAL_S", 0.05)
    monkeypatch.setattr(iq, "MAX_INFLIGHT", 2)
    monkeypatch.setattr(iq, "MAX_DEPTH", 4)
    monkeypatch.setattr(iq, "JOB_HARD_TIMEOUT_S", 5)
    monkeypatch.setattr(iq, "RUN_P50_S", 1)
    return iq


async def _ok_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Fast successful worker."""
    await asyncio.sleep(0.01)
    return {"base64": f"img-{payload.get('n', 0)}"}


async def _slow_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Slow worker — useful for proving the in-flight cap holds."""
    await asyncio.sleep(0.5)
    return {"base64": f"img-{payload.get('n', 0)}"}


async def _failing_worker(payload: dict[str, Any]) -> dict[str, Any]:
    raise RuntimeError("boom")


async def _ratelimited_worker(payload: dict[str, Any]) -> dict[str, Any]:
    return {"error": "rate_limited", "retry_after": 0}  # 0 so we don't actually pause


async def _wait_for_state(queue: iq.ImageQueue, job_id: str, user: str, target: str, timeout: float = 5.0):
    """Poll the queue's status until job reaches target state or we time out."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        status = queue.status(job_id, user)
        if status and status["state"] == target:
            return status
        await asyncio.sleep(0.02)
    raise AssertionError(f"job {job_id} never reached {target}; last status={queue.status(job_id, user)}")


async def test_simple_round_trip(fast_queue):
    queue = iq.get_queue()
    await queue.start(_ok_worker)
    try:
        job = queue.enqueue(user_hash="u1", payload={"n": 1})
        assert job.state == iq.STATE_QUEUED
        status = await _wait_for_state(queue, job.job_id, "u1", iq.STATE_DONE)
        assert status["result"] == {"base64": "img-1"}
    finally:
        await queue.stop()


async def test_admit_cadence_enforced(fast_queue):
    """Three jobs should start with at least ADMIT_INTERVAL_S spacing between starts."""
    starts: list[float] = []

    async def _record_start(payload: dict[str, Any]) -> dict[str, Any]:
        starts.append(asyncio.get_event_loop().time())
        await asyncio.sleep(0.01)
        return {"base64": "x"}

    queue = iq.get_queue()
    await queue.start(_record_start)
    try:
        jobs = [queue.enqueue(user_hash="u1", payload={"n": i}) for i in range(3)]
        for j in jobs:
            await _wait_for_state(queue, j.job_id, "u1", iq.STATE_DONE)
        # Spacing between admissions should be ≥ ADMIT_INTERVAL_S (allowing
        # tiny scheduling slop).
        assert len(starts) == 3
        for i in range(1, len(starts)):
            gap = starts[i] - starts[i - 1]
            assert gap >= iq.ADMIT_INTERVAL_S * 0.9, (
                f"admit gap {gap:.4f}s is below cadence {iq.ADMIT_INTERVAL_S}s"
            )
    finally:
        await queue.stop()


async def test_queue_full_rejects(fast_queue):
    """Once MAX_DEPTH is reached, enqueue raises QueueFullError with a Retry-After hint."""
    queue = iq.get_queue()
    # Don't start the admitter — we want the queue to fill up.
    queue._accepting = True  # bypass start() since we don't want a worker
    for i in range(iq.MAX_DEPTH):
        queue.enqueue(user_hash="u1", payload={"n": i})
    with pytest.raises(iq.QueueFullError) as exc:
        queue.enqueue(user_hash="u1", payload={"n": 99})
    assert exc.value.depth == iq.MAX_DEPTH
    assert exc.value.retry_after_s > 0


async def test_inflight_cap_holds(fast_queue, monkeypatch):
    """With MAX_INFLIGHT=2 and a slow worker, never more than 2 should be running concurrently."""
    in_flight_peak = 0
    in_flight_now = 0
    lock = asyncio.Lock()

    async def _tracked_worker(payload: dict[str, Any]) -> dict[str, Any]:
        nonlocal in_flight_peak, in_flight_now
        async with lock:
            in_flight_now += 1
            in_flight_peak = max(in_flight_peak, in_flight_now)
        try:
            await asyncio.sleep(0.2)
            return {"base64": "x"}
        finally:
            async with lock:
                in_flight_now -= 1

    queue = iq.get_queue()
    await queue.start(_tracked_worker)
    try:
        # 4 jobs fits within MAX_DEPTH=4. With MAX_INFLIGHT=2 we expect peak=2.
        jobs = [queue.enqueue(user_hash="u1", payload={"n": i}) for i in range(4)]
        for j in jobs:
            await _wait_for_state(queue, j.job_id, "u1", iq.STATE_DONE, timeout=10.0)
        assert in_flight_peak <= iq.MAX_INFLIGHT, (
            f"in-flight peak {in_flight_peak} exceeded cap {iq.MAX_INFLIGHT}"
        )
    finally:
        await queue.stop()


async def test_owner_check_returns_none_for_other_user(fast_queue):
    queue = iq.get_queue()
    await queue.start(_ok_worker)
    try:
        job = queue.enqueue(user_hash="alice", payload={"n": 1})
        # Different user hash → status() returns None (caller treats as 404).
        assert queue.status(job.job_id, "bob") is None
        # Owner can still see it.
        assert queue.status(job.job_id, "alice") is not None
    finally:
        await queue.stop()


async def test_failed_worker_marks_job_failed(fast_queue):
    queue = iq.get_queue()
    await queue.start(_failing_worker)
    try:
        job = queue.enqueue(user_hash="u1", payload={"n": 1})
        status = await _wait_for_state(queue, job.job_id, "u1", iq.STATE_FAILED)
        assert status["error_type"] == "RuntimeError"
        assert "boom" in status["error"]
    finally:
        await queue.stop()


async def test_ratelimited_response_marks_failed(fast_queue):
    queue = iq.get_queue()
    await queue.start(_ratelimited_worker)
    try:
        job = queue.enqueue(user_hash="u1", payload={"n": 1})
        status = await _wait_for_state(queue, job.job_id, "u1", iq.STATE_FAILED)
        assert status["error_type"] == "rate_limited"
    finally:
        await queue.stop()


async def test_shutdown_cancels_queued_jobs(fast_queue, monkeypatch):
    """Jobs sitting in the queue at shutdown time are marked cancelled."""
    # Force in-flight cap = 1 so j2 cannot start until j1 finishes.
    monkeypatch.setattr(iq, "MAX_INFLIGHT", 1)
    started_one = asyncio.Event()

    async def _gate_worker(payload: dict[str, Any]) -> dict[str, Any]:
        started_one.set()
        await asyncio.sleep(10)  # long enough to be cancelled
        return {"base64": "x"}

    queue = iq.get_queue()
    await queue.start(_gate_worker)
    j1 = queue.enqueue(user_hash="u1", payload={"n": 1})
    j2 = queue.enqueue(user_hash="u1", payload={"n": 2})
    await asyncio.wait_for(started_one.wait(), timeout=2)
    # j2 should still be queued; j1 is running.
    await queue.stop(drain_timeout_s=0.1)
    s2 = queue.status(j2.job_id, "u1")
    assert s2 is not None and s2["state"] == iq.STATE_CANCELLED
    # j1 was in-flight when stop() fired t.cancel(). Cancellation is async —
    # give the run-loop a beat to propagate, then verify it ended one way or
    # another.
    await asyncio.sleep(0.1)
    s1 = queue.status(j1.job_id, "u1")
    assert s1 is not None and s1["state"] in (iq.STATE_CANCELLED, iq.STATE_FAILED, iq.STATE_DONE)


async def test_estimate_wait_formula(fast_queue):
    queue = iq.get_queue()
    # position * admit_interval + run_p50
    assert queue.estimate_wait_s(1) == int(1 * iq.ADMIT_INTERVAL_S + iq.RUN_P50_S)
    assert queue.estimate_wait_s(5) == int(5 * iq.ADMIT_INTERVAL_S + iq.RUN_P50_S)
