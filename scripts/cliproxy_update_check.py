#!/usr/bin/env python3
"""Еженедельная проверка обновлений шлюза CLIProxyAPI.

По умолчанию сравнивает установленную версию с ОДОБРЕННОЙ в репозитории скилла
(scripts/cliproxy-approved.txt) — её автор скилла проверил и опробовал. Пишет,
только когда одобренная версия новее установленной. Обновление — фразой агенту
«обнови пул».

CLIPROXY_UPDATE_CHANNEL=upstream — для того, кто сам ведёт одобренную версию:
сообщает о каждом свежем релизе CLIProxyAPI у авторов (перед одобрением — аудит).

Пустой вывод = всё актуально (в no_agent-кроне это тишина).
Env: HERMES_HOME (default ~/.hermes), CLIPROXY_VERSION, CLIPROXY_APPROVED_URL,
     CLIPROXY_UPDATE_CHANNEL (approved | upstream).
"""
import json
import os
import re
import urllib.request

HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
VERSION_FILE = os.path.join(HERMES_HOME, "cliproxy", "VERSION")
APPROVED_URL = os.environ.get(
    "CLIPROXY_APPROVED_URL",
    "https://raw.githubusercontent.com/artemiimillier/hermes-codex-pool/main/scripts/cliproxy-approved.txt",
)
UPSTREAM_API = "https://api.github.com/repos/router-for-me/CLIProxyAPI/releases/latest"
CHANNEL = os.environ.get("CLIPROXY_UPDATE_CHANNEL", "approved").strip().lower()


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "codex-pool-update-check"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def version_key(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:4])


def current_version() -> str:
    v = os.environ.get("CLIPROXY_VERSION")
    if not v and os.path.exists(VERSION_FILE):
        with open(VERSION_FILE) as f:
            v = f.read().strip()
    return v or ""


def approved_version() -> str:
    text = fetch(APPROVED_URL).decode("utf-8", "replace")
    m = re.search(r"^tag=(\S+)", text, re.M)
    return m.group(1) if m else ""


def main() -> None:
    current = current_version()
    if not current:
        print("⚠️ Не знаю текущую версию CLIProxyAPI: нет файла cliproxy/VERSION")
        return
    try:
        approved = approved_version()
        latest = json.loads(fetch(UPSTREAM_API)).get("tag_name", "") if CHANNEL == "upstream" else ""
    except Exception as e:  # сеть/GitHub — не повод будить человека каждую неделю
        print(f"⚠️ Не смог проверить обновления CLIProxyAPI: {type(e).__name__}")
        return

    if CHANNEL == "upstream":
        if latest and version_key(latest) > version_key(max(current, approved, key=version_key)):
            print(f"🆕 CLIProxyAPI: у авторов вышла {latest} (у вас {current}, одобрена {approved or '—'}).\n"
                  f"Что нового: https://github.com/router-for-me/CLIProxyAPI/releases/tag/{latest}\n"
                  f"Перед одобрением — аудит: scripts/cliproxy_audit_hosts.sh и проверка на своём сервере.")
        return

    if approved and version_key(approved) > version_key(current):
        print(f"🆕 Пул: одобрена новая версия шлюза {approved} (у вас {current}).\n"
              f"Скажи агенту «обнови пул» — он соберёт её из исходников и проверит.")


if __name__ == "__main__":
    main()
