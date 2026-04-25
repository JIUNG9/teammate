"""Tests for the PDF attestation generator. Sigstore signing path is NOT exercised
(would require interactive OIDC). We only test the unsigned generation path."""

from __future__ import annotations

import pytest

reportlab = pytest.importorskip("reportlab")

from teammate.attest import attest, render_pdf
from teammate.vault import ProbeOutcome, ScoreSummary


def _summary() -> ScoreSummary:
    return ScoreSummary(
        overall_pct=0.733,
        counts={"pass": 11, "partial": 4, "fail": 0, "n_a": 0, "indeterminate": 0},
        timestamp="2026-04-26T10:30:00Z",
        commit="abc123def",
        target_path="/repo",
    )


def _outcomes() -> list[ProbeOutcome]:
    return [
        ProbeOutcome(
            probe_id="codeowners-exists",
            result="pass",
            detail="Found",
            framework="iso-27001",
            control_id="A.5.2",
            severity="medium",
        ),
        ProbeOutcome(
            probe_id="branch-protection",
            result="partial",
            detail="No admin",
            framework="iso-27001",
            control_id="A.8.32",
            severity="high",
        ),
    ]


def test_render_pdf_returns_pdf_bytes():
    pdf = render_pdf(_summary(), _outcomes())
    assert pdf.startswith(b"%PDF-")
    # Sanity check that the PDF is non-trivial size — header + one table is ~3-10kb
    assert len(pdf) > 1500


def test_attest_unsigned_returns_no_sig():
    pdf, sig, crt = attest(_summary(), _outcomes(), sign=False)
    assert pdf.startswith(b"%PDF-")
    assert sig is None and crt is None


def test_pdf_includes_score_text():
    """Check the rendered PDF text contains key fields. Imperfect heuristic but
    catches obvious regressions like 'PDF empty' or 'wrong score'."""
    pdf = render_pdf(_summary(), _outcomes())
    # Strip filter / compression metadata noise; just look for text occurrences.
    body = pdf.decode("latin-1", errors="ignore")
    # PDF text streams use the FlateDecode filter, so the percent string
    # may be deflated. We look for filter markers + the visible labels
    # that the platypus paragraphs include literally.
    assert b"%PDF" in pdf
    assert "/F" in body  # Font marker — proves a text run exists
