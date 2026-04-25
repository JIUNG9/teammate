---
name: init-teammate
description: Set up teammate on this repo for the first time. Scaffolds compliance-vault/, installs git pre-push hook, detects Ollama (local LLM) and gbrain (cross-machine memory), builds the initial vault index. Idempotent — re-run safely.
---

# /init-teammate

One-command day-1 setup for a new SRE joining a team.

## When to invoke

- A new engineer just cloned the repo for the first time.
- The user mentions "set up teammate", "first run", "day 1", or "I just joined".
- After a `git clone` of a repo that ships teammate as a plugin.

## Behavior

1. **Vault** — create `compliance-vault/` with the documented Obsidian layout:
   `latest.md`, `history/`, `controls/{iso-27001,k-isms-p}/`, `advisories/`,
   `attestations/`. Drop `compliance-vault/.gitignore` containing `*` so
   the vault is local-by-default. Teams who want to track compliance
   history in git remove that gitignore.

2. **Hooks** — copy `hooks/pre-push` into `.git/hooks/pre-push`. **Refuses
   if a pre-push hook already exists** unless `TEAMMATE_FORCE_INIT=1` is set
   or the user passes `--force`. The Claude Code `PreToolUse` hook is
   configured via `.claude-plugin/plugin.json` automatically.

3. **Ollama** — check if Ollama is running on `localhost:11434`. If yes,
   list pulled models and flag any missing required models. If no, print
   the install link (https://ollama.com/download) and the two pull commands
   (`ollama pull llama3.2:3b`, `ollama pull nomic-embed-text`). Does NOT
   auto-install — that needs explicit user consent.

4. **gbrain** — check if `gbrain` is on PATH. If yes, mention it and offer
   `--register-gbrain` to register the vault as a gbrain source. If no,
   note that the built-in mini-RAG will run instead.

5. **Index** — build the initial vault index from any existing
   `compliance-vault/`, the team's root `CLAUDE.md`, `docs/*.md`, and
   `README.md`. Stores in `.teammate-cache/vault.sqlite`. Re-uses Ollama
   embeddings if available, falls back to keyword scoring if not.

## Run

```bash
teammate init
# or, to overwrite an existing pre-push hook:
TEAMMATE_FORCE_INIT=1 teammate init
# or, to also register the vault with gbrain:
teammate init --register-gbrain
```

## Output

Per-step status table:

```
teammate init —
  ✓ vault: scaffolded at compliance-vault/
  ✓ hooks: installed pre-push (.claude/settings.json untouched)
  · ollama: not detected; install https://ollama.com/download then ollama pull llama3.2:3b
  · gbrain: not on PATH; built-in mini-RAG will handle queries
  ✓ index: indexed 7 files without embeddings (0 unchanged)
```

## What blocks a successful init

- An existing `.git/hooks/pre-push` (per the design's D4 decision). Resolve
  by renaming the existing hook or running with `--force`.

## What does NOT block

- Ollama not running. The CLI will fall back to keyword retrieval and
  print install hints — `init` still exits zero.
- gbrain not installed. The built-in mini-RAG replaces it.
