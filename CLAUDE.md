# CLAUDE.md — siteadaptor-platform

Claude Code загружает этот файл автоматически в начале каждой сессии (память
проекта). **Держим актуальным:** после каждой завершённой задачи и каждого нового
решения — обновляем разделы «Сделано» / «Конвенции» / «Дальше». Глубокие детали —
в `docs/` (ссылки в §6).

## 1. Что это
Мультитенантный Django 5.1 SaaS для маленьких оффлайн-бизнесов DACH (пекарни,
мясные, кафе, ритейл): мини-сайт на субдомене, каталог, акции/резервирование с
anti-oversell, инструменты лояльности/ваучеров, локальный агрегатор (в планах),
тариф ~39 €/мес.

Стек: Django 5.1, django-tenants (схема-на-тенанта, Postgres 16), Redis 7,
Celery 5 (worker+beat), HTMX/Alpine/Tailwind, django-allauth, dj-stripe,
django-unfold (admin), django-storages (S3/Hetzner), Caddy 2 (on-demand TLS).
Python 3.12, менеджер uv.

## 2. Архитектура / где что
- `config/` — settings/{base,development,production,test}.py, urls_tenant.py
  (субдомены бизнеса), urls_public.py (онбординг + admin на public), celery.py.
- `apps/core/` — fsm.py (StateMachine), jobs.py (idempotent_task), audit.py,
  models.py (Timestamped/I18n/SoftDelete-миксины), pagination.py, health.py.
- `apps/tenants/` — Tenant, Domain; services.create_business; формы онбординга и
  настроек. Tenant: контакты, право, billing-поля, auto_redeem_on_scan.
- `apps/catalog/` — Product/Category, images.py, CRUD.
- `apps/imports/` — мастер импорта CSV/Excel.
- `apps/promotions/` — ядро акций: models, state_machine (PromotionSM/
  ReservationSM), services (reserve/confirm/fulfill/cancel/expire + anti-oversell,
  vouchers, loyalty), tasks (beat), notifications, views (кабинет), public_views
  (витрина).
- `apps/billing/` — Sprint 5: SubscriptionSM, plans, (далее) services/webhooks/
  middleware/tasks. **SHARED** (статус подписки — на Tenant в public-схеме).
- `apps/audit/`, `apps/integrations/webhooks/` — SHARED.
- `scripts/deploy.sh`, `scripts/dev-services.sh`, docker-compose.prod.yml, caddy/.

Главный документ по архитектуре: **`docs/platform-core-architecture.md`**.

## 3. Сделано
- Phase 1: мультитенантность, audit, soft-delete, cursor-пагинация,
  webhooks-scaffold, деплой Hetzner (single).
- Sprint 2: каталог (товары, категории, изображения, импорт CSV/Excel).
- Sprint 3: акции + резервирование (FSM, anti-oversell, beat, кабинет, витрина,
  письма, DSGVO авто-очистка PII).
- Витрина 2.0: цены/скидки/медиа, редизайн, A11y, DE/EN, мобильный grid 1/2,
  импорт акций, настройки бизнеса + Impressum/Datenschutz/Widerruf, отписка.
- QR: маркетинговый + канальный (атрибуция) + персональный + погашение в
  кабинете + авто-погашение по скану.
- Инструменты: waitlist, ваучеры, лояльность (штампы), аналитика акций.
  → всё в `main` (commit 6dd8bc3), задеплоено на dev-сервере.
- Миграции по порядку: promotions 0001…0008, tenants 0001…0004.
- **Sprint 5 — Биллинг/Stripe (✅ в `main`, commit 485c0ed):** apps.billing (SHARED),
  SubscriptionSM, Stripe services + свой webhook-эндпоинт, гейтинг middleware
  (suspended/trial_expired = read-only) + баннер, billing-страница (Checkout +
  Customer Portal), beat-просрочка + напоминания. Без новых моделей/миграций.
  Stripe-ключи — `.env.prod` по `docs/billing-stripe-setup.md` (оплата после ключей).
- **Sprint 4 — Авто-публикация + локальный агрегатор (✅ в `main`, commit eb1e8c0):**
  агрегатор `AggregatorListing` (SHARED) + sync-задача/бэкофилл (`sync_aggregator`) +
  хук PromotionSM; публичные страницы `/entdecken/<city>/[<type>/]`; фреймворк
  каналов Channel/Publication/SM (TENANT, адаптер `log`); кабинет каналов. Миграции
  `aggregator/0001` + `publishing/0001`. Деплой: `deploy.sh single` + один раз
  `manage.py sync_aggregator`.
- **Sprint 6 — Уведомления (✅ в `main`, commit f68c6a6):** apps.notifications
  (TENANT): Notification + NotificationSM (unique dedupe_key = БД-гарантия без
  дублей), generic-доставка send_notification, письма брони через Notification,
  HTML+text multipart шаблоны, waitlist «снова в наличии» (одно письмо на
  запись). Resend включается ключом в проде. Миграция `notifications/0001` —
  нужен деплой. S6.5 (WhatsApp) — опционально, по готовности Meta-провайдера.
- **Track B — DE quick wins (в работе):** B1 GBP-адаптер — ветка
  `claude/track-b1-gbp` (тип канала google_business, Google Posts, конфиг в
  кабинете; настройка — `docs/gbp-setup.md`). Дальше B2–B5 по roadmap §Track B.

## 4. Маршруты
- Корень субдомена `/` = витрина; акция `/p/<uuid>/`, бронь `/p/<uuid>/reserve/`,
  waitlist `/p/<uuid>/waitlist/`, подтверждение `/r/<code>/`, QR `…/qr.svg`,
  отписка `/u/<token>/`, право `/impressum /datenschutz /widerruf`.
- Кабинет (под логином): `/dashboard/`, `/catalog/`, `/promotions/` (+ redeem/,
  vouchers/, loyalty/, analytics/), `/imports/`, `/dashboard/settings/`.
- Django admin — только на public (urls_public).

## 5. Конвенции
- **Проверки — на git (GitHub Actions).** Локальный прогон — ФОЛБЭК, только если
  CI на git показал красный (для воспроизведения/отладки).
- CI (`.github/workflows/ci.yml`) гоняется на push в `main` и `claude/**` + на PR:
  `ruff check .`, `ruff format --check .`, `pytest -ra` на Postgres16 + Redis7.
- **Рабочий цикл (по подзадачам):** крупную задачу разбиваем на подзадачи и
  показываем разбивку владельцу. Одна подзадача = один инкремент: ветка
  `claude/<кратко>` → push → **CI на git зелёный** → **чекпоинт с владельцем**
  (показать, что дальше; опц. деплой на сервер `./scripts/deploy.sh single` и
  проверка там) → следующая подзадача. Создание/мерж PR через GitHub API
  недоступны (403) → в `main` мержим git-only push (main не защищён, FF/cherry-pick).
- После мержа с миграциями — деплой на сервере (вручную владельцем):
  `git pull origin main && ./scripts/deploy.sh single`.
- Миграции последовательные; новые TENANT-приложения — в base.py TENANT_APPS
  (test.py подхватит как SHARED). Billing — SHARED.
- Тесты django-tenants: вьюхи через RequestFactory; Tenant — через TenantFactory
  (`auto_create_schema=False`).
- Смена статусов — только через FSM `.apply()`; внешние действия (письма/
  публикации) — через Celery + idempotent_task / dedupe_key.
- Секреты не коммитить; идентификатор модели не светить в артефактах репозитория.
- Замечания «на будущее»/отложенные решения — сразу в `docs/roadmap-next-sprints.md`
  §«Отложено / заметки на будущее» (чтобы не терять между сессиями).
- Локальные службы для фолбэка: `bash scripts/dev-services.sh` (Postgres + Redis +
  роль/БД). Автоматически — SessionStart-хук (`.claude/hooks/session-start.sh`).

## 6. Документация (docs/)
- **`roadmap-next-sprints.md`** — ГЛАВНЫЙ план (Sprint 5/4/6, Hardening, Phase 2).
- **`platform-core-architecture.md`** — архитектура ядра; `full-platform-vision.md`.
- `references/patterns/` — state-machine, anti-oversell, notification-dedupe,
  audit-log, soft-delete, cursor-pagination, webhook-hmac-signing,
  csv-import-wizard, magic-link-auth.
- `DEVELOPMENT-GUIDE.md`, `phase1-*.md`, `monetization-unit-economics.md`,
  `hetzner-claude-code-setup.md`.
- `billing-stripe-setup.md` — настройка Stripe (ключи, Price 39 €, webhook) в `.env.prod`.

## 7. Дальше (порядок из roadmap)
1. **Sprint 5 — Биллинг/Stripe** (в работе): dj-stripe, SubscriptionSM, Checkout +
   Customer Portal, идемпотентные webhooks, гейтинг (suspended = read-only), beat
   по триалам (индекс `tenant_substatus_trial_idx`).
2. Sprint 4 — авто-публикация + локальный агрегатор (apps.publishing Channel/
   Publication+FSM, хуки PromotionSM, apps.aggregator по city/business_type).
3. Sprint 6 — уведомления (Notification + БД-dedupe, Resend в проде, опц. WhatsApp).
4. **Track B — быстрые победы DE-рынка** (после Sprint 6, порядок утверждён):
   B1 Google Business Profile адаптер → B2 «Überraschungstüte»/анти-waste →
   B3 recurring promotions + пресеты по вертикалям → B4 QR-постер PDF →
   B5 local SEO (schema.org). Детали — roadmap §Track B.
5. Hardening (параллельно): Resend-ключ, отдельный Postgres, ротация секретов,
   бэкапы, Sentry, нагрузочный тест anti-oversell, DSGVO-ревизия, rate-limit.
6. Phase 2 — мульти-доменные агрегаторы, SEO, клиентские аккаунты, монетизация
   портала, платежи клиента, отзывы, поиск, мобайл.

UX-принцип (владелец, 2026-06-09): для конечного потребителя — максимально
просто, понятно и без навязчивости (бронь без аккаунта, one-click отписка,
Double-Opt-In по UWG §7 до маркетинговых рассылок, без трекинг-куки на витрине).

## 8. Деплой / инфраструктура
- Сервер Hetzner `siteadaptor-dev` (178.105.206.209), режим single (bundled
  Postgres + Redis + Caddy). Деплой: `git pull origin main && ./scripts/deploy.sh single`.
- Домен Hostinger (A-записи), Caddy on-demand TLS. Почта Resend (anymail) — пока
  console-fallback, ключ в проде не прописан.
- `.env.prod`, БД и медиа — только на сервере (в git их нет).

## 9. Заметки
- Репозиторий: `yppolyakov-wq/siteadaptor-platform` (старый аккаунт adaptor2024
  приостановлен по ToS; история/ветки перенесены).
- Перед боевым запуском: настроить Resend, вынести Postgres на отдельный сервер,
  перегенерировать секреты.
