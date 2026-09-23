---
name: hermes-codex-pool
description: "Шлюз подписок Claude/ChatGPT/Kimi для Hermes: пул аккаунтов, CLIProxyAPI."
version: 1.2.0
author: artemiimillier
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [Codex, ChatGPT, Claude, CLIProxyAPI, pool, subscription, OAuth, gateway, s6, systemd]
    related_skills: [hermes-agent, codex, claude-code]
---

# Hermes Codex Pool (CLIProxyAPI)

Подписки Claude Pro/Max, ChatGPT Plus/Pro и Kimi (одна или несколько) → один
локальный шлюз [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) на
`127.0.0.1:8317` → Hermes / Codex CLI / Claude Code. Хватает и одного аккаунта
Claude — тогда это просто «шлюз подписки Claude для Hermes». Шлюз ротирует аккаунты (round-robin +
session-affinity), охлаждает упёршиеся в лимит, ретраит 429/5xx. Ручного
переключения аккаунтов нигде не нужно.

Файлы этого репозитория: `https://raw.githubusercontent.com/artemiimillier/hermes-codex-pool/main/`
(далее `$RAW`). Установка тянет только SKILL.md — остальное качай по `$RAW/...`.
Задай переменную в начале работы, иначе команды с `curl` получат пустой URL:

```bash
export RAW=https://raw.githubusercontent.com/artemiimillier/hermes-codex-pool/main
```

## ⚠️ ОБЯЗАТЕЛЬНО предупреди пользователя один раз

Использование подписочного OAuth вне официальных клиентов может нарушать ToS
OpenAI/Anthropic — риск ограничения аккаунтов ненулевой. Шлюз маскируется под
официальный Codex CLI (`disable-codex-cloaking: false`), но гарантий нет.
Лимиты подписок общие с «ручным» Codex CLI / Claude Code пользователя.

## Когда применять

- Пользователь хочет, чтобы Hermes работал по своей подписке Claude Pro/Max
  и/или ChatGPT (одной или нескольких), а не по платному API-ключу.
- Один аккаунт постоянно упирается в недельный лимит и работа встаёт.
- Пересобрать/починить шлюз после пересоздания контейнера.

## Термины и пути (обобщённые — не копируй чужие)

| Сущность | Значение |
|---|---|
| `HERMES_HOME` | `~/.hermes` (проверь: `echo $HERMES_HOME`; в контейнерах часто другое) |
| Каталог шлюза | `$HERMES_HOME/cliproxy/` — бинарь, `config.yaml`, `auths/`, `logs/`, `src/` (исходник), `VERSION`, `client.key` |
| Одобренная версия шлюза | `$RAW/scripts/cliproxy-approved.txt` — тег и точный коммит; ставим и обновляемся ТОЛЬКО на неё |
| Скрипты | `$HERMES_HOME/scripts/` |
| s6-сервис | `$HERMES_HOME/s6-services/cliproxy/run` → живое `/run/service/cliproxy` |
| systemd | `~/.config/systemd/user/cliproxy.service` |
| Порт | `127.0.0.1:8317` (env `CLIPROXY_URL` в скриптах) |

## Процедура установки с нуля

### 1. Собери шлюз из исходников (root не нужен)

Не бери релизный бинарь: шлюз держит OAuth-токены аккаунтов. Собираем сами из
исходника ОДОБРЕННОЙ версии (`cliproxy-approved.txt`: тег + точный коммит).

```bash
export HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
# logs/ создаём заранее: иначе шлюз пишет логи ВНУТРЬ auths/ — к токенам и в бэкап
mkdir -p "$HERMES_HOME/cliproxy/auths" "$HERMES_HOME/cliproxy/logs" "$HERMES_HOME/scripts" && chmod 700 "$HERMES_HOME/cliproxy/auths"
cd "$HERMES_HOME/scripts"
for f in install_go.sh cliproxy_audit_hosts.sh cliproxy-known-hosts.txt cliproxy-approved.txt; do
  curl -fsSL "$RAW/scripts/$f" -o "$f"
done
chmod +x install_go.sh cliproxy_audit_hosts.sh
# Go: официальный архив в ~/go с проверкой SHA-256 по go.dev (root не нужен);
# если Go уже есть — ничего не делает. GOPATH держим отдельно от GOROOT.
sh ./install_go.sh
export GOPATH=$HOME/gopath; export PATH=$HOME/go/bin:$GOPATH/bin:$PATH
go version
TAG=$(sed -n 's/^tag=//p' cliproxy-approved.txt); COMMIT=$(sed -n 's/^commit=//p' cliproxy-approved.txt)
echo "CLIProxyAPI $TAG (одобренная)"
# Исходник — в ПОСТОЯННУЮ папку: $TMPDIR на серверах часто пуст (путь превратился бы
# в /cliproxy-src), а для аудита при обновлении дерево нужно сохранить.
SRC="$HERMES_HOME/cliproxy/src"
rm -rf "$SRC" && git -c advice.detachedHead=false clone -q --depth 1 --branch "$TAG" https://github.com/router-for-me/CLIProxyAPI "$SRC"
cd "$SRC"
if [ "$(git rev-parse HEAD)" = "$COMMIT" ]; then echo "коммит $TAG совпал с одобренным"; else echo "СТОП: тег $TAG указывает не на одобренный коммит"; fi
# аудит сети: печатает только адреса, которых нет в эталоне; пустой вывод = ок
sh "$HERMES_HOME/scripts/cliproxy_audit_hosts.sh" "$SRC"
go build -trimpath -ldflags "-s -w" -o "$HERMES_HOME/cliproxy/cli-proxy-api" ./cmd/server/
echo "$TAG" > "$HERMES_HOME/cliproxy/VERSION"
```

Две остановки, после которых НЕ продолжай, а покажи пользователю вывод:
- `СТОП: тег … указывает не на одобренный коммит` — тег у авторов перевесили на
  другой код. Не собирай.
- аудит вывел «Незнакомые адреса…» — в исходнике появились сетевые адреса, которых
  нет в эталоне `cliproxy-known-hosts.txt` (там все адреса одобренной версии,
  разложенные по назначению). Собирай только с явного согласия пользователя.

Сборка идёт 3–10 минут (Go сам докачает нужный toolchain и зависимости) —
запускай фоном с уведомлением, а не в коротком таймауте.

Свежее одобренной (последний релиз у авторов) ставь, только если пользователь
прямо попросил: тогда вместо `TAG`/`COMMIT` из файла возьми последний релиз
(`git ls-remote --tags --refs --sort=-v:refname https://github.com/router-for-me/CLIProxyAPI 'v*' | head -1`),
а всё, что выдаст аудит, покажи ему до сборки.

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

`max-retry-credentials: 0` — шлюз пробует все аккаунты пула; при добавлении
аккаунтов ничего менять не нужно. Секрет management-ключа
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
sed -i "s|%h/.hermes|$HERMES_HOME|g" ~/.config/systemd/user/cliproxy.service
systemctl --user daemon-reload && systemctl --user enable --now cliproxy && loginctl enable-linger $USER
```

Нет ни s6, ни systemd (например, обычный Docker-контейнер без супервизора) —
запусти шлюз фоновым процессом агента из `$HERMES_HOME/cliproxy`:
`./cli-proxy-api --config config.yaml --local-model` и поставь крон-сторож из шага 7.

Проверка: `curl -s 127.0.0.1:8317/healthz` → `{"status":"ok"}`, а
`curl -s -H "Authorization: Bearer $(cat $HERMES_HOME/cliproxy/client.key)" 127.0.0.1:8317/v1/models`
→ `{"data":[],...}` (список пуст, пока нет ни одного аккаунта — это норма).

Шлюз запускается с флагом `--local-model`: список моделей берётся вшитый в
собранную версию, а не скачивается с серверов авторов каждые 3 часа. Новые модели
появляются вместе с обновлением шлюза до новой одобренной версии. Нужна модель
раньше — убери флаг из run-файла (или юнита) и перезапусти шлюз.

### 4. Вход в аккаунты (по одному)

Шлюз подхватывает новые аккаунты без рестарта. Аккаунтов может быть сколько
угодно, в любой комбинации: только Claude, только ChatGPT или оба.

#### Claude Pro/Max

```bash
cd $HERMES_HOME/cliproxy && ./cli-proxy-api --config config.yaml --claude-login --no-browser
```

Запусти фоновым PTY-процессом (процесс ждёт ввод ~3–4 минуты и умирает —
всё делай быстро). Шлюз напечатает подсказку про `ssh -L ...` — её
пользователю НЕ показывай, туннель не нужен. Нужна только длинная ссылка
`https://claude.ai/oauth/authorize?...` из строки «Visit the following URL».
Пользователю, пошагово:

1. Открой ссылку в браузере, войди в НУЖНЫЙ аккаунт Claude, нажми **Authorize**.
2. Браузер перейдёт на `http://localhost:54545/callback?code=...&state=...` и
   покажет ошибку «не удаётся открыть страницу» — так и должно быть.
3. Скопируй из адресной строки ВЕСЬ адрес и пришли мне.

Как только адрес пришёл — сразу подай его в stdin процесса (строка
`Paste the Claude callback URL`). `state` в адресе должен совпасть со ссылкой
этого же запуска, иначе `ErrInvalidState` — тогда просто запусти вход заново.
Готово, когда в `auths/` появился `claude-<email>.json`. Следующий аккаунт
Claude — тем же способом (в браузере сначала выйти из Claude или инкогнито).

#### ChatGPT Plus/Pro (device-code)

```bash
cd $HERMES_HOME/cliproxy && ./cli-proxy-api --config config.yaml --codex-device-login
```
Запусти фоновым PTY-процессом, вытащи из вывода строки `Codex device URL:`
(`https://auth.openai.com/codex/device`) и `Codex device code:` (`XXXX-XXXX`),
отдай пользователю пошагово: открыть ссылку → войти в НУЖНЫЙ аккаунт ChatGPT →
ввести код.
Код живёт 15 минут; истёк — запусти заново. Auth-файл `auths/codex-<id>-<email>.json`
появится сам; шлюз подхватывает новые файлы без рестарта. Повтори для каждого
аккаунта (пользователю: инкогнито или выйти из ChatGPT между логинами).

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
# тот же ключ — в переменную окружения Hermes (.env): её читают плагин-провайдер
# `pool` (порядок моделей, ниже) и `claude-pool`
hermes config set CLIPROXY_KEY "$KEY"
# какие модели реально есть у вошедших аккаунтов:
curl -s -H "Authorization: Bearer $(cat $HERMES_HOME/cliproxy/client.key)" 127.0.0.1:8317/v1/models | grep -o '"id":"[^"]*"'
```

Выбери модель по умолчанию ИЗ ЭТОГО СПИСКА (имена ниже — примеры, у разных
тарифов и версий шлюза они отличаются). Пусть `MODEL` — выбранное имя:

```bash
MODEL=claude-sonnet-5        # или gpt-..., что есть в списке выше
hermes config set providers.pool.default_model "$MODEL"
# сделать пул основной моделью Hermes (без этого Hermes остаётся на старом провайдере):
hermes config set model.provider pool
hermes config set model.base_url http://127.0.0.1:8317/v1
hermes config set model.default "$MODEL"
# короткие имена для /model — по одному на каждую нужную модель из списка:
hermes config set model_aliases.pool-sonnet.model claude-sonnet-5
hermes config set model_aliases.pool-sonnet.provider pool
```
Предупреждение «not a recognized config key» для `model_aliases` — норма.
Уже открытые чаты остаются на прежней модели — новый чат или `/model pool-sonnet`.

**Провайдер нужен РОВНО ОДИН — `pool`.** Аккаунты ChatGPT/Codex и аккаунты
Claude и так живут в одном шлюзе (один auth-dir, одна ротация), а дверь
`chat_completions` обслуживает ОБЕ семьи моделей: tool-calls, поле
`reasoning_content` и prompt-кэш работают и для `claude-*`, и для `gpt-*`.
Заводить второй провайдер под Anthropic-протокол не надо — это дублирование
одного и того же пула. Есть Claude-аккаунты — просто добавь их алиасы к тому
же провайдеру (пример для ChatGPT; имена — из `/v1/models`):

```bash
hermes config set model_aliases.pool-astra.model gpt-6-astra
hermes config set model_aliases.pool-astra.provider pool
hermes config set model_aliases.pool-opus.model claude-opus-5
hermes config set model_aliases.pool-opus.provider pool
```

Если какому-то стороннему скрипту нужна именно Anthropic Messages-дверь
(`POST /v1/messages`) — пусть резолвит тот же `pool` и сам срезает `/v1`
с `base_url`; отдельный провайдер ради этого не заводится.

**Порядок моделей в списке.** `/v1/models` отдаёт модели в порядке обхода
map внутри шлюза — он случайный и меняется от рестарта к рестарту, конфигом
шлюза не управляется. Порядком `model_aliases` это НЕ чинится: алиасы — это
короткие имена для `/model <имя>`, на список в пикере они не влияют вообще.

Чтобы задать порядок, нужен плагин-провайдер: его курируемый список идёт в
пикере ПЕРЕД живым, а модели, которых в списке нет, дописываются следом —
новая модель в шлюзе не потеряется. Создайте два файла:

`$HERMES_HOME/plugins/model-providers/pool/plugin.yaml`

```yaml
name: pool-provider
kind: model-provider
version: 1.0.0
description: Единый пул подписок с фиксированным порядком моделей
```

`$HERMES_HOME/plugins/model-providers/pool/__init__.py`

```python
from providers import register_provider
from providers.base import ProviderProfile

# Порядок строк = порядок в пикере. Менять только здесь.
POOL_MODELS = (
    "claude-sonnet-5", "claude-opus-5",      # сначала одна семья,
    "gpt-6-astra", "gpt-5.6-sol",            # потом другая — не вперемешку
)

register_provider(ProviderProfile(
    name="pool",
    display_name="Pool",
    api_mode="chat_completions",
    auth_type="api_key",
    base_url="http://127.0.0.1:8317/v1",
    env_vars=("CLIPROXY_KEY",),
    fallback_models=POOL_MODELS,
    supports_prompt_cache_key=True,
))
```

Подставьте свои модели — `curl` к `/v1/models` покажет доступные. Проверка
порядка (работает и в скрипте; `hermes model` для этого не годится — он
требует живой терминал и в пайпе падает):

```bash
HERMES_PY=$(for c in \
    "$(dirname "$(readlink -f "$(command -v hermes)")")/python3" \
    "$HERMES_HOME/.venv/bin/python3" \
    "$HOME/.hermes/.venv/bin/python3"; do
  [ -x "$c" ] && "$c" -c 'import hermes_cli' 2>/dev/null && { echo "$c"; break; }
done)
"$HERMES_PY" -c "from hermes_cli.models import provider_model_ids
for m in provider_model_ids('pool', force_refresh=True): print(m)"
```

Модели должны выйти ровно в том порядке, что задан в `POOL_MODELS`. Плагин
подхватывается при следующем старте Hermes; перезапускать шлюз не нужно.
В интерактивном терминале тот же список можно увидеть через `hermes model`.

Кроны Hermes: `hermes cron edit <job_id> --provider pool --model <модель>` —
тогда они не встают, когда один аккаунт в лимите. Проверка: `/model pool-sonnet`.

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

Claude Code через пул: `curl -fsSL $RAW/scripts/claude-pool.sh -o
$HERMES_HOME/scripts/claude-pool.sh && chmod +x ...`; запуск `claude-pool`,
модель через `CLAUDE_POOL_MODEL=...` — принимаются и `claude-*`, и `gpt-*`,
и любые другие модели из `/v1/models` вашего пула. Предупреждение Claude Code
«unknown model» на не-Anthropic моделях безобидно.

### 7. Скрипты и кроны Hermes

```bash
cd $HERMES_HOME/scripts
for f in codex_pool_report.py codex_pool_alerts.sh codex_pool_backup.sh cliproxy-watchdog.sh cliproxy_update_check.py cliproxy_audit_hosts.sh cliproxy-known-hosts.txt cliproxy-approved.txt install_go.sh; do
  curl -fsSL $RAW/scripts/$f -o $f && chmod +x $f
done
```
Скрипты читают `HERMES_HOME`; если у крона его нет в окружении — задай
`CLIPROXY_AUTH_DIR` / `CLIPROXY_URL` явно.

Кроны (все `no_agent`, доставка в мессенджер пользователя; пустой stdout = молчание):

| Имя | Расписание | Скрипт | Смысл |
|---|---|---|---|
| `cliproxy-watchdog` | каждые 2 мин | `cliproxy-watchdog.sh` | поднять шлюз после падения/пересоздания контейнера: другого автозапуска в контейнере нет, так что простой — не больше 2–3 минут |
| `codex-pool-morning` | 1 раз утром | `codex_pool_report.py` | квоты и ресеты по каждому аккаунту |
| `codex-pool-alerts` | 1 раз утром | `codex_pool_alerts.sh` | только проблемы: все в лимите / 401 / окно >90% |
| `codex-pool-backup` | ночью | `codex_pool_backup.sh` | tar.gz токенов, хранятся 3 последние копии |
| `cliproxy-update-check` | раз в неделю | `cliproxy_update_check.py` | в репозитории скилла одобрена новая версия шлюза → сообщение |

Создать все пять (`--deliver` — куда слать: `telegram`, `origin`, `local`…;
время в cron-выражении — по часам сервера, обычно UTC):

```bash
hermes cron create "every 2m"    --name cliproxy-watchdog     --script cliproxy-watchdog.sh     --no-agent --deliver telegram
hermes cron create "53 5 * * *"  --name codex-pool-morning    --script codex_pool_report.py     --no-agent --deliver telegram
hermes cron create "47 5 * * *"  --name codex-pool-alerts     --script codex_pool_alerts.sh     --no-agent --deliver telegram
hermes cron create "41 3 * * *"  --name codex-pool-backup     --script codex_pool_backup.sh     --no-agent --deliver telegram
hermes cron create "7 7 * * 1"   --name cliproxy-update-check --script cliproxy_update_check.py --no-agent --deliver telegram
```

Поле `script` крона НЕ принимает аргументов (вся строка = путь) — поэтому есть
обёртка `codex_pool_alerts.sh`. Алерты чаще раза в сутки — спам; не надо.

### 8. Кнопка лимитов в Hermes Desktop (опционально)

Плагин [hermes-codex-limits](https://github.com/artemiimillier/hermes-codex-limits)
показывает остаток по КАЖДОМУ аккаунту пула прямо рядом с выбором модели. Он
только читает auth-файлы этого пула и ничего в нём не меняет.

```bash
hermes plugins install artemiimillier/hermes-codex-limits --enable
```

Интерфейсную часть пользователь ставит у себя в Hermes Desktop: Capabilities →
Plugins → Install from Git → та же ссылка → отметить Desktop UI. Лимиты пула
видны сразу, перезапуск Hermes не нужен.

## Обновление шлюза — до одобренной версии, по фразе «обнови пул»

Крон `cliproxy-update-check` сообщает, когда в репозитории скилла одобрена новая
версия. Обновляйся ИМЕННО на неё:

1. Скачай свежие `cliproxy-approved.txt`, `cliproxy-known-hosts.txt`,
   `cliproxy_audit_hosts.sh` из `$RAW/scripts/` в `$HERMES_HOME/scripts/`;
   `TAG`/`COMMIT` — из `cliproxy-approved.txt`.
2. `cd $HERMES_HOME/cliproxy/src && git fetch --depth 1 origin tag "$TAG" && git checkout "$TAG"`,
   затем сверь `git rev-parse HEAD` с `COMMIT` (не совпал — СТОП, как в шаге 1).
   Папки `src` нет — ставили старой версией скилла: склонируй по шагу 1.
3. Аудит: `sh $HERMES_HOME/scripts/cliproxy_audit_hosts.sh $HERMES_HOME/cliproxy/src` — пусто = ок.
4. Собери рядом (3–10 минут, фоном): `go build -trimpath -ldflags "-s -w" -o $HERMES_HOME/cliproxy/cli-proxy-api.new ./cmd/server/`
5. Подмена на ЖИВОМ сервисе (обычный `cp` поверх даёт `Text file busy`):
   `mv cli-proxy-api cli-proxy-api.old-<старая версия>` → `mv cli-proxy-api.new cli-proxy-api` →
   `kill <PID>` — s6/systemd поднимет новый. PID бери ОТДЕЛЬНОЙ командой: подстановка
   `$(pgrep ...)` и `pkill -f` в той же строке могут поймать твой собственный шелл.
6. Проверка: `healthz`, `/v1/models`, настоящий запрос. Не работает — верни
   `.old-<версия>` на место и снова `kill <PID>`.
7. `echo "$TAG" > $HERMES_HOME/cliproxy/VERSION`; старый `.old-*` удали через пару дней.

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
2. `ls $HERMES_HOME/cliproxy/auths/ | grep -cE '^(codex|claude)-.*\.json$'` = число вошедших аккаунтов.
3. `curl -s -H "Authorization: Bearer $(cat $HERMES_HOME/cliproxy/client.key)" 127.0.0.1:8317/v1/models` — нужные модели есть.
4. Настоящий запрос: `curl -s 127.0.0.1:8317/v1/chat/completions -H "Authorization: Bearer <key>" -H 'Content-Type: application/json' -d '{"model":"<модель из /v1/models>","messages":[{"role":"user","content":"скажи ok"}]}'` → ответ с текстом.
5. `python3 $HERMES_HOME/scripts/codex_pool_report.py` — все аккаунты 🟢 или с понятной причиной.
6. В Hermes: новый чат (или `/model pool-sonnet`), короткий вопрос → ответ; в логах шлюза виден запрос.
7. Сервис переживает `kill <pid>` (поднялся сам за ~5 с).
8. `hermes cron list` — пять кронов пула, сторож `cliproxy-watchdog` — каждые 2 минуты.
