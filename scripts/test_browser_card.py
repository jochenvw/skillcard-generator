"""Playwright browser test: drives interview and screenshots the SkillCard.

Usage: uv run python scripts/test_browser_card.py [--port 8001] [--headed]
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, Page


def wait_for_response(page: Page, timeout: int = 30000):
    """Wait until the loading spinner is gone (chat no longer streaming)."""
    # Wait for any loading indicator to disappear
    page.wait_for_timeout(1000)  # Brief pause for stream to start
    # Wait for the submit button to be enabled again (not streaming)
    try:
        page.wait_for_function(
            """() => {
                const btn = document.querySelector('button[type="submit"]');
                return btn && !btn.disabled;
            }""",
            timeout=timeout,
        )
    except Exception:
        pass
    page.wait_for_timeout(500)


def send_chat(page: Page, text: str, label: str = "", timeout: int = 60000):
    """Type a message and wait for the response."""
    print(f"  Sending [{label}]: {text[:80]}...")
    textarea = page.locator("textarea")
    textarea.fill(text)
    page.keyboard.press("Enter")
    wait_for_response(page, timeout=timeout)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    url = f"http://localhost:{args.port}"
    screenshots_dir = Path("screenshots")
    screenshots_dir.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        print(f"Opening {url}...")
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(2000)
        page.screenshot(path=str(screenshots_dir / "01_loaded.png"))
        print("  Page loaded")

        # Introduction
        print("\n=== INTRODUCTION ===")
        send_chat(page,
            "Hi, my name is Alex Chen. I'm a Senior Cloud Solutions Architect "
            "specializing in Azure infrastructure and AI integration. Skip photo.",
            "intro"
        )
        page.screenshot(path=str(screenshots_dir / "02_intro.png"))

        # Fast-track through interview stages
        stages_content = [
            ("heroes", "I admire Satya Nadella for transforming Microsoft's culture, "
             "Kelsey Hightower for making Kubernetes accessible, and Werner Vogels "
             "for customer focus at AWS."),
            ("influences", "'Designing Data-Intensive Applications' by Martin Kleppmann "
             "changed how I think about distributed systems. 12-Factor App and "
             "Domain-Driven Design are constant references. Design Thinking too."),
            ("proud_projects", "Designed a multi-region event-driven architecture on Azure "
             "processing 2M events/sec with Event Hubs, Azure Functions, and Cosmos DB. "
             "Cut latency 70%, saved $400K/yr."),
            ("shower_thoughts", "AI agents will change software architecture from "
             "request-response to autonomous task completion. AI ethics in critical "
             "systems. AI-native design patterns."),
            ("hobby_projects", "Home automation with Raspberry Pi and Azure IoT Hub. "
             "Open-source K8s operator for AI workloads. RAG chatbot for a library."),
            ("aspirations", "Chief Architect role shaping technical strategy. AI governance "
             "frameworks. Mentoring next-gen cloud architects. Public speaking."),
            ("collaboration", "Bridge business and engineering teams. Lead architecture "
             "reviews. Translate complex tech into business value. Mentor 3 architects."),
        ]

        for stage_name, content in stages_content:
            print(f"\n=== {stage_name.upper()} ===")
            send_chat(page, "next stage", f"skip→{stage_name}")
            send_chat(page, content, stage_name)

        # Validation + card generation (stages flow: validation-confirm triggers card gen)
        print("\n=== VALIDATION → CARD GENERATION ===")
        send_chat(page, "next stage", "skip→validation")
        send_chat(page, "Looks perfect! Generate my card!", "trigger-card", timeout=120000)
        page.screenshot(path=str(screenshots_dir / "03_card_generating.png"))

        # Wait for the SkillCard component to appear
        print("\n=== WAITING FOR SKILL CARD ===")
        try:
            # The SkillCard has "Skill Deck" text in it
            page.wait_for_selector("text=Skill Deck", timeout=15000)
            print("  SkillCard rendered!")
            page.wait_for_timeout(1000)  # Let animations settle
        except Exception as e:
            print(f"  SkillCard not found: {e}")
            # Try scrolling down
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)

        # Take final screenshot
        page.screenshot(path=str(screenshots_dir / "04_card_final.png"), full_page=True)
        print(f"\n  Screenshots saved to {screenshots_dir}/")

        # Try to screenshot just the card
        card = page.locator("text=Skill Deck").first
        if card.is_visible():
            # Find the card container (parent with the border/frame)
            card_container = page.locator('[class*="border-cyan"]').first
            if card_container.is_visible():
                card_container.screenshot(path=str(screenshots_dir / "05_card_only.png"))
                print("  Card-only screenshot saved!")

        print("\n=== TEST COMPLETE ===")
        browser.close()


if __name__ == "__main__":
    main()
