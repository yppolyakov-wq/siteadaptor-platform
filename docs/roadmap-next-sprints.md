# Roadmap — следующие спринты и Phase 2

Рабочий документ-чеклист. Один PR на задачу, CI зелёный → squash-merge → деплой
`./scripts/deploy.sh single`. Миграции последовательные; стек-ветки ребейзить на
свежий main перед PR. Паттерны: `docs/references/patterns/`.

**Зафиксированный порядок исполнения:** Track A (инструменты) → **Sprint 5 (биллинг)** →
**Sprint 4 (авто-публикация)** → **Sprint 6 (уведомления)** → Hardening (параллельно).
Биллинг раньше публикации — раньше появляется выручка.

---

## 0. Сделано
- [x] Phase 1 (мультитенантность, audit, soft-delete, пагинация, webhooks-scaffold, деплой Hetzner single).
- [x] Sprint 2: каталог (товары, категории, изображения, CSV/Excel-импорт).
- [x] Sprint 3: акции + резервирование (FSM, anti-oversell 50/50/0, beat, кабинет, витрина, письма, DSGVO-очистка).
- [x] Витрина 2.0: цены/скидки/медиа, редизайн, A11y, DE/EN, мобильный grid 1/2, импорт акций, настройки бизнеса + право, отписка.
- [x] QR: маркетинговый + канальный (атрибуция) + персональный + погашение в кабинете.
- [x] Инструменты: лист ожидания; ваучеры; лояльность; авто-погашение по скану.
- [ ] **В очереди на мерж** (готово локально): ваучеры (PR #42), лояльность, авто-погашение, этот документ.

---

## Track A — добить инструменты

### A3. Аналитика акций (последний инструмент)
- [ ] A3.1 Сбор: счётчик `views` на `promotion_detail` (атомарный `F()+1`); брони из `Reservation`; каналы из `source_channel`; waitlist/ваучеры/штампы — count.
- [ ] A3.2 Метрики на акцию: просмотры, брони по статусам, конверсия = брони/просмотры, выдачи (fulfilled) и % выкупа, топ-каналы.
- [ ] A3.3 UI: блок «Статистика» на форме акции + сводная страница **Analytics** в сайдбаре.
- [ ] A3.4 (опц.) `PromotionDailyStat` — дневные агрегаты + графики (7/30 дней).
- [ ] A3.5 Тесты: инкремент просмотров, конверсия, разбивки.
- **DoD:** на акции видно просмотры/брони/конверсию; сводная страница со всеми акциями.

---

## Sprint 5 — Биллинг и подписки (Stripe)   ⟵ первый крупный
Поля на `Tenant` уже есть: `stripe_customer_id`, `subscription_status`, `trial_ends_at`,
`subscription_ends_at`; индекс `tenant_substatus_trial_idx`.

- [ ] 5.1 dj-stripe: ключи (test/live), вебхук-эндпоинт, синк Product/Price (39 €/мес); маппинг тарифа → `enabled_modules`.
- [ ] 5.2 `SubscriptionSM` (state-machine.md): trial→active→past_due→suspended (+ trial→trial_expired→suspended); `suspended` = read-only, данные не удаляем.
- [ ] 5.3 Оплата: Stripe Checkout Session (онбординг/кабинет) + Customer Portal (карта/отмена/инвойсы).
- [ ] 5.4 Webhooks (идемпотентные, подпись по `event.id`): `checkout.session.completed`→active, `invoice.payment_failed`→past_due, `subscription.deleted/updated`→пересчёт.
- [ ] 5.5 Гейтинг: middleware/декоратор — suspended/trial_expired → блок записи + баннер; trial-баннер с днями.
- [ ] 5.6 Beat ежедневно по индексу `(subscription_status, trial_ends_at)`: trial→trial_expired (д.14)→suspended (д.21); напоминания д.11/13/14 c `dedupe_key`.
- [ ] 5.7 Тесты: переходы SM, идемпотентность вебхуков, гейтинг, beat-просрочка.
- **DoD:** триал истекает по cron; оплата активирует; неоплата → suspended (read-only); всё идемпотентно.

---

## Sprint 4 — Авто-публикация и локальный агрегатор   ⟵ текущий

Цель: акция, став `active`, автоматически попадает в **локальный агрегатор**
(городские страницы на основном домене) и — через расширяемый фреймворк
**каналов** — во внешние площадки; при завершении/паузе снимается. Всё через
очередь, идемпотентно.

Архитектура: агрегатор — встроенная SHARED-витрина (материализованные
`AggregatorListing` в public-схеме, т.к. акции живут в TENANT-схемах и кросс-
схемный запрос дорог). Каналы — расширяемый механизм для внешних площадок
(адаптеры Instagram/GBP — Phase 2).

Мульти-доменные порталы → **Phase 2 P2.1** (`AggregatorPortal`): супер-админ
управляет доменами-порталами (`kind` vertical/city/region + фильтры + брендинг +
SEO, middleware host→портал) **поверх того же пула** `AggregatorListing` — это и
есть «агрегатор агрегаторов». Поэтому страницы основного домена в S4.2 — «портал
по умолчанию», а выборку выносим в `listings_for(filters)` для переиспользования
порталами (без хардкода под основной домен).

### S4.1 — Агрегатор: модель + sync-задача + хук PromotionSM (бэкенд)
- [ ] `apps.aggregator` (SHARED): `AggregatorListing` (public-схема) —
  денормализованная активная акция: `tenant_schema`, `tenant_slug`,
  `business_name`, `business_type`, `city`, `promo_uuid`, `title`, `teaser`,
  ценовые поля, `starts_at`/`ends_at`, `image_url`, `detail_url`, `is_active`;
  `unique(tenant_schema, promo_uuid)`; индексы `(city, is_active)`,
  `(business_type, city)`.
- [ ] `sync_aggregator_listing(tenant_schema, promotion_id)` (idempotent_task): в
  `schema_context` читает акцию + контакты тенанта; `active` → upsert листинга в
  public, иначе → удаление.
- [ ] Хук `PromotionSM.on_transition`: `→active` → enqueue upsert;
  `→ended/paused/archived` → enqueue remove; `dedupe_key=agg:{promo}:{dst}`,
  схема из `connection.schema_name`.
- [ ] Settings: `apps.aggregator` в SHARED_APPS; миграция `aggregator/0001`.
- [ ] Тесты: active→листинг есть; ended→нет; идемпотентность; чтение из схемы.
- DoD: переход акции отражается в `AggregatorListing` (ещё без UI).

### S4.2 — Агрегатор: публичные страницы (видимый результат)
- [ ] Вьюхи на основном домене (public-схема, `urls_public`): `/entdecken/`
  (индекс городов), `/entdecken/<city>/`, `/entdecken/<city>/<business_type>/` —
  активные листинги, ссылка на акцию на субдомене бизнеса.
- [ ] Шаблоны: grid карточек (цена/скидка/город/бизнес), A11y, DE/EN, пустое
  состояние, cursor-пагинация (есть в `apps.core`).
- [ ] Тесты: фильтр по `city`/`business_type`, только активные (RequestFactory).
- DoD: `/entdecken/<city>/` показывает активные акции города; клик → акция.

### S4.3 — Фреймворк каналов: Channel + Publication + SM + задачи (TENANT)
- [ ] `apps.publishing` (TENANT): `Channel` (type, is_enabled, config),
  `Publication` (promotion, channel, status, external_ref, `dedupe_key` unique,
  last_error, ts), `PublicationSM` (queued→published→removed; failed→queued;
  published→removed).
- [ ] Задачи (idempotent_task, schema_context, ретраи+backoff):
  `publish_to_channel` / `remove_from_channel` — статус/last_error; встроенный
  адаптер `log` (внешние адаптеры — Phase 2).
- [ ] Хук `PromotionSM`: `→active` → publish во включённые каналы;
  `→ended/paused/archived` → remove; `dedupe_key=publish:{promo}:{channel}`.
- [ ] Settings: `apps.publishing` в TENANT_APPS; миграция `publishing/0001`.
- [ ] Тесты: SM-переходы, enqueue, идемпотентность, last_error.
- DoD: активация → Publication на канал; ended → removed; идемпотентно.

### S4.4 — Кабинет: тумблеры каналов + статус публикаций
- [ ] `/dashboard/channels/`: каналы с тумблером `is_enabled` + панель статусов
  Publication (последние/ошибки); пункт меню.
- [ ] Тесты: тумблер меняет `is_enabled`; панель показывает статусы.
- DoD: владелец включает/выключает каналы и видит статусы.

Порядок: S4.1 → S4.2 (рабочий агрегатор, точка деплой-проверки) → S4.3 → S4.4.
Миграции: `aggregator/0001` (public) + `publishing/0001` (tenant) — деплой
(`deploy.sh single`) применит во всех схемах. Один инкремент на подзадачу, ветка
`claude/<кратко>`, CI на git зелёный → мерж.

---

## Sprint 6 — Зрелость уведомлений
- [ ] 6.1 `Notification` (уровень-1 dedupe): unique `dedupe_key`, type, recipient, status (FSM pending→sent→failed), payload, scheduled_at, priority.
- [ ] 6.2 Рефактор писем брони через `Notification` (БД-дедуп, не только Redis-lock).
- [ ] 6.3 Resend в проде (anymail подключён; сейчас console-fallback); зрелые шаблоны.
- [ ] 6.4 Лист ожидания → авто-уведомление при возврате остатка (флаг `notified`).
- [ ] 6.5 (опц.) WhatsApp (провайдер + согласие + шаблоны).
- **DoD:** письма через Resend; дубли невозможны (БД-unique + Redis).

---

## Hardening (сквозное, до боевого запуска)
- [ ] H1 Resend-ключ в проде (+ SPF/DKIM домена отправителя).
- [ ] H2 Отдельный Postgres (managed/VM), пул (pgbouncer), перенос данных.
- [ ] H3 Ротация секретов (SECRET_KEY/DB/API), инвалидация сессий.
- [ ] H4 Бэкапы (`pg_dump` cron + offsite) + регулярный restore-drill.
- [ ] H5 Sentry в проде (релизы/перформанс) + внешний uptime-чек + алерты.
- [ ] H6 Нагрузочный тест anti-oversell на реальном железе (k6/locust): 0 перепродаж + latency.
- [ ] H7 DSGVO-ревизия: retention (есть), экспорт/удаление по запросу, cookie-баннер при трекинге, AV-Verträge (Resend/Stripe/Hetzner).
- [ ] H8 Rate-limit на все публичные эндпоинты (reserve/waitlist/voucher/loyalty) — расширить текущий per-IP.

---

# Phase 2 — Мульти-доменные агрегаторы и рост

Цель фазы: из инструмента для одного бизнеса → в **сеть локальных порталов** (вертикальных
и городских) под нашими доменами, которые сводят предложения многих бизнесов и гонят им
трафик/лиды. Seam `AggregatorPortal` заложен в Phase 1 — здесь он становится мульти-доменным.

## P2.1 Мульти-доменные порталы
- [ ] `AggregatorPortal` (SHARED): `domain`, `kind` (vertical: bakery / city / region), `filters` (business_type/city/region), branding, SEO-поля, `is_active`.
- [ ] Резолвинг хоста → портал (middleware по аналогии с `TenantMainMiddleware`) + отдельный `urls_portal`.
- [ ] Свои домены (`baeckerei.de`, `metzgerei.de`, городские) — каждый тянет тенантов по фильтру; TLS on-demand (Caddy уже умеет).

## P2.2 SEO и контент порталов
- [ ] Sitemaps, мета, **schema.org** (LocalBusiness/Offer), hreflang (DE/EN).
- [ ] SSR-листинги + кэш/CDN; canonical; OpenGraph; контентные страницы (город/категория) + перелинковка.

## P2.3 Клиентские аккаунты (cross-tenant)
- [ ] Аккаунт конечного клиента на порталах (отдельно от владельцев): избранное, история броней по разным бизнесам, настройки уведомлений.
- [ ] Идентичность в public-схеме; связка с per-tenant `Customer`.

## P2.4 Монетизация портала
- [ ] Featured/Top-листинги (платное продвижение акций); тарифные уровни видимости; рекламные слоты; lead-gen/комиссия.

## P2.5 Платежи конечного клиента
- [ ] Онлайн-предоплата/депозит за бронь (Stripe), защита от no-show; возвраты.

## P2.6 Отзывы и рейтинги
- [ ] Отзывы по бизнесу/акции (модерация, анти-абьюз), агрегатный рейтинг в листингах.

## P2.7 Поиск и рекомендации
- [ ] Геопоиск «рядом со мной», фильтры, ранжирование; поисковый бэкенд (OpenSearch) при росте; рекомендации («скоро закончится», популярное).

## P2.8 Мобильный опыт
- [ ] PWA / нативное приложение, push-уведомления; Wallet-пассы (Apple/Google) для броней и карт лояльности.

## P2.9 Расширение каналов публикации
- [ ] Реальные адаптеры `Channel`: Instagram/Facebook, Google Business Profile, маркетплейсы.

## P2.10 Масштаб и инфраструктура
- [ ] Реплики/пул БД, очереди по приоритетам, медиа на CDN; многорегиональность (`Tenant.data_region` уже заложен).

## P2.11 Партнёрам и BI
- [ ] Публичное API/партнёрские интеграции, white-label порталы, реселлеры.
- [ ] Платформенная аналитика/BI: когорты, retention, выручка по тарифам.

---

## Рабочее соглашение
- Один PR на задачу; ветка `claude/<кратко>`; CI зелёный → squash-merge.
- Миграции последовательные; стек-ветки ребейзить перед PR.
- После пачки мержей с миграциями — `git pull origin main && ./scripts/deploy.sh single`.
- Тесты django-tenants: вьюхи — RequestFactory; новые TENANT-приложения видны в `config/settings/test.py` автоматически.

---

## Отложено / заметки на будущее

Ремарки, всплывшие по ходу работы. Фиксируем сразу, чтобы не терять между сессиями.

**Биллинг (Sprint 5):**
- Гейтинг S5.2 блокирует запись в кабинете владельца; публичная витрина (брони
  клиентов) при `suspended` НЕ блокируется — решить, паузить ли витрину при неоплате
  (Hardening / продуктовое решение).
- Напоминания о триале — дедуп через `idempotent_task` (Redis); БД-гарантия от
  дублей — в Sprint 6 (`Notification` с unique `dedupe_key`).
- Webhook `customer.subscription.deleted/canceled` → `past_due` (grace → suspended),
  не мгновенный suspend; при необходимости уточнить политику отмены.
- Live-режим Stripe: `STRIPE_LIVE_MODE=True` + `STRIPE_LIVE_SECRET_KEY` + live Price
  + live webhook-secret (см. `docs/billing-stripe-setup.md`).

**Агрегатор (Sprint 4):**
- `kind=region` (Phase 2 P2.1) потребует поле региона у Tenant/листинга (сейчас есть
  `city`/`district`/`country`).
- Картинка листинга — относительный `/media/...` работает на single-server (общий
  `MEDIA_ROOT`); при мульти-сервере/S3 нужен абсолютный URL.
- Листинги сортируются по `created_at` без отдельного индекса; для масштаба — составной
  индекс `(city, is_active, created_at)`.
- На основном домене нет переключателя языка (нет публичного `set_language`) — язык по
  `Accept-Language`; переключатель/`hreflang` — Phase 2 (SEO/i18n).
- Каналы (S4.3) — встроенный адаптер `log`; реальные адаптеры Instagram/GBP — Phase 2 P2.9.
