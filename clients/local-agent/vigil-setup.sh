#!/usr/bin/env bash
# vigil-setup — bootstrap a new engineer's laptop for the Vigil local sync agent.
#
# Idempotent. Re-runnable. Asks no questions except VIGIL_BRAIN_REMOTE if missing.
#
# Installs:
#   1) ~/.local/bin/vigil-sync                   the sync script
#   2) ~/.claude/hooks/SessionStart              triggers vigil-sync on every Claude session
#   3) ~/.claude/CLAUDE.md  (append section)     tells Claude where the brain is + how to read it
#
# Usage:
#   # one-time (or as part of dotfiles bootstrap)
#   curl -fsSL https://raw.githubusercontent.com/JIUNG9/vigil/main/clients/local-agent/vigil-setup.sh | bash

set -eu

VIGIL_HOME="${VIGIL_HOME:-$HOME/.vigil}"
LOCAL_BIN="${LOCAL_BIN:-$HOME/.local/bin}"
CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
CLAUDE_MD="$CLAUDE_HOME/CLAUDE.md"
HOOKS_DIR="$CLAUDE_HOME/hooks"
SCRIPT_URL="${VIGIL_SCRIPT_URL:-https://raw.githubusercontent.com/JIUNG9/vigil/main/clients/local-agent/vigil-sync.sh}"

mkdir -p "$LOCAL_BIN" "$HOOKS_DIR" "$VIGIL_HOME"

echo "▼ vigil-setup — installing the local sync agent"
echo

# 1) install vigil-sync
echo "  1/3 installing $LOCAL_BIN/vigil-sync"
if [ -f "$LOCAL_BIN/vigil-sync" ]; then
  echo "      (already exists — overwriting)"
fi
curl -fsSL "$SCRIPT_URL" -o "$LOCAL_BIN/vigil-sync"
chmod +x "$LOCAL_BIN/vigil-sync"

# Verify $LOCAL_BIN is on PATH
case ":$PATH:" in
  *":$LOCAL_BIN:"*) ;;
  *) echo "      ⚠ $LOCAL_BIN is not in your \$PATH. Add to your shell rc:"
     echo "         export PATH=\"$LOCAL_BIN:\$PATH\"" ;;
esac

# 2) install SessionStart hook
echo "  2/3 installing $HOOKS_DIR/SessionStart"
HOOK_LINE='~/.local/bin/vigil-sync 2>/dev/null &'
if [ -f "$HOOKS_DIR/SessionStart" ]; then
  if grep -qF "$HOOK_LINE" "$HOOKS_DIR/SessionStart"; then
    echo "      (already wired)"
  else
    echo "      (appending vigil-sync to existing hook)"
    echo "$HOOK_LINE" >> "$HOOKS_DIR/SessionStart"
  fi
else
  cat > "$HOOKS_DIR/SessionStart" <<'EOF'
#!/usr/bin/env bash
# Auto-installed by vigil-setup. Triggers a non-blocking brain sync.
~/.local/bin/vigil-sync 2>/dev/null &
EOF
  chmod +x "$HOOKS_DIR/SessionStart"
fi

# 3) append CLAUDE.md instructions (once)
echo "  3/3 wiring $CLAUDE_MD"
MARKER="<!-- vigil-brain-pointer -->"
if [ -f "$CLAUDE_MD" ] && grep -qF "$MARKER" "$CLAUDE_MD"; then
  echo "      (pointer already present)"
else
  cat >> "$CLAUDE_MD" <<EOF

$MARKER
## Team brain (auto-synced by vigil)

The team's brain (Jira / Confluence / GitHub / Slack archives + curated runbooks)
lives at \`~/.vigil/brain/\` — synced every 60 min by \`~/.local/bin/vigil-sync\`
and on every Claude Code session start. Check \`cat ~/.vigil/last-sync\` for
freshness.

When a question can be answered from the brain, read in this priority order:

1. \`~/.vigil/brain/docs/runbooks/\`     ← operational procedures
2. \`~/.vigil/brain/decisions/\`         ← architecture decisions (ADRs)
3. \`~/.vigil/brain/knowledge/\`         ← domain knowledge
4. \`~/.vigil/brain/archive/jira/INCD/\` ← past incidents (similarity-rich)
5. \`~/.vigil/brain/archive/confluence/\` ← wiki pages
6. \`~/.vigil/brain/archive/github/\`    ← code READMEs + PR discussions
7. \`~/.vigil/brain/archive/slack/\`     ← daily channel rollups (lower signal)

\`grep -r "<keyword>" ~/.vigil/brain/archive/\` is usually the fastest way in.
$MARKER
EOF
fi

# 4) first sync (will print hint if VIGIL_BRAIN_REMOTE is not set)
echo
echo "▼ running first sync"
"$LOCAL_BIN/vigil-sync" || true

echo
echo "✓ vigil-setup done."
echo "  brain at:    $VIGIL_HOME/brain"
echo "  last sync:   $VIGIL_HOME/last-sync"
echo "  hook:        $HOOKS_DIR/SessionStart"
echo "  CLAUDE.md:   $CLAUDE_MD"
echo
echo "  If this was the first run and no brain remote was set, export:"
echo "      export VIGIL_BRAIN_REMOTE=git@github.com:<your-org>/<your-brain-repo>.git"
echo "  ... and re-run vigil-sync."
