#!/usr/bin/env python3
"""Отчёт по пулу подписок (CLIProxyAPI): Codex + Claude.

Читает codex-*.json / claude-*.json из auth-dir, опрашивает usage-эндпоинты
по каждому аккаунту и печатает компактный русский отчёт для Telegram.
Режимы:
  python3 codex_pool_report.py          — полный отчёт
  python3 codex_pool_report.py --alerts — только проблемы (пусто = всё ок)
Env: CLIPROXY_AUTH_DIR (default $HERMES_HOME/cliproxy/auths, HERMES_HOME default ~/.hermes),
     REPORT_TZ_OFFSET_HOURS (default 3 = МСК).
"""
import json, sys, urllib.request, urllib.error, glob, os, time
from datetime import datetime, timezone, timedelta

HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
AUTH_DIR = os.environ.get("CLIPROXY_AUTH_DIR", os.path.join(HERMES_HOME, "cliproxy", "auths"))
MSK = timezone(timedelta(hours=float(os.environ.get("REPORT_TZ_OFFSET_HOURS", "3"))))
UA = "codex_cli_rs/0.76.0"


def fetch_usage(access_token: str, account_id: str) -> dict:
    req = urllib.request.Request(
        "https://chatgpt.com/backend-api/wham/usage",
        headers={
            "Authorization": f"Bearer {access_token}",
            "chatgpt-account-id": account_id,
            "User-Agent": UA,
        },
    )
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def fetch_claude_usage(access_token: str) -> dict:
    req = urllib.request.Request(
        "https://api.anthropic.com/api/oauth/usage",
        headers={
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "claude-code/2.0.0",
            "anthropic-beta": "oauth-2025-04-20",
        },
    )
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def fmt_reset(reset_at) -> str:
    if not reset_at:
        return "—"
    dt = datetime.fromtimestamp(reset_at, tz=MSK)
    now = datetime.now(tz=MSK)
    secs = (dt - now).total_seconds()
    if secs <= 0:
        return "сейчас"
    if secs < 86400:
        return f"{int(secs // 3600)}ч{int((secs % 3600) // 60):02d}м"
    return f"{int(secs // 86400)}д{int((secs % 86400) // 3600)}ч"


def window_str(w) -> str:
    """Одно окно: '23% (ресет 4ч12м)'."""
    if not w:
        return "—"
    used = w.get("used_percent", 0)
    days = (w.get("limit_window_seconds") or 0) / 86400
    label = "нед" if days >= 6.5 else ("5ч" if (w.get("limit_window_seconds") or 0) <= 20000 else f"{days:.0f}д")
    return f"{label} {used}% (ресет {fmt_reset(w.get('reset_at'))})"


def short_email(email: str) -> str:
    return email.split("@")[0]


def main():
    alerts_only = "--alerts" in sys.argv
    files = sorted(glob.glob(os.path.join(AUTH_DIR, "codex-*.json")))
    claude_files = sorted(glob.glob(os.path.join(AUTH_DIR, "claude-*.json")))
    if not files and not claude_files:
        print("🚨 Пул: нет ни одного аккаунта в auth-dir!")
        return

    lines, alerts = [], []
    active = 0
    total = len(files) + len(claude_files)

    # ---------- Claude-аккаунты ----------
    for f in claude_files:
        try:
            d = json.load(open(f))
        except Exception:
            alerts.append(f"🚨 {os.path.basename(f)}: битый auth-файл")
            continue
        email = d.get("email", os.path.basename(f))
        name = short_email(email)
        if d.get("disabled"):
            alerts.append(f"⚠️ {name} (claude): аккаунт выключен в шлюзе")
            continue
        try:
            u = fetch_claude_usage(d["access_token"])
        except urllib.error.HTTPError as e:
            if e.code == 401:
                alerts.append(f"🚨 {name} (claude): токен протух — нужен перелогин (скажи агенту «перелогин claude в пуле»)")
            else:
                alerts.append(f"⚠️ {name} (claude): не смог прочитать квоту (HTTP {e.code})")
            continue
        except Exception as e:
            alerts.append(f"⚠️ {name} (claude): сеть/API недоступны ({type(e).__name__})")
            continue

        org = d.get("organization_name") or "claude"
        parts = []
        worst = 0.0
        for key, label in (("five_hour", "5ч"), ("seven_day", "нед")):
            w = u.get(key)
            if w:
                util = w.get("utilization") or 0.0
                worst = max(worst, util)
                ra = w.get("resets_at")
                reset_unix = None
                if ra:
                    try:
                        reset_unix = int(datetime.fromisoformat(ra.replace("Z", "+00:00")).timestamp())
                    except Exception:
                        pass
                parts.append(f"{label} {util:.0f}% (ресет {fmt_reset(reset_unix)})")
        limited = worst >= 100
        status = "🔴 лимит" if limited else "🟢"
        lines.append(f"{status} {name} ({org}) claude: " + " · ".join(parts))
        if not limited:
            active += 1
        if worst >= 90 and not limited:
            alerts.append(f"⚠️ {name} (claude): окно {worst:.0f}% — почти упёрся")
        if limited:
            alerts.append(f"🔴 {name} (claude): лимит исчерпан")

    # ---------- Codex-аккаунты ----------
    for f in files:
        try:
            d = json.load(open(f))
        except Exception:
            alerts.append(f"🚨 {os.path.basename(f)}: битый auth-файл")
            continue
        email = d.get("email", os.path.basename(f))
        name = short_email(email)
        if d.get("disabled"):
            alerts.append(f"⚠️ {name}: аккаунт выключен (disabled) в шлюзе")
            continue
        try:
            u = fetch_usage(d["access_token"], d.get("account_id", ""))
        except urllib.error.HTTPError as e:
            if e.code == 401:
                alerts.append(f"🚨 {name}: токен протух/отозван — нужен перелогин (скажи агенту «перелогин codex-пул»)")
            else:
                alerts.append(f"⚠️ {name}: не смог прочитать квоту (HTTP {e.code})")
            continue
        except Exception as e:
            alerts.append(f"⚠️ {name}: сеть/API недоступны ({type(e).__name__})")
            continue

        plan = u.get("plan_type", "?")
        rl = u.get("rate_limit") or {}
        prim = rl.get("primary_window")
        sec = rl.get("secondary_window")
        resets = (u.get("rate_limit_reset_credits") or {}).get("available_count", 0)
        limited = rl.get("limit_reached", False)

        parts = [window_str(prim)]
        if sec:
            parts.append(window_str(sec))
        status = "🔴 лимит" if limited else "🟢"
        line = f"{status} {name} ({plan}): " + " · ".join(parts) + f" · сбросов: {resets}"
        lines.append(line)
        if not limited:
            active += 1

        # алерты по порогам
        for w, tag in ((prim, "осн."), (sec, "доп.")):
            if w and w.get("used_percent", 0) >= 90 and not limited:
                alerts.append(f"⚠️ {name}: {tag} окно {w['used_percent']}% — почти упёрся")
        if limited:
            till = fmt_reset((prim or {}).get("reset_at"))
            alerts.append(f"🔴 {name}: лимит исчерпан, ресет через {till}")

    if alerts_only:
        if active == 0:
            alerts.insert(0, "🚨 Пул: ВСЕ аккаунты в лимите — работа встала!")
        if alerts:
            print("\n".join(alerts))
        return

    now = datetime.now(tz=MSK)
    out = [f"📊 Модель-пул · {now.strftime('%d.%m %H:%M')} ", ""]
    out.extend(lines)
    out.append("")
    out.append(f"Активны: {active} из {total}.")
    if alerts:
        out.append("")
        out.extend(alerts)
    print("\n".join(out))


if __name__ == "__main__":
    main()
