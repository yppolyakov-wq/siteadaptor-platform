# Ключи интеграций и секреты — управление

Где живут ключи внешних сервисов, что шифруется, что в `.env`, и как добавить
новый ключ без правки кода. Источник правды по секретам платформы.

## 1. Два уровня секретов

### A. Платформенные ключи (общие для всей платформы)
Это ключи, которые **наш код читает в рантайме** (OAuth-клиенты интеграций и т.п.).
Хранятся зашифрованными в БД (`apps.secrets.PlatformSecret`, public-схема) и
редактируются в **админке** (unfold, на `admin.` / public) — без правки файлов.

- Шифрование: **Fernet** (`apps/secrets/crypto.py`). Мастер-ключ —
  `SECRETS_ENCRYPTION_KEY` из `.env.prod`. Если не задан — выводится из
  `SECRET_KEY` (рабочий фолбэк для dev/CI; в проде задаём отдельный).
- В UI значение **write-only**: вводится в маскированное поле, в списке виден
  только признак «задан» + дата; пустой ввод не затирает сохранённое.
- Чтение в коде: `from apps.secrets import store` →
  `store.get_or_setting("ключ", "SETTINGS_ATTR")` — значение из админки
  перекрывает `.env`, иначе берётся `.env` (прод не ломается, пока не задан).

### B. Ключи на уровне бизнеса (per-tenant)
Токены подключений конкретного бизнеса (каналы публикации, Telegram-бот). Их
владелец вводит **в кабинете** (self-service), хранятся в схеме арендатора. В UI
маскируются (поле-пароль, пустой ввод не затирает) и **зашифрованы at-rest**
(Fernet, тот же мастер-ключ):
- `TelegramBot.token` — через `apps/secrets/fields.py::EncryptedTextField`
  (прозрачно: открытый текст в Python, шифротекст в БД).
- `Channel.config` секретные подключи (`refresh_token`/`access_token`/`bot_token`)
  — точечно (`apps/publishing/secrets.py`; остальные подключи не секретны).
- Толерантно к легаси: незашифрованные старые значения читаются как есть и
  шифруются при следующем сохранении (без отдельной data-миграции).

## 2. Как добавить платформенный ключ (в админке)
1. Войти в Django-админку на основном домене (public): `…/admin/`.
2. **Secrets → Platform secrets → Add**.
3. `key` — машинное имя (snake_case), `value` — сам секрет, `description` — текст.
4. Save. Значение зашифровано и больше не показывается.

Чтобы новый ключ начал использоваться, код должен его читать через
`store.get_or_setting(...)` (см. пример GBP в `apps/publishing/adapters.py::
_gbp_access_token`). Уже подключено: **Google OAuth** (GBP) —
`google_oauth_client_id`, `google_oauth_client_secret`.

## 3. Реестр ключей по интеграциям

| Интеграция | Уровень | Где задаётся | Имя ключа / переменной | Статус |
|---|---|---|---|---|
| Google Business Profile (OAuth-клиент) | A | админка → `.env` фолбэк | `google_oauth_client_id`, `google_oauth_client_secret` (env `GOOGLE_OAUTH_CLIENT_ID/SECRET`) | ✅ в сторе |
| Google Business Profile (refresh token) | B | кабинет Channels | `Channel.config.refresh_token` | per-tenant |
| Facebook / Instagram (Meta) | B | кабинет Channels | `Channel.config.page_id`/`access_token`, `ig_user_id` | per-tenant |
| Telegram-канал бизнеса | B | кабинет Channels | `Channel.config.bot_token`/`chat_id` | per-tenant |
| Pinterest | B | кабинет Channels | `Channel.config.access_token`/`board_id` | per-tenant |
| Telegram-бот бизнеса | B | кабинет `/dashboard/telegram/` | `TelegramBot.token` | per-tenant |
| Meta Graph API version | — | `.env` (не секрет) | `META_GRAPH_API_VERSION` (default v21.0) | env |
| Stripe (secret/publishable/webhook) | инфра | `.env.prod` | `STRIPE_*` | env (см. §4) |
| Stripe Connect | инфра | `.env.prod` | `STRIPE_CONNECT_CLIENT_ID` | env |
| Resend / SMTP (почта) | инфра | `.env.prod` | `RESEND_API_KEY` / `EMAIL_*` | env (см. §4) |
| Шифрование секретов | инфра | `.env.prod` | `SECRETS_ENCRYPTION_KEY` | env |

## 4. Почему Stripe и почта остаются в `.env`
Эти ключи читаются **сторонними библиотеками на старте процесса** (dj-stripe,
django-anymail), до того как доступна БД и схема. Читать их из БД на этапе
загрузки настроек — хрупко (chicken-and-egg, мульти-тенант). Поэтому инфра-ключи
(Stripe, почта, БД, `SECRETS_ENCRYPTION_KEY`) держим в `.env.prod`. В админку
переезжают только ключи, читаемые нашим кодом в рантайме (уровень A).

## 5. Мастер-ключ шифрования: генерация и ротация
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Положить в `.env.prod` как `SECRETS_ENCRYPTION_KEY=...`, перезапустить сервис.

- **Без ключа** значения шифруются ключом из `SECRET_KEY` — работает, но при смене
  `SECRET_KEY` секреты станут нечитаемыми (расшифровка вернёт пустую строку, не
  упадёт). Поэтому в проде задаём отдельный `SECRETS_ENCRYPTION_KEY`.
- **Ротация:** после смены `SECRETS_ENCRYPTION_KEY` сохранённые значения нужно
  ввести заново в админке (старый шифротекст не расшифруется новым ключом).

## 5a. In-app OAuth (подключение каналов одной кнопкой)
Вместо ручного ввода токенов — кнопка «Connect» в кабинете каналов
(`/dashboard/channels/`). Поток (`apps/publishing/oauth.py`): кабинет → провайдер
→ **единый callback на основном домене** `/oauth/<provider>/callback/` (подписанный
`state` несёт схему арендатора, обходит redirect-URI-на-субдоменах) → обмен code
на токен → токен в `Channel.config` зашифрованным.

- Готово: **Google Business Profile**, **Pinterest** (OAuth-A), **Meta FB+IG**
  (OAuth-B — один поток подключает обе; берёт первую страницу + её IG-аккаунт,
  page-токен не истекает).
- Платформенные креды OAuth-приложений (в админ-сторе / `.env`):
  `google_oauth_client_id`/`secret`, `pinterest_client_id`/`secret`,
  `meta_app_id`/`meta_app_secret`.
- В консоли провайдера зарегистрировать **redirect_uri** =
  `https://<основной-домен>/oauth/<provider>/callback/` (или `OAUTH_CALLBACK_BASE`).

## 6. Отложено
- OAuth: UI выбора страницы Meta при нескольких страницах (сейчас берём первую).
- Версионирование/аудит изменений секретов.
- ✅ Шифрование per-tenant токенов at-rest (`Channel.config`, `TelegramBot.token`)
  — сделано (см. §1.B).

См. также: `docs/gbp-setup.md`, `docs/meta-social-setup.md`,
`docs/billing-stripe-setup.md`.
