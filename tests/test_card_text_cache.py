"""Smoke tests for the in-process card-text cache."""

from __future__ import annotations


def test_compute_key_is_deterministic_and_order_invariant(tmp_path, monkeypatch):
    from profile_agent.services import card_text_cache

    monkeypatch.setattr(card_text_cache, "_CACHE_DIR", tmp_path)

    base = dict(
        deployment="gpt-4o",
        identity={"name": "X", "role": "Eng", "title": "Sr", "photoStatus": "skipped"},
        completed_stages=[
            {"id": "intro", "summary": "hello"},
            {"id": "skills", "summary": "py, ts"},
        ],
        clifton_strengths=["Achiever", "Learner"],
        linkedin_skills=None,
        github_skills=None,
        bulk_extracted=None,
        style=None,
    )
    k1 = card_text_cache.compute_key(**base)

    # Reorder stages and clifton — should yield same key (we sort internally).
    base2 = dict(base)
    base2["completed_stages"] = list(reversed(base["completed_stages"]))
    base2["clifton_strengths"] = ["Learner", "Achiever"]
    k2 = card_text_cache.compute_key(**base2)
    assert k1 == k2

    # Change the role — must yield a different key.
    base3 = dict(base)
    base3["identity"] = dict(base["identity"], role="Manager")
    k3 = card_text_cache.compute_key(**base3)
    assert k1 != k3


def test_get_returns_none_on_miss_and_round_trips(tmp_path, monkeypatch):
    from profile_agent.services import card_text_cache

    monkeypatch.setattr(card_text_cache, "_CACHE_DIR", tmp_path)
    assert card_text_cache.get("nonexistent") is None

    card_text_cache.put("abc123", {"name": "Jane", "strengths": ["a", "b"]})
    got = card_text_cache.get("abc123")
    assert got == {"name": "Jane", "strengths": ["a", "b"]}


def test_put_ignores_invalid_input(tmp_path, monkeypatch):
    from profile_agent.services import card_text_cache

    monkeypatch.setattr(card_text_cache, "_CACHE_DIR", tmp_path)
    card_text_cache.put("k", {})  # empty dict
    card_text_cache.put("k", None)  # type: ignore[arg-type]
    assert card_text_cache.get("k") is None
