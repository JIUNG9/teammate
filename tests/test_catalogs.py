"""Tests for the catalog loader + Probe-Control mapping."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from teammate.catalogs import (
    Catalog,
    Control,
    PROBE_CONTROL_MAP,
    all_referenced_controls,
    controls_for_probe,
    find_catalogs_dir,
    load_all_catalogs,
    load_catalog,
    unreferenced_controls,
)


def test_find_catalogs_dir_in_repo(repo_root: Path) -> None:
    """The shipped catalogs/ directory is discoverable from anywhere in the repo."""
    found = find_catalogs_dir(repo_root)
    assert found.is_dir()
    assert (found / "iso-27001-annex-a.yaml").exists()
    assert (found / "k-isms-p.yaml").exists()


def test_find_catalogs_dir_env_override(tmp_path: Path, monkeypatch) -> None:
    custom = tmp_path / "custom-catalogs"
    custom.mkdir()
    (custom / "fake.yaml").write_text("framework: x")
    monkeypatch.setenv("TEAMMATE_CATALOGS_DIR", str(custom))
    assert find_catalogs_dir() == custom.resolve()


def test_find_catalogs_dir_env_missing_raises(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TEAMMATE_CATALOGS_DIR", str(tmp_path / "nope"))
    with pytest.raises(FileNotFoundError):
        find_catalogs_dir()


def test_load_iso_catalog(repo_root: Path) -> None:
    cat = load_catalog(repo_root / "catalogs" / "iso-27001-annex-a.yaml")
    assert cat.framework == "iso-27001"
    assert cat.version
    assert "A.5.1" in cat.controls
    assert "A.8.32" in cat.controls
    assert all(isinstance(c, Control) for c in cat.controls.values())


def test_load_k_isms_p_catalog(repo_root: Path) -> None:
    cat = load_catalog(repo_root / "catalogs" / "k-isms-p.yaml")
    assert cat.framework == "k-isms-p"
    assert "1.1.1" in cat.controls
    assert "2.5.1" in cat.controls
    # K-ISMS-P controls cross-reference ISO 27001
    secrets_ctrl = cat.controls["2.5.1"]
    assert "A.8.24" in secrets_ctrl.iso_27001 or "A.5.10" in secrets_ctrl.iso_27001


def test_load_all_catalogs(repo_root: Path) -> None:
    catalogs = load_all_catalogs(repo_root / "catalogs")
    assert "iso-27001" in catalogs
    assert "k-isms-p" in catalogs


def test_load_catalog_missing_field(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump({"framework": "x", "controls": []}))
    with pytest.raises(ValueError, match="missing keys"):
        load_catalog(bad)


def test_load_catalog_duplicate_id(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        yaml.safe_dump(
            {
                "framework": "x",
                "version": "1",
                "updated": "2026-01-01",
                "source": "test",
                "license_note": "test",
                "controls": [
                    {"id": "1", "title": "a", "summary": "x"},
                    {"id": "1", "title": "b", "summary": "y"},
                ],
            }
        )
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_catalog(bad)


def test_probe_control_map_is_complete() -> None:
    """Every probe in score.PROBES has a mapping (or empty list)."""
    from teammate.score import PROBES

    probe_ids = {p[0] for p in PROBES}
    mapped = set(PROBE_CONTROL_MAP.keys())
    assert probe_ids == mapped, (
        f"Drift between PROBES and PROBE_CONTROL_MAP: "
        f"only-in-probes={probe_ids - mapped}, only-in-map={mapped - probe_ids}"
    )


def test_probe_control_map_resolves_against_catalogs(repo_root: Path) -> None:
    """Every (framework, control_id) referenced by the map exists in the catalogs."""
    catalogs = load_all_catalogs(repo_root / "catalogs")
    for probe_id in PROBE_CONTROL_MAP:
        ctrls = controls_for_probe(probe_id, catalogs)
        assert ctrls, f"probe {probe_id!r} resolved to no controls"


def test_controls_for_probe_unknown_returns_empty(repo_root: Path) -> None:
    catalogs = load_all_catalogs(repo_root / "catalogs")
    assert controls_for_probe("does-not-exist", catalogs) == []


def test_unreferenced_controls_present(repo_root: Path) -> None:
    """v0.1 ships 25 K-ISMS-P controls but only 10 probes — there should be unreferenced controls."""
    catalogs = load_all_catalogs(repo_root / "catalogs")
    unref = unreferenced_controls(catalogs)
    assert len(unref) >= 5, "expected several catalogued controls without a probe yet"
