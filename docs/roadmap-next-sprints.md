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
`claude/<кратко>`, CI на git зелёный → мерж. **Тесты — на git; локально только при красном CI.**

---

## Sprint 6 — Зрелость уведомлений   ⟵ текущий

Цель: надёжные уведомления с гарантией без дублей. Единая модель `Notification`
(БД-dedup = гарантия, поверх Redis-lock = оптимизация) + FSM, рефактор писем
брони/waitlist через неё, Resend в проде, авто-уведомление листа ожидания при
возврате остатка.

Архитектура: `apps.notifications` (TENANT) — уведомления тенант-скоупные (клиенты/
брони в схеме арендатора). Триал-напоминания биллинга (Sprint 5, public) остаются
на Redis-dedup. Паттерн — `docs/references/patterns/notification-dedupe.md`:
unique `dedupe_key` в БД + проверка статуса перед отправкой = гарантия.

### S6.1 — Notification + NotificationSM (бэкенд)
- [ ] `apps.notifications` (TENANT): `Notification` — `dedupe_key` (unique), `type`
  (reservation_confirmed/cancelled/expired, waitlist_available), `channel`
  (email/whatsapp), `recipient`, `subject`, `payload` (JSON), `status`
  (pending/sent/failed), `scheduled_at`, `sent_at`, `attempts`, `last_error`,
  `priority`; `NotificationSM` (pending→sent/failed; failed→pending).
- [ ] Settings: `apps.notifications` в TENANT_APPS; миграция `notifications/0001`.
- [ ] Тесты: SM-переходы, дедуп (повтор dedupe_key → одна строка).
- DoD: уведомление с гарантией уникальности + управляемый статус.

### S6.2 — Диспетч-задача + рефактор писем брони
- [ ] `send_notification` (idempotent_task, schema_context): pending → рендер +
  отправка через адаптер канала → sent/failed (last_error, attempts++).
- [ ] Рефактор `apps.promotions.notifications` (confirmed/cancelled/expired):
  `get_or_create(Notification, dedupe_key=reservation:{res}:{status})` + enqueue
  вместо прямого письма + Redis-lock. Хук ReservationSM — точка постановки.
- [ ] Тесты: переход брони → одна Notification; двойной триггер → одна строка;
  send → sent; повторный send → skip.
- DoD: письма брони через Notification, дубль невозможен.

### S6.3 — Resend в проде + зрелые шаблоны
- [ ] Email-адаптер: anymail Resend при `RESEND_API_KEY` (иначе console).
- [ ] Зрелые HTML+text шаблоны (подтверждение брони код/QR/детали, отмена,
  waitlist-доступно), DE/EN; `DEFAULT_FROM_EMAIL` + домен (SPF/DKIM — Hardening H1).
- [ ] Тесты: рендер, выбор backend (в CI — console).
- DoD: в проде письма через Resend (после ключа); шаблоны зрелые.

### S6.4 — Waitlist: авто-уведомление при возврате остатка
- [ ] `WaitlistEntry.notified` (флаг) — миграция `promotions/0009`.
- [ ] Возврат остатка (ReservationSM cancelled/expired → anti-oversell) → для
  непрошедших entries в пределах вернувшегося qty: enqueue `waitlist_available`,
  `notified=True`, `dedupe_key=waitlist:{entry}:available`.
- [ ] Тесты: возврат остатка → уведомлён; идемпотентно (флаг + dedupe).
- DoD: освободилось место → ждущие получают письмо ровно один раз.

### S6.5 — (опц.) WhatsApp
- [ ] Адаптер канала WhatsApp (провайдер Twilio/Meta) + согласие
  `Customer.whatsapp_opt_in` + шаблоны; за флагом/config. Тем же ядром Notification.
- [ ] Опционально / по готовности провайдера (внешние блокеры: аккаунт, шаблоны
  Meta, opt-in, стоимость). Web-push — Phase 2 (низкий приоритет: бронь разовая).
- DoD: при согласии — уведомление в WhatsApp через тот же Notification.

Порядок: S6.1 → S6.2 (ядро+рефактор) → S6.3 (Resend) → S6.4 (waitlist) → S6.5 (опц.).
Миграции: `notifications/0001` + `promotions/0009`. H1 (Resend-ключ + SPF/DKIM) —
параллельно для боевых писем. Один инкремент = ветка → CI зелёный → мерж.
**DoD спринта:** письма брони/waitlist через Resend; дубли невозможны (БД-unique + Redis).

---

## Track B — Быстрые победы для DE-рынка   ⟵ после Sprint 6

Цель: дать малому бизнесу инструменты, которыми концерны пользуются через
агентства. Порядок утверждён владельцем (2026-06-09). Один кор — пресеты по
вертикалям (мы не только пекарни: business_type уже bakery/butcher/grocery/
clothing/restaurant/cafe/retail/tour_operator/hotel).

- [x] B1 **Google Business Profile** — первый внешний адаптер каналов (Google
  Posts API): локальный discovery в DE = Google Maps/Search. Каркас каналов
  готов (S4.3), нужен адаптер + OAuth-подключение в кабинете. ✅ ветка
  `claude/track-b1-gbp`: тип канала google_business, адаптер Google Posts
  (publish/remove, OAuth refresh-token из config), конфиг в кабинете канала,
  гайд `docs/gbp-setup.md`. Боевое — после выдачи Google API-доступа.
- [x] B2 **«Überraschungstüte» / анти-waste**: пресет акции «сюрприз-пакет» +
  позиционирование «Retten statt wegwerfen» в агрегаторе (наш ответ Too Good To
  Go без комиссии за пакет). Даёт потребителю причину ходить в /entdecken. ✅
  `Promotion.is_surprise` (миграция 0009) + бейдж на витрине/в агрегаторе
  (`AggregatorListing.is_surprise`, миграция aggregator/0002); поверх обычной
  брони, отдельной механики не нужно.
- [x] B3 **Recurring promotions** («Angebot der Woche») + **пресеты по
  вертикалям** (один клик). ✅ ветка `claude/track-b3-recurring`:
  - B3a `apps/promotions/presets.py` — `business_type → пресеты` (Bäckerei
    Feierabend-Tüte/Angebot der Woche, Metzgerei Grillpaket/Wochenangebot,
    Restaurant+Café Mittagstisch/Happy Hour, Grocery MHD-Rabatt, Mode/Retail
    Schlussverkauf, Hotel Last-Minute + общий Rabatt); `?preset=<key>` пред-
    заполняет форму из business_type тенанта, кнопки быстрого старта в форме.
  - B3b `Promotion.recurrence` (—/daily/weekly, миграция 0010) + beat
    `roll_recurring_promotions` (раз в час, все схемы): завершившаяся акция →
    ровно один scheduled-наследник со сдвигом окна на следующий будущий цикл
    (пропущенные циклы не догоняются); recurrence переходит к наследнику,
    у родителя гасится → цепочка не ветвится. Дальше его активирует штатный
    `roll_promotion_statuses`. Деплой: миграция 0010 + новый beat-джоб.
  - Покрытые вертикали (один кор): Metzgerei Grillpakete-Vorbestellung к
    праздникам (бронь), Mode/Retail waitlist по размерам (waitlist есть),
    Hofladen/Bio «frisch geerntet ab …» (scheduled), Hotel/Tour Last-Minute
    (бронь-заявка; полный booking — Phase 2/3).
- [x] B4 **QR-постер PDF (A4)** для витрины магазина («Scan & Angebote sichern»)
  — кнопка «Скачать постер» в кабинете; QR уже есть, добавить PDF-шаблон. ✅
  ветка `claude/track-b4-qr-poster`: `apps/promotions/poster.py`
  (`build_shop_poster_pdf` — segno QR в PNG + reportlab A4, слоган + название +
  URL + футер «без приложения»), вьюха `shop_poster_pdf` + `/promotions/poster/`,
  кнопка на странице акций. QR несёт `?ch=schaufenster` → сканы с постера идут в
  атрибуцию каналов. Зависимость `reportlab`.
- [x] B5 **Local SEO**: schema.org LocalBusiness/Offer + sitemap на витринах и
  в агрегаторе (вынесено вперёд из P2.2) — малые выигрывают локальную выдачу. ✅
  ветка `claude/track-b5-local-seo`: `apps/core/seo.py` (localbusiness_ld/
  offer_ld/itemlist_ld); B5a — LocalBusiness в `<head>` витрины (тег
  `{% localbusiness_jsonld %}`) + Offer на странице акции + `sitemap.xml`/
  `robots.txt` витрины; B5b — ItemList на городской странице агрегатора +
  `sitemap.xml`/`robots.txt` основного домена (без django.contrib.sites: домен
  из request, мульти-тенант-safe).

**UX-принципы конечного потребителя (зафиксировано владельцем): просто,
понятно, без навязчивости.**
- Бронь без аккаунта и без лишних полей (есть); подтверждение по коду.
- One-click отписка в каждом письме (есть, RFC 8058); waitlist — ровно одно
  письмо на запись (есть, S6.4).
- Частотные лимиты уведомлений (не чаще N в неделю на клиента) — когда появятся
  маркетинговые пуши по базе (B2/B3 потребителя не уведомляют: recurring и
  surprise-пакет планирует владелец, рассылок клиентам они не шлют).
- **Double-Opt-In (UWG §7) — ОБЯЗАТЕЛЕН до любых маркетинговых рассылок по
  базе** (транзакционные письма брони — ок без DOI). Сделать до promo-пушей.
- Никакого трекинга/cookie-баннера на витрине без необходимости (сейчас
  first-party счётчик просмотров — баннер не нужен).

---

## Hardening (сквозное, до боевого запуска)
- [ ] H1 Resend-ключ в проде (+ SPF/DKIM домена отправителя).
- [ ] H2 Отдельный Postgres (managed/VM), пул (pgbouncer), перенос данных.
- [ ] H3 Ротация секретов (SECRET_KEY/DB/API), инвалидация сессий.
- [ ] H4 Бэкапы (`pg_dump` cron + offsite) + регулярный restore-drill.
- [ ] H5 Sentry в проде (релизы/перформанс) + внешний uptime-чек + алерты.
- [x] H6 Нагрузочный тест anti-oversell: код ✅ в `main` (549bc9c+b6b84a4 — k6-скрипт
  `scripts/load/anti_oversell.js` + README + кейс конкурентности); сам прогон на железе — на владельце.
- [x] H7 DSGVO-ревизия: код ✅ в `main` (be36f06 — команда `dsgvo_customer` экспорт/удаление,
  `docs/dsgvo-review.md`); cookie-баннер не нужен (нет трекинга); AV-Verträge (Resend/Stripe/Hetzner) — на владельце.
- [x] H8 Rate-limit публичных эндпоинтов ✅ в `main` (8c43a43 — `apps/core/ratelimit.py`:
  бронь/waitlist на IP+акцию, QR-вьюхи кодов на IP → 429).

---

# Phase 2 — Мульти-доменные агрегаторы и рост

Цель фазы: из инструмента для одного бизнеса → в **сеть локальных порталов** (вертикальных
и городских) под нашими доменами, которые сводят предложения многих бизнесов и гонят им
трафик/лиды. Seam `AggregatorPortal` заложен в Phase 1 — здесь он становится мульти-доменным.

## P2.1 Мульти-доменные порталы

**Согласованный подход (2026-06-10):** мульти-домен на **поддоменах `*.siteadaptor.de`**
(DNS-wildcard уже есть). Custom-домены (`baeckerei.de`, `angebote-muenchen.de`) — поверх,
через готовый `internal/verify-domain` + Caddy on-demand TLS. Path-based вариант
(`/b/<vertical>/`, `/c/<city>/` на основном домене) рассмотрен и **отклонён** — нужны
отдельные брендированные хосты.

**Типы порталов (`kind`):** `city` (город), `vertical` (тип бизнеса), `combo` (город+тип).
**Фильтры выдачи:** `city` + `business_type` — переиспользуют сем
`listings_for(*, city, business_type)` (`apps/aggregator/views.py`), без новых кросс-схемных
запросов (читаем общий пул `AggregatorListing`).

**Модель `AggregatorPortal`** (SHARED, public; миграция `aggregator/0003`):
- `host` — полный хост, уникальный ключ резолвера; `kind`; фильтры `city` + `business_type`.
- Брендинг: `title`/`tagline`/`intro` (i18n-JSON), `logo_url`, `primary_color`; `is_active`.
- Индекс `agg_portal_active_idx`.

**Резолвер `AggregatorPortalMiddleware`** (сразу после `TenantMainMiddleware`): host → портал
на public-схеме → `request.portal` (или None). Карта `host→id` кэшируется в Redis (TTL 300 c
+ сигнал-сброс на save/delete портала). На основном домене и на субдоменах бизнеса
`request.portal = None` — поведение текущих страниц не меняется. Подмена
`request.urlconf → config.urls_portal` — в P2.1b.

**Провижининг:** на каждый портал — строка `Domain(host → public tenant)` (иначе
`TenantMainMiddleware` отдаёт 404). Команда `create_portal` (портал + Domain) и unfold-admin
— в P2.1d.

**Разбивка (инкременты; ветка → CI зелёный → чекпоинт):**
- [x] **P2.1a** — модель `AggregatorPortal` + миграция 0003 + резолвер-middleware
  (`request.portal`, кэш + сигнал-сброс) + тесты. _(✅ в `main`, 2d28be2, CI run 39 зелёный)_
- [x] **P2.1b** — `config/urls_portal.py` + `portal_home` (корень портала = листинги его фильтра)
  + уточнение по 2-й оси (город→тип / тип→город) + брендированный base-шаблон; подмена
  `request.urlconf`; health-пробы и media-фолбэк на хосте портала. _(✅ в `main`,
  4d09b76+c9f79b2, CI runs 42/43 зелёные; без миграций)_
- [x] **P2.1c** — SEO портала: meta + JSON-LD (CollectionPage/ItemList) + canonical + sitemap/robots
  по хосту портала. _(✅ в `main`, 18c1c09+5e27113, CI run 46 зелёный; без миграций)_
- [x] **P2.1d** — провижининг: unfold-admin + команда `create_portal` (+ `Domain`) +
  `docs/portal-setup.md` (DNS, Caddy on-demand TLS, custom-домены). _(✅ в `main`,
  223de16+c5f6e8c, CI run 50 зелёный; без миграций)_

## P2.2 SEO и контент порталов
- [x] Sitemaps, мета, **schema.org** — закрыто ранее (Track B5 + P2.1c). hreflang (DE/EN)
  сознательно не делаем, пока язык в cookie, а не в URL (см. §Отложено).
- [x] SSR-листинги (были) + кэш (P2.2b: `apps/core/pagecache.py`, TTL 120с); canonical
  (P2.1c порталы + P2.2a городские страницы); OpenGraph (P2.2a); перелинковка
  город↔портал↔сеть порталов (P2.2a). _(✅ в `main`, a573b35+75ba11d, CI runs 64/65
  зелёные; без миграций.)_ Полноценные контентные SEO-тексты городов — §Отложено.

## Track C — витрина сайта, конструктор v1, CRM-минимум (решение владельца 2026-06-11)

Витрина бизнеса перестаёт быть только лентой акций — становится мини-сайтом.
Полный drag-and-drop конструктор остаётся Phase 3+ (vision Модуль 20), полный CRM
с лидами/воронками — Phase 2 позже (vision Модуль 9). Сейчас — прагматичный v1:
- [x] **C1 — витрина товаров:** публичный каталог на витрине (`/sortiment/` список
  с фильтром по категориям + страница товара), секция «Sortiment» на главной,
  товары в sitemap. Без корзины/заказов (покупка офлайн, бронь — только у акций).
  _(✅ в `main`, be17d17+d2ece12, CI run 77 зелёный; без миграций.)_
- [x] **C2 — конструктор витрины v1 (секции):** `Tenant.site_config` (JSON, миграция
  tenants/0006): порядок/видимость секций главной (hero / акции / товары / о нас /
  контакты+часы) + тексты hero/about; страница «Site» в кабинете (без drag-and-drop).
  _(✅ в `main`, ffe4628+c84a0b3, CI run 81 зелёный.)_
- [x] **C3 — CRM-минимум «Клиенты»:** отдельный блок ведения клиентов в кабинете,
  не привязанный к товарам/заказам: список с поиском (вкл. по тегу), карточка
  (контакты, теги, заметки), ручное добавление; история броней — readonly-справка.
  `Customer.tags` (promotions/0011) + `apps/crm` CustomerNote (TENANT, crm/0001);
  tags/crm_notes включены в DSGVO-экспорт/стирание. Лиды/воронки/канбан —
  следующий шаг (Модуль 9). _(✅ в `main`, 2d8f4ae, CI run 84 зелёный.)_

**Track C завершён (C1–C3).** Возврат к плану: P2.3d → P2.4 монетизация.

## P2.3 Клиентские аккаунты (cross-tenant)
Разбивка согласована (2026-06-11): a) magic-link идентичность → b) избранное →
c) история броней (email-связка с Customer) → d) настройки уведомлений.
- [x] **P2.3a** — `PortalUser` (public) + magic-link вход на порталах `/konto/`
  (паттерн magic-link-auth.md; анти-энумерация, rate-limit email/IP). _(✅ в `main`,
  5730386, CI run 68 зелёный; миграция aggregator/0004.)_
- [x] **P2.3b** — избранное: сердечки на карточках + `/konto/favoriten/` + раздел в /konto/;
  pagecache мимо непустых сессий. _(✅ в `main`, 6ac2af0+279b417, CI run 71; миграция aggregator/0005.)_
- [x] **P2.3c** — история броней по всем бизнесам (email-связка с per-tenant `Customer`,
  кросс-схемный сбор + кэш 60с). _(✅ в `main`, 2d97db7, CI run 72; без миграций.)_
- [x] **P2.3d** — настройки уведомлений: центральная (от)подписка в /konto/
  (`PortalUser.marketing_opt_out` → Celery-синк в per-tenant `Customer.unsubscribed`;
  транзакционные письма не затрагиваются). _(✅ в `main`, f61b35e, CI run 89 зелёный;
  миграция aggregator/0006.)_

**P2.3 завершён (a–d).** Дальше: P2.4 монетизация портала.

## P2.4 Монетизация портала
Разбивка (2026-06-11, с учётом Track D): сначала механика — продавать можно вручную,
самообслуживание оплаты — после D0 (впишется в Modul-Framework как модуль).
- [x] **P2.4a — featured-листинги (механика):** `AggregatorListing.featured_until`
  (aggregator/0007), закрепление сверху первой страницы выдачи (портал + /entdecken)
  с бейджем «★ Empfohlen», без дублей в keyset-ленте; админка листингов для ручной
  продажи (sync не трогает срок). _(✅ в `main`, c6ad8f9+2befa88, CI run 94 зелёный.)_
- [x] **P2.4b — самообслуживание (Stripe one-time Checkout):** кнопка
  «Bewerben/Verlängern» на странице активной акции → `/promotions/<pk>/feature/`
  (планы 7/14/30 дн., решение владельца — 9/15/25 €) → разовый Checkout
  (`mode="payment"`, inline `price_data` — без Price в Stripe-дашборде) → вебхук
  `checkout.session.completed` с `metadata.kind="featured"` ставит/продлевает
  `AggregatorListing.featured_until` (продление от `max(now, текущий)`). Цены —
  `apps/billing/featured.py`, env-оверрайд `BILLING_FEATURED_PRICES="7=900,…"`.
  Без миграций (поле из P2.4a). Гранулярность — на одну акцию (её листинг).
  _(✅ в `main` — заполнить commit/CI после пуша.)_
- Отложено: тарифные уровни видимости (вместе с тарифной сеткой), рекламные слоты
  (нужен спрос), lead-gen/комиссия (конфликтует с «39 € без комиссий» — не делаем).
- Отложено (P2.4b): featured хранится на строке листинга — если акцию завершить
  раньше срока, листинг удаляется (sync_listing) и оплаченное продвижение
  пропадает (срок featured ≈ срок акции). При спросе — хранить «оплаченное окно»
  отдельно от листинга и восстанавливать при ресинке.
- Отложено (Track D / D1): связь Voucher↔Customer (ваучеры в карточке 360°) —
  сейчас ваучеры standalone-коды без клиента; добавить при спросе.

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
- Один инкремент на подзадачу; ветка `claude/<кратко>`; CI на git зелёный → мерж.
- **Проверки (pytest) — на git (GitHub Actions), НЕ локально** — экономим ресурсы
  Claude. Локальный прогон тестов — ТОЛЬКО если CI на git красный (воспроизведение/
  отладка). Локально допустимо лишь `makemigrations` (генерация миграции в коммит).
- Миграции последовательные; стек-ветки ребейзить перед PR.
- После пачки мержей с миграциями — `git pull origin main && ./scripts/deploy.sh single`.
- Тесты django-tenants: вьюхи — RequestFactory; новые TENANT-приложения видны в `config/settings/test.py` автоматически.

---

## Отложено / заметки на будущее

Ремарки, всплывшие по ходу работы. Фиксируем сразу, чтобы не терять между сессиями.

- **G6 Aufträge/Angebote / смета Handwerker (2026-06-13, ✅ F1–F3 в `main`):**
  `apps.jobs` — Anfrage→Angebot→Auftrag→Rechnung (детали CLAUDE.md §3). **Отложено
  по G6:** Anzahlung онлайн за смету (Handwerker платят по Rechnung — норма DACH;
  при спросе — Stripe Connect как P2.5); дробные часы/единицы в позициях (qty
  целочисленный — для совпадения суммы сметы и Rechnung через finance.compute_totals,
  который int(qty)); фото/вложения к заявке; несколько версий Angebot на заявку;
  привязка Termin под работу (связать с `apps.booking`). Модуль opt-in
  (universal). **Деплой:** миграции jobs/0001 + tenants/0013.

- **Track E date-range booking / Übernachtung (2026-06-13, ✅ E1–E4 в `main`):**
  `apps.stays` — движок «по ночам» (отели/ретриты/Ferienwohnung), детали в
  CLAUDE.md §3. **Отложено по Track E:** сезонные/выходные тарифы и rate-plans
  (v1 — одна ставка/ночь + min_nights); листинг размещений в агрегаторе `/entdecken`
  (A8 — отдельно, нужна модель листинга под date-range); авто-Rechnung на каждую
  бронь (пока выручка в `finance`, счёт вручную из D4b); iCal/каналы (Booking.com)
  — вне периметра микробизнес-вертикалей. `UnitBlock` для `quantity>1` уменьшает
  доступность на 1 (не закрывает все юниты) — при спросе пересмотреть.
  **НДС размещения = 7 %** (Beherbergung) зашит в finance-хук; завтрак/доп (19 %)
  — вне v1. **Деплой:** миграции stays/0001, tenants/0012, finance/0003.

- **P2.5a Connect redirect-URI на субдоменах (2026-06-13):** OAuth-callback сейчас
  per-tenant (`<sub>.siteadaptor.de/dashboard/billing/payments/callback/`), а Stripe
  Connect требует регистрации redirect URI в настройках платформы — на множестве
  субдоменов это неудобно. Варианты на будущее: единый callback на основном домене
  со state→tenant + сквозная авторизация, либо wildcard-регистрация. Пока feature
  гейтится `STRIPE_CONNECT_CLIENT_ID`, в бою включаем после выбора стратегии.

- **Карта микробизнес-вертикалей (2026-06-12):** `docs/micro-business-verticals.md` —
  ~40 типов микробизнесов DE по 3 «движкам» (retail/каталог · booking по времени ·
  booking по датам), потребности каждого до «логической полноты» и сквозной бэклог
  G1–G9 (оплата, варианты+весовая цена, остаток, доставка, date-range, смета,
  LMIV, отзывы+гео, курсы/абонемент). Source of truth для планирования вертикалей.

- **Чат покупатель ↔ бизнес внутри системы (решение владельца 2026-06-11: позже).**
  В исходном vision не было (только односторонние каналы/рассылки). Добавляем в ТЗ
  как будущий модуль: единый inbox в кабинете + виджет «вопрос по акции/товару» на
  витрине; старт без realtime (email-тред/WhatsApp deep-link), realtime — после.
  Делать после Track C и P2.4.
- **hreflang DE/EN (из P2.2):** корректен только при языковых URL (`/en/...` или
  отдельные хосты); у нас язык в cookie → не делаем. Вернуться, если решим
  выносить язык в URL (это отдельное решение с редиректами и canonical).
- **Контентные SEO-тексты городов/категорий (из P2.2):** интро-текст у порталов
  уже есть (`AggregatorPortal.intro`); для страниц `/entdecken/<city>/` нужна
  модель/поле под уникальный текст города — делать при появлении SEO-спроса.

- **Custom-домен бизнеса — самообслуживание (✅ реализовано 2026-06-11):**
  `/dashboard/domains/` — владелец добавляет домен, ставит A-запись на наш IP,
  жмёт «Проверить»; при совпадении создаётся `Domain(домен → тенант)` и Caddy
  выпускает сертификат. Модель `CustomDomain` (заявка/статус, миграция
  tenants/0005), логика `apps/tenants/domains.py`, нужен `CUSTOM_DOMAIN_TARGET_IP`
  в `.env.prod`. **Осталось на будущее:** canonical-политика (какой хост главный —
  субдомен или custom-домен для SEO; сейчас оба отдают одинаковый контент,
  rel=canonical на витрине пока на текущий хост); опц. авто-перепроверка pending
  по beat.

**Стратегия DE-рынка (обсуждение 2026-06-09, кандидаты после Sprint 6):**
- Google Business Profile — ПЕРВЫЙ внешний адаптер каналов (Google Posts через
  API): локальный discovery в DE идёт через Google Maps/Search; у сетей это
  делают агентства, у малых — никто. Каркас каналов готов (S4.3), нужен адаптер.
- «Überraschungstüte» / Lebensmittel retten: тип акции «сюрприз-пакет» +
  позиционирование анти-waste (наш ответ Too Good To Go, но за фикс €39 без
  комиссии за пакет). Даёт потребителям причину ходить в агрегатор.
- Recurring promotions («Angebot der Woche»): еженедельный авто-повтор акции —
  ритм пекарни, удержание (инструмент в еженедельном использовании → ниже churn).
- QR-постер PDF (A4) для витрины магазина: генерация печатного постера со
  сканируемым QR («Scan & Angebote sichern») — мост офлайн→онлайн, копеечно
  (QR уже есть, добавить PDF-шаблон).
- Local SEO раньше Phase 2: schema.org LocalBusiness/Offer + sitemap на витрине
  и в агрегаторе — малые выигрывают у концернов именно локальную выдачу.
- Wallet-Stempelkarte (Apple/Google Wallet) для лояльности — «как у сетей»,
  поднять из P2.8 при первом спросе.
- UI-языки tr/ru/uk для владельцев (демография малого бизнеса DE).
- AV-Vertrag (DPA) авто-генерация для тенантов + бейдж «Hosted in Germany» —
  дешёвый аргумент доверия для DACH.
- НЕ делать сейчас: POS/TSE (KassenSichV), собственный checkout-эквайринг,
  маркетплейс-корзина — другой класс сложности, после PMF.

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
