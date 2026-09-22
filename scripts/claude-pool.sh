#!/bin/sh
# claude-pool — Claude Code поверх пула (CLIProxyAPI :8317), модели GPT.
# Ключ шлюза читается из env CLIPROXY_KEY или из файла $HERMES_HOME/cliproxy/client.key.
# Примеры:  claude-pool -p "разбери PR"
#           CLAUDE_POOL_MODEL=gpt-5.6-terra claude-pool
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
KEY="${CLIPROXY_KEY:-}"
[ -z "$KEY" ] && [ -f "$HERMES_HOME/cliproxy/client.key" ] && KEY=$(cat "$HERMES_HOME/cliproxy/client.key")
if [ -z "$KEY" ]; then
  echo "claude-pool: нет ключа шлюза (CLIPROXY_KEY или $HERMES_HOME/cliproxy/client.key)" >&2
  exit 1
fi
export ANTHROPIC_BASE_URL="${CLIPROXY_URL:-http://127.0.0.1:8317}"
export ANTHROPIC_AUTH_TOKEN="$KEY"
export ANTHROPIC_MODEL="${CLAUDE_POOL_MODEL:-gpt-6-astra}"
unset ANTHROPIC_API_KEY
exec claude "$@"
