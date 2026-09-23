#!/bin/sh
# Ставит свежий стабильный Go в ~/go с проверкой SHA-256 по официальному
# списку go.dev. Ничего не делает, если Go уже есть. Root не нужен.
set -eu

if command -v go >/dev/null 2>&1; then echo "Go уже есть: $(command -v go)"; exit 0; fi
if [ -x "$HOME/go/bin/go" ]; then echo "Go уже есть: $HOME/go/bin/go"; exit 0; fi
# ~/go бывает рабочей папкой GOPATH с чужим кодом — не трогаем то, что не является дистрибутивом Go.
if [ -e "$HOME/go" ] && [ ! -f "$HOME/go/VERSION" ]; then
  echo "СТОП: ~/go уже существует и это не дистрибутив Go — переименуй папку или поставь Go вручную" >&2
  exit 2
fi

case "$(uname -m)" in
  x86_64|amd64) ARCH=amd64 ;;
  aarch64|arm64) ARCH=arm64 ;;
  *) echo "неизвестная архитектура: $(uname -m)" >&2; exit 2 ;;
esac
OS=$(uname -s | tr 'A-Z' 'a-z')

LINE=$(curl -fsSL 'https://go.dev/dl/?mode=json' | python3 -c "
import json, sys
release = json.load(sys.stdin)[0]
f = [x for x in release['files'] if x['os'] == '$OS' and x['arch'] == '$ARCH' and x['kind'] == 'archive'][0]
print(f['filename'], f['sha256'])")
FILE=${LINE% *}
SUM=${LINE#* }

DL="${HERMES_HOME:-$HOME/.hermes}/cliproxy/.dl"
mkdir -p "$DL"
curl -fsSLo "$DL/$FILE" "https://go.dev/dl/$FILE"
if command -v sha256sum >/dev/null 2>&1; then GOT=$(sha256sum "$DL/$FILE" | cut -d' ' -f1)
else GOT=$(shasum -a 256 "$DL/$FILE" | cut -d' ' -f1); fi
if [ "$GOT" != "$SUM" ]; then
  rm -f "$DL/$FILE"
  echo "СТОП: SHA-256 архива Go не совпал с go.dev — не устанавливаю" >&2
  exit 3
fi

rm -rf "$HOME/go"
tar -C "$HOME" -xzf "$DL/$FILE"
rm -f "$DL/$FILE"
echo "Go установлен: $(GOPATH="$HOME/gopath" "$HOME/go/bin/go" version)"
