#!/bin/sh
# Бэкап auth-dir пула (OAuth-токены всех аккаунтов). Ротация: 14 копий.
# Молчит при успехе (пустой stdout = тишина в no_agent-кроне), пишет при ошибке.
# Env: HERMES_HOME (default ~/.hermes), CLIPROXY_DIR, CLIPROXY_BACKUP_DIR
set -e
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
SRC="${CLIPROXY_DIR:-$HERMES_HOME/cliproxy}"
DEST="${CLIPROXY_BACKUP_DIR:-$HERMES_HOME/backups/cliproxy}"
mkdir -p "$DEST"
chmod 700 "$DEST"
TS=$(date +%Y%m%d-%H%M)
if ! tar czf "$DEST/auths-$TS.tar.gz" -C "$SRC" auths 2>/dev/null; then
  echo "🚨 Бэкап auth-dir пула НЕ удался ($TS)"
  exit 0
fi
ls -1t "$DEST"/auths-*.tar.gz 2>/dev/null | tail -n +15 | xargs -r rm -f
exit 0
