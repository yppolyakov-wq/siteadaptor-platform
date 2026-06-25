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

## 3. Сделано — статус
Полная хронология завершённых задач — **`docs/build-log.md`** (извлечена из этого
файла 2026-06-22). Срез/оценка — **`docs/audit-2026-06-22.md`**. Здесь — только
верхнеуровневый статус:

- **Stage 1 (архетипы A1–A9 → ~100% «из коробки»)** — завершён: каталог/Click&Collect/
  доставка, бронь по времени и датам (Übernachtung), события/билеты, сметы Handwerker,
  Werkstatt, финансы (счета/DATEV/GoBD), агрегатор+порталы, отзывы+гео.
- **Stage 2 (Phase 2)** — частично: порталы, поиск/фильтры, отзывы, гео, органик-постинг
  (GBP/FB/IG/Telegram/Pinterest), in-app OAuth, Telegram-боты/Mini App. Осталось:
  PWA/push/Wallet (P2.8), импорт Shopify/Woo (M21), платная реклама (M23c).
- **Stage 3 («лёгкий ERP»)** — только архитектурные швы (`core.Membership`/роли,
  `Order.parent_order`/`supplier_tenant_schema`). Не начато: склад-леджер (M10),
  маркетплейс-корзина (M14), закупки (M12), dropshipping (M15), AI (M18),
  workflow-билдер (M19), drag-drop конструктор (M20).
- **Последнее:** **архетип A5 «Отель» — H1–H9 + бэклог роста G1–G11**. Помимо H-ядра
  (тарифы/питание, поиск, богатая карточка, промокоды/самоотмена, дети, Kurtaxe, SEO
  `Hotel`+Hausordnung, агрегатор отелей): **G1** Geschenkgutscheine, **G2** pre/post-stay,
  **G3** рассылки гостям (Double-Opt-In, UWG §7), **G4** многоступенчатые авто-скидки
  (LOS/Frühbucher/Last-Minute, неск. правил на тип), **G5** мультикомнатная бронь,
  **G6** Online-Checkin + цифровой Meldeschein (BMG, retention 1 год), **G7** гибкая
  предоплата по тарифу (0/частично/100 %), **G8** фид цен/наличия для метапоиска
  (Google Free Booking Links), **G9** отчёты Belegung/ADR/RevPAR, **G10** iframe-виджет,
  **G11a/b** фундамент Channel Manager (модель `Channel` + идемпотентный импорт броней
  из OTA; реальные API Booking/Expedia/Airbnb — партнёрство, отложено G11c–e). UX витрины
  номера: 2 колонки (галерея/бронь), лайтбокс, карточки номеров на главной, полное меню.
  Демо — **по нескольку примеров на фичу**: `seed_demo_tenants --kit hotel --recreate`
  (+ `hotels.<base>`). Доки: `docs/hotel-demo.md`, планы `hotel-archetype-plan.md` /
  `hotel-growth-plan.md` / `hotel-channel-manager-plan.md`.
- Самые свежие миграции: `stays/0014–0019` (auto-discount fields→rules, prepayment_percent,
  rooms, GuestRegistration, Channel+external_ref) + `promotions/0018` (NewsletterCampaign +
  marketing_opt_in_at). Полный список — в build-log.

**Конвенция памяти:** завершая инкремент — дописывать строку в `docs/build-log.md`,
а ЗДЕСЬ обновлять только верхнеуровневый статус и раздел «Дальше».

## 4. Маршруты
- Корень субдомена `/` = витрина; акция `/p/<uuid>/`, бронь `/p/<uuid>/reserve/`,
  waitlist `/p/<uuid>/waitlist/`, подтверждение `/r/<code>/`, QR `…/qr.svg`,
  отписка `/u/<token>/`, право `/impressum /datenschutz /widerruf`.
- Витрина-бронь по времени `/termin/` → `/t/<code>/`; по датам (Übernachtung)
  `/unterkunft/` (юнит → даты → buchen) → `/s/<code>/`; Click&Collect `/warenkorb/`
  → `/bestellung/<code>/`; Handwerker `/anfrage/` (заявка) + `/angebot/<token>/`
  (публичная смета: принять/отклонить).
- Кабинет (под логином): `/dashboard/`, `/catalog/`, `/promotions/` (+ redeem/,
  vouchers/, loyalty/, analytics/), `/imports/`, `/dashboard/settings/`,
  `/dashboard/domains/` (custom-домены), `/dashboard/booking/` (по времени),
  `/dashboard/stays/` (по датам), `/dashboard/auftraege/` (Aufträge/Angebote),
  `/dashboard/orders/`, `/dashboard/finance/`.
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
- **`build-log.md`** — 📜 хронология ВСЕХ завершённых задач (извлечена из §3
  2026-06-22). Source of truth по сделанному; новые инкременты дописываем сюда.
- **`audit-2026-06-22.md`** — срез состояния + оценка готовности (Stage 0/1/2/3,
  архетипы A1–A9, модули M1–M23, риски). Периодически обновляем.
- **`master-plan.md`** — 🧭 КАНОНИЧЕСКИЙ мастер-план (сводит vision+roadmap+verticals;
  стадии: архетипы→100% + Phase 2 → глобальные функции; модули M1–M23; архитектурные
  швы под миграции). Создан 2026-06-14. Верхний уровень планирования.
- **`roadmap-next-sprints.md`** — операционный план (Sprint 5/4/6, Hardening, Phase 2 P2.x).
- **`platform-core-architecture.md`** — архитектура ядра; `full-platform-vision.md`
  (северная звезда, модули M1–M21, Phase 1–4+).
- `references/patterns/` — state-machine, anti-oversell, notification-dedupe,
  audit-log, soft-delete, cursor-pagination, webhook-hmac-signing,
  csv-import-wizard, magic-link-auth.
- `DEVELOPMENT-GUIDE.md`, `phase1-*.md`, `monetization-unit-economics.md`,
  `hetzner-claude-code-setup.md`.
- `billing-stripe-setup.md` — настройка Stripe (ключи, Price 39 €, webhook, §4
  featured, §5 Connect/оплата клиента) в `.env.prod`.
- **`micro-business-verticals.md`** — карта вертикалей DACH (потребности → полнота,
  бэклог G1–G9, порядок retail-пакета и P2.5).

## 7. Дальше (актуальный порядок, 2026-06-23)
Архетип A5 «Отель» закрыт: H1–H9 + бэклог роста G1–G10 + фундамент G11 (a/b).
Демо наполнено по нескольку примеров на фичу, агрегатор согласован. История —
build-log; планы — `hotel-growth-plan.md` / `hotel-channel-manager-plan.md`.
Текущий порядок (выбор владельца, 2026-06-23: сначала G11, затем M20):

1. **G11 (Channel Manager):** ✅ фундамент G11a/b (модель `Channel` + идемпотентный
   импорт броней из OTA + кабинет). **Отложено G11c–e** — реальные API
   Booking/Expedia/Airbnb (партнёрские аккаунты/сертификация — шаг владельца).
2. **M20 — Site Builder.** Аудит ✅ (2026-06-23). Адаптивный билдер + нативный кабинет
   (таб-бар `nav_primary`, поиск меню, липкая шапка). План — `docs/m20-site-builder-plan.md`.
   **M20U «унификация страниц» 🚧 (2026-06-25, активный трек, план
   `docs/m20-retreat-pages-plan.md`):** «архетип = главный товар + способ покупки»
   поверх JSON, без новых моделей. ✅ единая главная (слайдер/категории/события +
   реестры `archetypes.primary_item`/`purchase_mode`/`purchase_label`, hero-CTA, пилюли
   действия, мобильный buybar), каталог (подкатегории-первыми, фильтры свёрнуты на
   маленьком сайте), **единая детальная `storefront/detail.html`** (product/stay/event
   сведены), билдер (селектор пресета раскладки + live-preview). Осталось: per-page
   блок-редактор, хвосты каталога events/stays, realtime-чат. Хронология — build-log.
3. **Далее — наполнение архетипов** (по вертикалям). Карта потребностей —
   `micro-business-verticals.md`; для каждого архетипа заводим отдельный план-док
   перед разработкой (конвенция: docs готовим до кода).
4. **Рефактор-гигиена (по желанию):** loyalty/vouchers уже вынесены в `apps.loyalty`.

**Параллельно — Stage 0 (на владельце, блокер боевого запуска):** Stripe live
(ключи/Price 39 €/Connect/webhook — `billing-stripe-setup.md`), инфра (отдельный
Postgres, бэкапы, `SECRETS_ENCRYPTION_KEY`, SENTRY_DSN, RESEND_API_KEY), право DACH
(AVV — `dsgvo-review.md`, прогон k6 — `scripts/load/README.md`).

**Stage 2/3 (после M20+архетипы):** P2.8 PWA/push/Wallet, M21 импорт Shopify/Woo,
M23c платная реклама; затем Stage 3 (склад-леджер, маркетплейс-корзина, закупки,
dropshipping, AI, workflow). Подробно — `master-plan.md` / audit §6.

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
