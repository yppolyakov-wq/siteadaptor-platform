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

- **(2026-10-24, KA-12 E6.4b) Заметки к процедурам: срок хранения и данные о здоровье.** Сейчас
  удаляются только вместе с клиентом; салоны пишут «реакция на PPD» (Art. 9 DSGVO) — в v1 только
  подсказка под полем. Вопросы владельцу: В-4 отдельное поле аллергий с явным согласием, В-5
  шифрование текста, срок хранения `kind=service` (напр. 3 года после последнего визита, beat).
- **(2026-10-24, KA-12 E6.4a) Свой статус неявки не считается.** Счётчик неявок берёт только
  встроенный `no_show`; кастом-статус FB-3 с ролью cancelled («Nicht gekommen») молча не войдёт.
  При спросе — флаг `counts_as_no_show` в `status_defs` и `no_shows.NO_SHOW_STATUSES` из реестра.
- ~~**(2026-10-24, KA-12 E11.1) Счёт: НДС «из брутто» (Bruttomethode).**~~ ✅ 2026-10-25 (`finance/0018`, build-log). Осталось: подтвердить формат у Steuerberater (план §6); черновики, созданные до деплоя, остаются net.
- [x] SSR-листинги (были) + кэш (P2.2b: `apps/core/pagecache.py`, TTL 120с); canonical
  (P2.1c порталы + P2.2a городские страницы); OpenGraph (P2.2a); перелинковка
  город↔портал↔сеть порталов (P2.2a). _(✅ в `main`, a573b35+75ba11d, CI runs 64/65
  зелёные; без миграций.)_ Полноценные контентные SEO-тексты городов — §Отложено.

- **(2026-10-25, T-6b) § 25 UStG + Sicherungsschein для пакетных туров.** Флаг тура «Pauschalreise
  (§ 25 UStG)» (миграция) → счёт печатает «Sonderregelung für Reisebüros» без выделения НДС; поле
  загрузки Sicherungsschein (§ 651r BGB) + ссылка в письме. Ждёт формулировок Steuerberater'а и
  отмашки владельца; счёт по билету (T-6a) уже работает по обычной ставке.
- **(2026-10-25, T-5 ревью) Срок хранения анкет участников событий.** `Ticket.answers` и
  `TicketParticipant.answers` (возможны данные о здоровье, Art. 9) хранятся бессрочно; нужен beat,
  очищающий ответы через N дней после события, + срок в Datenschutzerklärung — решение владельца о N.

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
- ✅ (Track D / D1, сделано): связь Voucher↔Customer — ваучеры в карточке 360°
  CRM (`Voucher.customer` SET_NULL, выдача из `/crm/<pk>/`, миграция
  promotions/0014). Также сделаны quick-wins: JSON-LD AggregateRating + Verified-
  бейдж отзывов (G8) и booking-полировка (авто-confirm по карте, party_size как
  места в группе, booking/0005). См. CLAUDE.md §3 «Отложенные quick-wins».

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

## ✅ Одобренный стек ТЗ (владелец, 2026-07-02) — очередь разработки

> Владелец одобрил ЦЕЛИКОМ три списка: `feature-ideas-2026-07-02.md` (A1–D3),
> втяжку U-E-пакетов в U-C (`uc-plan §11` п.13–14), `market-content-analysis-2026-07-02.md`
> (CM-1–CM-9). Сводная очередь (сверху вниз; правило прежнее: план-док до кода, батчи, CI-гейт):

1. **Волна U-C (В РАБОТЕ с 2026-07-02):** критпуть UC1-1′→UC1-2′→UC1-3→UC2-1→UC2-2/2-3 →
   UC2-4 → UC3-1/3-2 → UC4-3 → UC4-2-доводка → UC5-1; параллельные ветки в паузах CI:
   **E-2 правовой пакет**, **UE2-пакет «Стили скидки»** (UE2-1→UE2-2→UE2-3), **UE3-пакет
   «Промо на канве»** (UE3-1+UE3-2). Source of truth — `uc-plan §11`.
2. **Волна «Контент-хаб» (после критпутя U-C):** CM-1 блог всем архетипам → CM-2
   контент-календарь/отложенная публикация → CM-3 авто-посты из событий платформы →
   CM-4 медиа-библиотека → CM-5 AI-контент-пакет (= A2; ядро Pro-тарифа D1).
3. **Быстрые победы (S; вставлять между батчами):** A3 именованные версии сайта ·
   A4 share-ссылка на черновик · C1 утренний дайджест владельцу · C2 QR-печатка PDF ·
   B3 апселл на деталях.
4. **Средние (M; после контент-хаба, порядок уточним):** B1 Geschenkgutscheine на все
   архетипы · CM-8 карточка клиента 360° · CM-6 репутационный модуль · B2 напоминание о
   незавершённой корзине/брони · B4/CM-9 купоны-триггеры/кампании по сегментам.
5. **Платформа:** D1 Pro-тариф/премиум-модули (решение прайсинга при готовности AI/SMS) ·
   D2 self-serve featured+«Anzeige» (с E-2/E-11) · D3 партнёрка веб-студий (L, позже).
5а. **Порядок после контент-хаба/быстрых побед (владелец, 2026-07-03: «Так и делай»):**
   **UE1+UE4-1 ✅ (2026-07-03)** (промо-блок на канве главной + промо-шаблоны)
   → **правовой-языковой пакет ✅ (2026-07-03, 4 слайса)** — PAngV-ноты, Zusatzstoffe,
   LegalDoc+/agb/+кабинет Recht+засев права, L4-письма (DE=msgid + en.po писем;
   план/грабля de.po-хрома — `docs/legal-lang-package-plan-2026-07-03.md`).
   U-D — после, свежей сессией с ревизией ud-плана. Массовый de.po хрома —
   отдельное решение владельца (§2 плана пакета).
6. **External-gated (двигаются в `external-integrations-backlog.md`):** CM-7 Google-отзывы
   (Places API) · B5/E-8 SMS · LLM-ключ для CM-5/A2 · A5/C3/AB-план — уже в anti-bitrix-плане.

## Отложено / заметки на будущее

- **FB-33 M3-2 (решение владельца 2026-11-20):** без скриптов переход по вкладке окна блока — обычная
  ссылка `?tab=`, набранный, но не отправленный текст теряется. Принято; решить в M3-5a
  (автосохранение при уходе со вкладки или предупреждение «Änderungen nicht gespeichert»).
- **FB-33 — отложено (по классам; M7-0, 2026-11-24).** Один список вместо блоков «FB-33 стопка N — отложено»
  стопок 1 (2026-11-20) … 12 и передач `fb33-next` §5-old/§5-old2/§5-old3/§5. Статусы и доказательства (file:line,
  коммит) — сверка `docs/audit/fb33-2026-11-24/roadmap-stacks-2-7.md` (номера `1.x`…`6.x`) и
  `roadmap-stacks-8-12.md` (`8.x`…`12.x`, `F*`, `G*`, `H*`, `I*`); `7.x` — бывшие строки стопки 7 (в сверку не
  входили), `S13-*` — новые строки плана `fb33-stack13-plan-2026-11-24.md`. Знаки: ⏳ открыто · ❓ чтением не
  проверить (стенд, сервер, владелец) · 🔁 дубль (номер дописан к основной строке) · «→ ст.13 Dn» — берёт стопка 13
  (✅ ставит координатор после свода). Новое отложенное — строкой в свой класс, не новым блоком стопки.
  - **Решение владельца:**
    - ⏳ ст.4 · 4.8 — M4: «Speichern und öffnen» у ⚙ Студии при несохранённых правках (отложено владельцем 2026-11-21).
    - ⏳ ст.4 · 4.13 — подпись «Grundtext» → «Ausgangstext»? (`project-memory.md`, стопка 4).
    - ⏳ ст.5 · 5.2 — M3-7: `allow-scripts` в кадре «Vorschau» (`aufbau_preview.js:140`; рекомендация — без скриптов).
    - ❓ ст.6 · 6.4 — C5: строка про столик у любого бизнеса с `orders` — печатал ли владелец QR.
    - ⏳ ст.6 · 6.6 — M2i-7b: остальные онлайн-оплаты (запись, билеты, Mehrfachkarte, сертификат, доплата остатка, номера) требуют e-mail до оплаты и не берут адрес из вебхука (`booking/public_views.py:257-263`; перенос `orders.payments._adopt_payer_email` в core при втором потребителе).
    - ⏳ ст.6 · 6.7 — M2i-7: принятый риск — письма на непроверенный адрес из Stripe и «старейший клиент» по e-mail; задача «адрес не подтверждён».
    - ⏳ ст.3 · 3.1 — M3-4b: путаница «Kompakt mit Foto» (форма, `card_forms.py:34`) и «Kompakte Zeilen» (вид, `siteconfig.py:4807`).
    - ⏳ ст.3 · 3.2 (🔁 2.2) — форма карточки «Nur Text» (строка без фото): рендер-шаблон + LAY-4 замки, макет за владельцем.
    - ❓ ст.3 · 3.17 — подтвердить текст плашки «Kaufen».
    - ⏳ ст.1 · 1.7 — M3-3 (M0-9): новые виды Team «Raster/Karussell/Liste», Galerie «Mosaik/Karussell», «Fotos zeigen», «Abstand».
    - ⏳ ст.8 · 8.2 — M5a: заголовок «Beliebt» у набора «Hauptmenü» на любой странице (`_block_quick_links.html:2`).
    - ⏳ ст.8 · 8.7 — M2i-6: владелец, сбросивший все поля, при смене типа получит пресет снова (`anfrage_presets.py:108-109`).
    - ⏳ ст.8 · 8.10 (🔁 9.2) — контраст неактивной точки слайдера / обложки `bg-white/50` (~1,5:1) — меняет вид.
    - ⏳ ст.8 · 8.11 — серые ссылки подвала `text-gray-400` (`_base.html:400`) — меняет вид.
    - ⏳ ст.10 · 10.1 — M5b-2: «in ★ bearbeiten» ≠ доступному имени (2.5.3; `page_window.py:105-110`) — принятый остаток по V4.
    - ❓ ст.10 · 10.2 — M5b-2: с JS «Übernehmen» формы заголовка на «Seite» остаётся видимой.
    - ⏳ ст.11 · 11.3 — M5c: новый блок получает `CBLOCK_DEMO_DATA` (`siteconfig.py:1232`).
    - ⏳ ст.12 · 12.2 — M5d-4a: «In der Anprobe zurücklegen» — ключ `site_config["anprobe"]` без экрана в кабинете (→ M5d-7).
    - ❓ ст.12 · 12.7 — en «%(all)s wird dieser Block nicht gezeigt.» — вычитать носителем.
    - ❓ ст.12 · 12.8 — переводы tr/uk стопки 12 — без носителя.
    - ⏳ ст.7 · 7.9 — M2i-7.1: брошенные онлайн-заказы С e-mail висят бессрочно (одно напоминание) — отменять ли через 72 ч после напоминания.
    - ⏳ ст.7 · 7.10 (🔁 F18) — M2i-7.1: лимит пересоздания неоплаченных заказов (удержание товара серией брошенных).
    - ⏳ ст.7 · 7.15 — M2i-7.1: повтор возврата покрывает и «владелец отменил оплаченный заказ, Stripe отказал» — сообщить владельцу как улучшение.
    - ⏳ S13-D5-event-cancel — сводка владельцу «Veranstaltung abgesagt» (`events/services.py:607`, ключ `event-cancel:…:owner`) несёт коды билетов клиентов; по Art. 17 не стирается (`crm.dsgvo.OWNER_MAIL_EXEMPT`, ревью §10.6) — стирать ли и её (тогда коды билетов клиента — в префиксы).
  - **Код-редактор:**
    - ⏳ ст.4 · 4.1a — M3-5c: переводы USP (полоса доверия) в окне (`_bw_usp.html`; `block_i18n.py` usp не знает).
    - ⏳ ст.4 · 4.1b — M3-5c: переводы SEO страницы в окне (`_bw_seo.html`).
    - ⏳ ст.4 · 4.2 — «Deutsch (Grundtext)» и язык бизнеса первым во вкладке «Felder» (`block_i18n.py:787`; в `form_spec.py` нет).
    - ⏳ ст.4 · 4.5 — «🌐 Übersetzen» для «Texte» и свой `id` вместо единственного `id="i18n-ai-note"` (`_bw_formfields_ai.html:2,4`).
    - ⏳ ст.4 · 4.6 — M2i-5c: перевод формы заявки частями (> 60 текстов / 6000 знаков — `i18n_translate.py:36,38,155`).
    - ⏳ ст.4 · 4.11 (🔁 F29) — «Auf der Seite bearbeiten» ведёт на образец типа, а не на объект (`site_schema_views.py:696-699`).
    - ⏳ ст.4 · 4.12 (🔁 F29) — «Seitenaufbau öffnen» у баннера не на главной — голый экран (`_cb_row.html:196`).
    - ⏳ ст.5 · 5.10 (🔁 F28) — M4b: ссылка «Liste» блока страницы (не главной) на окно (`_cb_row.html:154-155`).
    - ⏳ ст.6 · 6.17a — ~80 видов блоков без окна: остаток вне M5d — главная, листинги, категории (`scripts/fb33_m5d_inventory.py`).
    - ⏳ ст.3 · 3.4 — M2b-2b: форма события/тура перезаписывает прочие ключи `details` (сверка отпечатка `details` целиком).
    - ⏳ ст.3 · 3.5 (🔁 2.13, 1.6b) — «Überschrift» блока FAQ в окне (`_bw_faq.html`; `section_titles.faq` черновик не держит).
    - ⏳ ст.3 · 3.6 — переводы своих вопросов объекта в окне (`_bw_faq.html:45`).
    - ⏳ ст.3 · 3.7 — `aufbau_draft.info` не показывает конфликт своих вопросов (`aufbau_draft.py:772-777`).
    - ⏳ ст.3 · 3.8 — ссылки на формы на общем хосте — первые 8 без поиска (`object_faq.py:645` `LINKS_MAX`).
    - ❓ ст.3 · 3.9 — общий хост: «Eigene Fragen jeder Seite» без правки списка (`object_faq.py:1023`).
    - ⏳ ст.3 · 3.10 — M3-6: ось «Breite der Seite» на одну страницу (`_schema_settings.html:58`).
    - ⏳ ст.3 · 3.11 — виды мест «Katalog»/«Seite» в «Wo zeigen» и «Wo zeigen» у слайдера (`window_banner.py:6-7`).
    - ⏳ ст.3 · 3.12 — снимок `show_on` общий: «Abbrechen» вернёт и места второго баннер-блока (`aufbau_draft.py:890-892`).
    - ❓ ст.3 · 3.13 — «N Seiten» считает и текущий блок (`window_banner.py:135`).
    - ⏳ ст.3 · 3.14 — тексты итога корзины (Überschrift / Zeile für die Summe / Hinweis) — M2i-3.
    - ❓ ст.3 · 3.15 — свой вид товаров одной категории в окне (плитки у ★ категории; `page_window.py:293-316`).
    - ❓ ст.3 · 3.16 — `category_page_style` виден в «Seite» у category@… (`page_window.py:301`).
    - ⏳ ст.2 · 2.3 — явный «Standard» поверх формы из Design (`block_card.py:143-147`).
    - ⏳ ст.2 · 2.4 — значок ✓ на выбранной плитке (`_view_tiles.html:6,8`).
    - ❓ ст.2 · 2.5 — асимметрия смены вида: «Liste» сбрасывает форму (M1c), встроенный список главной — нет.
    - ❓ ст.2 · 2.6 — ★-строка каталога (форма), related/upsell, «Karte (bei Kacheln)» категорий (M0-3).
    - ⏳ ст.2 · 2.9 — «Wie anordnen» без JS: две формы, набранное при уходе теряется (`_block_window.html:8`).
    - ❓ ст.2 · 2.10 — после отказа (небезопасная ссылка) без JS введённое не возвращается.
    - ❓ ст.2 · 2.14 — канва Студии не шлёт `faq_base` (правка из устаревшей вкладки — в соседний вопрос).
    - ❓ ст.1 · 1.3c — новый вопрос получает поля перевода только после «Übernehmen».
    - ⏳ ст.1 · 1.6c — «Erste Frage geöffnet» у FAQ (строки нет в коде).
    - ⏳ ст.1 · 1.8 — M3-3a: плитки вида у about/process/cta/testimonials/trust/reviews/contact (`_style_thumb.html`).
    - ⏳ ст.1 · 1.9 — M3-3c: одна группа «Darstellung» вместо двух осей (`_schema_list_field.html:3`); вид «Liste» товаров главной; «ändern» у типа акции.
    - ⏳ ст.1 · 1.10 — подсказка «Regale» у «Liste» с source=categories (`block_views.py:173-178`).
    - ⏳ ст.1 · 1.13 — плитки смены вида в две колонки, в макете M0-9 — три (`_view_tiles.html:4`).
    - ⏳ ст.8 · 8.1 — M5a: `site_search` ограничен хостом `not_found` только в «+ Block»; `normalize` принимает на любом (`siteconfig.py:174`).
    - ⏳ ст.8 · 8.8 — M2i-6: язык, включённый позже, не получает перевод подписи пресета (`anfrage_presets.py:107-108,120-121`).
    - ⏳ ст.10 · 10.4 — класс `ui-tone-run` («запущено») у плашки «Hauptliste» (`site_schema.html:201`, `_cb_row.html:17`).
    - ⏳ ст.10 · 10.5 — имя главного списка в `blocks_for` без тенанта («Sets & Pakete» у гастро; `site_schema.py:1380`).
    - ❓ ст.11 · 11.4 — сводки «тип · параметры» не у всех строк схемы (`_schema_row.html:13`; прогон `fb33_m5d_inventory.py`).
    - ⏳ ст.12 · 12.1 — M5d-4e: «Beispiele unserer Arbeit» без ссылки — нет записи `nav_registry` галереи (`detail_sections.py:755-757`; M5d-6).
    - ⏳ ст.12 · 12.3 — M5d-4a: «Woher» — одна подпись вкладки, не из нескольких полей (`detail_sections.py:143-145`; M5d-8).
    - ⏳ ст.12 · 12.4 — M5d-4b: «— ausgefüllt. / — leer.» для галочки «Video-Beratung» (`window_parts.py:145-146`).
    - ⏳ ст.12 · 12.5 — M5d-3: фраза про «Versandarten…» в `note` до «Er gehört fest…» (`_bw_inhalt.html:2-3`).
    - ⏳ ст.7 · 7.1 (🔁 F16) — M4c: блок только с `card` при охвате «Den ganzen Typ» снимает `layout` типа; раздельного охвата по осям нет.
    - ⏳ передача · G10 — `page_row_ref(None, code)` отвечает `__page` для любого типа (`site_schema.py:4152-4166`).
    - ⏳ ст.15 · S15-draft-fp — восстановленный черновик Студии не несёт отпечатка текстов секций главной (M5e-1a, §14.5): восстановленная вкладка не сверяется с тем, что записало окно.
    - ⏳ ст.15 · S15-item-i18n — переводы пунктов «Schritt», команды и отзывов только в Студии; в окне «Texte» полей перевода у них нет (M5e-1b, §14.5).
    - ⏳ ст.15 · S15-vorher — «Vorher & nachher» без экрана правки; отдельный пункт (решение владельца 2026-11-25).
    - ⏳ ст.15 · S15-versand — ⚙ Студии на `/versand/` открывает схему «Über uns».
    - ⏳ ст.15 · S15-versand-gear — страница-слаг `versand` при выключенных заказах теряет ⚙ (ContentPage).
    - ⏳ ст.15 · S15-upper-slug — страницы с заглавными буквами в слаге не получают ⚙ (`_CONTENT_PAGE_HOST_RE`).
    - ⏳ ст.15 · S15-usp-wie — у `usp_bar` «Wie anordnen» по-прежнему ссылками, без JS набранное теряется (§14.5; отступление от §4 плана).
    - ⏳ ст.15 · S15-von — параметр `von` принимает несуществующую текстовую страницу (LOW, ревью E1t).
  - **Код-витрина:**
    - ⏳ ст.13 · S13-event-anchor — без JS после ошибки брони события редирект без `#buchen`: гость видит верх страницы (итоговое ревью стопки 13).
    - ⏳ ст.13 · S13-event-early — ранние отказы брони события (нет имени, 429, нет мест, промокод) теряют ввод — тот же слот сессии D6.
    - ⏳ ст.14 · S14-E4-route-fp — маршрут тура и разделы структуры формой тура пишутся без своей сверки: чужая правка маршрута в окне перетирается формой, открытой до неё (ревью E4 L2).
    - ⏳ ст.14 · S14-E4-compat — после выката убрать ветку «нет `details_base` в POST — без проверки» в `events/views.py::_save_form_fresh` (ревью security E4 L1).
    - ⏳ ст.14 · S14-E4-photos — при отказе формы события/тура загруженные фото и `delete_image` не сохраняются до повтора (решение владельца 2026-11-24: пока — просьба в сообщении).
    - ✅ ст.14 · S14-E3-wie — «Wie» без JS у блоков с видом в форме `fields` (FAQ, USP, CTA, «Über uns», отзывы) по-прежнему ссылками: набранное теряется при смене вкладки (решение владельца 2026-11-24 — только списки в стопке 14). — сделано ст.15: M5e-1b (ст.15): «Wie» у FAQ, CTA, «Über uns», отзывов — кнопкой вкладки; `usp_bar` — ссылками (§14.5).
    - ✅ ст.14 · S14-E2-ghost — ссылка Студии на окно блока строится по коду хоста без проверки, что страница есть: хост удалённой категории/группы ведёт на `SchemaError`; нет сквозного теста «адрес окна открывает окно этого блока» (ревью E2 LOW). — сделано ст.15: M5e-3 (ст.15): проверка через `host_for(known_slugs=)`.
    - ✅ ст.14 · S14-E8-cleanup — старый `site_search` вне 404 снимается при чтении, лог `info` на каждый запрос; нужна разовая чистка конфигов (команда шагом `deploy.sh`) и `bump_storefront_cache` после деплоя (ревью E8). — сделано ст.15: E8c (ст.15): команда `drop_stray_site_search` шагом `deploy.sh`.
    - ✅ ст.14 · S14-catalog-500 — `/catalog/` на тенанте попадает в `storefront-content-page` (`<slug>/`), у которого нет правила `view_perms`: 500 `ImproperlyConfigured` на стенде (находка исполнителя E7; до стопки 14, маршруты стопка не трогала). — сделано ст.15: K0 (ст.15): `/catalog/` → экран «Produkte», `/imports/` → «Import starten».
    - ⏳ ст.14 · S14-a11y-targets — 16 целей < 44 px вне схемы «Seitenaufbau»: сайдбар, «Öffnen/Speichern/Verwerfen» (`.ui-btn` 40 px, `static/src/app.css:1884`); AA (24 px) соблюдён, планка проекта — AAA → стопка 22.
    - ✅ ст.14 · S14-E1-text — `site_schema.code_for_path` для своей текстовой страницы с собственными блоками (`seite:<slug>`) даёт общий `text` («Über uns»): ⚙ Студии на такой странице открывает схему «Über uns»; в стопке 14 `von` для неё не принимается (запасной вариант), правильно — `text@seite:<slug>` (ревью E1 MEDIUM). Черновые собственные блоки (только в черновике) проверка не видит. — сделано ст.15: E1t (ст.15): своя текстовая страница `seite:<slug>`, ⚙ открывает её схему; призрак — без ссылки.
    - ⏳ ст.14 · S14-E1-L6 — ⚙ на ключ страницы (`window_links.py::settings_url`) `von` не несёт: окно «Seite» правит настройки типа (решение исполнителя E1 по плану L6).
    - ⏳ ст.13 · S13-d8-meta — страницы платформы и портала по токену получают только заголовок `X-Robots-Tag` (их шаблоны не на `storefront/_base`).
    - ⏳ ст.5 · 5.1a, 5.1b, 5.1c (🔁 F30) — M3-7: якоря `data-sf-section` у разделов детали товара (`product_detail.html:21,175`), корзины, подтверждения.
    - ⏳ ст.5 · 5.3 (🔁 F25) — M2i-34: ответы на вопросы, удалённые до POST, теряются молча (`form_answers.py:161-168`) → ст.13 D1.
    - ⏳ ст.5 · 5.4 (🔁 F24) — KDS: расшифровка `custom_answers` на каждый поллинг, без лимита (`orders/views.py:132-149`) → ст.13 D2.
    - ❓ ст.6 · 6.8a (🔁 7.16) — ratelimit писем и страниц (отложено координатором стопки 7).
    - ⏳ ст.1 · 1.3a — перевод закреплённых подписей заявки («What do you need?», «Name» — хардкод `_anfrage_form.html:10`).
    - ⏳ ст.1 · 1.3b — полоса главной: textarea однострочно, choice/bool не рисует (`sections/_anfrage.html:41`).
    - ⏳ ст.8 · 8.6 — M5a: превью подтверждения несёт JSON-LD (`_base.html:30`) → ст.13 D7.
    - ⏳ ст.9 · 9.11 — M5a-2: JSON-LD на выдаче `?q=` (`_base.html:30`, `products.html:16`) → ст.13 D7.
    - ⏳ ст.9 · 9.3 — «Slide» → «Banner-Slide» у фото категории (`_category_header.html:24`).
    - ⏳ ст.9 · 9.8 — query и cookie обходят кэш 404 (`pagecache.py:154-156`) — принято.
    - ⏳ ст.9 · 9.9 — поля Tenant на 404 устаревают до 60 с (`pagecache.py:118`) — принято.
    - ⏳ ст.9 · 9.10 — прогрев кэша 404 без блокировки (`pagecache.py:141`).
    - ❓ ст.9 · 9.12 — порядок токенов `Vary` на хите ≠ промаху.
    - ⏳ ст.7 · 7.14 (🔁 F19) — M2i-7.1: «Jetzt bezahlen» видна за минуты до отмены / при оплате «в пути» (`order_confirmation.html:69-71`) → ст.13 D4a.
    - ⏳ S13-§9.9 — D7: настоящие подтверждения `/bestellung/<code>/` несут LocalBusiness и без `noindex` — после мнения `seo-specialist`.
    - ⏳ S13-§10.2-L7 — D7: FAQPage на выдаче `?q=` — вопрос `seo-specialist`.
    - ⏳ S13-§10.2-L6 — D2: неоплаченные `new` (онлайн-оплата не дошла) стоят в голове доски KDS.
    - ⏳ ст.15 · S15-intro-nl — вступления листингов схлопывают переносы строк; сохраняет их только каталог (`whitespace-pre-line`); голден M2d.
  - **Деньги:**
    - ⏳ ст.13 · S13-advance — `finance/advance.py:254` зовёт `settle_late_payment` без защиты (`settle_late_safely`).
    - ⏳ ст.13 · S13-notify-pending — `notify` при сбое постановки в очередь оставляет строку с `dedupe_key`: повтор письма не создаётся; проверить подбор pending.
    - ⏳ ст.13 · S13-replay — повторённые Stripe СТАРЫЕ события второго платежа после деплоя D4 станут «новым вторым платежом» (граница по дате).
    - ⏳ ст.13 · S13-refund-open — пометка «Rückerstattung offen» в карточках записи, номера, билета (сейчас — письмо и повтор).
    - ⏳ ст.13 · S13-timeouts — таймаут и `max_network_retries` у `connect.refund` и создания Checkout (сейчас только у `expire`/`retrieve`).
    - ⏳ ст.6 · 6.8b — M2i-7: `mark_order_paid` → False = 200 без заказа молча (`billing/webhooks.py:217-219`) → ст.13 D3.
    - ⏳ ст.6 · 6.18c (🔁 F22) — лишний лог и запрос на повтор вебхука («`catch_up` при «same»») → ст.13 D3.
    - ⏳ ст.7 · 7.11 (🔁 F17) — M2i-7.1: `Session.expire` в Stripe при автоотмене не зовётся (сессия моложе 45 мин живёт без своего срока) → ст.13 D4a.
    - ⏳ ст.7 · 7.12 (🔁 F20) — M2i-7.1: «второй intent» у брони/номера/билета (`mark_deposit_paid`, `mark_stay_paid`, билеты) → ст.13 D4b.
    - ⏳ ст.7 · 7.13 — M2i-7.1: писем владельцу «заказ отменён автоматически» и «поздняя оплата возвращена» нет (карточка и лог).
    - ⏳ передача · F21 — два платежа на НЕотменённом заказе (решение владельца: вернуть второй сразу) → ст.13 D4a.
    - ⏳ S13-§9.12 — D3: автовозврат оплаты без сделки (Connect, аккаунт сверен); сейчас письмо владельцу «Zahlung nicht verbucht» (сделку могли удалить намеренно).
    - ⏳ S13-§9.5 — D4a: `Session.expire` и при ручной отмене заказа владельцем (сейчас — только автоотмена; поздняя оплата и так возвращается).
  - **ПДн:**
    - ⏳ ст.5 · 5.5 (🔁 F23) — `Notification.payload` с ответами владельцу — в DSGVO-карту (ретеншн 30 дней есть, `notifications/tasks.py:136-151`; `dsgvo-review.md:13` — только `recipient`) → ст.13 D5.
    - ⏳ ст.12 · 12.11 — K: `registration.collect` не сверяет select со списком (формула `=…` в CSV; `registration.py:101`) → ст.13 D6.
    - ⏳ S13-D5-offer — предложение без FK на клиента (только `Offer.customer_email`) при удалении по Art. 17 сохраняет `customer_name`/`customer_email`/`note`: `ERASURE_POLICY` идёт по FK, в `_email_linked` оферт нет (письма владельцу о нём D5 уже стирает по адресу).
  - **a11y:**
    - ⏳ ст.13 · S13-base-role — роль сообщения об ошибке в `storefront/_base.html` (`status` → `alert`).
    - ⏳ ст.13 · S13-kds — доска KDS: `text-gray-400` (контраст 2.54), кнопки 36 px.
    - ⏳ ст.13 · S13-event-form — имя/e-mail/телефон брони события только с placeholder (без `<label>`, `autocomplete`), без `maxlength` (эталоны).
    - ⏳ ст.13 · S13-csp — инлайн-скрипты страницы события без nonce (CSP пока report-only).
    - ⏳ ст.1 · 1.5 — видимый фокус `<summary>` FAQ (`sections/_faq.html:56`, `_faq_own.html:50`) — меняет эталоны главной.
    - ⏳ ст.1 · 1.11 — `_schema_catalog_view.html:12,21`: рамка `border-gray-200` < 3:1, устаревший текст про Seitenvorlage.
    - ❓ ст.2 · 2.8 — две группы радио одного имени (прогнать a11y-architect).
    - ⏳ ст.2 · 2.15 — контраст `text-amber-600` ≈3,2:1 (`sections/_hero_tiles.html:11`, `_hero_widget.html`) — эталоны многих сайтов.
    - ⏳ ст.5 · 5.6 — «Name *» в корзине без sr-only «(Pflichtfeld)» (`storefront/cart.html:129`).
    - ⏳ ст.8 · 8.12 — плавная прокрутка слайдера без `prefers-reduced-motion` (`_slider_script.html:50,55`).
    - ⏳ ст.9 · 9.4 — без JS точки обложки и шапки — мёртвые кнопки (`_archetype_cover.html:26`).
    - ⏳ ст.9 · 9.5 — автоход обложки 6 с без кнопки паузы, WCAG 2.2.2 (`_archetype_cover.html:57`).
    - ⏳ ст.9 · 9.6 (🔁 F4) — прочие кандидаты мелких целей: `_fulfillment_choice:72`, `products:144`, `lookbook:34`, `wishlist:30,76`, `finder:43`, `offer:105`, `termin_manage:32`, `sections/_cta:19`, `menu/_panel_columns:15`, `booking_index:39`.
    - ⏳ ст.10 · 10.3 — плашка «Hauptliste» + фраза «Die Hauptliste …» — повтор слова (`site_schema.html:201`).
    - ⏳ ст.11 · 11.5 — «Menü» без JS не переключает вкладки (`site_menu.html:32-34`).
    - ⏳ ст.11 · 11.6 — нет `<noscript>` у «Menü».
    - ⏳ ст.11 · 11.7 — стрелки между вкладками «Menü» (APG).
    - ❓ ст.11 · 11.10 (🔁 H4) — горизонтальная прокрутка 104 px шапки кабинета на 320×568 при 200 %.
    - ⏳ ст.12 · 12.6 — M5d-2b: без JS после «Abbrechen» скрытой строки нет якоря `#schema-row-…` (`site_schema_views.py:430-434`).
  - **Стенды и процесс:**
    - ❓ ст.5 · 5.1d — у подтверждения адрес «Vorschau» есть (`urls_tenant.py:985`) — проверить стендом, не хватает ли только якорей.
    - ❓ ст.5 · 5.7 (🔁 F14) — ЛК клиента (konto) с ответами стендом не гонялся — нужен вход magic-link.
    - ❓ ст.6 · 6.3 (🔁 F13) — C5: подсказка про Stripe/e-mail во «Felder» корзины стендом не проверена.
    - ❓ ст.3 · 3.19 — отчёт database-reviewer по catalog/0046, stays/0049 не найден.
    - ⏳ ст.8 · 8.3 — замки превью 404 подменяют `_may_preview` (`test_fb33_m5a_not_found.py:588`).
    - ⏳ ст.8 · 8.4 — замки 404 (R7) без `resolver_match`.
    - ❓ ст.8 · 8.5 — правка блоков 404 из Студии не проверялась.
    - ⏳ ст.8 · 8.13 — `LB4C_WRITE` пишет даты маской (`test_lb4c_section_parity.py:52`).
    - ⏳ ст.8 · 8.14 (🔁 F8) — стенд C5 на свежей БД требует двух `--setup` (в шапке один).
    - ❓ ст.8 · 8.15 — демо-киты без подвала в колонках.
    - ⏳ ст.10 · 10.7 — замки-«грепы» в `test_fb33_m5b2_review2.py:173,180,198,207`.
    - ❓ ст.10 · 10.8 (🔁 G1) — `fb33_m35c_i18n_stand.py` 2 ✗ «живая область окна — снятый перевод» (и на базе).
    - ❓ ст.10 · 10.9 (🔁 G2) — Студия на 390 и без JS новым стендом не проверена.
    - ❓ ст.10 · 10.10 (🔁 G2) — метка на `anfrage` и бросок на promos не проверены.
    - ❓ ст.10 · 10.11, ст.11 · 11.9, ст.12 · 12.12 (🔁 F5, G5, H3) — Firefox / Safari / iOS не проверены (стенды — Chromium).
    - ❓ ст.11 · 11.11 — порог 1280 px и 35 % полосы черновика — по макету, не замером (`aufbau.js:917`).
    - ❓ ст.12 · 12.9 — в стенд-БД обхода нет тура — случаи одного тура «пропущено» (добавить тур в сидер стенда).
    - ❓ ст.12 · 12.10 — окна «Gutschein» и «Finder» стенд «Inhalt» пропускает (`fb33_m5d_inhalt_stand.py:658,719`).
    - ⏳ ст.7 · 7.7 — Студия (`studio_pages`) и прочие списки страниц вне `site_schema` — гейт «Versand без заказов» не проверен.
    - ❓ передача · F3 — разовые 395 ✗ «панель блока с заголовком» — причина не выяснена.
    - ❓ передача · F7 — бизнес без адреса поиска в браузере не открывался (стопка 8).
    - ❓ передача · G3 — подсказка `data-window-hint` без JS (`_block_window.html:8`).
    - ⏳ передача · G4 — стенд M3-7 по умолчанию ждёт блок `m3d1` (`fb33_m37_preview_stand.py:24`; `STAND_REF=st35c` не в шапке).
    - ⏳ передача · G11 — оракул подписи ★ в `test_fb33_m5b_page_row.py:129` — регэксп.
    - ❓ передача · H2 — ECC-прогоны: что не закрыто к мержу (журнал `skill-feedback.md`).
    - ⏳ передача · I1 — итог обхода верхушки стопки 12 в `build-log.md` не записан.
    - ⏳ ст.15 · S15-slice-view — `preflight --slice` сравнивает с `origin/main`, а не с P0 стопки, и не выбирает тесты, которые идут через вьюхи (пример: `test_fb27_r7_category`); инструмент T-13.
    - ⏳ ст.15 · S15-catering-302 — инвентарь: 302 на экранах кейтеринга (находка сессии; причина в стопке 15 не выяснена).
  - **Ops:**
    - ⏳ ст.3 · 3.18 — `lock_timeout` для `migrate_schemas` (AddField с `db_default` на 130+ схемах; `run_locked.py:48` — не БД).
    - ⏳ ст.1 · 1.1 — снять позиционный `legacy_event_i18n` после `form_i18n_realign` и `--residue` на сервере (до 2026-12-15; `siteconfig.py:5688`, `form_spec.py:848`, `jobs/views.py:195`, `demo_i18n.py:289-290`).
    - ⏳ ст.9 · 9.7 — кэш 404 не заменяет лимит частоты.
    - ⏳ ст.7 · 7.4 — одна блокировка на весь отрезок миграций деплоя (сейчас по шагу; пересев между «shared» и «tenant»).
    - ⏳ ст.7 · 7.5 — `seed_demo_tenants`: код выхода ≠ 0, если часть китов упала.
    - ⏳ ст.7 · 7.6 (🔁 F26) — WARNING «блокировку держит родитель» на каждый кит при `--jobs` — одной строкой.
    - ❓ передача · F6, F15, G7 — деплой стопок 6–12 на сервере; пересев, `sync_aggregator`, `rebuild_search_index`; лог «renamed/merged» `__title`.
    - ❓ передача · F9 — `deploy.sh` на сервере (самоперезапуск, `run_locked`, чистка образов) не запускался.
    - ❓ передача · F10 — автоотмена брошенных заказов на живых данных не наблюдалась.
    - ❓ передача · F11 — возвраты и «платёж в пути» на test-ключах Stripe.
    - ⏳ передача · F31 — нет защиты от ручного `migrate` в обход `run_locked`.
    - ❓ передача · F32 — диск сервера (`docker system df`).
  - **Уборка:**
    - ⏳ ст.13 · S13-mark-paid — тело `mark_*_paid` трижды (`booking`, `stays`, `events/payments.py`) и второй платёж заказа inline в `orders/payments.py:592-633` рядом с `payment_holds.is_extra_payment/record_extra_payment` — свести в один помощник (итоговое ревью стопки 13).
    - ⏳ ст.1 · 1.6a — старый конструктор (`site_home.html`) подписывает виды FAQ по `SECTION_STYLE_LABELS`, не по `faq_views` (`siteconfig.py:4766`).
    - ⏳ ст.1 · 1.12 — `media_registry` не учитывает фото блоков (при сборке мусора медиа — `INACTIVE_FIELDS`).
    - ⏳ ст.4 · 4.10 — `aufbau_url` в контексте Студии шаблоном не читается (`core/views.py:3540`).
    - ⏳ ст.5 · 5.11 (🔁 F28) — мёртвый JS «Liste»: остался `site_home.html:2869-2870` `[data-lb-source]`.
    - ⏳ ст.5 · 5.12 — «Im Kabinett ändern» / «🖼 Manage slides» — старые области Студии (`site_home.html:313`, `_stu19_summary.html:9`).
    - ⏳ ст.3 · 3.3 — мёртвые msgid «Kompakte Zeile», «Preis-Etikett» ×5 `.po`.
    - ⏳ ст.2 · 2.7 — мёртвая ветка `f.name == "card"` (`_schema_list_field.html:3,14`).
    - ⏳ ст.8 · 8.9 — `i18n_input.extra_locales` глотает исключение без лога (`i18n_input.py:25-26`).
    - ⏳ ст.9 · 9.1 — общий JS «точка + `aria-current`» в трёх шаблонах (`_archetype_cover.html:51`, `_category_header.html:43`, `sections/_banner_slider_script.html:28`).
    - ⏳ ст.9 · 9.13 — `site_schema._default_rows` кэширует dict (`lru_cache`; в тестах — `cache_clear`).
    - ⏳ ст.10 · 10.6 — двойной расчёт `page_row_ref`/`pseudo_row` во вьюхе (`site_schema_views.py:530,538,665`).
    - ⏳ ст.11 · 11.8 — миниатюры строк схемы (`_schema_thumb.html`) — снос отдельной уборкой (оставлены по ответу владельца).
    - ⏳ ст.7 · 7.2 — вызовы `list_blocks.apply_type_scope` в Студии (`views.py`: Save и `site_preview_draft`) только чистят случайный ключ — снять.
    - ⏳ ст.7 · 7.3 (🔁 F27) — msgid «Den ganzen Typ» (без имени) в `.po` ×5 не используется.
    - ⏳ S13-D6 — три копии CSV-помощника рядом с `apps/core/csv_safe.py::csv_safe`: `aggregator/admin.py:202` `_csv_safe`, `catalog/views.py:1635` `_csv_safe`, `core/legacy_redirects.py:209` `_safe_cell` (без `\t \r`) — свести на ядро.
  - **✅ Сделано или закрыто решением (для истории; доказательство — строка сверки):**
    - ✅ ст.4 · 4.3 — перевод вопроса при «Trotzdem speichern» ложится поверх (`faq_content.py:168-171`; `roadmap-stacks-2-7.md` 4.3).
    - ✅ ст.4 · 4.4 — у нового C-блока поля перевода сразу — заметка о поведении, не долг (`roadmap-stacks-2-7.md` 4.4).
    - ✅ ст.4 · 4.7 — лимит `max` для меток ≤ 500 (`_i18n_translate_js.html:109`, `_bw_formfields.html:28,35,48,58`; сверка 4.7).
    - ✅ ст.4 · 4.9 — M4b: дубли старой панели Студии сняты (стопка 5, `test_fb33_m4b_studio_dupes.py`; сверка 4.9).
    - ✅ ст.5 · 5.8 — подсказка «Felder» корзины про e-mail при онлайн-оплате — C5, стопка 6 (`test_fb33_m2i34_c5_window.py`; сверка 5.8).
    - ✅ ст.5 · 5.9 — M4b: пустой темп «Liste» не очищается — принято как есть (сверка 5.9).
    - ✅ ст.6 · 6.1 — C5: «Übernehmen» без JS 44 px (стопка 8, M3-9c; отмечено ранее).
    - ✅ ст.6 · 6.2 — C5: строка cart/form в матрице M3-0 (`test_fb33_m3_window_before.py:60`, `golden_fb33m3/panel.json`; сверка 6.2).
    - ✅ ст.6 · 6.5 — M2i-7: брошенный онлайн-заказ держит склад — M2i-7.1 (`ORDERS_ABANDONED_HOURS`, `test_fb33_m2i71_abandoned.py`; сверка 6.5).
    - ✅ ст.6 · 6.8c — `folio.record_online` внутри `transaction.atomic()` (`orders/payments.py:361…389`, M2i-7.1; сверка 6.8c).
    - ✅ ст.6 · 6.9 — M3-9 №1 превью «Kategorie» 404 (`site_schema.py:615`, `test_fb33_m39a_links.py:39`; сверка 6.9).
    - ✅ ст.6 · 6.10 — M3-9 №2 «Team» без команды (`page_settings.py:552-557`, `test_fb33_m39a_links.py:54`; сверка 6.10).
    - ✅ ст.6 · 6.11 — M3-9 №3 «Versand» без заказов (`test_fb33_m39a_links.py:73,80`; сверка 6.11).
    - ✅ ст.6 · 6.12 — M3-9 №4 кнопки без JS 40 px (стопка 8, M3-9c; отмечено ранее).
    - ✅ ст.6 · 6.13 — M3-9 №5 `/p/<uuid>/` ru 390 скролл (M3-9a `min-w-0`, `test_fb33_m39a_links.py:130`; сверка 6.13).
    - ✅ ст.6 · 6.14 — M3-9 №6 мелкие цели (стопка 8, M3-9c; отмечено ранее).
    - ✅ ст.6 · 6.15 — M3-9 №7 «Button-Lösung» в ru (`test_fb33_m39a_links.py:109`; сверка 6.15).
    - ✅ ст.6 · 6.16 — M3-9 №8 `blocks_for(summaries=False)` и combos (`test_fb33_m39a_links.py:96`; сверка 6.16).
    - ✅ ст.6 · 6.17b — правило `__page` → `site_schema.page_row_ref` (M5b-1, стопка 9, `test_fb33_m5b_page_row.py`; сверка 6.17b).
    - ✅ ст.6 · 6.18a — защита от одновременного деплоя и пересева (M3-9b `ops_lock`/`run_locked`, `test_ops_lock.py`; сверка 6.18a).
    - ✅ ст.6 · 6.18b — автоочистка образов Docker в `deploy.sh` (M3-9b; сверка 6.18b).
    - ✅ ст.2 · 2.1 — подписи форм карточек по M0-2 (M3-4b, стопка 3, `test_fb33_m3_4b_card_labels.py`; сверка 2.1).
    - ✅ ст.2 · 2.11 — M3-5c переводы текстов блока в окне (стопка 4, `test_fb33_m35c_*`; сверка 2.11).
    - ✅ ст.2 · 2.12 — переводы вопросов FAQ и подписей плашек (`block_i18n.py:17,770-775`; сверка 2.12).
    - ✅ ст.2 · 2.16 — стенд `fb33_m3_window_stand.py`: `&tab=wie`, ожидание ответа (`:351,355-357`; сверка 2.16).
    - ✅ ст.1 · 1.2 — M2i-5c «Übersetzen» во «Felder» (стопка 4, `test_fb33_m2i5c_translate.py`; сверка 1.2).
    - ✅ ст.1 · 1.4 — `role=status` сброшенного перевода (`_bw_formfields.html:12`; сверка 1.4).
    - ✅ ст.7 · 7.8 — M3-9 №4/№6 (указатель «стопка 8») — сделано стопкой 8 (= 6.12, 6.14).
    - ✅ ст.8 · 8.16 — M3-9c остаток №6 (точки обложки, «Rückruf anfordern», «Alle Fotos →») — стопка 9, M3-9d (отмечено ранее).
    - ✅ ст.8 · 8.17 — M5a кэш 404 — стопка 9, M5a-2 (отмечено ранее).
    - ✅ ст.8 · 8.18 — `archetype_cover` на 404 — стопка 9, M5a-2 (отмечено ранее).
    - ✅ ст.8 · 8.19 — `noindex` листингов при `?q=` — стопка 9, M5a-2 (отмечено ранее).
    - ✅ ст.8 · 8.20 — M3-9c мелкие цели вне №6 (`_event_thematic.html:52`, «✎» `products.html:115`, `_schema_pick.html`) — стопка 9, M3-9d (отмечено ранее).
    - ✅ ст.8 · 8.21 — «Закрыто стопкой 8»: C5 40 px, M3-9 №4, №6 блока стопки 6 (отмечено ранее).
    - ✅ ст.9 · 9.14 — `preflight.py` сравнивает `DB_NAME` чужого pytest (`scripts/preflight.py:205-230`, коммит 71d2047; `roadmap-stacks-8-12.md` 9.14).
    - ✅ ст.10 · 10.12 — M5c: «＋ Block» под выбранной и в конце, фокус на ⚙ (стопка 11, `_schema_add.html`; сверка 10.12).
    - ✅р ст.11 · 11.1 — «Felder» у Kontaktformular — нет, ответ владельца: только `anfrage` (сверка 11.1).
    - ✅р ст.11 · 11.2 — плашка «neu» / «— noch leer» — не берём, ответ владельца (сверка 11.2).
    - ✅ ст.11 · 11.12 — M5d-1: «Inhalt» у G3/G1/G4 — стопка 12, M5d-2…5 (`detail_sections.py` `ContentSource`, `test_fb33_m5d3_text.py`, `m5d4a…e`, `m5d5_checkout.py`; сверка 11.12).
    - ✅ ст.11 · 11.13 — варианты select «Ernährung» и др. через `pgettext_lazy` (Kindermenü; 10606fe, `registration.py:27-28`; сверка 11.13).
    - ✅ передача · F1 — полный обход на верхушке стопки 9 — стопка 10: 63 525 ✓ / 0 ✗ (сверка F1).
    - ✅ передача · F2 — стенд целей ru и hotel/restaurant/retreat после ревью — перекрыт обходами стопок 10–11 (сверка F2).
    - ✅ передача · F12 — полный обход на верхушке стопок 6–7 — обходы стопок 8–11 (сверка F12).
    - ✅ передача · G6 — замер «до» P0 скриптом — `scripts/fb33_m5c_measure.py` (стопка 11; сверка G6).
    - ✅ передача · H1 — обход верхушки стопки 11 (2 ✗ Kindermenü) — закрыт 10606fe; база стопки 12 59 643 ✓ / 0 ✗ (сверка H1).
    - ✅ передача · H5 — патчи `docs/wip/` сняты: каталога `docs/wip/` нет (сверка H5, 2026-11-24).
  - Учёт сводки (M7-0, сверка счётом): было 126 строк-пунктов (115 в блоках стопок 1–6 и 8–12 + 11 строк стопки 7; в строке
    бывало несколько дел) = 192 дела: 104 (`roadmap-stacks-2-7.md`) + 66 (`roadmap-stacks-8-12.md` A–E) + 16 (ст.7, `7.1`…`7.16`)
    + 6 уже отмеченных ✅ стопки 8 (`8.16`…`8.21`); плюс 52 дела передач (F1–F33, G1–G12, H1–H6, I1). Все 244 номера выше; чистые 🔁
    передач без своей строки — F33, G8, G9, G12, H6 (указатели на блоки A–E). Стало: 210 строк, из них 46 ✅ (36 отмечены этой
    сводкой) и 6 новых `S13-*`.
- **FB-33 M2i-5 (a11y-architect, отложено):** после ↑/↓/Entfernen/«+ Frage» во вкладке «Felder» фокус
  не возвращается на этот вопрос — `aufbau.js` при открытом окне намеренно пропускает фокус по якорю;
  нужна правка JS (фокус по id вопроса после подмены панели) со стендом 1440/390 — вместе с M3-5a (в M3-3 не делалось).
- **FB-33 M2i-5 (SHOULD security-reviewer, не сделано):** предупреждение во вкладке «Felder» при смене
  типа вопроса, на который уже есть ответы, — готового способа узнать нет (ответы зашифрованы, поиска нет);
  старые заявки и так показывают снимок (замок `test_fb33_m2i5_window_ui`).
- **FB-33 M2i-5 (S0, найдено grep'ом):** в `apps/core/views.py` (строки ~4804, 5123, 5246, 5268, 5495, 5526,
  5552, 5632, 5775, 6043), `stays/views.py:1450`, `aggregator/account_views.py:131`, `tenants/menu.py:1060`
  остались самодельные проверки `next` (`startswith("/") and not startswith("//")`) — `/\host` они пропускают.
  Перевести на `owner_login.safe_next`/`local_next` отдельным security-срезом с тестами (в M2i-5 исправлены
  `jobs._safe_next` и `inbox._safe_next`).
- **FB-33 M2i-2 (ревью 2026-11-20):** `Job/Order.custom_answers` (зашифрованный JSON) грузится со строкой; при нагрузке — `defer("custom_answers")` в больших списках и выгрузках, где ответы не нужны.
- **FB-33 M2i (2026-11-19, architect):** анкета билета (`Event.questions` — подписи, ответ под ключом-текстом вопроса; `apps/events/registration.py`) — перевести на общее ядро `apps/core/form_answers.py` (id `q<n>` и снимок подписи), не меняя событий в M2i.
- **FB-33 M2h (2026-11-19):** блоки «Hinweise» в корзине стоят в узкой левой колонке (2/3 ширины на
  1440) — широкие блоки (баннер, «Liste» в 4 колонки) там тесные; если владельцу нужно — место
  «Hinweise во всю ширину» над сеткой или ограничение видов блока в этом месте.
- **FB-32 S4/S6a (ревью 2026-11-18):** `cart_show_upsell` — и настройка типа страницы корзины,
  и видимость строки «Passt gut dazu»: если в одном черновике «Seitenaufbau» поменять обе, побеждает
  последний писатель (настройки). Свести к одному писателю (убрать ключ из настроек корзины) или
  сверять в `commit`.
- **FB-31.7 (решение владельца 2026-11-16):** перенос старых кодов шаблонов (`*_page_style`,
  `page_styles`, `promo_*_style`, `Category/Promotion.page_style`) в строки-оси схемы —
  команда `materialize_page_axes` (`--dry-run`, отчёт по схемам, шаг `deploy.sh`), прогон на
  копии БД, затем снос чтения `legacy_code` и перевод демо-китов/`sitetemplates` на оси
  (`docs/fb31-p6-cleanup-plan-2026-11-16.md`, срез B).
- FB-31 P6 отложено (LOW): кэш объекта на запрос в схеме объекта (5–7 чтений одной строки на
  показ); `apps/catalog/catalog_parts.py` → ядро `page_parts`; вкладка карточки объекта пишет
  `page_override` без `select_for_update` (окно гонки — миллисекунды после свежего чтения).

- **FB-29, остаток на 2026-11-14 (после R1–R4; сделанное — в `docs/build-log.md`).**
  *Ждёт владельца.* (1) Снять прежние копии слайдов (`site_config["heroes"]`, свои поля
  слайда в блоках «Banner»), менеджер слайдов Студии и `undo` — после сверки переноса на
  сервере. (2) Перенос собственных слайдов блоков на живых данных не прогонялся — первый
  деплой смотреть глазами.
  *Решения по смыслу (как есть, пока не скажут иначе).* (3) Все выбранные баннеры главной
  выключены или вне срока — одиночный заголовок. (4) Блок-место в «catalog» не действует для
  категории со своей схемой — баннер на месте по умолчанию. (5) Место по умолчанию без
  настроек (высота «schmal», стрелки) — настраивается блоком-местом. (6) Адрес фото баннера
  может вести на чужой сервер; запрет сломал бы перенесённые слайды с внешними фото —
  решать вместе с чисткой. (7) Обрезка «по размеру» — по центру. (8) «Zurück zum Standard»
  на вкладке объекта сбрасывает и положение своих блоков.
  *Функции на потом.* (9) свои блоки у тура — сделано (T1, 2026-11-14). (10) Потолок 120 объектов со своими блоками — общий на пять
  видов; копия события в серии переносит отличия, но не свои блоки; скрывать/показывать
  разделы может сотрудник с правом на раздел (без `website.edit`), свои блоки — только с
  `website.edit`. (11) Студия «Aufbau ändern» у объекта со своими блоками ведёт на его строку — сделано (T2).
  (12) Копирование товара — копировать и свои блоки. (13) Примеры в предпросмотре дизайна:
  нет у категорий, акций и на страницах-списках услуг/номеров/событий (только секции
  главной и каталог товаров). (14) Превью готовых дизайнов без скриптов пустые. (15) Поиск
  страниц у баннера фильтрует в базе — сделано (T3). (16) Колонки в узкой ширине — у
  встроенных списков главной и у своего блока «Liste»; прочие блоки-сетки (галерея) — нет.
  *Проверки.* (20) Локально `apps/booking` и часть `apps/catalog` в общем прогоне дают
  «DatabaseWrapper has no attribute schema_name» — загрязнение между тестами, на CI зелёные;
  `test_list_block_sources::test_event_block_queries_do_not_grow_with_cards` падает только
  локально.

- **FB-27 «Design» (2026-11-13).** (1) В «Empfohlen» выходят все сборки типа бизнеса (у
  магазина 14), на макете — 4: решить с владельцем, сколько показывать и по какому признаку.
  (2) Без скриптов превью в карточках пустые — при желании отдавать статичный снимок.
  (3) Готовый дизайн перезаписывает рамки, тени и отступы карточек (панель об этом говорит);
  сохранять значения владельца — отдельное решение.
- **FB-27 (2026-11-13), вывод «Liste» у блока списка.** В макете «Seitenaufbau» у «Wie» три
  кнопки «Raster · Slider · Liste»; витрина умеет сетку и ленту. Вывод строками (фото слева,
  название, цена) — новая функция `list_blocks` + шаблон; решить с владельцем, нужен ли.
- **FB-27 (2026-11-13), остаток границы со Студией.** (1) Наборы блоков страницы акций
  (`use_page_preset`, `add_type_block`) и шаблоны страниц главной ещё применяются из Студии —
  перенести в «Seitenaufbau» или снять. (2) Положение узкого блока (слева/справа) и скрытие
  на устройстве правятся в Студии — в «Seitenaufbau» контролов нет. (3) Оси блока «Liste»
  правятся в обоих местах. (4) Серверные действия вставки блока Студии (`add_block` и др.)
  из интерфейса недостижимы — снять вместе с переносом тестов на `site_schema.apply`.
  (5) Порядок секций страницы события — в Студии. (6) На телефоне подсказка пустой панели
  «Seitenaufbau» говорит «links», хотя схема стоит выше панели.

- **FB-27 R0 (2026-11-11, ревью django-reviewer) — остаточные окна «потерянной записи» в Студии.**
  Основной Save и автосейв закрыты (отпечаток структуры + блокировка строки). Не закрыто:
  (1) нестуктурные ключи (`page_settings`, `design`, меню, `notify`) — отпечаток их не видит, вкладка
  Студии, открытая до такой записи, при Save её откатит; (2) прочие писатели `views.py`
  (инлайн-правка, фото блока, версии, `_insert_list_block`, видео галереи) собирают конфиг из
  `request.tenant` начала запроса без блокировки. Решение — общий хелпер «lock → normalize →
  mutate → save»; часть уйдёт сама в R8 (Студия = только содержимое).

- **SHP-5 (2026-11-09):** приписка «zzgl. Versandkosten» есть у цены на детали товара, в корзине и в подвале; у цен в КАРТОЧКАХ листингов/акций/главной её нет — сверить с юристом, достаточно ли (обычно хватает рядом с каждой ценой), и при необходимости добавить в общую плашку цены.

- **AIS-4 v2 (2026-11-07):** сканированный PDF без текстового слоя сейчас даёт «bitte als Foto
  hochladen». v2 — рендер страниц (pypdfium2) → тот же путь фото W4-4; только при включённом ИИ.

- **W4-6c «Preis auf Anfrage» в каталоге города (2026-11-06).** Товар «nur auf Anfrage» без цены в
  городской каталог пока не попадает (`_product_snapshot` отбрасывает цену 0 — замок). Следующий шаг:
  листинг с `new_price=None` + «Auf Bestellung» (поле уже nullable) — сверить карточки портала,
  сортировку/фильтр цены, `portal_facets`, MCP, открытый фид. Там же: сортировка «Preis aufsteigend»
  на витрине ставит такие товары первыми (0), колонка `primary_action` в CSV-выгрузке, подсказка
  «übersprungen» в массовой правке цены помощника, фикс-наборы (ComboGroup) владельца с таким
  товаром и подарок PR-4 — сейчас не фильтруются (решение владельца, риск низкий).

- **Notifications: досылка «застрявших» PENDING (найдено ревью AIS A-3b, 2026-11-06).**
  `notify()` создаёт строку, затем ставит `send_notification.delay`; если брокер в этот миг
  недоступен, строка остаётся PENDING навсегда — `retry_failed` берёт только FAILED, а
  dedupe-ключ не даёт создать письмо заново. Касается ВСЕХ писем платформы. Нужен beat-проход
  «PENDING старше N минут → в очередь» с защитой от двойной отправки (status-check +
  select_for_update в deliver). Не делать походя — отдельный инкремент с замками.

- **a11y: контраст рамки полей `.ui-input` (2026-11-05, ревью a11y W4-2).** `--ui-line #e5e7eb` ≈ 1,2:1
  на белом — не проходит WCAG 1.4.11 (3:1) для границ полей; фокус — только смена цвета рамки
  (кольцо `--ui-accent-soft` почти белое). Правка глобальная (все экраны кабинета и мастера):
  рамка ≥ #6b7280 или `--ui-line-strong` + `:focus-visible { outline: 3px solid var(--ui-focus) }`.
  Отдельным инкрементом со стендом по экранам.

- **(2026-11-04, FLT) Хвосты фильтров.** (1) GIN-индекс на `AggregatorListing.city_tags` —
  нужен только около 50 тыс. листингов (замер database-reviewer: сейчас последовательный
  проход дешевле). (2) FLT-1f: «живое» число найденного в шторке до «Treffer anzeigen»
  (fetch счётчика) — по спросу. (3) Пилюля «Nur Aktionen» из макета портала не сделана —
  акции уже во вкладках. (4) Вертикальные порталы (FLT-2) получают ту же строку без правок —
  проверить глазами при первом запуске такого портала.
  (5) Кабинет: строка фильтров ещё не стоит на CRM (там один поиск и фильтр компании),
  «Ausgaben»/«Journal» (период) и Lager (свой поиск по коду, без пагинации) — по спросу;
  у «Nur Lieferungen» больше нет отдельной пилюли-переключателя (вход — подпункт сайдбара
  «Lieferungen» и шторка).

- **(2026-11-04, решение владельца «позже») Копия бэкапа вне сервера.** Ночной
  `scripts/backup.sh single` (cron 03:17, восстановление проверено) кладёт дамп и медиа
  только на тот же сервер. Внешняя копия включается без кода: в `.env.prod`
  `BACKUP_S3_BUCKET` + `AWS_S3_ENDPOINT_URL`/`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`
  (Hetzner Object Storage). Отдельный бакет/ключ только на запись — желательно.

- **KA-12 Z-5 — хвосты стойки (2026-10-25, ревью).** (1) Старая кнопка «Abgereist»
  (`action=fulfilled`) и доска переводят бронь в выезд без права `rezeption.edit` — свести гейт
  в `apply_action` для kind stay. (2) Индекс `(status, departure)` у `StayBooking` — когда броней
  станет много (Heute/виджет фильтруют по `departure`). (3) Колонки Heute режутся на 50 без
  подсказки «ещё N», виджет считает всё. (4) Виджет «Abreisen heute» теперь = «выезд сегодня»
  (включая выехавших), а не «ещё выедут». (5) Из плана: no-show-подсказка по `checked_in_at IS
  NULL` после выезда; JSON-LD `checkinTime/checkoutTime`; счёт фирме со стойки; деактивация
  категории с будущими бронями; «offen €» в Heute; `checkin_hour` как гейт раннего заезда.
- **E6.7g хвост (2026-10-25):** формы создания сделки (orders/booking/stays/events/jobs) ищут клиента по e-mail и могут перезаписать телефон существующего клиента — у сотрудника без `kunden.kontakte` это и запись контакта, и «оракул» существования адреса. Решать вместе: создание без права — новый клиент или только имя.
- ✅ **ЗАКРЫТО 2026-10-25 (E6.7g).** ~~KA-12 E6.7g — право `kunden.kontakte` по всем экранам (ревью безопасности E6.7e, 2026-10-25).~~
  Палитра Ctrl+K маскирует e-mail/телефон без `kunden.kontakte`, а список клиентов CRM (и вкладка
  «Kunden» продаж), карточка клиента, карточки сделок показывают контакты любому с `kunden.view`;
  поиск `?q=` по e-mail/телефону позволяет их угадывать. Сделать одним проходом: общий хелпер
  маскировки (уже есть `palette_search.mask_email/mask_phone`), все поверхности с контактами +
  поиск без право-зависимых полей; замок «staff без kunden.kontakte не видит ни одного полного
  адреса». Сегодня право только у владельца (пресет), дыра появится, как только владелец выдаст
  `kunden.view` без контактов.

- **KA-12 E4.2a хвост (2026-10-24, security-ревью B4a):** прямая запись к мастеру
  `/termin/<resource>/` (без услуги) не знает навыков/лид-тайма услуги — горизонт закрыт,
  остальное пред-существующее поведение. Решение владельца: скрывать прямую запись у
  ресурсов, привязанных к услугам навыками, или переводить её на услугу.
- **KA-12 E4.4a:** правила записи (буфер/лид-тайм/горизонт) правит и сотрудник — как цену
  и длительность; закрыть только владельцу — по решению владельца.

- **KA-12 E2.9b — входящие сообщения в две панели (DE-8).** Список тредов слева + тред справа на lg+.
  Тред-страница с поллингом/формами — отдельный инкремент со стендом (2026-10-24).
- **Массовая отмена с возвратом — синхронно в запросе** (≤10, как одиночная кнопка). При росте лимита —
  выносить возвраты в Celery с ключом идемпотентности.


- **B2-8a (2026-10-24): возвраты отдельными событиями.** `DealPayment.refunded_at` — одна дата на строку (дата ПОСЛЕДНЕГО частичного возврата); для точного Ist-среза при нескольких частичных возвратах в разных месяцах — таблица событий возврата. Плюс индекс `DealPayment.created_at` при ~100k строк (ревью БД).
- **KA-12 B2-5 (ревью безопасности 2026-10-24): сверка `event.account` во ВСЕХ денежных ветках
  вебхука Stripe.** Новая ветка `deal_balance` принимает событие только от connected account
  самого бизнеса и только с `payment_status == paid`. Старые ветки (`stay_deposit`,
  `booking_deposit`, `order_payment`, билет, сертификат) доверяют `metadata.tenant_schema` без
  сверки аккаунта и не проверяют `payment_status` (SEPA). Эксплуатация требует знать UUID чужой
  сделки. Нужен отдельный инкремент: `handle_event` уже получает `account`; перед включением
  проверки — убедиться по логам прода, что события Connect приходят с `account`.

- **CI-скорость (2026-10-23, KA-12):** ~15 тестов (billing webhooks/tasks, notifications-settings,
  t829, demo_hygiene) идут по ~60 с каждый — похоже на сетевой таймаут без мока; группа g1 CI выросла
  до 13–40 мин. Найти общий вызов (Telegram/Stripe/resolve) и замокать в conftest.

- **KA-W1 хвосты (2026-10-23, после батча C):** время самовывоза пока только в корзине —
  покупка по акции, принятие предложения и Anprobe его не спрашивают; неоплаченные заказы
  «на месте»/Vorkasse держат окно до ручной отмены (защита — максимум 3 будущих окна на
  контакт); при включённой опции без часов работы кнопка заказа видна, но заказ не
  принимается; две смены в день и срок изготовления по товару («Torte 48 h») — вне v1.

- **MC (2026-10-23, после KA-6 батча E):** ~30 мест с ручным разбором суммы
  `replace(",", ".")` (варианты, допы, смета, расходы, кассовые формы) — свести к
  `apps/core/money.py::parse_money` (одно правило тысяч/запятой на всю платформу).

- **Касса / TSE (KassenSichV), чаевые** (KA-11 В-6, 2026-10-23): НЕ в пилоте. Mini App
  не позиционируем как кассу до решения; при запуске — юрист + сертифицированная TSE
  (облачная), чаевые отдельной строкой. Источники: KA-1 ⚠️, KA-5b G-7.
- **GoBD 10 лет vs DSGVO Art. 17** для клиентов только с заказами/счетами (KA-H11):
  решение «нет» (не трогаем) — клиенты без резерва/брони номера вне обезличивания.

- **KA-H5 хвосты (2026-10-23, ревью счёта из сметы):** (1) «Wertgutschein vs Rabatt» в заявке
  определяется только совпадением `Job.voucher_code` с кодом `Voucher` с балансом; DC-5 кладёт туда
  же заметку владельца — нужна запись о погашении/привязка ваучера к сделке (миграция); (2) PDF счёта
  заявки доступен по двум путям (`/dashboard/finance/…` и `/dashboard/auftraege/<uuid>/rechnung.pdf`) —
  если finance станет owner-only, закрыть и второй; (3) номера Zusatzstoffe на витрине (прайс-лист,
  попап блюда) — как в PDF, общий источник `food.additive_numbers`.
- **KA-H4 хвосты (2026-10-23, ревью возврата денег):** (1) свой статус роли «cancelled» всегда
  возвращает оплату — нужен флаг «ohne Erstattung» (Storno kostenpflichtig) в редакторе статусов;
  (2) рассрочка билета R10 — автовозврата нет (только предупреждение), возврат всех долей по
  `InstallmentCharge` — отдельным инкрементом; (3) отмена оплаченной сделки сотрудником = возврат —
  решить, нужен ли гейт «только владелец»; (4) ЛК `account.cancel_booking` возвращает депозит без
  окна бесплатной отмены (было до KA-H4) — выровнять с правилом stays/events; (5) окно «захвачено,
  Stripe не ответил» — сверка beat-задачей по логу/состоянию «refunding», если появятся случаи.

- **T-8.30 хвосты (2026-10-20):** (1) ✅ T-8.30e (2026-10-21); долг оттуда закрыт T-8.30g (2026-10-21) — было: вне Telegram
  `redeem_detail`/`voucher_redeem` при `auto_redeem_on_scan` по-прежнему гасят по GET (так задумано
  для камеры телефона) — перевести на POST-подтверждение, если появится жалоба; (2) ✅ T-8.30f (2026-10-21): повторное открытие той же initData — до 3 входов с того же IP;
  (3) ✅ T-8.30f: пользователь в самой `OwnerTelegramLink.user_pk` (миграции 0003/0004).
  **Долг T-8.30f:** через релиз убрать чтение зеркала `site_config["notify"].owner_user_pk`
  в `links.still_owner` и `miniapp._owner_pk` (сейчас фолбэк для легаси-связей без
  `user_pk`; до удаления проверить в проде `SELECT count(*) FROM
  platform_bot_ownertelegramlink WHERE is_active AND user_pk IS NULL` = 0); запись зеркала
  пока оставлена;
  (4) проверить, что Caddy ПЕРЕЗАПИСЫВАЕТ `X-Forwarded-For` (лимиты `tgapp-ip`/`tg-start`).

- **(2026-10-20, T-10) Dockerfile: дайджест образа uv и хэши зависимостей** — `uv:0.11.32` закреплён
  тегом (лучше `@sha256:…`), `uv export --no-hashes` (лучше с хэшами + `--require-hashes`).
  Проверять только на реальной сборке образа (здесь сборки нет).
- **(2026-10-20, T-10 D-2) Отпечаток демо не видит файлы фото и код сидера** — после смены фото
  или логики `apply_kit` поднять `SEEDER_VERSION` или пересеять нужный кит `--kit X --recreate`.

- **(2026-10-20, T-8.28) Токен бота портала шифротекстом** (`PortalBot.token` хранится
  открытым текстом; B5b — `EncryptedTextField` с data-миграцией, как `doc_number` MT-2).

- **(2026-10-20, T-8.14) GIN-индекс `jsonb_path_ops` на `AggregatorListing.city_tags`** — тема и
  `?merkmal=` дают seq scan; не срочно до ~50k листингов. Отдельной миграцией с
  `AddIndexConcurrently`; перед этим EXPLAIN ANALYZE фида тематического портала.
- **(2026-10-20, T-8.14) Избранное/сравнение на тематическом портале** не сужаются темой
  (`account_views`, `shortlist`) — свои сохранённые предложения жителя, не утечка; по спросу.

- **(2026-10-20, T-8.10h H-6) Сроки хранения строк уведомлений** — `notifications` хранит chat id
  получателя без срока; нужна очистка (например 180 дней) вместе с журналом доставки.
- **(2026-10-20) Datenschutzerklärung ПЛАТФОРМЫ** — нет абзацев про журнал поиска (T-8.21),
  подписки «Folgen» (T-8.7, T-8.10d) и ИИ-функции; плюс раздел 8 (бот) у бизнеса — юридическая вычитка.

- ✅ **ЗАКРЫТО SF-9/SF-10 (2026-10-19).** (находка M23b.4) Утечка mystery-цены на странице товара.** Rose-баннер акции в `templates/storefront/product_detail.html` печатает `target_promo.new_price` и процент и для `discount_style="mystery"` — секрет акции виден на карточке товара (каталог города и фид Merchant его прячут). Нужен гард как в `_discount_display`. Отдельно: при исчерпанном лимите акция остаётся `active`, корзина показывает промо-цену, а чекаут отказывает «Aktionslimit erreicht» — решение владельца (снимать акцию с витрины или продавать по обычной цене).
- ✅ **(2026-10-19, хвост SF-9) Mystery-акции на услугах/номерах — закрыто тем же коммитом ревью:** слой цены услуги/номера их не видит, форма запрещает такое сочетание.

- **В5 V5-5 (2026-10-17): сделки не считаются в предложениях `/o/<token>/`, публичной смете `/angebot/`, покупке Gutschein/Abo и Warteliste** — v1 покрывает заказ/акции/билеты/заявки/сообщения/брони. Цифры подделываемы (любой может прислать `ch=portal`) — для биллинга не использовать. Строка в Datenschutzerklärung про Referer (атрибуция одного перехода по Referer своего сайта) — за владельцем/юристом. Канал теряется при переходе на «похожий номер» и в месячной навигации календаря номера (Referer частично спасает).
- **В5 V5-4 (2026-10-17): показы не считаются в попапах карты и в таблице сравнения (shortlist)** — v1 считает только карточки `_cards.html`. Сигналы DNT/Sec-GPC не учитываем (агрегат без cookie); если решим учитывать — гейт в `portal_stats.should_count` для всех действий. Строка о показах в Datenschutzerklärung — за владельцем/юристом. Метка пред-гейта view (`first_sight`) при сбое записи не снимается — недосчёт одного просмотра на день, осознанно.

- **В5 V5-2 (2026-10-17): переходы к продавцу из отельной выдачи с датами не считаются.** Попап карты с `range_nights` ведёт напрямую (редирект `/weiter/<pk>/` взял бы листинг из БД и потерял даты). Если понадобится — передавать даты параметром в `weiter` (whitelist `von/bis`) или считать маячком. Фид и сводка жителю тоже идут мимо счётчика (v2, план §13).

- **В2 хвосты (django-ревью 2026-10-16, LOW):** (1) выручка резерва условной акции
  (`promotions/state_machine.py` ~116) = обычная цена × кол-во — для «2 für 1» завышена;
  (2) инлайн-правка цены на канве у условной акции пишет `price_override`, который
  не действует при условии и оживёт при снятии условия — спрятать `data-price-edit`
  у условных; (3) витрина при пустом состоянии товара пишет NewCondition в JSON-LD,
  а портал (В4) — нет; выравнивание по решению владельца.

- **DCC хвосты (2026-10-16):** фото-добор для плейсхолдеров `sg-*` (≈290 ключей; контактные листы Openverse `cc0,pdm` + просмотр глазами + `SOURCES.md`); сводный стенд Playwright портала после пересева (главная, 15 разделов, поиск, «рядом», 390/1440, de/ru); `seed_demo_tenants --refresh-events` (события демо протухают через 1–90 дней); гашение сигналов агрегатора на время сидинга; замер цены деплоя (`migrate_schemas` по +79 схемам — решение владельца Р-4: `--executor=multiprocessing` или сидить по спросу).

- **T-8.7 «Folgen» — хвосты (2026-10-15):** bounce-обработка писем (Resend webhook → снять подписки адреса); Telegram-канал подписки (`channel` — шов, Р-7); «Folgen» на разделе/районе на `/entdecken/` (нужна привязка города из реестра); ротация `follow_token` по расписанию; Р-П9b колокольчик на плитках разделов (решено «нет»).

- **T-8.8 хвосты (2026-10-15):** sitemap-index портала — когда упрёмся в кап 45 000 URL;
  `/llms-full.txt` — не делаем (полный список отдаёт фид); StrikethroughPrice в JSON-LD — только
  после данных «низшая цена за 30 дней» (§11 PAngV); `?ch=` на CTA страницы предложения
  портала (канал страницы, а не только фида) — по спросу; перевод на self-canonical страниц
  предложений (Р-1 B) — после пилота по факту. Ops: `sync_aggregator` после деплоя (старые
  листинги mystery-акций держат цену до пересинка).

- **⚠️ ВАЖНО — внешний Postgres и права на расширения (T-8.20, 2026-10-15; пометка
  владельца «важное»).** Миграция `aggregator/0023` выполняет `CREATE EXTENSION IF NOT
  EXISTS pg_trgm` (поиск опечаток и частей слов). В текущем single-режиме роль
  `POSTGRES_USER` образа — суперпользователь, поэтому проходит молча. При переезде на
  отдельный сервер или managed-Postgres (Stage 0, CLAUDE.md §9) роль приложения ОБЯЗАНА
  иметь право создавать расширения (владелец БД достаточно: `pg_trgm` trusted с PG13),
  иначе `migrate_schemas` остановится и деплой не пройдёт. Чек-лист переезда: (1) убедиться,
  что `pg_trgm` есть в `pg_available_extensions` целевого сервера; (2) либо дать роли
  владение БД, либо заранее выполнить `CREATE EXTENSION pg_trgm` суперпользователем
  провайдера (миграция идемпотентна — `IF NOT EXISTS`); (3) после переезда —
  `manage.py migration_state` + `manage.py rebuild_search_index`. Найдено
  database-reviewer при ревью T-8.20.
- **Студия: блок «Landing pages» панели иногда шире колонки (замечено стендами LB-3 и
  LB-4d-2, 2026-10-03/09).** На скриншоте сразу после перезагрузки билдера подсказка
  «Switch the preview to a page…» и плашка «Showing only blocks…» обрезаны по правому
  краю панели; замер через 4 с переполнения уже не показывает — дело во времени раскладки
  (вероятно, `<fieldset>` с `min-inline-size: min-content` до инициализации панели).
  Косметика, не регрессия: кандидат — `min-w-0` на `fieldset[data-scope="landing"]` +
  стенд-замер в момент первого кадра.
- **N+1 на карточках товара и акции (найдено LB-1a, 2026-10-02).** `Product.has_variants`
  — некешируемое свойство (`active_variants.exists()`), его зовут карточка товара,
  `Promotion.grundpreis` и `price_layer.attach_promos` — по запросу на товар (и больше:
  `in_stock`/`price_from` повторяют) на ВСЕХ поверхностях: главная, каталог,
  `/aktionen/`, блоки «Liste». `prefetch_related` не помогает (`.filter()` на related
  manager мимо кеша). Кандидат: предвычисленный признак/список активных вариантов на
  инстансе (одним запросом на страницу), который свойства читают первым; замок —
  число запросов страницы не растёт с числом карточек. Отдельный перф-инкремент.
- **Приватные медиа за proxy-вьюхой (после P0-2, 2026-09-09).** Гейт
  `apps/core/media_views.py` закрыл `imports/` и `documents/`, но две папки
  остаются публичными ПО ССЫЛКЕ осознанно, потому что приватить их без вьюхи
  значит сломать показ законным пользователям (в шаблонах стоит прямой
  `{{ img.url }}`): `community/` — фото в ленте заезда, доступ к которой
  fail-closed (`apps/community/access.py::role_of`), и `job_photos/` — фото
  клиента к заявке. Нужны: вьюха с проверкой доступа (образец —
  `apps/documents/views.py`), переписывание URL при рендере (в БД лежат
  `/media/...`) и перенос обеих папок в `PRIVATE_PREFIXES`. Туда же — гейт
  «файл принадлежит хосту» и префикс схемы в путях (P1 из плана P0).
- **P0-1 follow-up: токен вне тела.** `_cacheable` перестал класть в общий кэш
  всё, что несёт `{% csrf_token %}`, сессию или flash. Замер на живой главной
  (`test_real_storefront_home_is_still_cached_by_default`): при дефолтном
  конфиге главная кэшируется, форма подписки/заявки — уже нет. Чтобы вернуть
  кэш и таким страницам: убрать токен из разметки, отдавать его JS из куки
  `csrftoken` (+ `ensure_csrf_cookie`-эндпоинт).

- **SSE для чата (M22b, отложено 25.06, зафиксировано 2026-08-01):** тред клиента и
  кабинет живут на поллинге (5 с) + индикатор «печатает» на кэш-флаге — этого
  достаточно и не несёт инфра-рисков. Server-Sent Events — отдельная инфра-задача
  (ASGI, пул воркеров, буферизация в Caddy, backpressure на длинных соединениях);
  делать спланированно, не в автоцикле.
- ~~**i18n характеристик и FAQ услуги (`Service.attributes`/`faq`)**~~ и
  ~~**группа акции (`Promotion.group`)**~~ — **ЗАКРЫТО 2026-08-01**
  (`docs/i18n-owner-content-plan-2026-08-01.md`): оверлеи `attributes_i18n`/
  `faq_i18n` (миграция `booking/0020`, поэлементно через `apps/core/i18n_seq.py`)
  и `group_i18n` (миграция `promotions/0024`, ключ фасета `?gruppe=` остался
  плоским) + рендер `*_localized` + per-locale ввод метки группы в форме акции +
  проход в `demo_i18n.translate_tenant_content` и 66 строк × 4 словаря.
- **Свободные метки вариантов/опций/доп. услуг** (`ProductVariant.label`,
  `ProductOption.label`, `Extra.label`) — тот же класс «free-text владельца на
  витрине», переводов нет. Отложено решением владельца 2026-07-09
  («variant/modifier labels — отдельным решением»); механика для фикса готова
  (`i18n_seq`/`resolve_overlay`).
- **`Service.attributes`/`faq` не редактируются в кабинете** — поля завёл UA4-3,
  форма услуги их не показывает, наполняются только демо-китами. Отдельная задача
  (фича, не i18n); появится форма — per-locale ввод добавится паттерном Ф1.
- **Multi-axis варианты товара (цвет×размер) + фото на вариант** — гэп движка для
  Boutique/Mode (market-gap-a1a2 D3, CONFIRMED_MISSING, размер L): сейчас варианты
  одноосевые. Владелец 2026-07-10: «ок» = в roadmap после демо-волн; демо clothing
  идёт с размерами S–XL одноосево.
- **Таймслоты туров (product → слоты одного дня)** — гэп T6 (market-gap-a6,
  pretix/Regiondo-модель) для tour_operator: сейчас слот = booking-услуга либо
  отдельное Event на дату. Владелец 2026-07-10: «ок» = в roadmap; демо туров
  строится на текущем движке.

- **C1-Telegram (дайджест владельцу в Telegram):** chat_id ВЛАДЕЛЬЦА нигде не
  хранится (TelegramLink — только клиенты). Нужен /start-биндинг владельца
  (поле owner_chat_id на TelegramBot или отдельная привязка) → потом
  notify(channel=telegram) в send_digest_for_tenant. MVP C1 — email (2026-07-03).

- **CM-3, остаток:** авто-черновики из ТОВАРОВ сознательно не делаем (шум при массовом
  импорте/CSV); при желании владельца — префилл-кнопка «Teilen» на форме товара (5 строк,
  паттерн blog_edit). Авто-ПРАВИЛА («каждую новую акцию — сразу в каналы») — уже есть
  фактически (Promotion→active публикуется автоматом); правила для блога/событий — при
  спросе.

- **Per-page хост C-блоков (решение владельца 2026-07-03: ПОКА НЕ ДЕЛАЕМ).** Пакет
  UC2-3(b) (hide-управление секциями info) + UC3-2 (hidden_on+width на детали/листинге) +
  слайс 3 UC2-2 (инсертер C-блоков вне home) требует per-page хранения секций
  (расширение normalize — горячее). Анализ/дизайн готовы: `uc2-3-page-scope-plan-2026-07-02.md`,
  `uc2-2-oncanvas-plan-2026-07-02.md §2`. Вернуться по запросу владельца.

Ремарки, всплывшие по ходу работы. Фиксируем сразу, чтобы не терять между сессиями.

### Волна «Склад-2 / ERP-расширение» — отложено флажком (владелец 2026-07-08)
Крупная СЛЕДУЮЩАЯ волна поверх склад-леджера (U-D3 + T1–T5). Три эпика, каждый —
отдельный трек с миграциями; делать отдельной волной по решению владельца. Границы
уже отмечены в `docs/ud-stock-t5-plan-2026-07-08.md §7`.
- **Chargen / MHD (партии + срок годности) — для еды.** Модель `Lot`/`Charge`
  (product/variant, qty, mhd-Datum, received_at); приёмка по партиям; FEFO-выбор при
  продаже/списании; алерты «скоро истекает»; связать с Verderb-списанием (reason уже
  есть в T3) и с истёкшими партиями. Затрагивает движение остатка (привязка к партии).
- **Мультисклад (несколько локаций).** Склад/локация (Filiale/Lager) как измерение
  остатка: `StockMovement += location`, остаток и реконсиляция per-location, переброски
  (Umlagerung). Затрагивает модель счётчика (сейчас один `stock_quantity` на сущность).
- **Закупки / поставщики (модуль M12).** `Lieferant` (поставщик) + `Bestellung`
  (закупочный заказ): Bestellvorschlag (T5) → черновик заказа поставщику → приёмка
  закрывает заказ и книжит Wareneingang. Связывает `cost_price` (T5) с реальными
  закупочными ценами/условиями.
Точка встраивания: после текущих приоритетов; каждый эпик — план-доком до кода.

### SEO-модуль v2 — прогрессивные/адаптивные настройки + AI-SEO (идея владельца 2026-07-02)
Поверх уже сделанного (per-entity JSON-LD UA4-4b, sitemap/robots, `Hotel`+SEO A5):
- **Заготовки-шаблоны мета** (title/description/OG) с подстановками-плейсхолдерами
  (`{name}`, `{price}`, `{city}`, `{category}`, `{tenant}`) — per-тип страницы
  (главная/листинг/деталь/категория) и per-сущность override; настройка в кабинете
  (вкладка «SEO» в билдере или настройках), live-превью сниппета.
- **Прогрессивность:** разумные дефолты из архетипа (ничего не настраивал → уже хорошо),
  прогрессивное раскрытие («Обычный/Эксперт» как в билдере).
- **Адаптация под ИИ (GEO/LLM):** `llms.txt` на витрине тенанта, чистые семантические
  заголовки, расширение JSON-LD (FAQPage из FAQ-секций UA4-3, Offer/PriceSpecification),
  контроль индексации AI-краулеров (GPTBot/ClaudeBot/PerplexityBot) в robots per-tenant.
- Точка встраивания: после U-B (листинги дадут новые страницы под мета-шаблоны) или
  малым треком параллельно U-C; мета-title листинга услуг/номеров — первый кандидат.
  Согласовать объём/приоритет с владельцем перед стартом.

### Aggregator Stage 3 — единая корзина агрегатора (отложено 2026-06-21)
Заказ из НЕСКОЛЬКИХ бизнесов одним чекаутом → разбивка на per-tenant заказы.
Крупный архитектурный эпик; разложен, ждёт решения владельца по двум развилкам.

**Сложности:**
- Кросс-схемность: заказы (`apps.orders`) живут в схеме тенанта, агрегатор — на
  `public`; единый чекаут пишет заказы в несколько схем (`schema_context`).
- Нет витрины заказуемого каталога на `public` (агрегатор листит акции/stays/
  события — это брони/билеты, не «товар в корзину»). Нужен синк каталога C&C.
- Оплата: split по бизнесам (Stripe Connect, application fee на каждого) — тяжёлый
  отдельный слой поверх P2.5.

**Разбивка:**
- **AG1 — каталог в агрегаторе:** синк заказуемых товаров C&C в `public` (как
  листинги). Предусловие.
- **AG2 — единая корзина (public):** структура `(tenant, product, qty)` в сессии +
  add/remove на карточках агрегатора/портала.
- **AG3 — мультибизнес-чекаут:** один флоу → `create_order` в каждой схеме через
  `schema_context`, подтверждение со всеми кодами. v1 — оплата при получении.
- **AG4 — split-оплата (позже):** Stripe Connect per бизнес, application fee.

**Развилки (решение владельца):**
1. Что класть в корзину: **(A)** только Click&Collect товары еды/ретейла
   (рекомендация — осмысленный мульти-ресторан food-cart, нужен AG1) vs **(B)**
   расширить на акции/предзаказ.
2. Оплата v1: **оплата при получении** (рекомендация — без Stripe-split) vs сразу
   онлайн-split (AG4).

Рекомендация: A + pay-on-pickup, фазами AG1→AG2→AG3, AG4 позже. Старт — AG1.

### Витрина/корзина — что осталось (после UX-итерации R1–R5 + точки самовывоза)
- **Скидка от акции на плитке товара (запрос владельца 2026-06-19).** Товары сами
  скидки не несут — скидка живёт в `promotions.Promotion` (механизм брони/акции,
  отдельный от Click&Collect-заказа). Чтобы показывать «старая→новая цена» на
  карточке БЕЗ расхождения, нужно, чтобы и заказ C&C считал цену со скидкой
  активной акции на товар. План: helper `attach_promo_prices(products)` (один
  запрос активных акций по product_ids → атрибуты old/new/percent на product) для
  карточек; `create_order` применяет скидку активной акции к строке товара. Отдельный
  инкремент (трогает ценообразование заказа).
- **Полные филиалы (Standorte).** Сейчас — лёгкие «точки самовывоза»
  (`Tenant.pickup_locations`, выбор в корзине). Полноценные филиалы со своим меню/
  остатком/часами/QR — крупный отдельный проект (решение владельца: позже).
- **Автозаполнение форм брони/события/Übernachtung** вошедшим клиентом (CA4 сделал
  только чекаут заказа; контекст `account_customer` уже доступен на всех витринных
  страницах — осталось проставить `value=` в формах `/termin/`, `/veranstaltung/`,
  `/unterkunft/`).

### ТЗ: настройка нижнего меню витрины в кабинете (визуальный конструктор)

> **✅ РЕАЛИЗОВАНО 2026-07-03 через доводку S7-билдера (решение владельца:
> «довести существующий», не отдельный bottom_nav-ключ).** Состав/порядок/
> подписи давно настраиваются в /dashboard/site/menu/ (fieldset «Bottom
> menu»); доведено: узел-корзина в кастомном меню получает акцент
> (kind=primary) + бейдж позиций (context.py, S7-ветка), кап 5 был, подсказка
> о лимите и семантике корзины — в билдере. Недоступные модули и так не
> предлагаются (archetype_targets по active_modules). Легаси без кастом-меню —
> авто-таб-бар T2b без изменений (замки test_action_bar). Пункты konto/suchen
> — по-прежнему ждут Tier 3 ЛК / поиска витрины.

**Контекст (решение владельца 2026-06-19).** Витрина получает мобильное нижнее
меню (sticky tab-bar в стиле приложения; референс владельца — иконка+подпись,
корзина акцентом). Владелец должен **настраивать его сам** в кабинете
`/dashboard/site/` — в том же разделе, где живёт визуальный конструктор сайта
(сейчас секции/навигация/шаблоны M20; drag-drop — Stage 3). ТЗ ниже — для
итерации «бизнес настраивает нижнее меню визуально».

**Цель.** Владелец выбирает состав, порядок, подписи и стиль нижнего таб-бара
витрины без кода; превью; легаси без настройки работает как сейчас (P1
`_action_bar`: Звонок + главное действие + Маршрут).

**Модель данных.** `site_config["bottom_nav"]` (через `siteconfig.normalize`,
паттерн как у `nav` M20 ④):
```
bottom_nav = {
  "enabled": bool,            # выключено → текущее поведение P1 (без регрессии)
  "style": "icons_labels",    # на будущее: icons_only / labels_only
  "items": [ {"key": str, "enabled": bool, "label": str(опц. кастом)} , … ]  # порядок = порядок списка
}
```
Реестр известных пунктов `BOTTOM_NAV_ITEMS` (key, дефолт-иконка, дефолт-подпись,
требование-доступности):
- `speisekarte` → `/sortiment/` (нужен catalog; для не-каталожных — «Start» `/`)
- `aktionen` → якорь на секцию акций главной (или страница акций, если появится)
- `warenkorb` → `/warenkorb/` (нужен модуль **orders**; бейдж кол-ва позиций), **акцент**
- `termin` → `/termin/` (нужен модуль **booking**)
- `kontakt` → якорь `#kontakt`/секция контактов (или `tel:` если только телефон)
- `anruf` → `tel:` (нужен `public_phone`)
- `route` → `map_url` (нужен `map_url`/координаты)
- `konto` → личный кабинет клиента — **появляется только когда построим
  кросс-архетипный ЛК (Tier 3, см. пункт ниже)**; до тех пор пункт скрыт
- `suchen` → поиск по витрине — **появляется, когда сделаем поиск витрины**
  (сейчас его нет; для агрегатора поиск есть, для витрины — нет)

**Правила/гейтинг.**
- Пункт показывается, только если выполнено его требование-доступности (модуль
  активен / есть телефон / есть ЛК). Недоступные — не предлагаются в кабинете.
- Лимит видимых на мобайле — **5** (валидация формы + подсказка; лишние
  включённые отсекаются по порядку либо предупреждение).
- Резолвер `apps/core/context.py::_storefront_bottom_nav(tenant)` (зеркало
  `_storefront_nav`) отдаёт готовый список `{url, label, icon, kind, badge}` →
  контекст `storefront_bottom_nav`; шаблон `storefront/_action_bar.html`
  рендерит его вместо текущего хардкода (с фолбэком на P1, если `bottom_nav`
  не задан/выключен).
- Корзина: `kind="primary"` (акцент `var(--accent)`), бейдж = число позиций в
  сессионной корзине.

**UI в кабинете (`/dashboard/site/`).** Отдельный fieldset «Mobile bottom menu»
(как fieldset «Navigation menu» M20 ④): тумблер enabled; список пунктов с
порядком (число) + чекбокс + опц. кастом-подпись; бейдж «недоступно — включите
модуль X»; подсказка про лимит 5. Сохранение — в общий POST формы Site
(`config["bottom_nav"]`), `normalize` санитайзит (неизвестные ключи отброшены,
требования перепроверяются при рендере).

**Stage 3 (drag-drop конструктор).** Нижнее меню — отдельная панель визуального
билдера с live-превью мобильного фрейма; перетаскивание порядка пунктов; выбор
иконки из набора. Пока (до Stage 3) — форма с числовым порядком, как у nav.

**Вне scope текущей итерации.** Пункт `konto` (ждёт Tier 3 ЛК клиента); пункт
`suchen` (ждёт поиск витрины); кастом-иконки (Stage 3); per-страничный таб-бар.

**Критерии приёмки.** (1) Легаси-тенант без `bottom_nav` — витрина как сейчас.
(2) Владелец включает меню, выбирает Speisekarte/Aktionen/Warenkorb — на мобайле
рендерится таб-бар в этом порядке, корзина акцентом с бейджем. (3) Выключенный/
недоступный модуль убирает свой пункт. (4) Тесты: normalize bottom_nav, резолвер
гейтит по модулям, рендер на мобайле, регрессия легаси.

- **Личный кабинет конечного клиента — КРОСС-АРХЕТИПНАЯ задача (решение владельца
  2026-06-19):** нужен НЕ только ресторану, а ВСЕМ архетипам (заказы/брони/термины/
  ночёвки/события/билеты/сметы/лояльность/ваучеры). Проектировать сразу для всех и
  разрабатывать ОТДЕЛЬНО (крупный Tier 3, меняет модель «без аккаунта»). Что
  свести: сейчас аккаунт клиента живёт на портале агрегатора (`PortalUser` в
  aggregator, magic-link, `/konto/`: избранное P2.3b + история броней по email
  P2.3c + opt-out P2.3d) — но НЕ на витрине бизнеса (там всё «без аккаунта»). Надо
  решить: единый кросс-бизнес `PortalUser` ↔ per-tenant аккаунт; история по всем
  движкам (orders/booking/stays/events/jobs/passes), повтор заказа, сохранённые
  адреса, бонусы/уровни лояльности, купоны/сертификаты. Связка — по email (как
  P2.3c кросс-схемно). Вынести в отдельный план перед реализацией. Приоритет —
  после доводки архетипов (Stage 1) и QR-стол/комбо (выбор владельца).
- **Ресторан — доводка до wishlist (2026-06-19, в работе):** Tier 0 (демо-кит до
  100%: модификаторы-пицца, orders+доставка-зоны, events, jobs-кейтеринг,
  лояльность) + Tier 1 мелочи (комментарий повару, блюдо дня/новинка, калории/вес,
  обратный звонок+карта на витрине, upsell, видео). Tier 2 приоритет владельца:
  **QR-заказ со стола** + **комбо/промокоды/upsell**. Tier 3 (схема зала,
  подписки клиента, POS/персонал/франшиза/курьеры, оплата счёта за столом, вызов
  официанта, AI-рекомендации, нативное приложение) — стратегически, позже.

- **G4 Доставка/Versand (2026-06-13, ✅ G4a+G4b в `main`):** расширение
  `apps.orders` доставкой по адресу (детали CLAUDE.md §3). **Отложено по G4:**
  зоны по PLZ-таблице (разные тарифы по регионам — v1 плоский тариф + бесплатно-от
  + Mindestbestellwert + текст-зона); генерация лейбла через API перевозчика
  (DHL/Hermes) + Lieferschein-PDF (v1 — текстовый tracking_code вручную); разные
  мин-суммы pickup/доставка; возвраты/Widerruf-флоу (A2). НДС доставки = как осн.
  товар (включён в total/выручку). **Деплой:** миграции tenants/0014 + orders/0004.

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

- **Чат + поддержка/тикеты (M22) — ЭЛЕВИРОВАНО в план (владелец 2026-06-14).**
  Бывший отложенный «чат покупатель↔бизнес» расширен до полноценного модуля
  коммуникаций: M22a чат клиент↔бизнес (TENANT, виджет+inbox, из коробки для
  архетипов), M22b helpdesk-тикеты бизнеса для его клиентов (status-FSM/приоритет/
  назначение/SLA), M22c платформенная техподдержка (SHARED, владелец↔SiteAdaptor).
  v1 async (email-тред/WhatsApp через `notifications`), realtime/AI — позже.
  **Полное ТЗ и швы — `docs/master-plan.md` §3/§6/§7 (M22).**
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

- **E7-4 (отложено 2026-07-02): Vorkasse за пределами orders** — stays G7 (тарифы с предоплатой),
  booking-депозит, events: сейчас только Stripe; Vorkasse-вариант там = брони с дедлайном оплаты и
  авто-отменой (отдельное согласование UX). База готова: реквизиты на Tenant (`tenants/0020`),
  реестр `Order.PAYMENT_METHODS`. См. `docs/e7-payments-plan-2026-07-02.md §E7-4`.

- **B2.4 (cart-abandonment до ввода email):** требует захвата email на первом
  шаге чекаута (модель CartLead) + DOI-совместимость; UWG-серая зона. Делать
  только по явному решению владельца (каталог §3).

- **Отложено (2026-07-06): UC6-6d — варианты отображения FAQ и похожих фикс-секций (5 шт.)** —
  запрошено владельцем в пакете UC6-6; C-блочные пресеты сделаны (UC6-6c), фикс-секции требуют
  другого механизма (style-ключ секции + ветвление шаблона) — отдельным инкрементом.

- **Контраст акцента витрины (`--accent-fg`)** — ревью 2026-07-28 (low, пред-
  существующее, вне батча): у семейства Look «Nacht» акценты намеренно светлые,
  а CTA-кнопки печатают по ним белый текст (`style="background: var(--accent)"`
  + `text-white`) → на светлом акценте контраст ниже WCAG AA. Системный фикс —
  парная переменная `--accent-fg` рядом с резолвом `storefront_accent`
  (порог относительной яркости 0.179) и её использование во всех местах, где
  сейчас жёстко `text-white` поверх акцента. Требует прохода по витринным
  шаблонам — отдельным инкрементом.
- **(2026-10-16, T-8.26 п.3, database-reviewer) стоимость ночной сверки агрегатора:** прокинуть
  `tenant` в `sync_*_listing` (−2 запроса на объект: Tenant + CustomDomain), батч-снимок
  товара (варианты/категории одним запросом вместо свойств модели), partial-индекс под
  `public()` (`city, -updated_at` при `is_active, hidden_at IS NULL`) — после EXPLAIN на >50k
  строк, кэш `withheld_schemas` на запрос/30 с. Сейчас ~20 запросов на товар за ночь — терпимо.


- (2026-10-16, T-8.26) Кандидат на флак: `aggregator/tests/test_follow.py::test_one_mail_per_day_for_daily_plus_weekly_and_instant_excluded` — один раз упал локально (в т.ч. в изоляции на коде до 5c), на повторе и в CI #2718/#2720 зелёный; `confirmed_at` считается от реального `timezone.now()` при замороженном `now=_at(9)` (2026-10-21) — при повторе на CI заморозить и его.
- **(2026-10-25, KA-12 E6.4c/Z-1, ревью)** (а) подсчёт неявок по `customer__email__iregex` без индекса — при
  росте клиентов хранить нормализованный ящик в `Customer` (lowercase без `+tag`) и сравнивать равенством;
  (б) `invoice_for_deal` без блокировки сделки — двойной клик теоретически даёт два черновика (прецедент
  DC-6): `select_for_update` или частичный unique на `(deal_kind, deal_id)` живых счетов; (в) сброс кэша
  витрины при `site_config` до коммита (класс W9) — `transaction.on_commit`.
- **(2026-10-25, KA-12 Z-2, ревью)** (а) загрузка окон NightRate — запрос на юнит (кэш на экземпляре);
  при росте числа категорий — bulk `load_night_rates(units, …)`/Prefetch `to_attr` (тот же приём снимет N+1
  `season_rates`); (б) «ab»-цена номера в каталоге города — база юнита, не минимум ночей (как и с сезонами);
  (в) фид G8 отдаёт min_nights дня, но не правила G12; (г) разбивка легаси-броней без снимка — по текущим
  ценам (purge NightRate меняет её через 30 дней); (д) Z-3: единственный сервис записи NightRate
  (нейтральная строка → delete, замок против прямых `.update()`), `forget_night_rates` после записи.
- **(2026-10-25, KA-12 Z-3, ревью)** ✅ (д) сделан (`night_rates.py`, grep-замок). Остаток: (а) редирект после
  массовой правки/дня теряет фильтр `?kat=`; (б) неизвестный `?kat=` молча показывает все категории (без
  предупреждения); (в) отказ ±% — без указания, какая категория/день; (г) если «ab»-цена каталога города
  станет минимумом по ночам — реконсиляция листинга при записи NightRate (сейчас не нужна: листинг на
  базовой цене); (д) неизвестный `price_mode`/`min_mode` в ручном POST — молча «nicht ändern».
- **(2026-10-25, KA-12 Z-4)** Остаток: (а) предупреждение «тариф не для этой категории» после drag-переноса
  (fetch 204) не показывается — только при переносе формой; (б) `hotel_search` зовёт `auto_discount` без
  `unit=`/`departure=`/`extra=` — портал может показать цену без Lücken-Deal/акции на номер (расхождение с
  витриной, найдено планом Z-4); (в) спека демо-китов `rate_plans` не умеет ключ `units` — тарифы демо «для
  всех» (наполнить в Z-7); (г) сдвиг доступа staff к ценам (тарифы/сезоны/Kurtaxe/скидки/цена номера) —
  сообщить владельцу в чекпоинте.
- **«Preis auf Anfrage» на витрине (M21.2, 2026-10-31).** CS-Cart умеет «Kontaktieren Sie
  uns für den Preis» (цена 0); у нас `primary_action="request"` по-прежнему рисует цену →
  «0,00 €». Импорт CS-Cart прячет такие товары до цены. Если тип товаров «цена по запросу»
  понадобится — показывать вместо цены «Preis auf Anfrage», без PAngV-нот и корзины.
- **Журнал 404 после переезда (M21.1).** Сейчас недостающие старые адреса видны только в
  Search Console; при спросе — счётчик ненайденных путей тенанта (агрегат без PII) с
  кнопкой «Weiterleitung anlegen».
- **Цены отеля на даты прямо в каталоге города (решение владельца 2026-11-09: «понадобится
  для портала типа Booking»).** Сейчас портал показывает честную «ab … / Nacht» (минимум
  ближайших 60 дней, `stays.from_price`), а цену на конкретные даты — только на сайте отеля.
  Нужно: при «Wann» с датами (заезд/выезд, гости) — цена за эти ночи и скрытие занятых
  номеров в выдаче портала. Это запрос в схему КАЖДОГО отеля на выдачу → не живым расчётом,
  а материализацией: SHARED-таблица «номер × ночь → свободно/цена» (горизонт ~180 дней,
  пересчёт теми же триггерами `aggregator/stay_reprice.py` + ночью), выдача — один запрос
  по диапазону ночей (все ночи свободны, сумма цен), затем точная перепроверка тем же
  `pricing.from_price_cents` на странице отеля. Отдельный план-док; плюс карточка «N ночей ·
  X €» и deep-link с датами (`?von=&bis=&erw=`), как у фида метапоиска G8.
