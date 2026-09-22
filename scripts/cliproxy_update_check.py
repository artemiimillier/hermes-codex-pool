#!/usr/bin/env python3
"""Еженедельная проверка обновлений CLIProxyAPI.
Новый релиз -> сообщение со ссылкой. Молчит, если версия совпадает.
Обновление — ТОЛЬКО вручную агентом (сборка из исходников + аудит diff).

Текущая версия читается из файла $HERMES_HOME/cliproxy/VERSION
(скилл пишет туда тег при сборке) либо из env CLIPROXY_VERSION.
"""
import json, os, urllib.request

HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
VERSION_FILE = os.path.join(HERMES_HOME, "cliproxy", "VERSION")
API = "https://api.github.com/repos/router-for-me/CLIProxyAPI/releases/latest"


def current_version() -> str:
    v = os.environ.get("CLIPROXY_VERSION")
    if not v and os.path.exists(VERSION_FILE):
        v = open(VERSION_FILE).read().strip()
    return (v or "").lstrip("v")


current = current_version()
if not current:
    print("⚠️ Не знаю текущую версию CLIProxyAPI: нет файла VERSION и env CLIPROXY_VERSION")
    raise SystemExit(0)

req = urllib.request.Request(API, headers={"User-Agent": "codex-pool-update-check"})
try:
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.load(r)
except Exception as e:
    print(f"⚠️ Не смог проверить обновления CLIProxyAPI: {type(e).__name__}")
    raise SystemExit(0)

latest = (d.get("tag_name") or "").lstrip("v")
if latest and latest != current:
    print(f"🆕 CLIProxyAPI: вышла v{latest} (у нас v{current}).\n"
          f"Что нового: {d.get('html_url')}\n"
          f"Скажи агенту «обнови cliproxy» — соберёт из исходников после аудита diff.")
