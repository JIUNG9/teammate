"""Tests for the bundled `brain-ci.yml` GitHub Actions workflow.

We don't actually run the workflow; we parse the YAML and assert the
structure that v0.4 promised. If a future maintainer renames a job or
removes the `validate` step, these tests fail loudly.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


@pytest.fixture
def workflow_doc(repo_root: Path) -> dict:
    path = (
        repo_root
        / "templates"
        / "team-brain-skeleton"
        / ".github"
        / "workflows"
        / "brain-ci.yml"
    )
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_workflow_yaml_parses(workflow_doc: dict):
    assert isinstance(workflow_doc, dict)
    assert workflow_doc.get("name") == "Brain CI"


def test_workflow_has_required_triggers(workflow_doc: dict):
    """`on:` must include push, pull_request, and a weekly schedule."""
    # `on` becomes Python `True` when YAML loads (yes/no/on/off truthy keys);
    # accept either form.
    on = workflow_doc.get("on") or workflow_doc.get(True)
    assert on is not None
    assert "push" in on
    assert "pull_request" in on
    assert "schedule" in on
    schedule = on["schedule"]
    assert isinstance(schedule, list)
    assert any(item.get("cron") == "0 6 * * 1" for item in schedule)


def test_workflow_has_validate_job(workflow_doc: dict):
    jobs = workflow_doc["jobs"]
    assert "validate" in jobs
    job = jobs["validate"]
    steps_text = " ".join(s.get("run", "") + " " + s.get("name", "")
                          for s in job["steps"])
    assert "teammate validate" in steps_text


def test_workflow_has_pr_comment_job(workflow_doc: dict):
    jobs = workflow_doc["jobs"]
    assert "pr-comment" in jobs
    job = jobs["pr-comment"]
    assert "if" in job
    assert "pull_request" in job["if"]
    # Must have pull-requests: write permission to post a comment.
    perms = job["permissions"]
    assert perms.get("pull-requests") == "write"


def test_workflow_pr_comment_runs_adopt_dry_run(workflow_doc: dict):
    job = workflow_doc["jobs"]["pr-comment"]
    runs = " ".join(s.get("run", "") for s in job["steps"])
    assert "teammate adopt" in runs
    assert "--dry-run" in runs


def test_workflow_pr_comment_posts_with_gh_cli(workflow_doc: dict):
    job = workflow_doc["jobs"]["pr-comment"]
    runs = " ".join(s.get("run", "") for s in job["steps"])
    assert "gh pr comment" in runs
    assert "--body-file" in runs


def test_workflow_keeps_md_lint_and_link_check(workflow_doc: dict):
    """Don't break what was already working."""
    jobs = workflow_doc["jobs"]
    assert "md-lint" in jobs
    assert "link-check" in jobs


def test_workflow_build_index_uses_softprops_release(workflow_doc: dict):
    job = workflow_doc["jobs"]["build-index"]
    actions = [s.get("uses", "") for s in job["steps"]]
    assert any("softprops/action-gh-release" in a for a in actions)


def test_workflow_build_index_runs_on_schedule(workflow_doc: dict):
    job = workflow_doc["jobs"]["build-index"]
    assert "schedule" in job["if"]


def test_workflow_validate_install_includes_rag_extra(workflow_doc: dict):
    """`teammate validate` itself doesn't need [rag], but the install line
    in CI is uniform across jobs and references the rag extra. Sanity-check
    that the install command is present so a future refactor doesn't
    accidentally remove the install."""
    job = workflow_doc["jobs"]["validate"]
    runs = " ".join(s.get("run", "") for s in job["steps"])
    assert "claude-teammate" in runs
    assert "pip install" in runs


def test_workflow_top_level_permissions_present(workflow_doc: dict):
    assert workflow_doc.get("permissions", {}).get("contents") == "read"
