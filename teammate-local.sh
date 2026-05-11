#!/bin/bash
# Local teammate development setup — Socket Mode edition
# Usage: source teammate-local.sh && teammate agent listen --no-fail-on-disconnect

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRAIN_DIR="/Users/jiung.gu/Downloads/projects/pn-doc-nx-brain-docs"

export TEAMMATE_BRAIN_ROOT="$BRAIN_DIR"
export TEAMMATE_LLM_HOST=http://localhost:11434
export TEAMMATE_EMBEDDING_HOST=http://localhost:11434

# ---- Slack Socket Mode (required for 'teammate agent listen') ----
# SLACK_APP_TOKEN: api.slack.com/apps → Socket Mode → App-Level Tokens (xapp-...)
# SLACK_BOT_TOKEN: api.slack.com/apps → OAuth & Permissions (xoxb-...)
# Load from AWS SM so nothing is hardcoded here:
if command -v aws &>/dev/null; then
  _SM=$(aws --profile placen secretsmanager get-secret-value \
    --secret-id /pn/nx/core/prod/teammate/credentials \
    --query SecretString --output text 2>/dev/null)
  if [ -n "$_SM" ]; then
    export SLACK_APP_TOKEN=$(echo "$_SM" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('slack-app-token',''))" 2>/dev/null)
    export SLACK_BOT_TOKEN=$(echo "$_SM" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('slack-bot-token',''))" 2>/dev/null)
    export ANTHROPIC_API_KEY=$(echo "$_SM" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('anthropic-api-key',''))" 2>/dev/null)
    export ATLASSIAN_API_TOKEN=$(echo "$_SM" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('atlassian-token',''))" 2>/dev/null)
    export ATLASSIAN_EMAIL="jiung.gu@placen.co.kr"
    export JIRA_BASE_URL="https://placen.atlassian.net"
    export CONFLUENCE_BASE_URL="https://placen.atlassian.net/wiki"
    export CONFLUENCE_WATCHER_SPACES="DEVOPS,NEXUS,INFRA"
    echo "credentials loaded from AWS SM"
  else
    echo "WARNING: could not load credentials from AWS SM — set tokens manually"
  fi
fi

# Watch the rnd_devsecops_remote_share channel
export TEAMMATE_SLACK_CHANNELS="rnd_devsecops_remote_share"

source "$SCRIPT_DIR/.venv/bin/activate"
cd "$BRAIN_DIR"
echo "teammate local env ready"
echo "  BRAIN:    $BRAIN_DIR"
echo "  LLM:      $TEAMMATE_LLM_HOST"
echo "  CHANNELS: $TEAMMATE_SLACK_CHANNELS"
echo "  APP_TOKEN: ${SLACK_APP_TOKEN:0:12}..."
echo ""
echo "Run: teammate agent listen --no-fail-on-disconnect"
