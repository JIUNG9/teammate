"""Tests for the vault writer."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from teammate.vault import ProbeOutcome, ScoreSummary, Vault


def _make_summary() -> ScoreSummary:
    return ScoreSummary(
        overall_pct=0.733,
        counts={"pass": 11, "partial": 4, "fail": 0, "n_a": 0, "indeterminate": 0},
        timestamp="2026-04-26T10:30:00Z",
        commit="abc123def",
        target_path="/repo",
    )


def _make_outcomes() -> list[ProbeOutcome]:
    return [
        ProbeOutcome(
            probe_id="codeowners-exists",
            result="pass",
            detail="Found .github/CODEOWNERS",
            framework="iso-27001",
            control_id="A.5.2",
            severity="medium",
        ),
        ProbeOutcome(
            probe_id="codeowners-exists",
            result="pass",
            detail="Found .github/CODEOWNERS",
            framework="k-isms-p",
            control_id="2.1.3",
            severity="medium",
        ),
        ProbeOutcome(
            probe_id="branch-protection",
            result="partial",
            detail="No admin token",
            framework="iso-27001",
            control_id="A.8.32",
            severity="high",
        ),
    ]


def test_ensure_layout_creates_dirs_and_gitignore(tmp_path: Path):
    Vault(tmp_path / "vault").ensure_layout()
    base = tmp_path / "vault"
    for sub in ("history", "advisories", "attestations", "controls"):
        assert (base / sub).is_dir()
    gi = (base / ".gitignore").read_text()
    assert gi.strip().endswith("*")


def test_write_score_run_produces_latest_history_and_evidence(tmp_path: Path):
    vault = Vault(tmp_path / "vault")
    history_path = vault.write_score_run(_make_summary(), _make_outcomes())
    assert history_path.exists()
    latest = (tmp_path / "vault" / "latest.md").read_text()
    assert "73.3" in latest or "0.733" in latest
    # per-control evidence written
    iso_evidence = tmp_path / "vault" / "controls" / "iso-27001" / "A.5.2.md"
    assert iso_evidence.exists()
    k_isms_evidence = tmp_path / "vault" / "controls" / "k-isms-p" / "2.1.3.md"
    assert k_isms_evidence.exists()


def test_frontmatter_is_valid_yaml(tmp_path: Path):
    vault = Vault(tmp_path / "vault")
    vault.write_score_run(_make_summary(), _make_outcomes())
    text = (tmp_path / "vault" / "latest.md").read_text()
    assert text.startswith("---\n")
    closing = text.find("\n---", 3)
    assert closing != -1
    fm = text[3:closing].strip()
    parsed = yaml.safe_load(fm)
    assert parsed["framework"] == "" or parsed["framework"] is None
    assert parsed["timestamp"] == "2026-04-26T10:30:00Z"
    assert "counts" in parsed
    assert parsed["counts"]["pass"] == 11


def test_history_files_are_append_only(tmp_path: Path):
    vault = Vault(tmp_path / "vault")
    s1 = _make_summary()
    s2 = ScoreSummary(
        overall_pct=0.8,
        counts={"pass": 12, "partial": 3, "fail": 0, "n_a": 0, "indeterminate": 0},
        timestamp="2026-04-26T11:30:00Z",
        commit="def456",
        target_path="/repo",
    )
    vault.write_score_run(s1, _make_outcomes())
    vault.write_score_run(s2, _make_outcomes())
    history_files = sorted((tmp_path / "vault" / "history").glob("*.md"))
    assert len(history_files) == 2
    # latest reflects the most recent run
    latest = (tmp_path / "vault" / "latest.md").read_text()
    assert "80.0" in latest or "0.8" in latest


def test_write_advisory_diff(tmp_path: Path):
    vault = Vault(tmp_path / "vault")
    items = [
        {"id": "1", "title": "First", "link": "http://example.com/1", "published": "2026-04-26", "summary": "..."},
        {"id": "2", "title": "Second", "link": "http://example.com/2", "published": "2026-04-26", "summary": "..."},
    ]
    path = vault.write_advisory_diff(source="kisa", new_items=items, timestamp="2026-04-26T10:30:00Z")
    assert path.exists()
    body = path.read_text()
    assert "First" in body and "Second" in body


def test_write_attestation_unsigned(tmp_path: Path):
    vault = Vault(tmp_path / "vault")
    pdf = b"%PDF-1.4 (test fixture)"
    path = vault.write_attestation(pdf, None, None, _make_summary())
    assert path.exists() and path.read_bytes() == pdf
    # No .sig / .crt
    assert not path.with_suffix(".pdf.sig").exists()


def test_iter_evidence(tmp_path: Path):
    vault = Vault(tmp_path / "vault")
    vault.write_score_run(_make_summary(), _make_outcomes())
    items = list(vault.iter_evidence(framework="iso-27001"))
    assert any("A.5.2" in str(p) for p, _ in items)
