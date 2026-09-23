---
name: hermes-codex-pool
description: "Пул подписок ChatGPT/Claude под одним шлюзом CLIProxyAPI для Hermes."
version: 1.0.0
author: artemiimillier
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [Codex, ChatGPT, Claude, CLIProxyAPI, pool, subscription, OAuth, gateway, s6, systemd]
    related_skills: [hermes-agent, codex, claude-code]
---

# Hermes Codex Pool (CLIProxyAPI)

Несколько подписок ChatGPT (и опционально Claude Pro/Max) → один локальный шлюз
[CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) на `127.0.0.1:8317` →
Hermes / Codex CLI / Claude Code. Шлюз ротирует аккаунты (round-robin +
session-affinity), охлаждает упёршиеся в лимит, ретраит 429/5xx. Ручного
переключения аккаунтов нигде не нужно.

Файлы этого репозитория: `https://raw.githubusercontent.com/artemiimillier/hermes-codex-pool/main/`
(далее `$RAW`). Установка тянет только SKILL.md — остальное качай по `$RAW/...`.

## ⚠️ ОБЯЗАТЕЛЬНО предупреди пользователя один раз

Использование подписочного OAuth вне официальных клиентов может нарушать ToS
OpenAI/Anthropic — риск ограничения аккаунтов ненулевой. Шлюз маскируется под
официальный Codex CLI (`disable-codex-cloaking: false`), но гарантий нет.
Лимиты подписок общие с «ручным» Codex CLI / Claude Code пользователя.

## Когда применять

- Пользователь хочет, чтобы Hermes/кроны работали «по подписке ChatGPT», и у него
  2+ аккаунта.
- Один аккаунт постоянно упирается в недельный лимит и работа встаёт.
- Пересобрать/починить шлюз после пересоздания контейнера.

## Термины и пути (обобщённые — не копируй чужие)

| Сущность | Значение |
|---|---|
| `HERMES_HOME` | `~/.hermes` (проверь: `echo $HERMES_HOME`; в контейнерах часто другое) |
| Каталог шлюза | `$HERMES_HOME/cliproxy/` — бинарь, `config.yaml`, `auths/`, `logs/`, `VERSION`, `client.key` |
| Скрипты | `$HERMES_HOME/scripts/` |
| s6-сервис | `$HERMES_HOME/s6-services/cliproxy/run` → живое `/run/service/cliproxy` |
| systemd | `~/.config/systemd/user/cliproxy.service` |
| Порт | `127.0.0.1:8317` (env `CLIPROXY_URL` в скриптах) |

## Процедура установки с нуля

### 1. Собери шлюз из исходников (root не нужен)

Не бери релизный бинарь: шлюз держит OAuth-токены аккаунтов, собираем сами
по пинованному тегу.

```bash
export HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
mkdir -p $HERMES_HOME/cliproxy/auths $HERMES_HOME/scripts && chmod 700 $HERMES_HOME/cliproxy/auths
# Go: если нет — скачай tarball в ~/go (GOPATH держи отдельно от GOROOT)
export GOPATH=$HOME/gopath; export PATH=$HOME/go/bin:$GOPATH/bin:$PATH
TAG=$(curl -s https://api.github.com/repos/router-for-me/CLIProxyAPI/releases/latest | python3 -c 'import sys,json;print(json.load(sys.stdin)["tag_name"])')
git clone --depth 1 --branch $TAG https://github.com/router-for-me/CLIProxyAPI $TMPDIR/cliproxy-src
cd $TMPDIR/cliproxy-src
# аудит: куда бинарь может ходить в сеть
grep -rhoE 'https?://[a-zA-Z0-9./_-]+' --include=*.go . | sort -u
go build -trimpath -ldflags "-s -w" -o $HERMES_HOME/cliproxy/cli-proxy-api ./cmd/server/
echo "$TAG" > $HERMES_HOME/cliproxy/VERSION
```

Ожидаемые домены: `chatgpt.com`, `auth.openai.com`, `api.anthropic.com`,
`claude.ai`, `*.googleapis.com`, `github.com`. Незнакомый домен — покажи
пользователю до запуска.

### 2. Конфиг

```bash
cd $HERMES_HOME/cliproxy
curl -fsSL $RAW/config.yaml.template -o config.yaml
CLIENT_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))')
MGMT_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))')
sed -i "s|__CLIENT_KEY__|$CLIENT_KEY|; s|__MGMT_KEY__|$MGMT_KEY|; s|__AUTH_DIR__|$HERMES_HOME/cliproxy/auths|" config.yaml
printf '%s' "$CLIENT_KEY" > client.key
chmod 600 config.yaml client.key
```

`max-retry-credentials` поставь равным числу аккаунтов. Секрет management-ключа
шлюз при старте перепишет в bcrypt (`$2a$...`) — это норма, не «порча файла».
Не печатай ключи в чат.

### 3. Сервис

**s6-overlay** (rootless-контейнеры, есть `/run/service`):
```bash
mkdir -p $HERMES_HOME/s6-services/cliproxy
curl -fsSL $RAW/scripts/s6/cliproxy/run -o $HERMES_HOME/s6-services/cliproxy/run
sed -i "s|__HERMES_HOME__|$HERMES_HOME|g; s|__USER__|$(id -un)|g" $HERMES_HOME/s6-services/cliproxy/run
chmod +x $HERMES_HOME/s6-services/cliproxy/run
cp -r $HERMES_HOME/s6-services/cliproxy /run/service/cliproxy && /command/s6-svscanctl -a /run/service
```
`s6-svc` для непривилегированного пользователя обычно не работает (supervise/
принадлежит root) — рестарт = `kill <PID>` процесса, s6 поднимет за ~3 с.

**systemd** (обычный Linux):
```bash
mkdir -p ~/.config/systemd/user
curl -fsSL $RAW/scripts/systemd/cliproxy.service -o ~/.config/systemd/user/cliproxy.service
# если HERMES_HOME ≠ ~/.hermes — поправь пути в юните
systemctl --user daemon-reload && systemctl --user enable --now cliproxy && loginctl enable-linger $USER
```

Проверка: `curl -s 127.0.0.1:8317/healthz` → `{"status":"ok"}`.

### 4. Логин в аккаунты ChatGPT (device-code, по одному)

```bash
cd $HERMES_HOME/cliproxy && ./cli-proxy-api --config config.yaml --codex-device-login
```
Запусти фоновым PTY-процессом, вытащи из вывода URL
`https://auth.openai.com/oauth/device?user_code=XXXX-XXXX` и код, отдай
пользователю пошагово: открыть → войти в НУЖНЫЙ аккаунт → подтвердить код.
Код живёт 15 минут; истёк — запусти заново. Auth-файл `auths/codex-<id>-<email>.json`
появится сам; шлюз подхватывает новые файлы без рестарта. Повтори для каждого
аккаунта (пользователю: инкогнито или выйти из ChatGPT между логинами).

**Claude Pro/Max (опционально):** `--claude-login`. Другой флоу: отдай
пользователю длинный URL `claude.ai/oauth/authorize?...`; после Authorize
браузер упадёт на `http://localhost:54545/callback?code=...&state=...` — так и
надо; пользователь копирует ПОЛНЫЙ адрес, ты подаёшь его в stdin процесса
СРАЗУ (процесс ждёт ввод ~3-4 минуты и умирает).

**Подписка по API-ключу (Kimi и подобные, опционально).** Не всякая подписка
логинится по OAuth: некоторые дают обычный ключ. Такой аккаунт кладётся не в
`auths/`, а блоком `claude-api-key:` в `config.yaml` шлюза — и попадает в тот
же единственный пул. Для не-Anthropic апстрима задай `base-url` и ЯВНЫЙ список
моделей с алиасами (иначе клиенты не узнают, как их звать):

```yaml
claude-api-key:
  - api-key: "<ключ подписки>"
    base-url: "https://api.example.com/coding"   # апстрим провайдера
    models:
      - name: "upstream-model-id"   # как называет апстрим
        alias: "short-name"         # как зовут клиенты
```

Список моделей апстрима сначала узнай запросом `GET <base-url>/v1/models` с этим
же ключом — не угадывай имена. После правки конфига перезапусти шлюз и проверь
`/v1/models` и настоящий запрос. Флаги `--kimi-login` / `--kimi-ai-login` — это
ДРУГОЙ, OAuth-вариант; для ключа они не нужны.

### 5. Подключи Hermes

Только через `hermes config set` (прямая правка config.yaml может быть
заблокирована политикой). Ключ — из `$HERMES_HOME/cliproxy/client.key`.

```bash
KEY=$(cat $HERMES_HOME/cliproxy/client.key)
hermes config set providers.pool.name pool
hermes config set providers.pool.base_url http://127.0.0.1:8317/v1
hermes config set providers.pool.api_key "$KEY"
hermes config set providers.pool.api_mode chat_completions
hermes config set providers.pool.default_model gpt-5.6-sol
# алиасы — по списку из curl -s -H "Authorization: Bearer ***" 127.0.0.1:8317/v1/models
hermes config set model_aliases.pool-sol.model gpt-5.6-sol
hermes config set model_aliases.pool-sol.provider pool
hermes config set model_aliases.pool-astra.model gpt-6-astra
hermes config set model_aliases.pool-astra.provider pool
```
Предупреждение «not a recognized config key» для `model_aliases` — норма.

**Провайдер нужен РОВНО ОДИН — `pool`.** Аккаунты ChatGPT/Codex и аккаунты
Claude и так живут в одном шлюзе (один auth-dir, одна ротация), а дверь
`chat_completions` обслуживает ОБЕ семьи моделей: tool-calls, поле
`reasoning_content` и prompt-кэш работают и для `claude-*`, и для `gpt-*`.
Заводить второй провайдер под Anthropic-протокол не надо — это дублирование
одного и того же пула. Есть Claude-аккаунты — просто добавь их алиасы к тому
же провайдеру:

```bash
hermes config set model_aliases.pool-sonnet.model claude-sonnet-5
hermes config set model_aliases.pool-sonnet.provider pool
hermes config set model_aliases.pool-opus.model claude-opus-5
hermes config set model_aliases.pool-opus.provider pool
```

Если какому-то стороннему скрипту нужна именно Anthropic Messages-дверь
(`POST /v1/messages`) — пусть резолвит тот же `pool` и сам срезает `/v1`
с `base_url`; отдельный провайдер ради этого не заводится.

**Порядок моделей в списке.** `/v1/models` отдаёт модели в порядке обхода
map внутри шлюза — он случайный и меняется от рестарта к рестарту, конфигом
не управляется. Читаемый порядок в пикере задаётся ТОЛЬКО порядком ключей
в `model_aliases`. Менять его надо целиком, одной командой — поключевой
`hermes config set` дописывает новый алиас в конец:

```bash
hermes config set --force model_aliases '{
  "pool-sonnet": {"model":"claude-sonnet-5","provider":"pool"},
  "pool-opus":   {"model":"claude-opus-5","provider":"pool"},
  "pool-astra":  {"model":"gpt-6-astra","provider":"pool"},
  "pool-sol":    {"model":"gpt-5.6-sol","provider":"pool"}
}'
```

Кроны Hermes: `hermes cron edit <job_id> --provider pool --model <модель>` —
тогда они не встают, когда один аккаунт в лимите. Проверка: `/model pool-astra`.

### 6. Codex CLI и Claude Code (опционально)

`~/.codex/config.toml` (сохрани бэкап старого):
```toml
model_provider = "pool"
model = "gpt-5.6-sol"
[model_providers.pool]
name = "pool"
base_url = "http://127.0.0.1:8317/v1"
wire_api = "responses"
supports_websockets = false
requires_openai_auth = false
experimental_bearer_token = "<ключ из client.key>"
```

Claude Code на моделях GPT: `curl -fsSL $RAW/scripts/claude-pool.sh -o
$HERMES_HOME/scripts/claude-pool.sh && chmod +x ...`; запуск `claude-pool`,
модель через `CLAUDE_POOL_MODEL=...`. Предупреждение Claude Code «unknown
model» безобидно.

### 7. Скрипты и кроны Hermes

```bash
cd $HERMES_HOME/scripts
for f in codex_pool_report.py codex_pool_alerts.sh codex_pool_backup.sh cliproxy-watchdog.sh cliproxy_update_check.py; do
  curl -fsSL $RAW/scripts/$f -o $f && chmod +x $f
done
```
Скрипты читают `HERMES_HOME`; если у крона его нет в окружении — задай
`CLIPROXY_AUTH_DIR` / `CLIPROXY_URL` явно.

Кроны (все `no_agent`, доставка в мессенджер пользователя; пустой stdout = молчание):

| Имя | Расписание | Скрипт | Смысл |
|---|---|---|---|
| `cliproxy-watchdog` | каждые 13 мин | `cliproxy-watchdog.sh` | поднять шлюз после падения/пересоздания контейнера |
| `codex-pool-morning` | 1 раз утром | `codex_pool_report.py` | квоты и ресеты по каждому аккаунту |
| `codex-pool-alerts` | 1 раз утром | `codex_pool_alerts.sh` | только проблемы: все в лимите / 401 / окно >90% |
| `codex-pool-backup` | ночью | `codex_pool_backup.sh` | tar.gz токенов, ротация 14 |
| `cliproxy-update-check` | раз в неделю | `cliproxy_update_check.py` | новый релиз шлюза → сообщение |

Поле `script` крона НЕ принимает аргументов (вся строка = путь) — поэтому есть
обёртка `codex_pool_alerts.sh`. Алерты чаще раза в сутки — спам; не надо.

## Обновление шлюза — только вручную

1. `git fetch --depth 1 origin tag vX.Y.Z && git checkout vX.Y.Z`
2. Аудит diff: `git diff <стар>..<нов> | grep -iE 'https?://'` на новые домены.
3. `go build -trimpath -ldflags "-s -w" -o $HERMES_HOME/cliproxy/cli-proxy-api ./cmd/server/`
4. `kill <pid>` → сервис перезапустит; `healthz`; настоящий запрос.
5. Обнови `$HERMES_HOME/cliproxy/VERSION`.

Подмена бинаря на ЖИВОМ сервисе: обычный `cp` поверх даёт `Text file busy`.
Порядок: `mv cli-proxy-api cli-proxy-api.old-<ver>` → `cp` новый → `kill <PID>`.
PID бери отдельной командой: подстановка `$(pgrep ...)` внутри той же строки
может поймать твой собственный шелл.

Сборка требует Go той версии, что указана в `go.mod` апстрима (сейчас 1.26).
Toolchain Go скачает сам, сборка занимает 5–10 минут — запускай её фоном
с уведомлением, а не в коротком таймауте.

### Новая модель есть в `/v1/models`, но запрос к ней падает

Симптом: `Claude Code X does not support this model; version Y or newer is
required`. Это НЕ конфиг и НЕ фильтры моделей: апстрим проверяет User-Agent
`claude-cli/<версия>`, вшитый в бинарь шлюза. Лечится ТОЛЬКО обновлением
CLIProxyAPI до релиза, где подняли baseline. Проверить, что вшито сейчас:

```bash
strings $HERMES_HOME/cliproxy/cli-proxy-api | grep -o 'claude-cli/[0-9.]*'
```

## Как это работает (объясни пользователю по-простому)

- Аккаунты крутятся по кругу, но один разговор держится на одном аккаунте
  1 час (`session-affinity`) — так работает кэш промптов, дешевле по лимитам.
- Аккаунт упёрся в лимит → шлюз кладёт его «остывать» (`.cds`-файл рядом с
  auth, переживает рестарт) и берёт следующий.
- У планов ChatGPT окно может быть только недельное (`primary_window` 604800 с),
  без 5-часового — `secondary_window: None` в отчёте это норма.
- Ручные сбросы лимита (`rate_limit_reset_credits`) — только по явной команде
  пользователя, не автоматизируй.

## Подводные камни

- `pkill -f cli-proxy-api` убивает и твой собственный шелл (паттерн есть в его
  командной строке). Убивай ТОЛЬКО по числовому PID.
- Access-токен шлюз рефрешит сам и ПЕРЕЗАПИСЫВАЕТ auth-файл; поле `expired` —
  срок refresh-токена (~10 дней от логина). Протух → перелогин этого аккаунта.
- Список моделей для клиентов режется в `oauth-excluded-models` (wildcards
  `prefix-*`, `*-substr-*`). После правки — рестарт, проверка `/v1/models`.
  Пикер Hermes Desktop может держать старый кэш — переоткрыть настройки.
- Hermes-провайдер `pool` объявлен как `chat_completions`, но шлюз обслуживает
  и Responses API, и Anthropic Messages — Codex CLI ходит по
  `wire_api = "responses"`, а `claude-pool` — по `/v1/messages`. Это ОДИН пул;
  второй провайдер ради другого протокола не заводится.
- PTY-сессии могут не видеть `codex`/`claude` в PATH — используй абсолютные пути.
- Никогда не печатай в чат содержимое `auths/*.json`, `config.yaml`, `client.key`.

## Чеклист самопроверки (не рапортуй «готово» без него)

1. `curl -s 127.0.0.1:8317/healthz` → `{"status":"ok"}`.
2. `ls $HERMES_HOME/cliproxy/auths/codex-*.json | wc -l` = число аккаунтов.
3. `curl -s -H "Authorization: Bearer $(cat $HERMES_HOME/cliproxy/client.key)" 127.0.0.1:8317/v1/models` — нужные модели есть.
4. Настоящий запрос: `curl -s 127.0.0.1:8317/v1/chat/completions -H "Authorization: Bearer <key>" -H 'Content-Type: application/json' -d '{"model":"gpt-5.6-sol","messages":[{"role":"user","content":"скажи ok"}]}'` → ответ с текстом.
5. `python3 $HERMES_HOME/scripts/codex_pool_report.py` — все аккаунты 🟢 или с понятной причиной.
6. В Hermes: `/model pool-sol`, короткий вопрос → ответ; в логах шлюза виден запрос.
7. Сервис переживает `kill <pid>` (поднялся сам за ~5 с).
