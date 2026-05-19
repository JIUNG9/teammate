# Vigil local sync agent

A 30-line shell script that keeps the team brain repo cloned and current on every engineer's laptop, so their existing Claude Code session can read it directly — no API call, no auth, no service to be up.

This is the simplest part of Vigil. It exists because:
- Engineers already have Claude Code open during incidents.
- Asking the team brain a question should not require leaving Claude Code.
- The brain is just a git repo of markdown — Claude Code can read files natively.
- A server that proxies the brain through a chat UI adds latency and a dependency.

## What's here

| File | Role |
|---|---|
| `vigil-sync.sh` | The actual sync script. Clones on first run, `git fetch + reset --hard` on subsequent runs. Lock-protected against concurrent invocations. |
| `vigil-setup.sh` | Bootstrap installer. Wires `vigil-sync` into `~/.local/bin/`, hooks into `~/.claude/hooks/SessionStart`, appends a brain pointer to `~/.claude/CLAUDE.md`. |
| `README.md` | This file. |

## Install (one-time, per laptop)

```bash
# Set your team brain repo URL (only needed for the first sync):
export VIGIL_BRAIN_REMOTE=git@github.com:<your-org>/<your-brain-repo>.git

# Bootstrap:
curl -fsSL https://raw.githubusercontent.com/JIUNG9/vigil/main/clients/local-agent/vigil-setup.sh | bash
```

After this:

- `~/.vigil/brain/` is a fresh clone of the brain.
- Every Claude Code session start triggers a non-blocking sync (see `~/.claude/hooks/SessionStart`).
- `~/.claude/CLAUDE.md` has a section telling Claude where the brain is and how to read it.

## Cron-based sync (optional, in addition to SessionStart)

```cron
0 * * * *  $HOME/.local/bin/vigil-sync >/dev/null 2>&1
```

This catches the "I left Claude Code running for hours" case where SessionStart-only sync would go stale.

## Privacy notes

- The sync uses `git fetch + git reset --hard`. Local edits to `~/.vigil/brain/` are blown away on every sync. Don't write to that directory.
- The brain repo is a *private* repo. The local copy inherits any restrictions the engineer's git auth provides.
- `vigil-sync` writes only to:
  - `~/.vigil/brain/`
  - `~/.vigil/sync.lock`
  - `~/.vigil/last-sync`

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `vigil-sync: command not found` | `~/.local/bin` not in `$PATH` | Add `export PATH="$HOME/.local/bin:$PATH"` to your shell rc |
| `VIGIL_BRAIN_REMOTE is not set` | First-run, no remote URL given | `export VIGIL_BRAIN_REMOTE=...` and re-run |
| Permission denied on fetch | SSH key not set up for the brain repo | `gh auth login` or add ssh key to GitHub |
| Sync feels stale | SessionStart hook didn't run | Check `~/.claude/hooks/SessionStart` exists and is executable; check `cat ~/.vigil/last-sync` |

## Why this beats running a chat-API service for engineers

| Approach | Failure mode | Engineer latency |
|---|---|---|
| Chat UI → backend → vector search → LLM | If any layer is down: no answer | 1–5s per query (network + LLM) |
| **Local Claude Code → ~/.vigil/brain** | If git pull failed: stale (still works) | ~0 (local file read) |

Single-source-of-truth (the brain repo) + zero-service-dependency (Claude Code reads files) = engineer's tool keeps working even if the dashboard is down.
