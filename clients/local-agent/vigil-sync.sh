#!/usr/bin/env bash
# vigil-sync — clone-or-pull the team brain repo on a local laptop.
#
# Designed to run from:
#   1) ~/.claude/hooks/SessionStart  (every Claude Code session start)
#   2) cron (every 60 min):  0 * * * *  ~/.local/bin/vigil-sync
#   3) manually:             ~/.local/bin/vigil-sync
#
# Env vars (optional):
#   VIGIL_BRAIN_DIR    target directory (default: ~/.vigil/brain)
#   VIGIL_BRAIN_REMOTE git remote URL (default: must be set externally on first run)
#   VIGIL_VERBOSE      "1" for verbose output

set -eu

BRAIN_DIR="${VIGIL_BRAIN_DIR:-$HOME/.vigil/brain}"
BRAIN_REMOTE="${VIGIL_BRAIN_REMOTE:-}"
LOCK_FILE="$HOME/.vigil/sync.lock"
LAST_SYNC_MARKER="$HOME/.vigil/last-sync"

mkdir -p "$(dirname "$LOCK_FILE")"

# Concurrency: bail out silently if another sync is in flight.
exec 200>"$LOCK_FILE"
flock -n 200 || exit 0

log() {
  if [ "${VIGIL_VERBOSE:-0}" = "1" ]; then
    printf '%s vigil-sync: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
  fi
}

# First-run: clone (requires VIGIL_BRAIN_REMOTE set, or print hint and exit).
if [ ! -d "$BRAIN_DIR/.git" ]; then
  if [ -z "$BRAIN_REMOTE" ]; then
    cat <<'HINT' >&2
vigil-sync: VIGIL_BRAIN_REMOTE is not set, and no clone exists at $BRAIN_DIR.

First-run setup needs the team brain repo URL. Add this to your shell rc
or run once:
  export VIGIL_BRAIN_REMOTE=git@github.com:<your-org>/<your-brain-repo>.git
  vigil-sync

Then it will clone, and subsequent runs need no env var.
HINT
    exit 2
  fi
  log "first-run clone: $BRAIN_REMOTE -> $BRAIN_DIR"
  mkdir -p "$(dirname "$BRAIN_DIR")"
  git clone --depth 1 "$BRAIN_REMOTE" "$BRAIN_DIR"
fi

# Periodic: shallow fetch + hard reset (clean rebase, no merge conflicts on engineer's side).
log "fetching origin"
git -C "$BRAIN_DIR" fetch --depth 1 origin main >/dev/null 2>&1 || {
  log "fetch failed (offline?) — using last-known-good"
  exit 0
}
log "resetting to origin/main"
git -C "$BRAIN_DIR" reset --hard origin/main >/dev/null 2>&1

# Marker for "Claude, when was the brain last synced?"
date -u +%Y-%m-%dT%H:%M:%SZ > "$LAST_SYNC_MARKER"
log "done"
