"""End-to-end API test: drives through all interview stages and generates a card.

Usage: uv run python scripts/test_e2e_flow.py [--port 8001]
"""
from __future__ import annotations

import argparse
import json
import sys

import httpx

BASE = "http://localhost:{port}"


def parse_sse_events(text: str) -> list[dict]:
    """Parse SSE text into a list of event dicts."""
    events = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("data: ") and line != "data: [DONE]":
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


def extract_text(events: list[dict]) -> str:
    """Extract concatenated text from SSE events."""
    return "".join(e.get("delta", "") for e in events if e.get("type") == "text-delta")


def send_message(client: httpx.Client, session_id: str, text: str, label: str = "") -> tuple[str, list[dict]]:
    """Send a chat message and return (response_text, all_events)."""
    payload = {
        "messages": [{"role": "user", "content": text}],
    }
    r = client.post(
        f"/api/sessions/{session_id}/chat",
        json=payload,
        timeout=120.0,
    )
    if r.status_code != 200:
        print(f"  ERROR [{label}]: HTTP {r.status_code} — {r.text[:200]}")
        return "", []

    events = parse_sse_events(r.text)
    response_text = extract_text(events)

    # Check for card data in every response
    card_events = [e for e in events if e.get("type") == "data-cardData"]
    card_marker = " [CARD DATA!]" if card_events else ""

    print(f"  [{label}] ({len(response_text)} chars){card_marker}: {response_text[:120]}...")
    return response_text, events


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    base = BASE.format(port=args.port)
    client = httpx.Client(base_url=base)

    # Health check
    r = client.get("/health")
    assert r.status_code == 200, f"Health check failed: {r.status_code}"
    print("Server healthy\n")

    # Create session
    r = client.post("/api/sessions")
    assert r.status_code == 200, f"Create session failed: {r.status_code} — {r.text}"
    session_id = r.json()["session_id"]
    print(f"Session created: {session_id}\n")

    # Track card data across all steps
    all_card_data: list[dict] = []

    def step(text: str, label: str) -> tuple[str, list[dict]]:
        resp, events = send_message(client, session_id, text, label)
        for e in events:
            if e.get("type") == "data-cardData":
                all_card_data.append(e.get("data", {}))
        return resp, events

    # ─── Introduction ───
    print("=== INTRODUCTION ===")
    step("Hi, my name is Alex Chen. I'm a Senior Cloud Solutions Architect at Microsoft, specializing in Azure infrastructure and AI integration. Skip photo.", "intro")

    # ─── Stage progression (intro auto-advances, so "next stage" skips one ahead) ───
    stages = [
        ("heroes", [
            "I really admire Satya Nadella for transforming Microsoft's culture, "
            "Kelsey Hightower for making Kubernetes accessible, and Werner Vogels "
            "for his relentless customer focus at AWS."
        ]),
        ("influences", [
            "'Designing Data-Intensive Applications' by Martin Kleppmann "
            "changed how I think about distributed systems. 12-Factor App "
            "methodology and Domain-Driven Design by Eric Evans are constant references. "
            "Design Thinking — starting with user needs before jumping to solutions."
        ]),
        ("proud_projects", [
            "I designed a multi-region event-driven architecture on Azure that "
            "processes 2M events/sec using Event Hubs, Azure Functions, and Cosmos DB "
            "with custom partitioning. Cut latency 70%, saved $400K/yr."
        ]),
        ("shower_thoughts", [
            "AI agents will fundamentally change software architecture — from "
            "request-response to autonomous task completion. The ethics of AI "
            "decision-making in critical systems. 'AI-native' design patterns "
            "like cloud-native patterns."
        ]),
        ("hobby_projects", [
            "Home automation with Raspberry Pi and Azure IoT Hub. Contributing to "
            "an open-source Kubernetes operator for auto-scaling AI workloads. "
            "Built a RAG chatbot for a community library."
        ]),
        ("aspirations", [
            "Chief Architect role shaping technical strategy. Building AI governance "
            "frameworks. Mentoring the next generation of cloud architects. "
            "Becoming a compelling public speaker at major conferences."
        ]),
        ("collaboration", [
            "I bridge business stakeholders and engineering teams. Lead architecture "
            "review boards. My superpower is translating complex tech into business "
            "value. Mentor 3 junior architects and run monthly tech talks."
        ]),
    ]

    for stage_name, messages in stages:
        print(f"\n=== {stage_name.upper()} ===")
        step("next stage", f"skip→{stage_name}")
        for i, msg in enumerate(messages):
            step(msg, f"{stage_name}-{i}")

    # ─── Validation (synthesis runs automatically) ───
    print("\n=== VALIDATION ===")
    step("next stage", "skip→validation")
    resp, events = step("Looks great! Everything looks accurate. Let's generate the card!", "validation-confirm")

    # ─── Card Generation ───
    print("\n=== CARD GENERATION ===")
    step("next stage", "skip→card_gen")
    resp, events = step("Generate my card!", "card-gen-trigger")

    # ─── Results ───
    print(f"\n{'='*60}")
    print(f"Card data events found: {len(all_card_data)}")
    if all_card_data:
        print("SUCCESS: Card data was generated!")
        print(f"\nCard data:\n{json.dumps(all_card_data[0], indent=2)}")
    else:
        print("FAILED: No card data generated in any response")
        print("Check server logs for errors")

    client.close()
    return 0 if all_card_data else 1


if __name__ == "__main__":
    sys.exit(main())
