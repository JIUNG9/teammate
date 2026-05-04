"""`teammate` CLI — entry point for the team-brain workflow.

Subcommands:

  teammate scaffold <dir>     — TEAM LEAD: create a new team-brain repo
                                 from the bundled template. One-time per org.
  teammate init               — ENGINEER: set up teammate inside an
                                 already-cloned team-brain repo.
  teammate ask "<query>"      — query the brain locally (provider + RAG).
  teammate index [--rebuild]  — rebuild / refresh the local sqlite-vec index.
  teammate stats              — show what's in the brain (file counts by section).
  teammate config show        — print the effective provider config.
  teammate config init        — write a starter `.teammate/config.toml`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from teammate import __version__
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


if __name__ == "__main__":
    main()
