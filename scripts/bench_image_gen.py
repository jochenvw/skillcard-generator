"""Local image generation benchmark.

Times one or more end-to-end card image generations against the configured
Foundry image deployment. Use this to confirm whether the production 504s on
/api/regenerate are caused by genuinely slow image generation (>2 min) or by
something else upstream.

Usage:
    uv run python scripts/bench_image_gen.py            # 3 runs, no photo
    uv run python scripts/bench_image_gen.py -n 5       # 5 runs
    uv run python scripts/bench_image_gen.py --photo path/to/me.png

Auth uses DefaultAzureCredential (run `az login` first) unless
FOUNDRY_IMAGE_API_KEY is set. Requires the same env vars as the app.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import logging
import statistics
import sys
import time
from pathlib import Path

# Ensure src/ is importable when running directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from profile_agent.config.logging import configure_logging  # noqa: E402
from profile_agent.config.settings import get_settings  # noqa: E402
from profile_agent.services.stateless_interview_service import (  # noqa: E402
    _generate_card_image,
    _get_openai_client,
)

# Minimal but realistic card_data so the prompt isn't trivially short.
SAMPLE_CARD = {
    "name": "Alex Kim",
    "title": "Distributed Systems Engineer",
    "archetype": "The Architect",
    "tagline": "Quietly shipping foundations others build on.",
    "abilities": [
        {"name": "Systems Thinking", "value": 92},
        {"name": "Reliability Mindset", "value": 88},
        {"name": "Mentorship", "value": 81},
        {"name": "Pragmatism", "value": 86},
    ],
    "signature_strengths": ["Strategic", "Learner", "Achiever"],
    "color_theme": "Indigo / Slate",
}


async def _run_once(client, settings, photo_b64: str | None, idx: int) -> tuple[float, str]:
    t0 = time.perf_counter()
    result = await _generate_card_image(client, settings, SAMPLE_CARD, photo_base64=photo_b64)
    dt = time.perf_counter() - t0
    if result is None:
        outcome = "none"
    elif "base64" in result:
        outcome = f"ok_base64({len(result['base64'])} chars)"
    elif "url" in result:
        outcome = "ok_url"
    elif result.get("error"):
        outcome = f"error:{result.get('error')}"
    else:
        outcome = "unknown"
    print(f"  run {idx + 1:>2}: {dt:6.1f}s  {outcome}")
    return dt, outcome


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-n", "--runs", type=int, default=3, help="Number of generations (default 3)")
    parser.add_argument("--photo", type=Path, default=None, help="Optional reference photo (PNG/JPG)")
    parser.add_argument("--quiet", action="store_true", help="Suppress app logs (only show timings)")
    args = parser.parse_args()

    if not args.quiet:
        configure_logging(level="INFO")
    else:
        logging.basicConfig(level=logging.WARNING)

    settings = get_settings()
    photo_b64: str | None = None
    if args.photo:
        if not args.photo.exists():
            print(f"Photo not found: {args.photo}", file=sys.stderr)
            return 2
        photo_b64 = base64.b64encode(args.photo.read_bytes()).decode("ascii")
        print(f"Reference photo: {args.photo} ({len(photo_b64)} chars b64)")

    print(f"Endpoint:           {settings.foundry_project_endpoint}")
    print(f"Primary deployment: {settings.foundry_image_deployment_name}")
    print(f"Fallback deployment:{settings.foundry_image_fallback_deployment_name}")
    print(f"Runs:               {args.runs}")
    print()

    client = await _get_openai_client(settings)

    durations: list[float] = []
    outcomes: list[str] = []
    overall_start = time.perf_counter()
    for i in range(args.runs):
        try:
            dt, oc = await _run_once(client, settings, photo_b64, i)
            durations.append(dt)
            outcomes.append(oc)
        except Exception as exc:
            print(f"  run {i + 1:>2}: FAILED ({type(exc).__name__}: {exc})")
            outcomes.append(f"exception:{type(exc).__name__}")

    total = time.perf_counter() - overall_start
    print()
    print(f"Total wall time: {total:.1f}s")
    if durations:
        print(f"min/median/max:  {min(durations):.1f}s / {statistics.median(durations):.1f}s / {max(durations):.1f}s")
        if any(d > 120 for d in durations):
            print("⚠️  At least one run exceeded 120s — Container Apps default ingress timeout is 240s.")
        if any(d > 240 for d in durations):
            print("🚨 At least one run exceeded 240s — this WILL cause a 504 from Container Apps ingress.")
        else:
            print("✓ All runs completed within 240s — 504s in prod are likely NOT caused by raw image latency.")
    print(f"Outcomes: {outcomes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
