# Changelog

## [0.3.0] — 2026-05-04

### Added
- Provider abstraction (`teammate.providers`) — `LLMProvider` and `EmbeddingProvider` ABCs.
- Config system: `.teammate/config.toml` (per-repo) → `~/.teammate/config.toml` (per-user) → env-var overrides.
- `teammate config show` and `teammate config init` CLI subcommands.
- Index versioning — `(provider, embedding_model, dim)` stamped at index time; mismatch is a hard error with a `--rebuild` hint.
- Auto-detection of available providers in `teammate init`.
- Example configs in `examples/configs/`.

### Changed
- `rag.ask.answer()` and `rag.index.index_paths()` now take provider objects (`LLMProvider`, `EmbeddingProvider`) instead of `OllamaClient`.
- `rag.ollama` is now a deprecation shim; import from `teammate.providers` instead.

### Backward-compat
- With no config present and Ollama running, behavior is identical to v0.2.
- `from teammate.rag.ollama import OllamaClient` still works (with `DeprecationWarning`).

### Roadmap (v0.4)
- Anthropic Claude API provider.
- OpenAI / Azure OpenAI provider.
- HTTP-generic provider (e.g. internal LLM gateways at corporate-VPN-only deployments).
