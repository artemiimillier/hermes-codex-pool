#!/bin/sh
# Аудит сетевых адресов в исходнике CLIProxyAPI перед сборкой (без тестов и
# examples/ — они в собранный шлюз не попадают).
# Печатает только хосты, которых НЕТ в эталоне cliproxy-known-hosts.txt
# (эталон проверен для одобренной версии). Пустой вывод и код 0 = новых нет;
# код 1 = есть незнакомые адреса — покажи их пользователю до сборки.
#
#   cliproxy_audit_hosts.sh <папка исходника> [эталон]
#   cliproxy_audit_hosts.sh --list <папка исходника>   — все хосты (для эталона)
set -eu

list_hosts() {
  grep -rhoE --include='*.go' --exclude='*_test.go' --exclude-dir=examples 'https?://[a-zA-Z0-9.-]+' "$1" \
    | sed -E 's#^https?://##; s#\.+$##; /^$/d' | tr 'A-Z' 'a-z' | sort -u \
    | grep -v -x -E 'localhost|127\.0\.0\.1|0\.0\.0\.0|host|example\.com|example\.invalid|api\.example\.com|www\.example\.com' \
    || true
}

if [ "${1:-}" = "--list" ]; then
  list_hosts "${2:?укажи папку исходника}"
  exit 0
fi

SRC="${1:?укажи папку исходника}"
KNOWN="${2:-$(dirname "$0")/cliproxy-known-hosts.txt}"
[ -f "$KNOWN" ] || { echo "нет эталона: $KNOWN" >&2; exit 2; }

tmp=$(mktemp "${HERMES_HOME:-$HOME/.hermes}/.audit-known.XXXXXX" 2>/dev/null || mktemp)
grep -v -E '^[[:space:]]*(#|$)' "$KNOWN" > "$tmp"
unknown=$(list_hosts "$SRC" | grep -v -x -F -f "$tmp" || true)
rm -f "$tmp"

if [ -n "$unknown" ]; then
  echo "Незнакомые адреса в исходнике (нет в эталоне):"
  printf '%s\n' "$unknown" | sed 's/^/  /'
  exit 1
fi
