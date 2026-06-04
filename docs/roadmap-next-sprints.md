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

## Sprint 4 — Авто-публикация и локальный агрегатор
Мульти-домен агрегатора → Phase 2 (seam `AggregatorPortal` уже абстрагирует).

- [ ] 4.1 `apps.publishing` (TENANT): `Channel` (type/is_enabled/config), `Publication` (promotion, channel, status, external_ref, unique `dedupe_key`, last_error), `PublicationSM` (queued→published→removed / failed→queued).
- [ ] 4.2 Хуки `PromotionSM`: `→active` → publish на каждый включённый канал; `→ended/paused/archived` → remove. Только через очередь, `dedupe_key=publish:{promo}:{channel}`.
- [ ] 4.3 Celery (idempotent_task): `publish_to_channel` / `remove_from_channel`, ретраи+backoff, статусы/ошибки, `schema_context`.
- [ ] 4.4 `apps.aggregator` (SHARED-чтение): выборка активных акций по `city`/`business_type` (индексы Tenant уже есть); `AggregatorListing` (материализация) или запрос-на-лету; `sync_aggregator_listing` по переходам; публичные страницы `/<город>/`, `/<город>/<категория>/`.
- [ ] 4.5 Кабинет: тумблеры каналов + панель статуса публикаций.
- [ ] 4.6 Тесты: публикация при активации, снятие при ended, идемпотентность, агрегатная выборка.
- **DoD:** активировал → видно в агрегаторе; завершил → исчезло; задача идемпотентна.

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
