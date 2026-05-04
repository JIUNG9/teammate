"""Configuration loader for teammate.

Precedence (highest first):

  1. Environment variables (``TEAMMATE_LLM_*`` / ``TEAMMATE_EMBEDDING_*``)
  2. Per-repo config: ``<brain_root>/.teammate/config.toml``
  3. Per-user config: ``~/.teammate/config.toml``
  4. Built-in defaults (Ollama on localhost:11434)

TOML schema::

    [llm]
    provider = "ollama"
    model    = "llama3.2:3b"
    host     = "http://localhost:11434"

    [embedding]
    provider = "ollama"
    model    = "nomic-embed-text"
    host     = "http://localhost:11434"

We use the stdlib ``tomllib`` for parsing. We hand-roll a tiny serializer for
``write_starter_config`` rather than pulling ``tomli-w`` — four keys per
section, no nested tables, doesn't justify a dependency.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from teammate.rag import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LLM_MODEL,
    DEFAULT_OLLAMA_HOST,
)

# ---------- dataclasses ----------


@dataclass(frozen=True)
class ProviderConfig:
    """A single provider's identity + transport options."""

    provider: str  # "ollama" | "anthropic" | "openai" | "http" | "none"
    model: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TeammateConfig:
    """Effective config after precedence resolution."""

    llm: ProviderConfig
    embedding: ProviderConfig
    config_source: str  # "default" | "repo" | "user" | "env" | "merged"


# ---------- defaults ----------


def _default_llm() -> ProviderConfig:
    return ProviderConfig(
        provider="ollama",
        model=DEFAULT_LLM_MODEL,
        options={"host": DEFAULT_OLLAMA_HOST},
    )


def _default_embedding() -> ProviderConfig:
    return ProviderConfig(
        provider="ollama",
        model=DEFAULT_EMBEDDING_MODEL,
        options={"host": DEFAULT_OLLAMA_HOST},
    )


# ---------- TOML reading ----------


def _read_toml(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return None


_KNOWN_TRANSPORT_KEYS = {"host", "base_url", "api_key_env", "timeout_s", "dim"}


def _provider_from_section(
    section: dict[str, Any], default: ProviderConfig
) -> ProviderConfig:
    """Fold a TOML section onto a default ProviderConfig."""
    if not section:
        return default
    provider = str(section.get("provider", default.provider))
    model = str(section.get("model", default.model))
    options: dict[str, Any] = dict(default.options)
    for key, val in section.items():
        if key in {"provider", "model"}:
            continue
        # Stash everything else as an option (host, base_url, api_key_env, ...).
        options[key] = val
    return ProviderConfig(provider=provider, model=model, options=options)


def _merge_toml(
    data: dict[str, Any], llm: ProviderConfig, embedding: ProviderConfig
) -> tuple[ProviderConfig, ProviderConfig]:
    llm_section = data.get("llm") or {}
    emb_section = data.get("embedding") or {}
    return (
        _provider_from_section(llm_section, llm),
        _provider_from_section(emb_section, embedding),
    )


# ---------- env overrides ----------


def _apply_env_overrides(
    llm: ProviderConfig, embedding: ProviderConfig
) -> tuple[ProviderConfig, ProviderConfig, bool]:
    """Apply TEAMMATE_* env vars on top of (llm, embedding). Returns (llm, emb, changed)."""
    changed = False

    def _override(cfg: ProviderConfig, prefix: str) -> tuple[ProviderConfig, bool]:
        provider = os.environ.get(f"{prefix}_PROVIDER")
        model = os.environ.get(f"{prefix}_MODEL")
        host = os.environ.get(f"{prefix}_HOST") or os.environ.get(f"{prefix}_BASE_URL")
        api_key_env = os.environ.get(f"{prefix}_API_KEY_ENV")
        if not any((provider, model, host, api_key_env)):
            return cfg, False
        new_options = dict(cfg.options)
        if host:
            new_options["host"] = host
        if api_key_env:
            new_options["api_key_env"] = api_key_env
        return (
            ProviderConfig(
                provider=provider or cfg.provider,
                model=model or cfg.model,
                options=new_options,
            ),
            True,
        )

    new_llm, c1 = _override(llm, "TEAMMATE_LLM")
    new_emb, c2 = _override(embedding, "TEAMMATE_EMBEDDING")
    changed = c1 or c2
    return new_llm, new_emb, changed


# ---------- public API ----------


def load_config(brain_root: Path) -> TeammateConfig:
    """Resolve effective config for the given brain root.

    Reads (in order, last wins):
      1. defaults
      2. ~/.teammate/config.toml
      3. <brain_root>/.teammate/config.toml
      4. env vars
    """
    llm = _default_llm()
    embedding = _default_embedding()
    source = "default"

    user_path = Path.home() / ".teammate" / "config.toml"
    repo_path = brain_root / ".teammate" / "config.toml"

    user_data = _read_toml(user_path)
    if user_data is not None:
        llm, embedding = _merge_toml(user_data, llm, embedding)
        source = "user"

    repo_data = _read_toml(repo_path)
    if repo_data is not None:
        llm, embedding = _merge_toml(repo_data, llm, embedding)
        source = "repo" if source == "default" else "merged"

    llm, embedding, env_changed = _apply_env_overrides(llm, embedding)
    if env_changed:
        source = "env" if source == "default" else "merged"

    return TeammateConfig(llm=llm, embedding=embedding, config_source=source)


# ---------- TOML writing (hand-rolled, four keys max per section) ----------


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _render_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    return f'"{_toml_escape(str(value))}"'


def _render_section(name: str, cfg: ProviderConfig) -> str:
    lines = [f"[{name}]", f'provider = "{_toml_escape(cfg.provider)}"',
             f'model = "{_toml_escape(cfg.model)}"']
    for key in ("host", "base_url", "api_key_env", "timeout_s", "dim"):
        if key in cfg.options:
            lines.append(f"{key} = {_render_value(cfg.options[key])}")
    # Surface any other options we don't know about — keep config round-trippable.
    for key, val in cfg.options.items():
        if key in _KNOWN_TRANSPORT_KEYS:
            continue
        lines.append(f"{key} = {_render_value(val)}")
    return "\n".join(lines)


def write_starter_config(
    brain_root: Path, llm: ProviderConfig, embedding: ProviderConfig
) -> Path:
    """Write a starter ``.teammate/config.toml`` under ``brain_root``.

    Returns the absolute path written. Caller decides whether to overwrite.
    """
    cfg_dir = brain_root / ".teammate"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = cfg_dir / "config.toml"
    body = (
        "# teammate config — see docs/PROVIDERS.md\n"
        "# Precedence: env vars > this file > ~/.teammate/config.toml > defaults\n"
        "\n"
        f"{_render_section('llm', llm)}\n"
        "\n"
        f"{_render_section('embedding', embedding)}\n"
    )
    cfg_path.write_text(body, encoding="utf-8")
    return cfg_path


__all__ = [
    "ProviderConfig",
    "TeammateConfig",
    "load_config",
    "write_starter_config",
]
