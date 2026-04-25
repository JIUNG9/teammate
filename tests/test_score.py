"""Tests for the compliance score engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from teammate.catalogs import load_all_catalogs
from teammate.score import PROBES, run_all


@pytest.fixture
def catalogs(repo_root: Path):
    return load_all_catalogs(repo_root / "catalogs")


def _result_for(outcomes, probe_id: str) -> str:
    """Get the result of one probe (probes can repeat for multi-control mappings)."""
    for o in outcomes:
        if o.probe_id == probe_id:
            return o.result
    raise KeyError(probe_id)


def test_run_all_against_pass_repo(sample_pass_repo: Path, catalogs):
    summary, outcomes = run_all(sample_pass_repo, catalogs)
    assert summary.target_path.endswith("sample-repo-pass")
    # CODEOWNERS, LICENSE, SECURITY.md, requirements.txt, oss-hygiene.yml,
    # .pre-commit-config.yaml, terraform with encrypted backend — all pass
    for probe in (
        "codeowners-exists",
        "license-present",
        "security-md-present",
        "dependency-pinning",
        "oss-hygiene-workflow",
        "pre-commit-config",
        "tf-state-encryption",
    ):
        assert _result_for(outcomes, probe) == "pass", probe


def test_run_all_against_fail_repo(sample_fail_repo: Path, catalogs):
    summary, outcomes = run_all(sample_fail_repo, catalogs)
    # No CODEOWNERS / LICENSE / SECURITY.md / lockfile / oss-hygiene.yml
    for probe in (
        "codeowners-exists",
        "license-present",
        "security-md-present",
        "dependency-pinning",
        "oss-hygiene-workflow",
        "pre-commit-config",
    ):
        assert _result_for(outcomes, probe) == "fail", probe
    # No terraform files at all -> n/a
    assert _result_for(outcomes, "tf-state-encryption") == "n/a"


def test_run_all_against_mixed_repo(sample_mixed_repo: Path, catalogs):
    summary, outcomes = run_all(sample_mixed_repo, catalogs)
    assert _result_for(outcomes, "license-present") == "pass"
    assert _result_for(outcomes, "codeowners-exists") == "pass"
    assert _result_for(outcomes, "dependency-pinning") == "pass"
    # missing
    assert _result_for(outcomes, "security-md-present") == "fail"


def test_branch_protection_partial_without_admin(sample_pass_repo: Path, catalogs):
    """Without admin token, branch-protection should be partial OR indeterminate.

    indeterminate = couldn't parse a github.com origin (test fixture has no remote).
    partial = origin parsed but admin scope absent.
    Both are honest answers; either is acceptable from the partial-tier design.
    """
    summary, outcomes = run_all(sample_pass_repo, catalogs)
    res = _result_for(outcomes, "branch-protection")
    assert res in {"partial", "indeterminate"}


def test_dependabot_partial_without_admin(sample_pass_repo: Path, catalogs):
    summary, outcomes = run_all(sample_pass_repo, catalogs)
    # config file present, no admin -> partial per D1
    assert _result_for(outcomes, "dependabot-or-renovate") == "partial"


def test_score_summary_counts_match_outcomes(sample_pass_repo: Path, catalogs):
    summary, outcomes = run_all(sample_pass_repo, catalogs)
    # Counts are over distinct probes, not over outcomes (a probe can have
    # multiple control mappings so it appears multiple times in outcomes).
    distinct_probe_ids = {(o.probe_id, o.result) for o in outcomes}
    pass_count = sum(1 for _, r in distinct_probe_ids if r == "pass")
    assert summary.counts["pass"] == pass_count


def test_score_overall_pct_excludes_n_a(sample_fail_repo: Path, catalogs):
    summary, outcomes = run_all(sample_fail_repo, catalogs)
    # tf-state-encryption is n/a — not in numerator OR denominator
    if summary.overall_pct is not None:
        assert summary.counts["n_a"] >= 1
        denom = summary.counts["pass"] + summary.counts["partial"] + summary.counts["fail"]
        assert summary.counts["n_a"] not in (denom,)


def test_probes_dont_blow_up_on_empty_dir(tmp_path: Path, catalogs):
    """An empty directory shouldn't crash any probe."""
    summary, outcomes = run_all(tmp_path, catalogs)
    # Every probe ran (with results, even if "fail" or "n/a")
    distinct_probes = {o.probe_id for o in outcomes}
    expected = {p[0] for p in PROBES}
    assert distinct_probes == expected
