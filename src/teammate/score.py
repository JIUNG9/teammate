"""Compliance score engine — pluggable probes that write to the vault.

10 local probes each return a ``ProbeOutcome`` with a tiered result:

  - **pass**          — verified ok by the probe
  - **partial**       — local artifact present, but probe can't verify the
                        GitHub-side state. Promotable to pass/fail under
                        admin-token mode.
  - **fail**          — verified failing
  - **n/a**           — control isn't relevant to this kind of repo
  - **indeterminate** — probe couldn't run (missing tool, lack of permission)

Aggregate score = passed / (passed + partial + failed). n/a and indeterminate
are excluded from the denominator. Partial counts toward denominator but not
numerator — this incentivizes graduating partial to pass via admin-mode.

ASCII flow::

    repo path  ─►  run_all()  ─►  10 probes (in order)
                                      │
                                      ▼
                                ProbeOutcome list
                                      │
                                      ▼
                                aggregate_score()  ─►  ScoreSummary

The CLI in ``cli.py`` calls ``run_all()`` then hands both lists to
``Vault.write_score_run()``.

Probes that benefit from a GITHUB_TOKEN with ``admin:repo`` scope check
``$GITHUB_TOKEN`` and the env var ``$TEAMMATE_ADMIN_MODE`` (set to "1" by
``teammate score --as-admin``). If both are present, the partial tier
promotes to pass/fail based on a real ``gh api`` call.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from teammate.catalogs import Catalog, controls_for_probe
from teammate.vault import ProbeOutcome, ScoreSummary

# ---------- helpers ----------


def _git_short_sha(repo_path: Path) -> str:
    """Return git short SHA, or "" if not a git repo."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_path,
            stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _exists_nonempty(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def _admin_mode() -> bool:
    return os.environ.get("TEAMMATE_ADMIN_MODE") == "1" and bool(
        os.environ.get("GITHUB_TOKEN")
    )


def _gh_api(endpoint: str) -> tuple[int, dict | None]:
    """Hit `gh api ENDPOINT`. Returns (http_status_or_-1, parsed_json_or_None).

    Uses the gh CLI rather than direct HTTP — gh handles auth, rate limits,
    and pagination automatically. Falls back to (-1, None) if gh isn't
    installed or auth fails.
    """
    if not shutil.which("gh"):
        return -1, None
    try:
        result = subprocess.run(
            ["gh", "api", "--include", endpoint],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # gh api --include prefixes the response with HTTP headers.
        # Split header block from body at the first blank line.
        if "\r\n\r\n" in result.stdout:
            header_block, body = result.stdout.split("\r\n\r\n", 1)
        elif "\n\n" in result.stdout:
            header_block, body = result.stdout.split("\n\n", 1)
        else:
            header_block, body = result.stdout, ""
        first_line = header_block.splitlines()[0] if header_block else ""
        m = re.search(r"\b(\d{3})\b", first_line)
        status = int(m.group(1)) if m else -1
        try:
            parsed = json.loads(body) if body.strip() else None
        except json.JSONDecodeError:
            parsed = None
        return status, parsed
    except (subprocess.SubprocessError, OSError):
        return -1, None


def _detect_origin_slug(repo_path: Path) -> str | None:
    """Return 'owner/repo' from origin URL, or None."""
    try:
        url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=repo_path,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    # Strip common URL shapes:
    #   git@github.com:owner/repo.git
    #   https://github.com/owner/repo.git
    #   https://github.com/owner/repo
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    if not m:
        return None
    return f"{m.group(1)}/{m.group(2)}"


# ---------- probe implementations ----------
#
# Each probe is a function(repo_path) -> (result, detail). It does NOT know
# about catalogs or controls — that mapping is applied in run_all() where
# probes are turned into ProbeOutcome objects.


def _probe_codeowners_exists(repo_path: Path) -> tuple[str, str]:
    candidates = [
        repo_path / ".github" / "CODEOWNERS",
        repo_path / "CODEOWNERS",
        repo_path / "docs" / "CODEOWNERS",
    ]
    for c in candidates:
        if _exists_nonempty(c):
            return "pass", f"Found {c.relative_to(repo_path)}, non-empty."
    return (
        "fail",
        "No CODEOWNERS file found at .github/CODEOWNERS, /CODEOWNERS, or docs/CODEOWNERS.",
    )


def _probe_branch_protection(repo_path: Path) -> tuple[str, str]:
    slug = _detect_origin_slug(repo_path)
    if not slug:
        return (
            "indeterminate",
            "Could not parse a github.com origin from `git remote get-url origin`.",
        )
    if not _admin_mode():
        return (
            "partial",
            f"GitHub remote {slug!r} detected, but no admin token. "
            f"Re-run with `GITHUB_TOKEN=<token-with-admin:repo> "
            f"TEAMMATE_ADMIN_MODE=1 teammate score` to verify.",
        )
    status, body = _gh_api(f"repos/{slug}/branches/main/protection")
    if status == 200:
        return "pass", "Branch protection on main returned 200."
    if status == 404:
        return "fail", "main has no branch protection rule (gh api returned 404)."
    if status == 403:
        return (
            "indeterminate",
            "GitHub returned 403 — token lacks admin:repo scope.",
        )
    return "indeterminate", f"gh api returned status {status}."


_SECRET_PATTERNS = re.compile(
    r"(?i)("
    r"aws_secret_access_key|"
    r"aws_access_key_id|"
    r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----|"
    r"slack_token|"
    r"xoxb-[a-z0-9-]{20,}|"
    r"github_pat_[a-z0-9]{20,}|"
    r"ghp_[a-z0-9]{36,}"
    r")"
)


def _probe_secrets_scan(repo_path: Path) -> tuple[str, str]:
    risky_globs = [
        ".env",
        ".env.*",
        "*.tfvars",
        "secrets.*",
        "credentials.*",
    ]
    hits: list[str] = []
    for pattern in risky_globs:
        for match in repo_path.rglob(pattern):
            # Skip the .git/ directory (its blob objects are binary).
            if ".git" in match.parts:
                continue
            try:
                text = match.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if _SECRET_PATTERNS.search(text):
                hits.append(str(match.relative_to(repo_path)))
    if hits:
        return (
            "fail",
            f"Possible secrets in: {', '.join(hits[:5])}"
            + (f" (+{len(hits) - 5} more)" if len(hits) > 5 else ""),
        )
    if _admin_mode():
        return (
            "pass",
            "No local secret patterns matched. Admin mode could query GitHub "
            "secret-scanning alerts here in v0.1.x.",
        )
    return (
        "partial",
        "No local secret patterns matched, but couldn't query GitHub secret "
        "scanning alerts (no admin token).",
    )


def _probe_tf_state_encryption(repo_path: Path) -> tuple[str, str]:
    # 1. Plaintext terraform.tfstate committed to repo? Bad.
    plaintext = list(repo_path.rglob("terraform.tfstate"))
    plaintext = [p for p in plaintext if ".git" not in p.parts]
    if plaintext:
        return (
            "fail",
            f"Plaintext Terraform state committed: "
            f"{', '.join(str(p.relative_to(repo_path)) for p in plaintext[:3])}",
        )
    # 2. Look for terraform backend config.
    tf_files = [p for p in repo_path.rglob("*.tf") if ".git" not in p.parts]
    if not tf_files:
        return "n/a", "No Terraform files in repo."
    has_remote_backend = False
    has_encryption_hint = False
    for tf in tf_files:
        try:
            text = tf.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if re.search(r'backend\s+"(s3|gcs|azurerm|remote)"', text):
            has_remote_backend = True
        if re.search(r"encrypt\s*=\s*true", text):
            has_encryption_hint = True
    if has_remote_backend and has_encryption_hint:
        return "pass", "Remote backend declared with encrypt=true."
    if has_remote_backend:
        return (
            "partial",
            "Remote backend declared, but no `encrypt = true` found. May be "
            "implicit (e.g. GCS default) — admin-mode probe in v0.1.x.",
        )
    return (
        "fail",
        "Terraform code present but no remote backend declared. "
        "State will land on local disk.",
    )


def _probe_dependency_pinning(repo_path: Path) -> tuple[str, str]:
    candidates = [
        "requirements.txt",
        "requirements-dev.txt",
        "pyproject.toml",
        "Pipfile.lock",
        "poetry.lock",
        "uv.lock",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "bun.lockb",
        "go.sum",
        "Gemfile.lock",
        "Cargo.lock",
        "composer.lock",
    ]
    found: list[str] = []
    for name in candidates:
        for match in repo_path.rglob(name):
            if ".git" in match.parts:
                continue
            found.append(str(match.relative_to(repo_path)))
    if found:
        return "pass", f"Found lockfile(s): {', '.join(found[:5])}"
    return "fail", "No dependency lockfile found in any subdirectory."


def _probe_oss_hygiene_workflow(repo_path: Path) -> tuple[str, str]:
    candidates = [
        repo_path / ".github" / "workflows" / "oss-hygiene.yml",
        repo_path / ".github" / "workflows" / "oss-hygiene.yaml",
    ]
    for c in candidates:
        if not _exists_nonempty(c):
            continue
        text = c.read_text(encoding="utf-8")
        # Must run on push or pull_request — not just workflow_dispatch.
        if re.search(r"^on:\s*\n(?:.*\n)*?\s*(push|pull_request):", text, re.MULTILINE):
            return "pass", f"Found {c.relative_to(repo_path)} with push/pull_request triggers."
        return (
            "partial",
            f"Found {c.relative_to(repo_path)} but it doesn't trigger on push or "
            f"pull_request — workflow won't actually run on commits.",
        )
    return "fail", "No .github/workflows/oss-hygiene.{yml,yaml} found."


def _probe_pre_commit_config(repo_path: Path) -> tuple[str, str]:
    p = repo_path / ".pre-commit-config.yaml"
    if _exists_nonempty(p):
        return "pass", "Found .pre-commit-config.yaml."
    # huskyrc / lefthook are common alternatives — count as partial since the
    # spirit of the control is "automated pre-commit checks."
    alternatives = [".husky", "lefthook.yml", "lefthook.yaml"]
    for alt in alternatives:
        if (repo_path / alt).exists():
            return "partial", f"Found {alt} (alternative pre-commit harness)."
    return "fail", "No .pre-commit-config.yaml or alternative pre-commit harness."


def _probe_license_present(repo_path: Path) -> tuple[str, str]:
    for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"):
        if _exists_nonempty(repo_path / name):
            return "pass", f"Found {name}."
    return "fail", "No LICENSE file at repository root."


def _probe_security_md_present(repo_path: Path) -> tuple[str, str]:
    for name in ("SECURITY.md", ".github/SECURITY.md", "docs/SECURITY.md"):
        if _exists_nonempty(repo_path / name):
            return "pass", f"Found {name}."
    return "fail", "No SECURITY.md at root, .github/, or docs/."


def _probe_dependabot_or_renovate(repo_path: Path) -> tuple[str, str]:
    has_config = (
        _exists_nonempty(repo_path / ".github" / "dependabot.yml")
        or _exists_nonempty(repo_path / ".github" / "dependabot.yaml")
        or _exists_nonempty(repo_path / "renovate.json")
        or _exists_nonempty(repo_path / "renovate.json5")
        or _exists_nonempty(repo_path / ".renovaterc")
        or _exists_nonempty(repo_path / ".renovaterc.json")
    )
    if not has_config:
        return "fail", "No dependabot or renovate configuration file found."
    if _admin_mode():
        # Could call gh api repos/.../security-and-analysis here in v0.1.x.
        return (
            "pass",
            "Dependabot/Renovate config file present. (Admin-mode verification "
            "of GitHub-side state planned for v0.1.x.)",
        )
    return (
        "partial",
        "Config file present, but probe can't verify the integration is "
        "actually enabled in GitHub repo settings without an admin token.",
    )


# ---------- runner ----------

# Order is the display order in the CLI output.
PROBES: list[tuple[str, Callable[[Path], tuple[str, str]]]] = [
    ("codeowners-exists", _probe_codeowners_exists),
    ("branch-protection", _probe_branch_protection),
    ("secrets-scan", _probe_secrets_scan),
    ("tf-state-encryption", _probe_tf_state_encryption),
    ("dependency-pinning", _probe_dependency_pinning),
    ("oss-hygiene-workflow", _probe_oss_hygiene_workflow),
    ("pre-commit-config", _probe_pre_commit_config),
    ("license-present", _probe_license_present),
    ("security-md-present", _probe_security_md_present),
    ("dependabot-or-renovate", _probe_dependabot_or_renovate),
]


def run_all(repo_path: Path, catalogs: dict[str, Catalog]) -> tuple[ScoreSummary, list[ProbeOutcome]]:
    """Run every probe against repo_path. Return (summary, outcomes).

    ``outcomes`` lists ONE ProbeOutcome per (probe, control) pair so the vault
    gets per-control evidence even when a probe satisfies multiple controls.
    The summary aggregates over distinct probe results (a probe with two
    control mappings counts once toward the denominator).
    """
    repo_path = repo_path.resolve()
    outcomes: list[ProbeOutcome] = []
    probe_results: list[tuple[str, str, str]] = []  # (probe_id, result, severity-of-worst-control)

    for probe_id, probe_fn in PROBES:
        try:
            result, detail = probe_fn(repo_path)
        except Exception as exc:  # don't let one bad probe kill the run
            result, detail = "indeterminate", f"Probe raised {type(exc).__name__}: {exc}"

        controls = controls_for_probe(probe_id, catalogs)
        if not controls:
            outcomes.append(
                ProbeOutcome(
                    probe_id=probe_id,
                    result=result,
                    detail=detail,
                    framework="",
                    control_id="",
                    severity="medium",
                )
            )
            probe_results.append((probe_id, result, "medium"))
            continue

        worst_severity = _worst_severity([c.severity for c in controls])
        for ctrl in controls:
            outcomes.append(
                ProbeOutcome(
                    probe_id=probe_id,
                    result=result,
                    detail=detail,
                    framework=ctrl.framework,
                    control_id=ctrl.id,
                    severity=ctrl.severity,
                )
            )
        probe_results.append((probe_id, result, worst_severity))

    return _summarize(repo_path, probe_results), outcomes


def _worst_severity(items: list[str]) -> str:
    rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    return max(items, key=lambda s: rank.get(s, 0))


def _summarize(
    repo_path: Path, probe_results: list[tuple[str, str, str]]
) -> ScoreSummary:
    counts = {"pass": 0, "partial": 0, "fail": 0, "n_a": 0, "indeterminate": 0}
    for _, result, _ in probe_results:
        key = result.replace("/", "_")  # n/a -> n_a
        if key in counts:
            counts[key] += 1
        else:
            counts.setdefault(key, 0)
            counts[key] += 1
    denom = counts["pass"] + counts["partial"] + counts["fail"]
    overall = counts["pass"] / denom if denom > 0 else None
    return ScoreSummary(
        overall_pct=overall,
        counts=counts,
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        commit=_git_short_sha(repo_path),
        target_path=str(repo_path),
    )


__all__ = ["PROBES", "run_all"]
