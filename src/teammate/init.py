"""`teammate init` — wire everything together for a new SRE on day 1.

Idempotent. Run as many times as you want. Safe defaults:

  1. Scaffold ``compliance-vault/`` with the documented Obsidian layout.
  2. Drop ``compliance-vault/.gitignore`` (default: don't track in git).
  3. Copy bundled hooks into ``.git/hooks/`` IF the repo has no existing
     pre-push hook. Refuses by default to avoid clobbering team setups.
     Override: ``TEAMMATE_FORCE_INIT=1 teammate init``.
  4. Detect Ollama. If running, mention which models are pulled.
     If not running, print install hint (link only, no auto-install).
  5. Detect gbrain. If on PATH, offer registration (interactive yes/no
     unless ``--yes`` was passed).
  6. Build the initial vault index from any existing ``compliance-vault/``,
     team ``CLAUDE.md``, and ``docs/`` markdown.

Returns a dict of step -> outcome ("ok"/"skipped"/"failed: <why>") so the
CLI can print a tidy summary and exit non-zero if anything blocked.
"""

from __future__ import annotations

import shutil
import textwrap
from pathlib import Path
from typing import Any

from teammate.rag import gbrain
from teammate.rag.index import discover_indexable_files, index_paths
from teammate.rag.ollama import OllamaClient
from teammate.vault import Vault

# ---------- step results ----------


def _ok(msg: str) -> dict[str, str]:
    return {"status": "ok", "detail": msg}


def _skip(msg: str) -> dict[str, str]:
    return {"status": "skipped", "detail": msg}


def _fail(msg: str) -> dict[str, str]:
    return {"status": "failed", "detail": msg}


# ---------- individual steps ----------


def step_vault(repo_root: Path) -> dict[str, str]:
    vault_path = repo_root / "compliance-vault"
    Vault(vault_path).ensure_layout()
    return _ok(f"Vault scaffolded at {vault_path.relative_to(repo_root)}/")


def step_hooks(repo_root: Path, *, force: bool = False) -> dict[str, str]:
    """Copy bundled hooks/ into .git/hooks/. Refuses to clobber by default."""
    git_dir = repo_root / ".git"
    if not git_dir.is_dir():
        return _skip("Not a git repo. Skipping hook install (run inside a git checkout).")

    hooks_src = _bundled_hooks_dir()
    if not hooks_src.is_dir():
        return _fail(f"Bundled hooks directory missing: {hooks_src}")

    hooks_dst = git_dir / "hooks"
    hooks_dst.mkdir(exist_ok=True)

    installed: list[str] = []
    for hook_name in ("pre-push",):
        src = hooks_src / hook_name
        dst = hooks_dst / hook_name
        if not src.exists():
            continue
        if dst.exists() and not force:
            return _fail(
                f"existing pre-push hook detected at {dst.relative_to(repo_root)}. "
                f"Rename it then re-run, or run `TEAMMATE_FORCE_INIT=1 teammate init` "
                f"to overwrite."
            )
        shutil.copy2(src, dst)
        dst.chmod(0o755)
        installed.append(hook_name)

    # The Claude Code PreToolUse hook is referenced from the repo root rather
    # than copied into .git/hooks/ — Claude Code reads it from the path
    # configured in .claude/settings.json. teammate ships a settings template.
    claude_settings_dir = repo_root / ".claude"
    if claude_settings_dir.exists() and (claude_settings_dir / "settings.json").exists():
        installed.append("(.claude/settings.json already exists; left untouched)")
    else:
        # Don't auto-write .claude/settings.json — the user may have global preferences.
        # Print guidance instead.
        installed.append(
            "(skipped .claude/settings.json — see docs/QUICKSTART.md for the snippet "
            "to add the PreToolUse guardrail)"
        )

    return _ok(f"Installed: {', '.join(installed)}.")


def step_ollama(*, host: str | None = None) -> dict[str, str]:
    client = OllamaClient(host=host)
    if not client.is_up():
        return _skip(
            "Ollama not detected on localhost:11434. Install: "
            "https://ollama.com/download (open-source, runs locally). "
            "After install, run `ollama serve` then `ollama pull "
            f"{client.llm_model}` and `ollama pull {client.embedding_model}`."
        )
    try:
        models = client.list_models()
    except Exception as exc:
        return _fail(f"Ollama responded but list-models failed: {exc}")
    needed = {client.llm_model, client.embedding_model}
    missing = [m for m in needed if not any(m == name or name.startswith(f"{m}:") for name in models)]
    if missing:
        cmds = " && ".join(f"ollama pull {m}" for m in missing)
        return _ok(
            f"Ollama up. Models present: {', '.join(models) or 'none'}. "
            f"Missing: {', '.join(missing)}. Pull with: {cmds}"
        )
    return _ok(f"Ollama up. Required models present: {', '.join(sorted(needed))}.")


def step_gbrain(repo_root: Path, *, register: bool = False) -> dict[str, str]:
    status = gbrain.detect()
    if not status.available:
        return _skip(status.notes)
    if not register:
        return _ok(
            f"{status.notes} Re-run `teammate init --register-gbrain` "
            f"to register the vault as a gbrain source."
        )
    vault_path = repo_root / "compliance-vault"
    ok, msg = gbrain.register_vault(vault_path)
    return _ok(msg) if ok else _fail(msg)


def step_index(repo_root: Path, *, ollama: OllamaClient | None = None) -> dict[str, str]:
    cache_dir = repo_root / ".teammate-cache"
    paths = discover_indexable_files([repo_root])
    if not paths:
        return _skip("No markdown found in compliance-vault/, docs/, or root yet.")
    indexed, skipped = index_paths(paths, cache_dir, ollama=ollama)
    embed_status = (
        "with embeddings"
        if (ollama and ollama.is_up())
        else "without embeddings (Ollama down — keyword search will work)"
    )
    return _ok(
        f"Indexed {indexed} files {embed_status} ({skipped} unchanged). "
        f"Cache: {cache_dir.relative_to(repo_root)}/vault.sqlite"
    )


# ---------- orchestration ----------


def run(
    repo_root: Path,
    *,
    force: bool = False,
    register_gbrain: bool = False,
) -> dict[str, dict[str, str]]:
    """Run the whole init flow. Returns step name -> result mapping."""
    repo_root = repo_root.resolve()
    results: dict[str, dict[str, str]] = {}

    results["vault"] = step_vault(repo_root)
    results["hooks"] = step_hooks(repo_root, force=force)
    results["ollama"] = step_ollama()
    results["gbrain"] = step_gbrain(repo_root, register=register_gbrain)
    # Build the index using whatever Ollama state we observed.
    ollama = OllamaClient()
    if ollama.is_up():
        results["index"] = step_index(repo_root, ollama=ollama)
    else:
        results["index"] = step_index(repo_root, ollama=None)

    return results


# ---------- helpers ----------


def _bundled_hooks_dir() -> Path:
    """Locate hooks/ shipped with the package.

    Resolution order:
    1. ``$TEAMMATE_HOOKS_DIR`` env var.
    2. Repo-root sibling of src/teammate (typical dev checkout).
    3. ``hooks/`` directory bundled in the wheel.
    """
    import os

    override = os.environ.get("TEAMMATE_HOOKS_DIR")
    if override:
        return Path(override).resolve()
    pkg_root = Path(__file__).resolve().parent.parent.parent
    candidate = pkg_root / "hooks"
    if candidate.is_dir():
        return candidate
    return Path(__file__).resolve().parent / "hooks"


def render_summary(results: dict[str, dict[str, str]]) -> str:
    """Produce a human-readable summary of the init results."""
    lines = ["teammate init —"]
    for step, result in results.items():
        status = result["status"]
        symbol = {"ok": "✓", "skipped": "·", "failed": "✗"}.get(status, "?")
        lines.append(f"  {symbol} {step}: {result['detail']}")
    return "\n".join(lines)


__all__ = [
    "render_summary",
    "run",
    "step_gbrain",
    "step_hooks",
    "step_index",
    "step_ollama",
    "step_vault",
]
