# T-8.10h «Общий бот платформы + свой бот по желанию» — план (2026-10-19)

План — агент planner (сверено с кодом). Решение владельца: старт с общего бота платформы,
свой бот — опция (своё имя для клиентов). ИИ — только после регистрации.

## 0. Факты из кода
- `apps.telegram` — TENANT-приложение; `TelegramBot` — строка на схему; вебхук только на
  хосте тенанта. Прецедент SHARED-бота — `PortalBot` (`aggregator/telegram_bot.py`).
- Привязка владельца — `site_config["notify"]` (`owner_chat_id`); у личного чата
  chat.id == user.id для любого бота → различается только «через какой бот слать».
- `telegram_promo` от бота использует только `.token`; привязки к своему боту: Celery-тела
  грузят `TelegramBot` из схемы, `is_owner_private`, callback `tp:…` разрешается в тенанте
  запроса, ✏️ веб-форма качает фото через `active_bot()` (а `file_id` привязан к БОТУ).
- `send_to_owner`/`_send_telegram` шлют только своим ботом.
- Попутный дефект: `core/personal_channels.py:44` читает `owner_chat_id` с верхнего уровня
  `site_config` (лежит в `notify`) — привязанный владелец без своего бота выглядит неготовым.

## 1. Решения
- Токен — `secrets.get_or_setting("telegram_platform_bot_token", …)`; env
  `TELEGRAM_PLATFORM_BOT_USERNAME`/`…_WEBHOOK_SECRET`/`…_ENABLED=False`.
- Вебхук на public: `tg/plattform/<secret>/`, секрет в пути + заголовок (compare_digest),
  тело только ставит Celery-задачу с дедупом по `update_id`.
- SHARED-апп `apps.platform_bot`, модель `OwnerTelegramLink(tg_user_id BigInt, tenant FK,
  is_active, via signup|cabinet, selected_at, blocked_at)`, unique (tg_user_id, tenant).
  Единственный писатель связи и зеркала `notify.owner_chat_id`+`owner_bot` — `links.bind/unbind`.
- `apps/telegram/bots.py::BotRef(kind, token, username)`; черновик помнит `draft["bot"]`.
- Callback общего бота `pb:…` → кэш-индекс `tgplat:ref:<tg_user_id>:<ref>` → схема
  (из индекса, не из «текущего бизнеса»); `tp:` своего бота байт-в-байт.
- Клиенты на общий бот не попадают (без TelegramLink/Mini App/групп; группа → leaveChat).
- Регистрация — автомат в кэше (2 ч): акция (правила, без ИИ) → имя → тип → город →
  район → адрес → телефон → e-mail → каталог → «Anlegen»; каждое поле — валидаторами
  `QuickStartForm`; лимиты per id + глобальный; `email_pending` до подтверждения почты;
  вход в кабинет — ссылкой из письма.
- DSGVO: храним только `tg_user_id` + связь; `/daten_loeschen`.

## 2. Инкременты
- **H-0** план + замки текущего поведения (callback-формат своего бота, уведомление без метки).
- **H-1** абстракция бота (без миграций, поведение прежнее; kwargs задач с дефолтами).
- **H-2** ⚠️ миграция `platform_bot/0001`: модель, вебхук, онбординг-заглушка,
  команда `telegram_platform_setup [--apply]`.
- **H-3** подключение существующего бизнеса одной кнопкой (одноразовая ссылка 15 мин, только
  owner, письмо «Telegram verbunden»), `/geschaeft` для нескольких бизнесов, фикс
  personal_channels.
- **H-4** акции из общего бота для привязанного бизнеса.
- **H-5** регистрация через общий бот.
- **H-6** DSGVO/i18n/доки + финальное ревью.

## 3. Риски
Расхождение источников привязки (один писатель) · утечка deep link (TTL, одноразовость, письмо)
· `file_id` привязан к боту (`draft["bot"]`) · спам-регистрации (лимиты, email_pending) ·
старые задачи в очереди (kwargs с дефолтами).

## 4. Ops владельцу
BotFather: создать бот платформы (privacy mode ВКЛ) → `.env.prod` (токен, username, секрет
`openssl rand -hex 24`, `ENABLED=1`) → деплой → `telegram_platform_setup --apply`;
письма — только с `RESEND_API_KEY`; абзац о боте в Datenschutzerklärung.

## 5. Решения по умолчанию (владелец может переиграть)
Адрес и телефон в регистрации через бот обязательны (как в вебе); вход в кабинет —
только ссылкой из письма. Открыто: имя/username бота (ops).
