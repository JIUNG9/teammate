"""`teammate` CLI — entry point for the team-brain workflow.

Subcommands:

  teammate scaffold <dir>     — TEAM LEAD: create a new team-brain repo
                                 from the bundled template. One-time per org.
  teammate init               — ENGINEER: set up teammate inside an
                                 already-cloned team-brain repo.
  teammate adopt              — mid-project file migration. Walk an existing
                                 project, classify markdown, fill template
                                 gaps. ``--dry-run`` default; ``--apply`` opt-in.
  teammate validate           — read-only structural check: CLAUDE.md presence
                                 + size, link resolution, orphan files,
                                 non-canonical paths, frontmatter.
  teammate ask "<query>"      — query the brain locally (provider + RAG).
  teammate index [--rebuild]  — rebuild / refresh the local sqlite-vec index.
  teammate stats              — show what's in the brain (file counts by section).
  teammate config show        — print the effective provider config.
  teammate config init        — write a starter `.teammate/config.toml`.
  teammate doctor [--json]    — diagnostic: config source, reachability,
                                 model availability, index, proxy/CA env.
"""

from __future__ import annotations

import json as _json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

import click

from teammate import __version__
from teammate.adopt import adopt as run_adopt
from teammate.brain import Brain
from teammate.config import (
    ProviderConfig,
    TeammateConfig,
    load_config,
    write_starter_config,
)
from teammate.init import render_summary
from teammate.init import run as run_init
from teammate.init import scaffold as run_scaffold
from teammate.providers import (
    load_embedding_provider,
    load_llm_provider,
)
from teammate.rag.ask import answer
from teammate.rag.index import (
    IndexVersionMismatch,
    discover_indexable_files,
    index_paths,
)
from teammate.validate import validate as run_validate


@click.group()
@click.version_option(version=__version__, prog_name="teammate")
def main() -> None:
    """teammate — your team's brain in your team's git repo."""


# ---------- scaffold (team lead) ----------


@main.command()
@click.argument("target_dir", type=click.Path(path_type=Path))
@click.option("--team-name", default="TEAM-NAME", show_default=True,
              help="Team name to substitute into the bundled template.")
def scaffold(target_dir: Path, team_name: str) -> None:
    """Create a fresh team-brain repo in TARGET_DIR (must be empty)."""
    result = run_scaffold(target_dir, team_name=team_name)
    click.echo(result["detail"])
    if result["status"] == "failed":
        sys.exit(1)


# ---------- init (engineer) ----------


@main.command()
@click.option("--register-gbrain", is_flag=True,
              help="If gbrain is installed, register this brain as a source.")
def init(register_gbrain: bool) -> None:
    """Set up teammate in this already-cloned team-brain repo."""
    brain_root = Path.cwd()
    results = run_init(brain_root, register_gbrain=register_gbrain)
    click.echo(render_summary(results))
    if any(r["status"] == "failed" for r in results.values()):
        sys.exit(1)


# ---------- ask ----------


@main.command()
@click.argument("query", nargs=-1, required=True)
@click.option("--rebuild", is_flag=True, help="Force a full re-index before answering.")
@click.option("--top-k", "top_k", type=int, default=6, show_default=True)
def ask(query: tuple[str, ...], rebuild: bool, top_k: int) -> None:
    """Ask a question about the brain. Streams a local-LLM answer."""
    brain_root = Path.cwd()
    cache_dir = brain_root / ".teammate-cache"
    cfg = load_config(brain_root)
    embedder = load_embedding_provider(cfg.embedding)
    llm = load_llm_provider(cfg.llm)
    paths = discover_indexable_files([brain_root])
    if paths:
        try:
            index_paths(paths, cache_dir, embedder=embedder, rebuild=rebuild)
        except IndexVersionMismatch as exc:
            click.echo(f"Index version mismatch: {exc}", err=True)
            click.echo("Hint: run `teammate index --rebuild`.", err=True)
            sys.exit(2)
    full_query = " ".join(query).strip()
    db_path = cache_dir / "vault.sqlite"
    for chunk in answer(
        full_query, db_path, brain_root, embedder=embedder, llm=llm, k=top_k
    ):
        click.echo(chunk, nl=False)
    click.echo("")


# ---------- index ----------


@main.command()
@click.option("--rebuild", is_flag=True, help="Drop the existing index and rebuild from scratch.")
@click.option("--output", "output_path", type=click.Path(path_type=Path),
              help="Write the index file to a custom path (default: .teammate-cache/vault.sqlite).")
def index(rebuild: bool, output_path: Path | None) -> None:
    """Build / refresh the local sqlite-vec index of the brain."""
    brain_root = Path.cwd()
    cache_dir = brain_root / ".teammate-cache"
    if output_path:
        cache_dir = output_path.parent if output_path.suffix else output_path
        cache_dir.mkdir(parents=True, exist_ok=True)
    cfg = load_config(brain_root)
    embedder = load_embedding_provider(cfg.embedding)
    paths = discover_indexable_files([brain_root])
    if not paths:
        click.echo("No markdown found in this directory. Are you in a team-brain repo?", err=True)
        sys.exit(1)
    try:
        indexed, skipped = index_paths(
            paths, cache_dir, embedder=embedder, rebuild=rebuild
        )
    except IndexVersionMismatch as exc:
        click.echo(f"Index version mismatch: {exc}", err=True)
        click.echo("Hint: run `teammate index --rebuild`.", err=True)
        sys.exit(2)
    click.echo(f"Indexed {indexed} files ({skipped} unchanged). Cache: {cache_dir}/vault.sqlite")


# ---------- stats ----------


@main.command()
def stats() -> None:
    """Show what's in the brain (file counts by section)."""
    brain = Brain(Path.cwd())
    if not brain.exists():
        click.echo("No CLAUDE.md found here. Are you in a team-brain repo?", err=True)
        sys.exit(1)
    s = brain.stats()
    click.echo(f"Brain at {brain.root}")
    click.echo(f"  Total markdown files: {s['total']}")
    click.echo(f"    CLAUDE.md          {s['claude']}")
    click.echo(f"    skills/            {s['skills']}")
    click.echo(f"    rules/             {s['rules']}")
    click.echo(f"    docs/              {s['docs']}")
    click.echo(f"    knowledge/         {s['knowledge']}")
    click.echo(f"    other              {s['other']}")


# ---------- config ----------


def _redact(options: dict) -> dict:
    """Redact api_key-ish values for safe display."""
    out = {}
    for k, v in options.items():
        if "api_key" in k.lower() and not k.lower().endswith("_env"):
            out[k] = "***redacted***"
        else:
            out[k] = v
    return out


def _render_provider_section(name: str, cfg: ProviderConfig) -> str:
    lines = [f"[{name}]", f'  provider = "{cfg.provider}"',
             f'  model    = "{cfg.model}"']
    for k, v in _redact(cfg.options).items():
        lines.append(f"  {k} = {v!r}")
    return "\n".join(lines)


@main.group()
def config() -> None:
    """Inspect and manage provider configuration."""


@config.command("show")
def config_show() -> None:
    """Print the effective provider config (env > repo > user > defaults)."""
    brain_root = Path.cwd()
    cfg: TeammateConfig = load_config(brain_root)
    click.echo(f"# config_source: {cfg.config_source}")
    click.echo(_render_provider_section("llm", cfg.llm))
    click.echo("")
    click.echo(_render_provider_section("embedding", cfg.embedding))


@config.command("init")
@click.option(
    "--provider",
    type=click.Choice(["ollama", "anthropic", "openai", "http", "none"]),
    default="ollama",
    show_default=True,
    help="Which provider to scaffold the starter config for.",
)
@click.option("--force", is_flag=True, help="Overwrite an existing config.toml.")
def config_init(provider: str, force: bool) -> None:
    """Write a starter ``.teammate/config.toml`` for the given provider."""
    brain_root = Path.cwd()
    target = brain_root / ".teammate" / "config.toml"
    if target.exists() and not force:
        click.echo(f"Config already exists at {target}. Use --force to overwrite.", err=True)
        sys.exit(1)

    if provider == "ollama":
        llm = ProviderConfig(
            provider="ollama",
            model="llama3.2:3b",
            options={"host": "http://localhost:11434"},
        )
        embedding = ProviderConfig(
            provider="ollama",
            model="nomic-embed-text",
            options={"host": "http://localhost:11434"},
        )
    elif provider == "none":
        llm = ProviderConfig(provider="none", model="", options={})
        embedding = ProviderConfig(provider="none", model="", options={})
    else:
        # Placeholder for v0.4 providers — write a stub so users can fill it in.
        # The provider registry will return None for these in v0.3 (keyword-only).
        llm = ProviderConfig(
            provider=provider,
            model="<set-me>",
            options={"api_key_env": f"{provider.upper()}_API_KEY"},
        )
        embedding = ProviderConfig(
            provider=provider,
            model="<set-me>",
            options={"api_key_env": f"{provider.upper()}_API_KEY"},
        )

    path = write_starter_config(brain_root, llm, embedding)
    click.echo(f"Wrote starter config to {path}")
    if provider not in {"ollama", "none"}:
        click.echo(
            f"Note: the `{provider}` provider is not yet shipped in v0.3 — "
            f"teammate will fall back to keyword-only retrieval until v0.4.",
            err=True,
        )


# ---------- adopt ----------


@main.command()
@click.option("--apply", "do_apply", is_flag=True,
              help="Actually copy template gap files. Without it, runs as a dry-run.")
@click.option("--dry-run", "force_dry_run", is_flag=True,
              help="Force dry-run mode (default). Cannot be combined with --apply.")
@click.option("--include", "includes", multiple=True,
              help="Extra paths to include (repeat for multiple). Extends defaults.")
@click.option("--exclude", "excludes", multiple=True,
              help="Extra paths to exclude (repeat for multiple). Extends defaults.")
@click.option("--max-claude-md-kb", type=int, default=4, show_default=True,
              help="CLAUDE.md size budget. Larger files trigger a split suggestion.")
@click.option("--output", "output_path", type=click.Path(path_type=Path),
              default=Path("MIGRATION-PLAN.md"), show_default=True,
              help="Where to write the human-readable plan.")
def adopt(
    do_apply: bool,
    force_dry_run: bool,
    includes: tuple[str, ...],
    excludes: tuple[str, ...],
    max_claude_md_kb: int,
    output_path: Path,
) -> None:
    """Walk this project and classify markdown into a team-brain layout.

    Default is dry-run: no files are touched. Pass ``--apply`` to copy
    template gap files into place. Existing content is never moved or
    merged automatically — move suggestions are surfaced for human action.
    """
    if do_apply and force_dry_run:
        click.echo("Cannot combine --apply with --dry-run.", err=True)
        sys.exit(1)
    brain_root = Path.cwd()
    try:
        plan = run_adopt(
            brain_root,
            dry_run=not do_apply,
            apply=do_apply,
            include=list(includes),
            exclude=list(excludes),
            max_claude_md_kb=max_claude_md_kb,
        )
    except RuntimeError as exc:
        click.echo(f"adopt: {exc}", err=True)
        sys.exit(1)
    md = plan.to_markdown()
    try:
        output_path.write_text(md, encoding="utf-8")
    except OSError as exc:
        click.echo(f"failed to write plan: {exc}", err=True)
        sys.exit(1)
    mode = "APPLY" if do_apply else "DRY-RUN"
    click.echo(f"teammate adopt — {mode} — wrote plan to {output_path}")
    click.echo(
        f"  KEEP={len(plan.by_action('KEEP'))}  ADD={len(plan.by_action('ADD'))}  "
        f"MOVE_SUGGESTED={len(plan.by_action('MOVE_SUGGESTED'))}  "
        f"REVIEW={len(plan.by_action('REVIEW'))}  "
        f"SKIP_PER_ENGINEER={len(plan.by_action('SKIP_PER_ENGINEER'))}"
    )
    if do_apply:
        click.echo(f"  MIGRATION.md written at {brain_root / 'MIGRATION.md'}")


# ---------- validate ----------


@main.command()
@click.option("--json", "as_json", is_flag=True,
              help="Emit a machine-readable JSON report (no ANSI).")
@click.option("--max-claude-md-kb", type=int, default=4, show_default=True,
              help="Soft size budget for CLAUDE.md (WARN if exceeded).")
def validate(as_json: bool, max_claude_md_kb: int) -> None:
    """Read-only structural check of the brain.

    Exit codes: 0 on all-PASS, 1 on any FAIL, 2 on only-WARN.
    """
    brain_root = Path(os.environ.get("TEAMMATE_BRAIN_ROOT") or Path.cwd())
    report = run_validate(brain_root, max_claude_md_kb=max_claude_md_kb)
    if as_json:
        click.echo(report.to_json())
    else:
        from rich.console import Console
        from rich.text import Text

        console = Console()
        console.print(f"[bold]teammate validate v{__version__}[/bold]\n")
        style = {"PASS": "green", "WARN": "yellow", "FAIL": "red"}
        for c in report.checks:
            tag = Text(f"[{c.status}]", style=style.get(c.status, "white"))
            line = Text.assemble(
                tag, " ", Text(f"{c.name:<30}", style="bold"), Text(c.summary)
            )
            console.print(line)
        if report.overall == "PASS":
            console.print("\n[bold green]OK[/bold green]")
        elif report.overall == "WARN":
            console.print(
                "\n[bold yellow]WARN[/bold yellow] — verify these are intentional."
            )
        else:
            console.print(
                "\n[bold red]FAIL[/bold red] — at least one critical check failed."
            )
    sys.exit(report.exit_code)


# ---------- doctor ----------


# Statuses, ordered by severity. The aggregate exit code is driven by the
# worst status seen across all checks.
_PASS = "PASS"
_WARN = "WARN"
_FAIL = "FAIL"

# user:pass@host shape inside an http(s) URL. Captures the scheme so we can
# preserve it; everything between scheme and `@` is the credential pair.
_PROXY_CREDS_RE = re.compile(r"(https?://)[^:/@]+:[^@]+@")


def _redact_proxy_url(value: str) -> str:
    """Strip ``user:pass`` from any http(s) URL embedded in ``value``.

    Applied to ``HTTPS_PROXY`` / ``HTTP_PROXY`` / ``NO_PROXY``. ``NO_PROXY``
    won't carry creds in practice, but uniform handling is cheaper than
    asymmetry — and the regex is a no-op on credential-free strings.
    """
    if not value:
        return value
    return _PROXY_CREDS_RE.sub(r"\1***:***@", value)


def _check_result(
    name: str, status: str, summary: str, **details: Any
) -> dict[str, Any]:
    return {"name": name, "status": status, "summary": summary, "details": details}


def _safe_check(name: str, fn) -> dict[str, Any]:
    """Run a check function, converting any uncaught exception into a FAIL.

    Each check is responsible for returning a dict with ``status`` /
    ``summary`` / ``details``. If it raises, we still produce a structured
    record so JSON output stays well-formed.
    """
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 — diagnostic surface, never raise
        return _check_result(name, _FAIL, f"check raised: {exc.__class__.__name__}: {exc}")


def _check_config(brain_root: Path) -> dict[str, Any]:
    cfg = load_config(brain_root)
    return _check_result(
        "config",
        _PASS,
        f"source={cfg.config_source}  llm={cfg.llm.provider}:{cfg.llm.model}  "
        f"embedding={cfg.embedding.provider}:{cfg.embedding.model}",
        config_source=cfg.config_source,
        llm_provider=cfg.llm.provider,
        llm_model=cfg.llm.model,
        embedding_provider=cfg.embedding.provider,
        embedding_model=cfg.embedding.model,
    )


def _check_brain(brain_root: Path) -> dict[str, Any]:
    brain = Brain(brain_root)
    if brain.exists():
        return _check_result(
            "brain", _PASS, f"CLAUDE.md present at {brain_root}",
            brain_root=str(brain_root),
        )
    return _check_result(
        "brain",
        _WARN,
        f"no CLAUDE.md at {brain_root} (running outside a brain repo?)",
        brain_root=str(brain_root),
    )


def _measure_reachability(provider) -> tuple[bool, float | None, str]:
    """Run ``is_up()`` with a wall-clock timer. Returns (up, latency_ms, host)."""
    host = getattr(provider, "host", "") or ""
    start = time.perf_counter()
    up = provider.is_up()
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return bool(up), elapsed_ms, host


def _check_provider_reachable(label: str, provider) -> dict[str, Any]:
    if provider is None:
        return _check_result(
            label, _WARN, "provider disabled (none) — fallback to keyword search",
            host=None, latency_ms=None,
        )
    up, latency_ms, host = _measure_reachability(provider)
    status = _PASS if up else _FAIL
    summary = (
        f"{host}  {latency_ms:.0f} ms" if up else f"{host}  unreachable ({latency_ms:.0f} ms)"
    )
    return _check_result(
        label, status, summary,
        host=host, latency_ms=round(latency_ms, 1) if latency_ms is not None else None,
        up=up,
    )


def _check_models(cfg: TeammateConfig, llm, embedder) -> dict[str, Any]:
    """Only meaningful for Ollama (the one provider with `list_models`).

    The ABCs don't define `list_models` — we duck-check it. For non-Ollama
    providers (none, or future v0.4 backends) we return WARN with a note.
    """
    candidates = [p for p in (llm, embedder) if p is not None]
    ollama_like = [p for p in candidates if hasattr(p, "list_models")]
    if not ollama_like:
        return _check_result(
            "models", _WARN,
            "skipped — neither provider exposes list_models()",
            available=None, missing=None,
        )
    # All Ollama-like providers in v0.3 share a host; query whichever we have.
    probe = ollama_like[0]
    try:
        available = probe.list_models()
    except Exception as exc:  # noqa: BLE001
        return _check_result(
            "models", _WARN,
            f"could not list models from {getattr(probe, 'host', '?')}: {exc}",
            available=None, missing=None,
        )
    wanted = {cfg.llm.model, cfg.embedding.model} - {""}
    missing = sorted(w for w in wanted if w and w not in available)
    if not missing:
        return _check_result(
            "models", _PASS,
            f"{', '.join(sorted(wanted))} all pulled",
            available=available, missing=[],
        )
    return _check_result(
        "models", _WARN,
        f"missing on the mirror: {', '.join(missing)} — pull them on the host",
        available=available, missing=missing,
    )


def _check_index(brain_root: Path, cfg: TeammateConfig, embedder) -> dict[str, Any]:
    """Read ``index_meta`` directly. Don't use ``open_index(embedder=...)`` —
    that would *raise* ``IndexVersionMismatch`` and abort the report. We
    want the mismatch as a soft WARN here, not a fatal exception.
    """
    db_path = brain_root / ".teammate-cache" / "vault.sqlite"
    if not db_path.exists():
        return _check_result(
            "index", _WARN,
            "no index yet — run `teammate index` to build it",
            db_path=str(db_path), exists=False,
        )
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            meta = dict(conn.execute("SELECT key, value FROM index_meta").fetchall())
            try:
                chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            except sqlite3.OperationalError:
                chunk_count = 0
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        return _check_result(
            "index", _FAIL, f"corrupt sqlite at {db_path}: {exc}",
            db_path=str(db_path),
        )

    stored_provider = meta.get("provider", "")
    stored_model = meta.get("embedding_model", "")
    stored_dim = meta.get("embedding_dim", "")
    stored_version = meta.get("teammate_version", "")
    stored_created = meta.get("created_at", "")

    # Compare against the configured embedder if present.
    if embedder is not None:
        cfg_model = embedder.model_id
        cfg_dim = str(embedder.dim)
        if (stored_model, stored_dim) != (cfg_model, cfg_dim):
            return _check_result(
                "index", _WARN,
                f"stamp mismatch: stored=({stored_model}, {stored_dim}d) "
                f"current=({cfg_model}, {cfg_dim}d) — run `teammate index --rebuild`",
                provider=stored_provider, model=stored_model, dim=stored_dim,
                chunks=chunk_count, teammate_version=stored_version,
                created_at=stored_created,
            )

    return _check_result(
        "index", _PASS,
        f"provider={stored_provider} model={stored_model} dim={stored_dim} "
        f"chunks={chunk_count}",
        provider=stored_provider, model=stored_model, dim=stored_dim,
        chunks=chunk_count, teammate_version=stored_version,
        created_at=stored_created,
    )


_PROXY_ENV_VARS = (
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "NO_PROXY",
    "SSL_CERT_FILE",
    "REQUESTS_CA_BUNDLE",
    "HTTPX_VERIFY",
)


def _check_proxy_env() -> dict[str, Any]:
    """Print effective proxy/CA env. Redact creds. Always PASS — informational.

    Reads both upper and lower-case forms (httpx accepts either); the
    upper-case wins by convention.
    """
    seen: dict[str, str] = {}
    for var in _PROXY_ENV_VARS:
        raw = os.environ.get(var) or os.environ.get(var.lower())
        if raw:
            seen[var] = _redact_proxy_url(raw) if "PROXY" in var else raw
    if not seen:
        return _check_result(
            "proxy", _PASS, "no proxy / CA env detected",
            env={},
        )
    pieces = [f"{k}={v}" for k, v in seen.items()]
    return _check_result(
        "proxy", _PASS, "  ".join(pieces),
        env=seen,
    )


def _check_runtime() -> dict[str, Any]:
    py = ".".join(str(x) for x in sys.version_info[:3])
    return _check_result(
        "runtime", _PASS,
        f"python={py}  teammate={__version__}",
        python=py, teammate=__version__,
    )


def _aggregate_exit_code(checks: list[dict[str, Any]]) -> int:
    statuses = {c["status"] for c in checks}
    if _FAIL in statuses:
        return 1
    if _WARN in statuses:
        return 2
    return 0


def _render_report(checks: list[dict[str, Any]]) -> None:
    """Pretty-print to stdout via rich, one row per check. No JSON here."""
    from rich.console import Console
    from rich.text import Text

    console = Console()
    console.print(f"[bold]teammate doctor v{__version__}[/bold]\n")
    style = {_PASS: "green", _WARN: "yellow", _FAIL: "red"}
    for c in checks:
        tag = Text(f"[{c['status']}]", style=style.get(c["status"], "white"))
        line = Text.assemble(tag, " ", Text(f"{c['name']:<22}", style="bold"),
                             Text(c["summary"]))
        console.print(line)
    overall = _aggregate_exit_code(checks)
    if overall == 0:
        console.print("\n[bold green]OK[/bold green]")
    elif overall == 2:
        console.print("\n[bold yellow]WARN[/bold yellow] — verify these are intentional.")
    else:
        console.print("\n[bold red]FAIL[/bold red] — at least one critical check failed.")


def _build_report(brain_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run all checks, return (ordered_results, aggregate_dict)."""
    checks: list[dict[str, Any]] = []
    # Load config once — every other check depends on it.
    cfg_check = _safe_check("config", lambda: _check_config(brain_root))
    checks.append(cfg_check)
    try:
        cfg = load_config(brain_root)
    except Exception:  # noqa: BLE001
        cfg = None  # type: ignore[assignment]

    checks.append(_safe_check("brain", lambda: _check_brain(brain_root)))

    llm = embedder = None
    if cfg is not None:
        try:
            llm = load_llm_provider(cfg.llm)
        except Exception:  # noqa: BLE001
            llm = None
        try:
            embedder = load_embedding_provider(cfg.embedding)
        except Exception:  # noqa: BLE001
            embedder = None

    checks.append(_safe_check(
        "llm.reachable", lambda: _check_provider_reachable("llm.reachable", llm),
    ))
    checks.append(_safe_check(
        "embedding.reachable",
        lambda: _check_provider_reachable("embedding.reachable", embedder),
    ))
    if cfg is not None:
        checks.append(_safe_check(
            "models", lambda: _check_models(cfg, llm, embedder),
        ))
        checks.append(_safe_check(
            "index", lambda: _check_index(brain_root, cfg, embedder),
        ))
    checks.append(_safe_check("proxy", _check_proxy_env))
    checks.append(_safe_check("runtime", _check_runtime))

    aggregate = {
        "version": __version__,
        "brain_root": str(brain_root),
        "exit_code": _aggregate_exit_code(checks),
        "checks": checks,
    }
    return checks, aggregate


@main.command()
@click.option("--json", "as_json", is_flag=True,
              help="Emit a machine-readable JSON report (no ANSI).")
def doctor(as_json: bool) -> None:
    """Diagnostic — config, reachability, models, index, proxy/CA env.

    Returns exit 0 (all PASS), 1 (any FAIL), or 2 (only WARNs).
    """
    brain_root = Path(os.environ.get("TEAMMATE_BRAIN_ROOT") or Path.cwd())
    checks, aggregate = _build_report(brain_root)
    if as_json:
        # Pure JSON — no rich, no ANSI. The smoke test pipes us into
        # `python -m json.tool`, which fails on stray escape sequences.
        click.echo(_json.dumps(aggregate, indent=2, sort_keys=True, default=str))
    else:
        _render_report(checks)
    sys.exit(_aggregate_exit_code(checks))


if __name__ == "__main__":
    main()
