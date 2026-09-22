#!/bin/sh
# Обёртка для крона: поле script в Hermes cron не принимает аргументы.
DIR="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$DIR/codex_pool_report.py" --alerts
