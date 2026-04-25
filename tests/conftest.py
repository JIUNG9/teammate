"""Shared pytest fixtures for the teammate test suite."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_pass_repo(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample-repo-pass"


@pytest.fixture
def sample_fail_repo(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample-repo-fail"


@pytest.fixture
def sample_mixed_repo(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample-repo-mixed"


@pytest.fixture
def repo_root() -> Path:
    """Resolve the actual teammate repo root from the test file location."""
    return Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Strip teammate env vars so tests start with a known baseline."""
    for var in (
        "TEAMMATE_ADMIN_MODE",
        "TEAMMATE_FORCE_INIT",
        "TEAMMATE_OVERRIDE",
        "TEAMMATE_VAULT_NO_ATOMIC",
        "TEAMMATE_VAULT_ROOT",
        "TEAMMATE_HOOKS_DIR",
        "TEAMMATE_PROTECTED_BRANCHES",
        "GITHUB_TOKEN",
    ):
        monkeypatch.delenv(var, raising=False)
