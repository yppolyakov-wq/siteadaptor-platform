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
- **Самое свежее (2026-06-26): этап «витрина/UX + анти-Битрикс» — Спринт E закрыт + кусок F.**
  E.1–E.4 on-canvas редактор (Undo/Redo, click-to-edit→попап, инсертер «+», drag-on-canvas).
  F: A7 Handwerker-кит · RV3 грид событий+countdown · RV2 agenda-timeline · A5 PAngV+рейтинг+
  **визуальный календарь наличия номера C1–C4** · A4 аллергены+Kombo-тизер · A9/A7 Festpreis ·
  A8 сортировка выдачи. Всё в `main` (`90107c6`), **без миграций**. Точка входа след. сессии —
  `docs/next-session-brief.md` (обновлён 2026-06-26); статусы — `archetype-ux-execution-plan.md`.
- **Самое свежее (2026-07-01): старт РЕАЛИЗАЦИИ «единого слоя продаваемой сущности» + мультиязычности.**
  Планы этапа интегрированы (merge ветки `nifty-einstein`: market-gap A1–A9, `unified-sellable-entity`
  master-track/U-A…U-E/decisions/priority-review, **план Волны L**) + код UA1-1 (деталь услуги). Начата
  **Волна L (мультиязычность, N локалей)**: **L1 ✅** — рантайм-биндинг локалей
  (`Tenant.active_locales`-резолвер, `set_language` валидирует по включённым локалям, оверлей витрины
  генерик по `settings.LANGUAGES`, переключатель шапки — N кнопок). **L2 ✅** — кабинет «Sprachen»
  (`/dashboard/settings/languages/`: чекбоксы языков реестра + дефолт → `enabled_locales`/`default_locale`).
  Обе без миграции. **L3-модель ✅** — i18n на `Service`/`StayUnit` (`name_i18n`/`description_i18n`,
  overlay-семантика: база в плоском поле, переводы в оверлее; `I18nMixin.get_overlay`/`i18n_full`;
  миграции `booking/0011`+`stays/0020`, чистый AddField) — фундамент адаптера U-A. Решения владельца
  S-1(a)/S-2(b LegalDoc)/S-3(реестр DE+EN). SOURCE OF TRUTH этапа —
  `docs/unified-sellable-entity-master-track-2026-06-30.md §4` (очередь волн) + `docs/multilanguage-wave-L-plan-2026-07-01.md`.
  Волна U-A: **UA1-1** (деталь услуги), **UA2-1** (контракт `sellable` в контексте деталей),
  **UA3-1** (override primary-CTA услуги), **UA4-3** (богатая карточка услуги: attributes+FAQ+primary_action),
  **L3c-рендер** (`*_localized` на витрине Service/StayUnit), **UA4-4a** ✅ — generic-модель отзыва
  `reviews.Review` (`entity_kind`+`entity_id`) + data-migration из `catalog.ProductReview` + product
  переключён на generic (список/деталь/submit/демо); per-kind верификатор fail-closed. **UA4-4b** ✅ —
  верифиц. отзывы на Service/Stay/Event через generic (per-kind `has_booked`/`has_stayed`/`has_ticket`
  fail-closed, единый `reviews.submit`, партиал `_entity_reviews.html`) + **per-entity JSON-LD** из
  контракта `SellableEntity` (`core.seo.entity_ld`+`entity_jsonld` в `detail.html`: @type
  Product/Service/Event/LodgingBusiness + AggregateRating на всех детальных). **UA4-1** ✅ — единый
  реестр секций детали `apps/core/detail_sections.py` (Slice A: реестр+LABELS; Slice B: обобщённый
  нормализатор `siteconfig`, паритет event/product; Slice C: билдер-инспектор + **рабочее скрытие
  секций** детали услуги/номера end-to-end). **Демо-отзывы** ✅ — `_seed_entity_reviews` (friseur/hotel/
  retreat: услуги/номера/события по 3 отзыва → секция видна в демо). **UA4-2** ✅ — data-driven цикл
  рендера секций детали: `service`/`stay` тела → `{% for s in body_sections %}` + партиалы
  `sections/detail/_*`; `event` уже был loop-based; `product` остаётся per-block (секции в aside/body/wide,
  управляются `product_detail_hidden`). Замки — паритет-тесты порядка секций; каждая миграция под
  адверсариальным ревью. **Волна U-A: UA1/UA2/UA4 закрыты; из UA3 — только override primary-CTA**
  (аудит 2026-07-01, `…-ua-plan §7`; остаток — см. запись 2026-07-02 ниже).
- **Самое свежее (2026-07-02): Волна U-B (единый листинг/категории/фасеты) — ЗАКРЫТА ЦЕЛИКОМ.**
  **UB1-1 ✅** каркас `templates/storefront/listing.html` (блоки header/facets/toolbar/grid/
  pagination/empty/after + `listing_width`) + `/termin/` на нём + `service_index_layout` (ключ НЕ
  материализуется normalize'ом: отсутствие = легаси-грид; канва: page-block «Services», опция
  «Standard» удаляет ключ). **UB1-2 ✅** единая карточка `_sellable_card.html` + тег `sellable_card`
  из контракта `SellableEntity` (опции вызовом, контракт не раздут) — услуги+номера, листинги+
  home-секции (home стали локализуемыми; `sf-card` теперь и на листингах — стиль SE-2d действует там).
  **UB1-3 ✅** свод products/event_index/stay_index на каркас; характеризационные замки написаны ДО
  свода (`events/tests/test_index_parity.py`, `catalog/tests/test_listing_parity.py`); cursor-пагинация
  и date-search сохранены. **UB2-1 ✅** протокол `apps/core/facets.py::FacetProvider`
  (selected/apply/present/search/sort) + ленивый `provider_for(kind)`, провайдеры-делегаты
  booking/catalog/events/stays — вьюхи зовут провайдер, не хардкод. **UB2-2 ✅** поиск `?q=`
  (icontains v1; i18n по всем локалям: плоские поля + `*_i18n` через JSON-KeyTransform) +
  user-facing сорт на всех 4 листингах; единый тулбар `listing_toolbar`; keyset-safe (q в carry).
  **UB2-3 ✅** фасеты цена/наличие (перенос из вьюхи) / Herkunft (`Product.origin`) / рейтинг
  (bulk_summary generic-отзывов, `pk__in`, без N+1) в `CatalogFacets`. **UB3-1 ✅** (подкатегории-
  первыми — в каркасе с UB1-3, замок в test_listing_parity). **UB3-2 ✅** — M2M-подборки: TENANT-апп
  `apps.collections` (модель `Collection`, плоская, i18n-оверлей, slug=параметр фасета) + M2M
  `Service.collections`/`StayUnit.collections`; фасет-чипы `?kollektion=` на /termin/ и /unterkunft/;
  кабинет `/dashboard/collections/` (CRUD+состав чекбоксами, presence-guard); демо friseur/hotel.
  Разведка-согласование — `docs/ub3-2-collection-recon-2026-07-02.md`. Всё FF-мержено в `main`
  по зелёным CI (ветка `claude/wave-ub-unified-listing-kmcg33`). **Миграции волны:**
  `collections/0001_initial` + `booking/0013` + `stays/0021` — ⚠️ ТРЕБУЮТ ДЕПЛОЯ владельцем
  (`./scripts/deploy.sh single`; опц. `seed_demo_tenants --kit friseur|hotel --recreate` для
  демо-чипов). Дальше: **U-C** (универсальный редактор) — либо L4 (i18n-хром) / E-2 (правовой
  пакет) по выбору владельца. Заметка: «SEO-модуль v2» (прогрессивные мета-заготовки + AI-SEO,
  идея владельца) — в roadmap §Отложено, кандидат после U-B.
- **Самое свежее (2026-07-02, после U-B): остаток Волны U-A (по `…-ua-plan §7`) — 3 из 5 пунктов.**
  **Демо-A9 ✅** — rich-карточка «Inspektion» werkstatt (attributes/FAQ/`primary_action='request'`)
  + 3 service-отзыва; тест рендерит витринную деталь (секции видны). **Combo i18n ✅** —
  `catalog.Combo` += `I18nMixin`+`name_i18n`/`description_i18n` (overlay как у Service/StayUnit,
  миграция `catalog/0012`), адаптер `_combo` локализован → i18n 5/5 kind. **Reviews-email wiring ✅**
  — post-event → `/veranstaltung/<pk>/bewerten/`, post-stay → `/unterkunft/<pk>/bewerten/` (вместо
  портала), booking post-visit НОВОЕ письмо → `/leistung/<pk>/bewerten/` (beat, `post_visit_sent_at`,
  миграция `booking/0014`); ссылки абсолютные, без домена — без ссылки/падения. **UA3-1 слайс 2 ✅**
  — единый `templates/storefront/_buybox.html`: диспатч `cart`/`reserve`/`request`/`booking` по
  `purchase_mode` контракта (или явный `buybox_mode`); паритет-замки ДО свода
  (`test_buybox_parity` catalog/promotions + точные href CTA услуги), разметка 1:1, вьюхи/формы
  не тронуты; план — `docs/ua3-1-buybox-plan-2026-07-02.md`. **UA3-2 ✅ (вариант A+ владельца)**
  — контракт `select_url`/`submit_url`/`buybox_ready`; ветка booking|request `_buybox` —
  двухшаговый гейт (POST-форма ТОЛЬКО при готовом выборе, фолбэк-причина иначе); stay —
  селектор дат+календарь и форма партиалами за одним include (`_buybox_stay_*`), service_slots —
  форма/хинт партиалами (`_buybox_service_*`, селектор = страница); POST-приёмники и
  `book_stay`/`booking.services.book` не тронуты; паритет-замки stays/booking ДО правок; план —
  `docs/ua3-2-two-step-buybox-plan-2026-07-02.md`. **ВОЛНА U-A ЗАКРЫТА ЦЕЛИКОМ (5/5 остатка).**
- **Самое свежее (2026-07-02, после закрытия U-A): E-7 платёжный микс DACH — внутренняя часть
  E7-1..3 ✅** (план `docs/e7-payments-plan-2026-07-02.md`; приоритет №1 вне волн, 6 архетипов).
  `Order.payment_method` (on_site/stripe/vorkasse; миграция `orders/0012`) + `Tenant`
  vorkasse/банк-реквизиты/`stripe_payment_methods` (SHARED `tenants/0020`); пикер способа на
  checkout (только при >1; паритет-замок «один способ = форма прежняя»), Vorkasse-флоу
  (реквизиты+Verwendungszweck в письме/подтверждении, guard IBAN); шов `payment_method_types`
  в `connect.checkout_session` из настроек тенанта (пусто = дефолт Stripe Dashboard) — прокинут
  во все 7 продажных вызовов (orders/stays/gift/booking/passes/events/jobs; installment без —
  мандат off_session), кабинет «Zahlarten» на billing/payments. Vorkasse вне orders — E7-4
  (roadmap §Отложено). Нативные PayPal/Klarna/SEPA — external-integrations-backlog (владелец).
- **Самое свежее (2026-07-02, автономная фаза): ВОЛНА U-C идёт + U-E-пакеты закрыты + E-2 начат.**
  **UC1 ✅ целиком** (UC1-1 golden-замки normalize + фасад page_types/keys/labels; UC1-2 listing/
  info/legal; UC1-3 SECTION_ICONS в реестр + generic `page_inspector`). **UC2-1 ✅ (A+B)** —
  план-док `docs/uc2-1-page-draft-plan-2026-07-02.md`, решение «виртуальный фасад» (хранение
  ПЛОСКОЕ): `PAGE_CONFIG_KEYS` + `apply_page_payload` (семантика 1:1) + `page_config`; шесть
  per-page блоков `site_preview_draft` → один вызов; save-блоки НЕ сводим (form-driven +
  presence-guards → место UC2-4). **Пакет U-E2 «Стили скидки» ✅ целиком:** UE2-1 единый
  `_discount_display.html` (замки parity ДО свода), UE2-2 `Promotion.discount_style` (7 стилей,
  default ""=легаси; миграция `promotions/0019`), UE2-3 mystery hidden-until-reveal (blur+кнопка,
  AlterField-миграция `promotions/0020` без изменения БД). **Пакет U-E3 «Промо на канве» ✅
  целиком:** UE3-1 инлайн discount_percent/compare_at_price/ends_at (+generic `data-dt-edit`
  datetime-попап; поля движка закрыты гейтом), UE3-2 `promotion-photo-edit` + 📷/🗑 на канве
  (реюз apply_gallery_op). **E-2 слайсы 1-2 ✅:** §312j-кнопка «Zahlungspflichtig bestellen»,
  UWG «★ Anzeige», бизнес-страница/отзывы на главном `/entdecken` (портал-опциональная
  `business_page`, тот же url-name). **Продолжение той же фазы:** **UC2-2 ✅** (слайсы 1+2:
  клик→инспектор на всех 4 деталях + drag тематических секций события через `data-ed-section`/
  `moveEdSection`; слайс 3 «C-блоки вне home» ЗАБЛОКИРОВАН архитектурой sections=home-only —
  решение владельца; план `docs/uc2-2-oncanvas-plan-2026-07-02.md`), **UC4-2-доводка ✅**
  (контракт += `price_value`/`price_currency`/`ld_extra`; Offer + BreadcrumbList вторым скриптом
  + Event startDate/location), **UC4-3 ✅** (галерея услуги: шим `Service.images` dict→[dict] БЕЗ
  миграции, `service_photo_edit` → replace/add/remove, `_media_gallery` на 5/5 kind),
  **UC5-1 ✅** (пометка `BUYBOX_CONFIGURABLE="form"` + замок границы). **UC3-1 ✅** (каскад
  темы: sf-card на пропущенных карточках — листинг событий, похожие номера; механизм
  `--sf-*` глобален). **Остаток U-C: UC2-4** (единый инлайн-диспетчер + свод save-блоков —
  чистый рефактор, свежей сессией) и **пакет за ОДНИМ решением владельца** (per-page
  хранение секций / C-блоки вне home): UC2-3(b)+UC3-2+слайс 3 UC2-2 — вопрос
  сформулирован в `docs/uc2-3-page-scope-plan-2026-07-02.md §3`.**
  Локальная грабля: `rl:*`/`resv_token:*` в Redis переживают
  прогоны (cache-префикс — чистить `scan_iter('*rl:*')`).
- **Самое свежее (2026-07-03): UE1+UE4-1 ✅ (промо-блок канвы, D2=LIVE fail-safe; U-E закрыта
  в объёме главной; быстрые победы B3/A3/C2 ✅) + ПРАВОВОЙ-ЯЗЫКОВОЙ ПАКЕТ L4+L5+E-2 ✅ целиком**
  (порядок владельца; план `docs/legal-lang-package-plan-2026-07-03.md`): PAngV-ноты
  деталь/корзина («inkl. MwSt.»/«zzgl. Versand», немецкие msgid) · Zusatzstoffe
  (`Product.additives` + реестр ADDITIVES 13 классов LMZDV, миграция catalog/0013) ·
  **LegalDoc** per-locale (kind×locale, core/0005) + резолвер `apps/core/legal.py`
  (LegalDoc[локаль]→[дефолт]→плоское поле→генерённый фолбэк) + `/agb/` (404 без текста) +
  AGB-ссылка в футере (`agb_present`) + кабинет `/dashboard/recht/` + честное право в
  демо-китах (AGB-заготовка по модулям) · **L4-письма**: `_render(locale)` +
  translation.override (дефолт-локаль тенанта, fail-safe de), клиентские шаблоны 5 флоу
  (reservation+HTML+waitlist/booking/stays/tickets/orders) DE=msgid байт-в-байт,
  `locale/en/.../django.po` ТОЛЬКО письма (109, все переведены), .mo не в git — msgfmt-шаг
  в CI, compilemessages в deploy.sh, gettext в Dockerfile. **Массовый de.po хрома —
  отдельный трек за решением владельца (план §2: сотни англ. тест-ассертов в DE-рендере).**
  Остаток DE-only: owner-письма + gift_voucher/inbox/installment/job_*.
- **Самое свежее (2026-07-03, продолжение): «средние» одобренного стека ЗАКРЫТЫ ВСЕ —
  B1 ✅ (Geschenkgutscheine 1.1–1.7: модуль gift, voucher_code в booking/jobs, un-redeem в 5 FSM,
  balance-сертификаты, кап промокодов tenants/0022) · CM-8 ✅ (карточка 360°) · CM-6 ✅ (Bewertungen
  + ответы + post-purchase) · B2 ✅ (напоминания о неоплате orders/booking/stays/tickets + pay-again
  /bezahlen/) · B4/CM-9 ✅ (купон-кампании по сегментам: `CouponCampaign` promotions/0021 +
  `Voucher.campaign` loyalty/0004 + `segment_customers` поверх UWG-гейта + /promotions/kampagnen/
  + NavItem «Campaigns» (crm) + вход из CRM + beat авто-win-back БЕЗ Tenant-миграции).
  Дальше в очереди: платформа D1–D3 (D1 ждёт прайсинг владельца); блокированы U-D/CM-5/T-1.**
- **Самое свежее (2026-07-03, поздний вечер): идея D3 (партнёрка) ✅ v1 D3.1–D3.4** — решения
  владельца: «делаем», деньги «несколько вариантов» (per-partner: скидка клиенту Stripe-купоном /
  ревшара вручную; wholesale ⏸), v1 read-only, **этап 2 — вход в кабинеты клиентов (D3.5)**.
  SHARED-апп `apps.partners` (Partner + reward-конфиг), `Tenant.partner`, атрибуция `?ref=`,
  кабинет `/partner/` на public, шов `discounts` в подписочный Checkout, unfold-админка.
  D1 Pro-тариф — 🧊 долгий ящик (владелец). Инвентаризация ВСЕХ остатков ТЗ — сводка в чате
  2026-07-03 (≈59 пунктов: 30 готовы к работе / 10 за решением владельца / 10 external-gated /
  5 крупных стадий / 4 Stage-0).
- **Самое свежее (2026-07-03, вечер): идея D2 (self-serve featured) ✅ D2.1–D2.4** — ядро было
  готово (P2.4b): доделаны «★ Anzeige» на карте (UWG на всех поверхностях), вход «★ Feature» из
  списка акций, owner-аналитика показов/кликов (`aggregator/0014`: F-инкременты в split_featured +
  редирект-счётчик `/entdecken/klick/<pk>/`, роут и в urls_portal), generic featured-checkout для
  stays/events (`billing` по `(listing_kind, source_ref)`, `apps/aggregator/featuring.py`,
  `tenant/listing_feature.html`, вьюхи stays/events + входы). D2.5 (цены планов в кабинете) — ⏸
  env-оверрайда достаточно; полный E-11 (claim-your-business) — позже.**
- **Самое свежее (2026-07-06): инциденты прода + ВОЛНА UC6 «Editor UX v2» ЦЕЛИКОМ.**
  **T-5** hotfix verify_domain (боты выжигали LE-квоту → строгий allowlist по Domain;
  опс: рестарт caddy). **T-6/T-6.1** «Edit design» убивал канву (XFO DENY в iframe;
  Chrome цитирует ORIGIN — голый `/`): FAB `target="_top"`+скрыт в канве, deep-link
  `?page=` (канва стартует со страницы клика), «Promotion page» в превью; замок
  `test_frame_escape_links`. **UC6 (план `editor-ux-v2-plan-2026-07-06.md`, решения
  владельца §5): 1** одна кнопка «✏️ Edit» (вкл. по умолчанию) + «⚙️ Template», канва-
  first (рейл/панель скрыты); **2** текст C-блока: align/size/color (ТОЛЬКО палитра
  темы); **3/3a/3b** ширины full/2-3/1-2/1-3..1-6 + положение + авто-РЯДЫ узких блоков
  (`group_block_rows`→md:flex, `_section_block.html`) + «Start new row»; **1b** селектор
  страниц убран — авто-скоуп по пути кадра (PAGE_GROUPS JSON, не escapejs — тот кодирует
  дефисы); **4** фото C-блока: 📷 на канве (`site-cblock-photo-edit`, синк формы по {url})
  + скругление; **5** библиотека блоков: иконки/подсказки + ДЕМО-данные при вставке
  (`CBLOCK_DEMO_DATA`); **6a** ЛЕНТА настроек над канвой (Word-style; попап остаётся В
  ФОРМЕ — панель прячется visibility+transform:none классом `bld-ribbon-open`; мобайл —
  bottom-sheet; свёртка ▾); **6b** visual C-блоков (тень/радиус/отступ/фон → `.cb-box`
  через `--sf-*`); **6c** пресеты при вставке (`CBLOCK_VARIANTS`, двухшаговый инсертер
  «+», адверсариальный замок «каждый пресет проходит normalize»); **6d** FAQ 5 видов
  (реестр `SECTION_STYLES` + `section_row` в рендер). Всё БЕЗ миграций, всё в main.
  Остаток фидбэка владельца: «10 типов на блок» — наполнять по мере (реестры готовы).
- Самые свежие миграции: **`partners/0001` + `tenants/0023`** (D3 партнёрка: Partner + Tenant.partner, SHARED, 2026-07-03 — ⚠️ требуют деплоя) + **`aggregator/0014`** (D2.3 featured показы/клики, 2026-07-03 — ⚠️ требует деплоя) + **`promotions/0021` + `loyalty/0004`** (B4/CM-9 CouponCampaign + Voucher.campaign, 2026-07-03 — ⚠️ требуют деплоя) + **`orders/0014` + `booking/0016` + `stays/0022` + `events/0022`** (B2 payment_reminder, 2026-07-03 — ⚠️ требуют деплоя) + **`reviews/0003` + `orders/0013`** (CM-6 reply + post-purchase — ⚠️ требуют деплоя); задеплоено 2026-07-03 (деплой №2 владельца): **`jobs/0011` + `tenants/0022` + `loyalty/0003`** (B1) и ранее **`booking/0015`** (B1.2 voucher_code/discount_cents) +
  **`tenants/0021`** (C1 owner_digest_enabled, SHARED) + **`catalog/0013` + `core/0005`**
  (Zusatzstoffe + LegalDoc, все 2026-07-03 — ⚠️ требуют деплоя; деплой также пересобирает
  образ с gettext и компилирует en.mo); ранее **`promotions/0019` + `promotions/0020`** (discount_style + mystery-choice,
  2026-07-02 — ⚠️ требуют деплоя); ранее **`orders/0012` + `tenants/0020`** (E-7: payment_method + Vorkasse-
  реквизиты/stripe_payment_methods, 2026-07-02 — ⚠️ требуют деплоя); **`catalog/0012` +
  `booking/0014`** (остаток U-A: combo i18n + post-visit,
  2026-07-02 — ⚠️ требуют деплоя) и **`collections/0001` + `booking/0013` + `stays/0021`** (UB3-2
  M2M-подборки, 2026-07-02 — ⚠️ требуют деплоя); ранее `reviews/0001`+`reviews/0002` (UA4-4a generic Review + data-migration из
  ProductReview); ранее `booking/0012` (UA4-3 attrs/faq/primary_action), `booking/0011` + `stays/0020`
  (L3-модель i18n Service/StayUnit); ещё ранее `stays/0014–0019` + `promotions/0018` (этап витрины/UX;
  L1/L2 миграций НЕ добавляли). Полный список — в build-log.

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
- **Скорость локального прогона: `--reuse-db`.** Вся стоимость локального pytest — в
  пересоздании тест-БД миграциями каждый раз (~70с даже для 1 теста). С `--reuse-db`
  БД переиспользуется → повторный прогон ~1-3с (замер 2026-06-28: 69с→1.1с). Для
  батч-режима/локального гейта гоняем `uv run pytest <модули> -k <...> --reuse-db`.
  ⚠️ При изменении МИГРАЦИЙ — добавить `--create-db` (иначе стале-схема даст ложные
  падения). CI всегда на свежей БД (контейнер эфемерный) — там `--reuse-db` нейтрален.
- CI (`.github/workflows/ci.yml`) гоняется на push в `main` и `claude/**` + на PR:
  `ruff check .`, `ruff format --check .`, `pytest -ra` на Postgres16 + Redis7.
- **Рабочий цикл (по подзадачам):** крупную задачу разбиваем на подзадачи и
  показываем разбивку владельцу. Одна подзадача = один инкремент: ветка
  `claude/<кратко>` → push → **CI на git зелёный** → **чекпоинт с владельцем**
  (показать, что дальше; опц. деплой на сервер `./scripts/deploy.sh single` и
  проверка там) → следующая подзадача. Создание/мерж PR через GitHub API
  недоступны (403) → в `main` мержим git-only push (main не защищён, FF/cherry-pick).
- **ВСЕГДА сначала подготовительная работа, потом код (обязательно).** Перед
  каждым нетривиальным инкрементом — план-док/разведка ДО кода (крупные доработки —
  план-доком до кода, источник правды — соответствующий план в `docs/`). **Паузы на
  проверку (ожидание CI, серийный раннер) НЕ простаивать** — в них вести
  подготовку следующих шагов параллельно: разведка кодовой базы (фоновые
  Explore/Plan-агенты — карта точек изменения, риски, переиспользование), уточнение
  развилок у владельца, проектирование схемы/резолверов, тест-кейсы. Затем
  разрабатывать СТРОГО по этим планам. Незакоммиченные планы/скелеты — сохранять
  (scratchpad или сразу в `docs/`), чтобы не терять между ходами/сжатием контекста.
- **Батч-режим (чтобы не платить латентность CI за каждый микрошаг).** CI — финальный
  гейт, но локальный прогон гоняет ТЕ ЖЕ проверки (`ruff check`/`ruff format --check`/
  `pytest`). Поэтому связные зависимые шаги пишем подряд, каждый гейтим ЛОКАЛЬНО (ruff+
  pytest затронутых модулей), коммитим отдельными коммитами (чистая история/ревью), пушем
  стопкой → **один** прогон CI на верхушке батча → merge по зелёному. На ветке включён
  `concurrency: cancel-in-progress` — промежуточные пуши отменяют устаревший прогон, копится
  только последний. Независимые треки (разные файлы) можно вести параллельными агентами в
  worktree. Размер батча — связный вертикальный срез (напр. резолвер→рендер→UI одной фичи);
  не раздувать так, чтобы при красном CI было трудно локализовать.
  **Финальный гейт ПЕРЕД пушем батча (уроки CI 1116/1121/1122):** `ruff format --check .`
  ЦЕЛИКОМ (не точечно — особенно после скриптовых/sed-правок); при новых Tailwind-классах
  в шаблонах — `npm run build:css` и закоммитить `static/css/app.css` (CI-замок свежести);
  при правках шаблонов — прогнать `apps/core/tests/test_template_comments.py` (многострочные
  `{# #}` запрещены). ⚠️ `ruff format` по ЯВНОМУ пути обходит exclude миграций — старые
  миграции не переформатировать. `billing/tests/test_tasks.py` виснет локально (среда,
  на CI зелёный) — локально гейтить с `--ignore`. ⚠️ Правки адаптеров
  `SellableEntity` (apps/core/sellable.py) гейтить ВКЛЮЧАЯ `apps/tenants` —
  секции главной рендерят карточки через SimpleNamespace-стабы контракта
  (test_services_section и т.п.; урок CI 1145).
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
- **`task-catalog.md`** — 🗂 ЕДИНАЯ КАРТА ID задач (создана 2026-07-03 по фидбэку
  владельца). Правила: новая работа берёт ID из каталога ДО план-дока;
  расширяется → углубляется (B1 → B1.1, не новая буква); семейства не плодить;
  коллидирующие коды называть с семейством («идея B1», «архетип A4»).
  Обновлять в том же коммите, что и build-log-строку.
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
- **`external-integrations-backlog.md`** — 🔌 пункты бэклога, требующие ВНЕШНИХ
  провайдеров (Stripe live, Resend, SMS, OTA-API, метапоиск, Shopify/Woo импорт, Ads,
  Push/Wallet). «Внутреннее» делаем сначала; эти — на этапе внедрения (что подключить +
  блокер владельца). Создан 2026-06-30.
- **`micro-business-verticals.md`** — карта вертикалей DACH (потребности → полнота,
  бэклог G1–G9, порядок retail-пакета и P2.5).
- **`archetype-ux-execution-plan.md`** — 🧭 ПОШАГОВЫЙ план текущего этапа (витрина/UX +
  «анти-Битрикс», Спринты A–F, по файлам/критериям/статусам). Идём строго по нему.
- **`archetype-market-analysis.md`** — сводный рыночный анализ по архетипам A1–A9 +
  «анти-Битрикс»-блюпринт; детальные отчёты — `market-analysis/*`.

## 7. Дальше (актуальный порядок, 2026-07-01)

**🔍 АУДИТ 2026-07-01 (план↔факт + рынок A1–A9 + security) — `docs/audit-2026-07-01.md`.** Пробелы
вплетены в ТЗ: **master-track §7** («что недостаёт» по очереди волн 0→4), `…-ua-plan §7` (остаток U-A:
`_buybox`/UA3-2/AutoRepair/демо-A9/reviews-email не сделаны — «U-A закрыта» неточна), `…-L-plan §10`
(остаток L3-ввод+демо/L4/L5), pointer'ы в ub/uc/ud-планах. Приоритет №1 после багфиксов — **E-7
платёжный микс DACH** (6 архетипов, вне волн). Security: 2× HIGH XSS в карте агрегатора (`_map.html`).

**🧭 АКТУАЛЬНАЯ ОЧЕРЕДЬ (этап реализации «единого слоя»):**
`docs/unified-sellable-entity-master-track-2026-06-30.md §4` — SOURCE OF TRUTH порядка волн.
Порядок: **Волна L (мультиязычность)** → **U-A** (адаптер SellableEntity) → U-B → U-C → U-D → U-E.
Решения владельца зафиксированы — `docs/unified-sellable-entity-decisions-2026-06-30.md` (A/B/C),
приоритеты — `…-priority-review-2026-07-01.md` (P/PR), план L — `docs/multilanguage-wave-L-plan-2026-07-01.md`.
**Статус Волны L:** L1 ✅ (рантайм-биндинг), L2 ✅ (кабинет «Sprachen»), **L3-модель ✅** (i18n
`Service`/`StayUnit`, overlay + миграции). Дальше: **L3c** (per-locale инпут форм/редактора + засев
демо + рендер витрины `*_localized` — идёт с UA1-3) → L4 (хром `.po/.mo`, вкл. кабинет — S-1a) → L5
(правовое i18n+AGB через модель `LegalDoc` — S-2b). Решения S-1/S-2/S-3 зафиксированы (реестр DE+EN).
**Статус U-A (2026-07-02): ЗАКРЫТА ЦЕЛИКОМ** — UA1/UA2/UA3/UA4 ✅ + весь остаток аудита 5/5
(демо-A9, combo i18n, reviews-email wiring, единый `_buybox.html`, двухшаговый buy-box A+).
**E-7 платёжный микс DACH (2026-07-02): внутренняя часть E7-1..3 ✅** (запущено по «делай e7»
владельца; см. §3 и план `docs/e7-payments-plan-2026-07-02.md`; E7-4 Vorkasse-вне-orders —
roadmap §Отложено; нативные провайдеры — external-integrations-backlog).
**ВОЛНА U-C — В РАБОТЕ (старт 2026-07-02, одобрение владельца «начинай UC1-1»).** Source of
truth — `uc-plan §11` (ревизия: часть волны закрыта U-A; втянуты U-E-пакеты UE2/UE3 —
одобрено). **Одобренный стек ТЗ владельца (2026-07-02) — `roadmap-next-sprints.md
§Одобренный стек ТЗ`**: U-C (+E-2, UE2, UE3) → Контент-хаб CM-1..5 → быстрые победы
A3/A4/C1/C2/B3 → средние B1/CM-8/CM-6/B2/B4 → платформа D1/D2/D3; идеи —
`feature-ideas-2026-07-02.md`, контент-анализ — `market-content-analysis-2026-07-02.md`.
**Статус U-B (2026-07-02): ЗАКРЫТА ЦЕЛИКОМ** — UB1-1/1-2/1-3 ✅ (каркас listing.html + единая
карточка + свод 4 листингов), UB2-1/2-2/2-3 ✅ (FacetProvider + поиск/сорт + фасеты цена/наличие/
Herkunft/рейтинг), UB3-1 ✅, UB3-2 ✅ (M2M `Collection` + кабинет + демо; миграции
`collections/0001`+`booking/0013`+`stays/0021` — ⚠️ деплой владельцем). Следующая волна очереди —
**U-C** (универсальный редактор) — либо L4 / E-2 по выбору владельца.
**Мерж-политика владельца (2026-07-01): FF-мерж в `main` после каждой фазы и на багфиксе** (main
не защищён; после мержа с миграциями — деплой `./scripts/deploy.sh single`).

**🔎 Аудит наполненности архетипов + план доработок (2026-06-30) —
`docs/archetype-completeness-audit-2026-06-30.md`.** Проверены 9 китов (демо/функ-
ционал), витрина (главная/категории/деталь товара+услуги/текст/право/ЛК), языковой
модуль; все ключевые факты адверсариально верифицированы. **Главные дыры:** (1) нет
ДЕТАЛЬНОЙ страницы услуги (A3, и через `booking.Service` — A7/A9); (2) AGB нет; (3)
правовое не засеяно в демо (Datenschutz → placeholder); (4) «описание услуг как FAQ»
не выделено. **Бэклог волны** — D1…D10 в §9 того дока (старт: D1 деталь услуги + D2 FAQ).

**🔬 Детальная проверка архетипов «рынок ↔ функционал» (2026-06-30, серия завершена 8/8) —
индекс `docs/market-gap-audit-2026-06-30-index.md`, капстоун `docs/market-gap-synthesis-2026-06-30.md`.**
Пошаговые доки `docs/market-gap-<a1a2|a3|a4|a5|a6|a7|a8|a9>-2026-06-30.md` (каждый: структура
сайта + матрица фич рынка DACH ↔ наш статус + приоритизир. гэпы, всё адверсариально
верифицировано против кода). **Сквозные темы (≥3 архетипов):** деталь услуги (A3/A7/A9),
платёжный микс DACH (PayPal/Klarna Kauf-auf-Rechnung/SEPA + `Order.payment_method`), верифиц.
отзывы per-item, AGB+правовое+§312j+PAngV, языковой модуль, JSON-LD по архетипу, переиспользование
движков между архетипами, SMS-канал. **Единый бэклог** — эпики E-1…E-15 в капстоуне (Tier 1 —
сквозные дешёвые победы; старт волны 1: деталь услуги → правовой пакет → JSON-LD → отзывы → reuse).

**🏗️ МАСТЕР-ТРЕК (решение владельца 2026-06-30, DRAFT на согласование) —
`docs/unified-sellable-entity-master-track-2026-06-30.md`.** Единый слой представления
продаваемой сущности (товар/услуга/номер/событие/заявка) для всех архетипов кроме
агрегатора: протокол `SellableEntity` (адаптер, модели НЕ сливаем) + единая деталь/
листинг/фасеты/категории; **отличается только buy-box по `purchase_mode`**. Поглощает
E-1 (деталь услуги) + T3/T6 (отзывы/JSON-LD) + весь редактор. Фазы: U-A контракт+деталь,
U-B листинг/фасеты, U-C **универсальный визуальный редактор на всех страницах/блоках**,
U-D **унифицированный заказ + Kanban-доска + склад-леджер** (подъём отложенного Stage 3
M10/M14), U-E **канва акций (Canva-like)** — двигать кнопки/шрифты/цвета, виды вывода
скидок. Идём инкрементально за каркасом M20U; старт U1 = вписать `Service` в `detail.html`.

**Языковой модуль (статус 2026-06-30):** фундамент НА ВИТРИНЕ тенанта уже есть —
переключатель DE/EN (`set_language`+`storefront-set-language`+`_base.html`), оверлей
`siteconfig.localize`, модельная i18n `{de,en}`, поля `Tenant.default_locale/
enabled_locales`. НЕ работает: `enabled_locales`/`default_locale` не читаются в
рантайме; `.po/.mo` пусты; хром/письма/правовое — DE-only; EN-контент только у
`pranasy`; нет кабинетного UI языков; на ПУБЛИЧНОМ домене переключателя нет (заметка
`roadmap §Отложено` про публичный домен — корректна). План достройки — L1…L6 (§6.4 дока).

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
   сведены), билдер: пер-секционные контролы (раскладка/число/заголовок/источник/«View all»),
   layout-движок на всех секциях-сетках, **per-page раскладки + вкладка «Pages»**
   (каталог/номера/события/похожие), archetype-aware дефолт главной — всё с live-preview.
   Осталось (опц.): per-page блок-редактор с панелью по клику, реестр секций детальной
   (отложен), realtime-чат (отдельный трек), применение к pranasy. Хронология — build-log.
3. **Наполнение архетипов — витрина/UX + «анти-Битрикс» 🚧 (активный трек, обновлён 2026-06-26).**
   **Точка входа — `docs/next-session-brief.md` (обновлён 2026-06-26).** SOURCE OF TRUTH этапа —
   `docs/archetype-ux-execution-plan.md` (Спринты A–F, статусы по инкрементам, идём строго по нему).
   **Сделано:** Спринт A–D ✅, **Спринт E ✅ (on-canvas E.1–E.4)**, Спринт F частично (A7-кит, RV3,
   RV2, A5 PAngV/рейтинг/**календарь наличия C1–C4**, A4 аллергены/Kombo, A9/A7 Festpreis, A8 sort).
   **Дальше (остаток F):** A6 RV1/RT1/RT2(онлайн-события, нужна миграция Event)/RT3/RT4 · A4 диет-фильтр ·
   A3 богатая карточка услуги (миграция Service)/мастера · A9 авто-данные · A7 before/after · A8 фасеты ·
   A1/A2 отзывы о товаре. Рыночный анализ — `docs/archetype-market-analysis.md` (+ `market-analysis/*`);
   карта потребностей — `micro-business-verticals.md`; крупные доработки — план-доком до кода.
4. **Спринт G — «настоящий анти-Битрикс»: кабинет/админка + онбординг 🆕 (фидбэк владельца
   2026-06-26).** План — `docs/anti-bitrix-admin-plan.md`: AB1 группировка меню кабинета по
   задачам · AB2 страница «Module» (рекомендовано/прочее/премиум + «для каких архетипов») ·
   AB3 мастер онбординга v2 (демо-дефолты + живое превью + язык задач) · AB4 чек-лист готовности
   сайта на дашборде · AB5 регистрация→мастер (high-risk). Цель: «чтобы ребёнок собрал магазин».
5. **Рефактор-гигиена (по желанию):** loyalty/vouchers уже вынесены в `apps.loyalty`.

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
