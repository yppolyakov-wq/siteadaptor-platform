# План: T-8.14 «Тематический портал» + T-8.28 «Бот портала v2» (2026-10-20)

Запрос владельца (2026-10-20): «Бот портала v2: поиск прямо в чате (тот же движок, что на
портале), кнопки разделов и районов, подписка «Folgen» из чата и сводка новых предложений
сообщением в Telegram вместо письма, переводы на 5 языков. T-8.14: тематический портал с
отбором по признакам — тогда бот такого портала сразу покажет только его тему.»
План — агент planner; решения по умолчанию приняты по рекомендации (§«Открытые вопросы»).

## 0. Факты из кода

- **Единого резолвера охвата портала нет.** Охват = пара `portal.city` + `portal.business_type`,
  руками передаваемая в `views.listings_for(...)` в ~30 местах (`portal_views.py`,
  `views._offer_pool/_offer_in_scope`, `reviews_views.py`, `mcp/handlers.py`,
  `district_liveness.py`, `follow_query.py`, `llms.py`, `open_feed.py`, `portal_home_blocks.py`).
- **Дыра:** `follow.items_for` для разделов/районов фильтрует только по `sub.city`, без
  `business_type` портала — сводка вертикального портала может прислать то, чего на нём нет.
- `apply_city_filters`/`search.apply_filters` умеют `city_category__in` и `city_tags__contains`.
- `search.execute(base_qs, …)` принимает готовый queryset → тема на базе = поиск получает её даром.
- `FollowSubscription.CHANNEL_TELEGRAM` уже есть; `build_digest` от канала не зависит.
- `PortalUser.email` уникален и обязателен — подписчика без почты нет.
- `PortalBot.token` открытым текстом; webhook ищет бота в БД до проверки заголовка; синхронно;
  английские msgid.
- `PortalStat.CHANNELS`, `SearchQueryLog.SURFACES` — закрытые choices (канал `telegram` = choices-миграция).
- Демо-портал Солингена — `seed_demo_tenants._ensure_city_portal`; отелей — `_ensure_hotel_portal`.

## A — T-8.14 «Тематический портал»

Решения: признаки темы — «любой из» (OR); разделы/категории — «любой из»; между осями — И;
пустая тема = прежнее поведение байт-в-байт; явный `?merkmal=`/`?kat=` пересекается с темой;
пустой `city` = весь регион; карточка бизнеса входит в тему, если подходит сама ИЛИ у бизнеса
есть предложение в теме.

- **A1** `apps/aggregator/portal_scope.py` — `Scope`, `scope_for`, `pool`, `apply`, `contains`;
  все пути чтения переведены на него. Без миграций, поведение прежнее.
  Замки: `test_portal_scope_single_entry` (AST-скан), `test_scope_refactor_parity`.
- **A2** ⚠️ миграция `aggregator/0034` (SHARED): `theme_tags`, `theme_categories`,
  `KIND_THEME`; `clean()` нормализует; админка. Замки: `test_theme_portal_no_leak[surface]`,
  `test_theme_merkmal_intersects`, `test_empty_theme_is_noop`, `test_theme_business_card_via_offer`,
  `test_facets_only_in_theme`.
- **A3** подписки/районы/кэши через `portal_scope` (заодно фикс дыры `business_type`).
  Замки: `test_digest_subset_of_scope`, `test_liveness_cache_key_per_theme`.
- **A4** демо `gesund-solingen.<base>` (`theme_tags` vegan/vegetarisch/bio/regional).
  Замок `test_demo_theme_portal_not_empty`.

## B — T-8.28 «Бот портала v2»

Решения: подписчик из Telegram — `PortalChat(bot, chat_id, user→PortalUser, locale,
blocked_at, last_seen_at)` unique(bot, chat_id), `PortalUser.email` nullable; согласие —
кнопка «✅ Ja, folgen» (UWG §7, доказательство `confirmed_at`+`source_host`), без письма;
канал атрибуции `telegram`; обработка асинхронно через Celery с дедупом `update_id`.

- **B1** ⚠️ миграция `aggregator/0035` (SHARED): `PortalChat`, email nullable, choices
  `telegram`. Общее с ботом платформы — в `apps/telegram/` (slim, locale_for, safe_send,
  set_commands). Пакет `apps/aggregator/portal_bot/`. Webhook: 404 до БД без заголовка;
  только личные чаты; из групп — leave; блок/разблок. `/start` с кнопками; немецкие msgid ×5;
  `/datenschutz`, `/daten_loeschen`. Замки: rejects-before-db, group, dedupe, strings,
  no-pii-logs, erase, emailless-user-never-hits-email-paths.
- **B2** поиск в чате тем же движком (`resolve_intent` + `search.execute` по `portal_scope.pool`),
  5 карточек, «Mehr» по токену в кэше (≤5 страниц), кнопки разделов (≤8) и районов, строгий
  разбор callback, лимит 20/мин, ссылки `ch=telegram`. Замки: same-as-portal, theme,
  callback-validated, links-carry-ch, stats-accepts-telegram.
- **B3** «Folgen» из чата: бизнес/раздел/район/поиск, подтверждение кнопкой, `/folgen` со
  списком и «Beenden», лимиты как в вебе. Замки: confirm-button, scope-inside-portal,
  unfollow-only-own, limits.
- **B4** сводка в Telegram: оба канала в `follow_digest`, отправка по каналу, ≤4096 символов,
  403 → `blocked_at`, 429 → retry. Замки: same-items-as-email, blocked-skipped, quiet-hours,
  dedupe-period.
- **B5** сроки хранения (beat: заблокирован > 30 дней / без подписок и активности 180 дней),
  `set_commands` при подключении, «Webhook setzen» в админке. Опционально B5b — шифрование
  `PortalBot.token`.

## Порядок и гейты

A1 → A2 → A3 → A4 → B1 → B2 → B3 → B4 → B5. Каждый срез: замки до кода → локальный гейт
(ruff, pytest, `i18n_quickcheck`, `template_comments`) → `django-reviewer` + `security-reviewer`
(+ `database-reviewer` на A2/B1) → зелёный CI → FF в `main`.

## Риски

A1 — широкий рефактор (паритет по pk + AST-скан). A2 — OR по тегам = несколько `@>` без GIN
(план запроса — database-reviewer). B1 — nullable email (замок). B3 — согласие в мессенджере.

## Ops после деплоя

Деплой → `migration_state` → `seed_demo_tenants` группой Солингена (тематический портал) →
админка `PortalBot`: «Webhook setzen» → privacy mode в @BotFather → строка про
Telegram-подписки в Datenschutzerklärung портала.

## Открытые вопросы владельцу (приняты рекомендации)

1. Признаки темы «любой из», между осями — И.
2. Хост демо — `gesund-solingen.<base>`.
3. Подписка в Telegram с кнопкой подтверждения, без письма (юр. вычитка).
4. Один подписчик на пару «бот + чат», без склейки с почтовым аккаунтом.
5. Шифрование `PortalBot.token` — отдельным срезом B5b.
6. Показы результатов в чате в статистике — нет в v1.

## Статус (2026-10-20)

- **T-8.14 ✅** A1–A4 + правки ревью (страница компании в теме, карточка компании по пулу
  без фильтров, резерв поддоменов порталов, отложено: GIN-индекс `city_tags`, избранное).
- **T-8.28 ✅** B1–B5 одним батчем: `apps/aggregator/portal_bot.py`, вебхук и задача,
  `PortalChat`, сводка в Telegram (`follow_digest.render_telegram`), сроки хранения
  (beat `purge-portal-bot-chats`). Шифрование токена бота (B5b) — не делали, в roadmap.
