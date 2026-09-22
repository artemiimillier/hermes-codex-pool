#!/bin/sh
# Сторож CLIProxyAPI. Для no_agent-крона Hermes: пустой stdout = тишина.
# Env: CLIPROXY_URL (default http://127.0.0.1:8317), HERMES_HOME (default ~/.hermes)
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
URL="${CLIPROXY_URL:-http://127.0.0.1:8317}/healthz"

if curl -sf -m 5 "$URL" >/dev/null 2>&1; then
  exit 0
fi

# s6-overlay: пересоздать сервис (после пересоздания контейнера /run пустой)
if [ -d /run/service ]; then
  if [ ! -d /run/service/cliproxy ]; then
    cp -r "$HERMES_HOME/s6-services/cliproxy" /run/service/cliproxy 2>/dev/null
  fi
  /command/s6-svscanctl -a /run/service >/dev/null 2>&1
# systemd
elif command -v systemctl >/dev/null 2>&1; then
  systemctl --user restart cliproxy >/dev/null 2>&1
fi
sleep 5

if curl -sf -m 5 "$URL" >/dev/null 2>&1; then
  printf '⚠️ Шлюз пула (CLIProxyAPI, :8317) падал и был автоматически перезапущен.\n'
else
  printf '🚨 Шлюз пула (CLIProxyAPI, :8317) не отвечает, автозапуск не помог. Скажи агенту «проверь cliproxy».\n'
fi
exit 0
