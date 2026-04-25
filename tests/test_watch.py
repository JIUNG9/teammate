"""Tests for the advisory watcher. Network calls are mocked out via monkeypatch."""

from __future__ import annotations

from pathlib import Path

from teammate import watch
from teammate.watch import diff_against_state, load_state, save_state


def test_state_round_trip(tmp_path: Path):
    state = {"kisa": ["a", "b"], "nvd": ["CVE-2026-0001"]}
    save_state(tmp_path, state)
    loaded = load_state(tmp_path)
    assert loaded == state


def test_load_state_missing_file(tmp_path: Path):
    assert load_state(tmp_path) == {}


def test_load_state_corrupt_file(tmp_path: Path):
    (tmp_path / ".teammate-watch-state.json").write_text("{not json")
    assert load_state(tmp_path) == {}


def test_diff_against_state_empty_seen(tmp_path: Path):
    items = [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}]
    new, refreshed = diff_against_state(items, {}, "kisa")
    assert {n["id"] for n in new} == {"a", "b"}
    assert set(refreshed) == {"a", "b"}


def test_diff_against_state_partial_seen(tmp_path: Path):
    items = [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}, {"id": "c", "title": "C"}]
    state = {"kisa": ["a"]}
    new, refreshed = diff_against_state(items, state, "kisa")
    assert {n["id"] for n in new} == {"b", "c"}
    assert set(refreshed) == {"a", "b", "c"}


def test_diff_caps_state_at_500(tmp_path: Path):
    items = [{"id": str(i), "title": f"T{i}"} for i in range(600)]
    new, refreshed = diff_against_state(items, {}, "nvd")
    assert len(refreshed) == 500


def test_run_creates_advisory_diff_files(tmp_path: Path, monkeypatch):
    """End-to-end run with feed adapters mocked."""
    fake_kisa = [{"id": "k1", "title": "k1", "link": "x", "published": "", "summary": ""}]
    fake_nvd = [{"id": "CVE-1", "title": "CVE-1", "link": "x", "published": "", "summary": ""}]

    monkeypatch.setattr(watch, "fetch_kisa_rss", lambda *_a, **_k: fake_kisa)
    monkeypatch.setattr(watch, "fetch_nvd_recent", lambda *_a, **_k: fake_nvd)

    summary = watch.run(tmp_path)
    assert summary["kisa"]["new"] == 1
    assert summary["nvd"]["new"] == 1
    # Advisory diff file written
    advisories = list((tmp_path / "advisories").glob("*.md"))
    assert len(advisories) == 2  # one per source

    # Second run with the same fake data should produce zero new items
    summary2 = watch.run(tmp_path)
    assert summary2["kisa"]["new"] == 0
    assert summary2["nvd"]["new"] == 0
