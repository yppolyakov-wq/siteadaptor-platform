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
- **Самое свежее (2026-07-06, вечер): UC6-7 «весь функционал канвы НА ВСЕХ страницах» —
  7a+7b+7c ЦЕЛИКОМ в main (отмашка владельца «редактирование блоков должно быть на всех»).**
  План `docs/uc6-7-page-blocks-plan-2026-07-06.md`. **7a** новый ключ `page_blocks`
  {host:[cblock]} (sections остаётся home-only, golden-паритет), `normalize_page_blocks`
  (whitelist `PAGE_BLOCK_HOSTS` — 11 страниц, legal исключён), тег `{% page_blocks "<host>" %}`
  (siteui; sess-черновик при ?preview=1; пустой хост в превью → пунктирный якорь). **7b**
  редактор: общий партиал `tenant/_cb_row.html` (pb_page-переключатель pb_id vs cb_id),
  `page_cblocks` в наборе «Landing pages», `_cblock_entry_from_post` (общий save главная+
  страницы, presence-guard `pb_present`), draft passthrough + инсертер «+» на страницах
  (`add_block`/`use_block_template` с page_key+page_path, `_redirect_builder` → `?page=`).
  **7c** drag-перестановка на страницах (`movePageBlock`, отдельное order-пространство хоста)
  + вставка БЕЗ перезагрузки билдера (fetch `_add_block_fetch_response` → row_html → schedule
  перерисует только канву; главная/первый блок пустого хоста — форм-POST). Settings-live на
  страницах уже работало (делегированные form-листенеры). **Два адверсариальных ревью-воркфлоу
  (по 5 измерений) нашли 5 реальных дефектов — все исправлены и проверены на стенде:** 7b —
  скоуп панели вне PAGE_GROUPS (`isHome && !curPbHost`) + `data-scope="home"` на «Content
  blocks»; 7c — drag-порядок при вставке (renumber по значению order_cb), идемпотентный
  фолбэк `.catch`→reloadBuilderPage (сервер коммитит до ответа → без дубля), скоуп drag/«+»
  до `[data-pb-host]` (не фикс-секции витрины). Замки: `test_cblocks_builder` (+8),
  `test_live_preview`, `test_home_content_blocks_details_is_home_scoped`; стенд verify_7b/
  verify_scope/verify_7c1/verify_7c_fixes/verify_scope3. **Всё БЕЗ миграций, всё в main
  (9900b09).** Остаток UC6-7: **7d** (настройки меню + библиотека примеров в ленту).
- **Самое свежее (2026-07-07): UC6-7d/8/9/10 + Sprint G (AB1+AB3) — всё в main, без миграций.**
  **UC6-7d** ✅ (☰ Menu / 🧱 Blocks шорткаты в тулбар). **UC6-8** ✅ — 10 видов отображения
  на КАЖДЫЙ тип C-блока (`CBLOCK_VARIANTS`) + 5 видов у фикс-секций со стилями
  (`SECTION_STYLES`, +team «duo», +trust «cards»). **UC6-9** ✅ — оптимизация пространства
  ленты: Undo/Redo/статус в верхнюю строку (полоса над канвой убрана), настройки-«поля»
  (мелкий заголовок сверху, контрол снизу; чекбоксы — чипы). **UC6-10** ✅ — компактный
  тулбар: имя блока + Простой/Эксперт + ▾/✕ переехали из шапки ленты в верхний тулбар
  (`.bld-ctx`, виден по `#bld-root.bld-has-block`); при выбранном блоке подсказка/статус
  прячутся; дублирующая подпись в ленте скрыта, голова блока в одну строку с настройками →
  **для простого блока весь редактор = 2 узкие строки** (проверено на стенде Playwright).
  **Sprint G «анти-Битрикс»** — аудит (4 Explore-агента): ~85% уже было в коде (AB2/AB4/AB5 ✅),
  дозакрыты **AB1** (язык задач в меню кабинета: `NAV_TASK_LABELS`/`nav_task_label` +
  тег `cabinet.nav_task_label`) и **AB3** (демо-дефолты в мастере: шаг 1 «🎁 Mit Beispielen
  starten» → `apply_business_type`+`load_demo`+шаг дальше). План — `docs/anti-bitrix-admin-plan.md`
  (трек ЗАКРЫТ). Остаток фидбэка UC6: «10 типов на блок» — наполнять по мере (реестры готовы).
  **Затем UC6-10b** (2026-07-07, «ещё компактнее»): высота хрома простого блока 119px→~81px
  (−32%; тулбар/лента/поля тоньше, зазор под тулбаром убран), стиль полей UC6-9 сохранён;
  main `a0e221b`, без миграций.
- **Самое свежее (2026-07-07): ВОЛНА U-D ЗАКРЫТА ЦЕЛИКОМ (UD1..UD3) — единый заказ + Kanban-доска
  + склад-леджер.** По ТЗ `docs/ud-wave-tz-2026-07-07.md` за одну сессию (ветка
  `claude/unified-order-kanban-stock-af3pl7`, 4 коммита). **UD1:** `apps/core/transactions.py`
  (`transaction_for(kind, obj)` над 6 FSM-транзакциями, ленивый резолвер модели/FSM, читает статус
  не пишет) + `apps/core/pipeline.py` (статус→стадия intake/in_progress/done/terminal per-kind);
  ЛК 6 билдеров на `transaction_for` (+побочно исправлен латентный баг: `_reservations` падал на
  `get_status_display()` — Reservation без choices → раздел скрывался); `manage_sections_for`.
  **UD2:** `_status_actions.html`+тег (замена хардкода в stays/booking-календарях), доска
  `/dashboard/board/` (вкладки/колонки/**drag-drop** нативный HTML5, snap-back на 409), generic
  `kanban_action` (`SM().apply` — тот же путь, что per-app; KDS не тронут, D2), модуль `board` (core).
  **UD3:** новый TENANT-апп `apps/inventory` — `StockMovement` (append-only, идемпотентность,
  миграция `inventory/0001`), леджер РЯДОМ со счётчиком (D1); врезка `record_movement` только в
  orders(sale/restore)+jobs(commit) в той же atomic; кабинет `/dashboard/stock/` (приёмки/корректировки/
  инвентаризация/Meldebestand + реконсиляция «Startbestand buchen»). `app.css` пересобран. **⚠️ Миграция
  `inventory/0001` ТРЕБУЕТ ДЕПЛОЯ.** Детали — build-log 2026-07-07.
- **Самое свежее (2026-07-07, продолжение): UD4-2 (каналы уведомлений email ∥ Telegram) — ЦЕЛИКОМ**
  (решение владельца «все три»). `apps/notifications/prefs.py` — реестр событий + `channel_enabled`
  (хранение `site_config["notify"]`, БЕЗ миграции, дефолт = всё вкл). Гейтинг customer email+telegram
  во всех 6 доменных `enqueue_*` + закрыты пробелы (Telegram для job «Auftrag fertig» и reservation).
  Telegram ВЛАДЕЛЬЦУ: deep-link `start=owner-<token>`, `owner_chat_id` в site_config, `send_to_owner`
  + пуш в owner-ветках. Кабинет `/dashboard/settings/notifications/` (матрица клиента + owner-каналы +
  «Telegram verbinden»), nav «Benachrichtigungen». SMS остаётся отложен (D3 external). Без миграций.
- **Самое свежее (2026-07-08, вечер): редактор-доводка + старт SEO-модуля v2.** Порядок владельца
  «редактор → SEO v2 → DE(T-1) → Склад-2». **UC2-4** закрыт: инлайн-диспетчер (`apps/core/inline_edit.py`)
  оказался уже готов (верифицирован); «свод save-блоков» — **WONT-FIX** (вьюха уже чистая, рефактор =
  риск без пользы; план `docs/uc2-4b-save-blocks-plan-2026-07-08.md`). **UC6-6h** — визуальные пресеты
  шапки (Classic/Centered/Minimal) в области «Menu» канвы. **SEO-1 ✅** — движок мета-заготовок
  (`apps/core/seo_meta.py`: плейсхолдеры+резолвер+клампы; `context_processors.seo`; провод `_base.html`
  title/description; проверено на сиде — home «… · Hilden»). **SEO-2 ✅** — кабинет
  `/dashboard/site/seo/` (per-тип редактор + плейсхолдер-чипы + **live Google-сниппет**) +
  `siteconfig.normalize_seo` (SEO-шаблоны переживают normalize, иначе сохранение билдера их бы стёрло);
  проверено на сиде (кабинет → `<title>` «Hofladen Sonnenfeld — Ihre Bäckerei in Hilden»). **SEO-3 ✅**
  — AI-SEO/GEO: **FAQPage JSON-LD** (тег у видимого FAQ), **контроль AI-краулеров** (`AI_CRAWLERS` в
  robots.txt по `seo.allow_ai`, тумблер в кабинете, `normalize_seo` materializ. только при False),
  **`llms.txt`** (описание бизнеса + разделы для AI-ассистентов). Проверено на сиде (robots блокирует
  GPTBot/ClaudeBot, llms.txt «# Hofladen Sonnenfeld», home = FAQPage JSON-LD). **Волна SEO v2
  (SEO-1..3) ЗАКРЫТА.** Всё БЕЗ миграций. Остаток идеи (миграция листингов/деталей на движок мета) —
  по спросу. Очередь владельца дальше: **T-1 (массовый de.po)** → **Склад-2** (Chargen/MHD·мультисклад·M12).
  План/очередь — `docs/seo-module-v2-plan-2026-07-08.md`, `docs/task-catalog.md`.
- **Самое свежее (2026-07-08): «склад-леджер до продакшн-качества» (T1–T5) — ЦЕЛИКОМ.** Владелец
  выбрал полную глубину (T1+T2+T3 + retail-дозапись = все срезы). План T5 —
  `docs/ud-stock-t5-plan-2026-07-08.md`. **T1** честная реконсиляция: правки остатка в форме
  товара/варианта пишут леджер (`log_catalog_change`, source="catalog") → счётчик↔леджер сходятся
  (+ починен давний баг: демо `shop`/`retail` падал `UnboundLocalError` в `_seed_kit_records`). **T2**
  учёт по вариантам (сущность = товар-без-вариантов|вариант; `select_for_update` на варианте, пикер
  `v/p<pk>`). **T3** ретейл: причины корректировки (Schwund/Bruch/…), поиск SKU/EAN (scan-to-count),
  Inventur-Zählliste. **T4** ERP-lite: drill-down истории (`?history=`), CSV-экспорт, архив-тумблер
  доски. **T5 (миграция `catalog/0014`, аддитив):** `cost_price`/`reorder_point`/`reorder_target` на
  Product+Variant → `stock_value`/`margin_pct`/`cost_value`-фолбэк/`effective_reorder_point`; сервис
  `inventory_value()` (Warenwert) + `reorder_suggestions()` (Bestellvorschlag = Soll−Bestand, Ausverkauft
  первыми); кабинет: Warenwert-плашка + колонки Wert/Marge + секция Bestellvorschläge; форма товара/варианта
  +3 поля; демо EK≈55% VK. Проверено на сиде shop (Warenwert 514.31 €, Vorschlag +18, Marge 45%). T1–T4
  без миграций; **⚠️ `catalog/0014` ТРЕБУЕТ ДЕПЛОЯ** (вместе с `inventory/0001`). Дальше по каталогу —
  платформа D1 (Pro-тариф, ждёт прайсинг) / другие треки за решением владельца.
- **Самое свежее (2026-07-08, вечер): программа УПРОЩЕНИЯ КАБИНЕТА «анти-Битрикс v2» — S1–S4
  ЗАКРЫТЫ (в `main`, БЕЗ миграций).** Задача владельца: «максимально упростить, скрыть ненужное
  по архетипам, визуал очень простой». Механика хабов (переиспользуемая): `HUB_TABS` в
  `cabinet.py` (5-кортеж url/label/nav_key/module_key/advanced) + тег `{% hub_tabs %}` +
  партиал `_hub_tabs.html` (tab-bar + ящик «Erweitert»); свод = `nav_items=()` у модуля,
  url_prefixes цел (гейт), под-страницы получают тег. **Сайдбар ~25 пунктов → ~8:** S1
  **Sortiment** (каталог 5→1, `a10da9c`), S2 **Verkäufe** (доска+продажи 6→1, вкладки гейтятся
  по архетипу, `cfef40e`+`a68c5bd`), S3 **Einstellungen** (настройки 10→2 + Erweitert, `a8cee5b`+
  `1d2c43d`), S4a **Marketing** (акции/отзывы/лояльность/публикация+Kampagnen, `c181f58`), S4b
  **Kunden** (контакты/сообщения/Telegram + перенос бейджа непрочитанного, `050c1ee`). **Дальше:
  S5** (режим Простой/Эксперт, дефолт expert, тумблер на «Funktionen») → **S6** (реальные
  архетипы friseur/handwerker/werkstatt/events + текущие — ⚠️ МИГРАЦИЯ Tenant.choices, деплой).
  Решения владельца: S6 «набор ок + текущие». **ПОЛНОЕ ТЗ/HANDOFF для новой сессии —
  `docs/admin-simplification-handoff-2026-07-08.md`** (+ exec-plan/analysis тех же дат).
  Уроки: правка формы HUB_TABS → grep импортёров + полный прогон; `msgfmt` локально нет →
  email_i18n падает локально/зелён на CI; `normalize` дропает неизв. ключи (ui_mode сохранять).
- **Самое свежее (2026-07-09): упрощение кабинета — S5 влит в main + S6a реальные архетипы.**
  **S5** (режим Простой/Эксперт) был готов на прежней ветке `unified-order-kanban-stock-af3pl7`
  (`0c45f44`), но НЕ влит; верифицирован (CI зелёный, 7 тестов) и FF-влит в `main` (`db412ed`,
  без миграции): `ui_mode()`/`is_simple()`, `SIMPLE_HIDDEN_MODULES={finance,analytics}`,
  тумблер на «Funktionen», `normalize` сохраняет `ui_mode`. **S6a** (⚠️ миграция `tenants/0024`):
  `Tenant.BUSINESS_TYPES += friseur/handwerker/werkstatt/events` (к 10, не заменяя) + пресеты
  модулей на архетип (`recommended_for`/`suited_for`) + маппинг демо-китов (FRISEUR/WERKSTATT/
  HANDWERKER/RETREAT) + карточки мастера (`BUSINESS_TYPE_META`) + тесты (`test_archetypes_s6`,
  +4 параметра `test_default_disabled_for_vertical`). **S6b** (без миграции): `ARCHETYPE_SIMPLE_HIDDEN`
  + `simple_hidden_modules()` — в Простом прячет хаб «Sortiment» (catalog) у friseur/handwerker/
  events/hotel (товары не primary; werkstatt держит — Teile). **Программа упрощения (S1–S6)
  закрыта.** Планы — `docs/admin-simplification-s6-plan-2026-07-09.md`, handoff §4. Ветка
  `claude/admin-simplification-handoff-dfawis`.
- **Самое свежее (2026-07-09, продолжение): глобальный АУДИТ кабинета + волны W0–W2 + языки — всё в
  main `6b3bd79`.** Аудит `docs/admin-global-audit-2026-07-09.md` (6 разведок + стенд; волны W0–W6 §9).
  **W0** критический баг: форма настроек стирала 6 полей на Save (в т.ч. `small_business`/НДС) —
  не выводились в шаблоне; фикс+замки. **W1** редактор: левая панель→лист из верхнего тулбара
  (`.bld-collapsed`=display:none, нет «прыжка»; рейл→вкладки `#bld-area-tabs`); адверсариальное
  ревью-workflow поймало HIGH-регрессию (display:none убивал ленту настроек блока) → фикс
  `.bld-ribbon-open{display:block!important}`; headless-верификация. **W2** форма товара: order_fields
  (название первым), секции+аккордеоны, Простой/Эксперт, чипы, help_text, гейт пищевой маркировки;
  замок «все поля в DOM, скрытие только CSS» (урок W0). **Языки**: `LANGUAGES` += 9 (tr/ru/uk/pl/fr/
  it/es/nl/pt), таб «Sprachen» прямой; регресс-фиксы (form_locales/locale-замки/format), broad 1964
  passed. **Перевод хрома (.po) — ОТЛОЖЕН в конец бэклога** (решение владельца). Дальше по аудиту:
  **W3** онбординг/демо новых архетипов → W4 настройки → W5 настройки Kanban-доски → W6 единый источник темы.
- **Самое свежее (2026-07-09, W3 — наполнение S6-архетипов): ЗАКРЫТ ЦЕЛИКОМ** (ветка
  `claude/admin-simplification-handoff-dfawis`, всё БЕЗ миграций; детали — build-log). **W3-1** демо
  friseur/werkstatt/events (услуги/билеты). **W3-2** CTA шага 6 мастера по архетипу (`offer_cta`).
  **W3-3** jobs — primary-архетип: `_PRIORITY` += jobs (между booking и catalog) → Handwerker (jobs on,
  booking off) ведёт на /anfrage/, а не в пустой каталог; werkstatt=booking (Termin); `primary_item`
  section через `.get` (jobs без секции-грида); offer_cta jobs → безопасный catalog-фолбэк (не Http404).
  golden normalize НЕ затронут. **W3-4** пресеты акций 4 архетипам (discount). **W3-5** шаблоны витрины
  termine/handwerk/veranstaltung — каждый ВКЛЮЧАЕТ primary-секцию (generic-шаблоны её прятали).
  **W3-6** регистрация: business_type карточками (иконка+язык задач) вместо `<select>`. Локальный
  broad-гейт 198 passed. **W3 влит в main + задеплоен владельцем (2026-07-09, `tenants/0024` = [X]).**
- **Самое свежее (2026-07-09, W4 — упрощение настроек): ЗАКРЫТ ЦЕЛИКОМ** (ветка
  `claude/admin-simplification-handoff-dfawis`, БЕЗ миграций; планы `w4-settings-simplification-plan`
  + `w4-3-payment-shipping-merge-plan`). **W4-1** `/dashboard/settings/`: аккордеоны (базовые всегда +
  Recht/Betrieb в `<details>`, Простой/Эксперт скрывает продвинутое), свод двух блоков «часы» в один.
  **W4-2** гейт полей по модулю (loyalty→voucher/auto_redeem; jobs/orders→service_area); инвариант W0
  (скрытие только CSS, все поля в DOM — замки). **W4-fix видимости (по фидбэку владельца):** тумблер
  Einfach/Experte + «🌐 Sprachen» вынесены в ШАПКУ кабинета (`set-ui-mode`, `ui_simple` в
  context-processor) — были не найдены (режим в «Erweitert», языки в табах). **W4-3 физический свод
  (решение владельца):** единый экран `payment_settings` «Zahlung & Versand» (`/dashboard/settings/
  payments/`) — свод оплаты/доставки с 3 экранов; save-хелперы извлечены (orders/billing делегируют,
  поведение байт-в-байт); одна форма/Save, **guard потери по сентинелам `sec_*`**; старые экраны
  слим-нуты до ссылки.
- **Самое свежее (2026-07-09, W5 — настройки Kanban-доски): ЗАКРЫТ** (ветка
  `claude/admin-simplification-handoff-dfawis`, БЕЗ миграций). Панель «⚙️ Spalten anpassen» на
  `/dashboard/board/` (владелец не находил, где настроить колонки): пер-тенантно `site_config['board']`
  — переименование (`labels`)/порядок (`order`)/скрытие (`hidden`) колонок; `pipeline.resolve_columns`
  поверх `pipeline_for`; **правила переходов карт (FSM/V4) НЕ трогаются**. `normalize_board` +
  golden-паритет (ключ только при непустом); `board_settings` targeted-write.
- **Самое свежее (2026-07-09, W6 — единый источник темы + ФИКС потери данных): ВОЛНА W (W0–W6)
  ЗАКРЫТА ЦЕЛИКОМ** (ветка `claude/admin-simplification-handoff-dfawis`, БЕЗ миграций). Найден+исправлен
  латентный баг: **`site_view` пересобирал config из ПОДМНОЖЕСТВА ключей** → сохранение «Your site»
  роняло `ui_mode`/`board`(W5!)/`seo`/типографику/стиль карточек. Фикс: `config = dict(current)` (как
  home_builder_view) + presence-safe TEXT_FIELDS. **W6:** цвет/шрифт/стиль баннера — единый источник в
  конструкторе главной (Theme); из `site.html` убраны (ссылка туда), `site_view` тему не пишет. Тесты
  preserve-keys/no-wipe/no-dup. Диагностика CI: billing webhook-тесты по ~60с (пред-существующая
  медлительность, не регресс), core+orders 677 зелёные. **Дальше:** T-1 (массовый de.po — в конце
  бэклога) / другие треки за решением владельца.
- **Самое свежее (2026-07-09, вечер): Ф1–Ф3 «per-language ввод + переводимые витринные метки
  товара» — ЦЕЛИКОМ** (ветка `claude/admin-simplification-handoff-dfawis`, план
  `docs/product-i18n-entry-plan-2026-07-09.md`; детали — build-log). Запрос владельца: язык
  переключается, поля разных языков НЕ видны одновременно; «портянка/нет табов»; ВСЕ витринные
  параметры переводимы. **Ф1** переключатель языка (пилюли `active_locales`) + партиалы
  `tenant/_i18n_switch.html`/`_i18n_group.html` + `core/i18n_input.py::i18n_form_groups`; форма
  товара→ТАБЫ (вместо `<details>`-портянки), поля неосновных локалей в DOM но `hidden` (инвариант W0);
  та же механика на форме акции. **Ф1-ext** свитчер на категориях; переводы услуг/номеров свёрнуты
  в `<details>🌐`. **Ф2** (⚠️ миграция `catalog/0015`, аддитив overlay) `origin_i18n`/`ingredients_i18n`
  на Product → `*_localized` на витрине, вписаны в свитчер. **Ф3** (БЕЗ миграции) метки-справочники
  витрины переводимы — аллергены/диеты/Zusatzstoffe в `food.py` → gettext_lazy, бейджи → `BADGE_LABELS`
  (lazy; `BADGE_CHOICES` модели остаётся DE, миграции целы); база=немецкий msgid, EN=37 переводов в
  `locale/en/.po` (.mo компилируется в CI как L4); проверено end-to-end (EN product_detail). UNIT_CHOICES
  не трогаем (только форма кабинета). Остаток: variant/modifier labels (per-товар free-text, за решением);
  полный chrome-перевод — T-1 (конец бэклога).
- **Самое свежее (2026-07-10): фидбэк-батч после Ф1–Ф3 — 5 пунктов, всё БЕЗ миграций**
  (ветка `claude/admin-simplification-handoff-dfawis`; детали — build-log). **#1** кнопки
  переключателя языка/табов не работали (регресс Ф1: скрипт партиала выполнялся раньше табов
  → пустой NodeList) → делегирование клика на `document`, проверено в Chromium. **#2**
  Varianten/Modifiers — отдельная вкладка «Variants & extras» + кнопка «Erweiterte Preise»
  под ценой (`data-pf-goto`). **#4** ясность Einfach/Experte — `simple_hidden_labels` +
  список скрываемого/бейдж режима на «Funktionen» и в тултипе тумблера. **#3/#5** кнопки
  «Demo ansehen» на карточках типов бизнеса (регистрация + мастер) → живая демо-витрина
  архетипа (`DEMO_KIT_HOST`, `demo_url` из `TENANT_DOMAIN_BASE`, гейт по засеянным `Domain`).
  ⚠️ ops: чтобы демо-кнопки появились — прогнать `seed_demo_tenants` на сервере. Остаток
  фидбэка: демо-сайты пока делят один kit на несколько типов (dedicated kits — по спросу);
  variant/modifier labels перевод — отдельным решением.
- **Самое свежее (2026-07-10): фидбэк-батч (кнопки/вкладки/демо-кнопки) + демо-трек «сайт
  под каждый тип» волна 1 + тип Online-Shop + фото-пайплайн — всё в main `e2aa49f`.**
  Утро: #1 фикс кнопок языка/табов (делегирование на document — партиал парсился раньше табов),
  #2 вкладка «Variants & extras»+«Erweiterte Preise», #4 ясность Einfach/Experte, #3/#5 кнопки
  «View demo site» на регистрации/мастере (гейт по засеянным Domain). Затем по запросу владельца
  («демо для всех видов, Metzgerei отдельно, нет онлайн-магазина, анализ рынка»): план
  `docs/demo-kits-per-type-plan-2026-07-10.md`; **волна 1** — dedicated-киты BAKERY «Backhaus
  Krume» (`baeckerei`) и BUTCHER «Metzgerei Bergmann» (`metzgerei`, Partyservice через jobs);
  **тип `online_shop`** (⚠️ миграция `tenants/0024`→`0025`, choices-only) с карточкой/пресетами/
  JSON-LD OnlineStore; **фото-пайплайн** `static/demo/photos/` (CC0/AI, резолвер с SVG-фолбэком,
  команда `demo_photo_report`, 298 ключей). **Волны 2+3 ЗАКРЫТЫ тем же днём (merge `448fcde`,
  без миграций): CAFE «Café Morgenrot» (`cafe`), CLOTHING «Studio Nordwind» (`mode`,
  per-size остаток → Warteliste), TOURS «Stadtgold Touren» (`touren`, тиры/депозит/QR,
  гиды-Teacher). Демо-трек закрыт: 13/14 типов со своим демо** (other — намеренно;
  dedicated online_shop-кит — по спросу). Фото-сессия — сеть открыта владельцем, промпт
  передан. ⚠️ ops после деплоя: `seed_demo_tenants` (baeckerei/metzgerei/cafe/mode/touren;
  handwerker на сервере не досеян — `--kit handwerker --recreate`).
- **Самое свежее (2026-07-10): демо-фото — реальный CC0-набор.** 146 webp в
  `static/demo/photos/` (Openverse `license=cc0,pdm` + Wikimedia Commons, лицензии проверены
  по метаданным API; каждое фото визуально верифицировано агентами, 4 reject-раунда);
  на момент набора — покрытие 167/248 позиций (67 %), после волн 2–3 ключей 298 (часть
  закрывается токен-фолбэком; актуально — `demo_photo_report`). Остальное — SVG-фолбэк.
  Провенанс — `static/demo/photos/SOURCES.md`. Портреты команды не брали (реальные лица).
  Набор сделан сессией `claude/youthful-lovelace-suk4wc`, интегрирован черри-пиком в
  основную ветку. **Дополнено (2026-07-10): AI-набор FLUX.1-schnell (Replicate) — 120 ключей →
  покрытие `demo_photo_report` 298/298 (100 %)** (нативный webp <150 KB, пропорции по типу,
  22 вымышленных портрета; провенанс в SOURCES.md; ветка `claude/demo-photos-replicate-rtcs78`,
  черри-пик). ⚠️ ops: фото попадут в демо после `seed_demo_tenants --recreate`.
- **Самое свежее (2026-07-10, вечер): ТЗ по фидбэку кабинета + старт трека перевода кабинета
  (T1/FB-12).** ТЗ `docs/cabinet-feedback-tz-2026-07-10.md` (14 пунктов FB-1..14: находимость
  food-labeling/customize-columns; пробелы — правила переходов/статусы заказа/единый «отдел
  продажных сущностей»; фото-«+»/фото категорий; гостиница; фикс иконки; перевод кабинета).
  **T1-a/a.2/c ✅** (merge `a69e0cb`, без миграций, план `docs/t1-cabinet-i18n-plan-2026-07-10.md`):
  T1-a — язык кабинета отделён от витрины (`CABINET_LANGUAGES`, `i18n_cabinet.py`,
  `CabinetLocaleMiddleware`, `<select>` в шапке, пилот); T1-a.2 — обёртка Python flash-messages
  (шаблоны уже были в `{% trans %}`); T1-c — django-rosetta `/rosetta/` (public, superuser-only;
  прод-цикл: править→коммитить .po→деплой). **Дальше: T1-b** (DeepL перевод .po — параллельной
  сессией; интеграция её ветки как фото). ⚠️ deploy: образ соберётся с django-rosetta. Разведены понятия: язык витрины (`/settings/languages/`) ≠ переводы контента
  (свитчер Ф1 в формах) ≠ язык кабинета (T1). ⚠️ Прод-багфикс сидинга демо-фото (`535664f`,
  плоский static-URL вместо манифеста) — в main; после деплоя нужен `seed_demo_tenants --recreate`.
- **Самое свежее (2026-07-11): T1-b — хром кабинета/витрины переведён на en/tr/ru/uk (DeepL)
  + фикс компиляции локалей** (ветка `claude/cabinet-de-en-deepl-zw5152`, готова к FF-мержу).
  `en.po` 2447 записей (383 DE→EN + 2042 identity + 22 plural; adversarial-QA коротких строк —
  DeepL коверкал ≤4-символьные: `AGB→"All-American Boy"`), tr/ru/uk по ~2499 (ru/uk — ручные
  4-форменные плюралы: DeepL давал «5 ночи»). `forms.py`: 4 хелп-текста с литеральным `%`
  переформулированы («% or» парсился как %-спека → были непереводимы). **ci.yml+deploy.sh
  теперь компилируют ВСЕ `locale/*/django.po`** (было `-l en` → новые локали молча не работали
  бы в тестах и ПРОДЕ — поймано CI #1396/#1397). **de.po ОТКАЧЕН** (решение владельца
  2026-07-11): активация вскрыла 54 англ-ассерта в DE-рендере + golden-normalize зависит от
  локали — ровно предсказание `legal-lang-package-plan §2`; коммиты `93e19cf`/`1c8be62` в
  истории ветки для cherry-pick при возобновлении T-1. Правка переводов без кода — rosetta
  (T1-c). Уроки/детали — build-log. **Hotfix (той же датой, ветка
  `i18n-prod-mo-cabinet-langs`):** .mo теперь компилируются В ОБРАЗ (Dockerfile msgfmt) —
  `compose run --rm compilemessages` в deploy.sh писал их в эфемерный контейнер, В ПРОДЕ
  локали (вкл. EN-письма L4) молча не работали; + `CABINET_LANGUAGES` += tr/ru/uk (селектор
  🗣 = 5 языков). **T1-b.2 (следом):** NAV_GROUPS/NAV_TASK_LABELS (сайдбар AB1) были голыми
  немецкими строками (обход «пока без de.po») → обёрнуты в lazy, 12 msgid добавлены в 4 .po
  вручную + фикс DeepL-коротышей (`Neu`→«или» в 3 языках, `Board`→«правление» и др.).
- **Самое свежее (2026-07-11): T1-b влит (en/tr/ru/uk хром кабинета, DeepL-сессия) + фикс
  «.mo в образ» + FB-батч 5/6/7/2 — main `217f8df`.** T1-b: перевод хрома DeepL'ом (de-тест-
  эксперимент откачен), `CABINET_LANGUAGES=["de","en","tr","ru","uk"]`; критичный фикс: .mo
  компилируются ПРИ СБОРКЕ ОБРАЗА (Dockerfile msgfmt; раньше compilemessages в `run --rm` →
  прод молча без переводов; шаг из deploy.sh убран). FB-батч: «＋ Foto»-плитка на формах
  товара/акции/категории (FB-5), фото категорий/подкатегорий + плитки витрины (FB-6,
  ⚠️ миграция `catalog/0016`), жирные даты календаря номера (FB-7), видимая кнопка
  «⚙️ Spalten» на доске (FB-2). FB-13 (иконка при hover) не воспроизводится в изоляции —
  ждём контекст владельца. Остаток T1: полный de-хром НЕ трогаем (msgid=de), rosetta-цикл
  прод: править в dev → коммит .po → деплой.
- **Самое свежее (2026-07-12): M-пачка FB-11/FB-10/FB-4a — в `main`, БЕЗ миграций.**
  **FB-11** карточка брони в кабинете `/dashboard/stays/buchung/<pk>/` (гость/даты/суммы/
  Meldeschein/кнопки статуса тем же FSM-путём; `_manage_url` доски→booking-detail;
  reference_code календаря — ссылка). **FB-10** суммы в письмах брони (гостю+владельцу) +
  owner-email в `notifications.html` (+предупреждение если пуст). **FB-4a** свои имена
  статусов заказа (кабинет-отображение): `normalize_status_labels`+тег `{% status_label %}`+
  панель «⚙️ Status-Namen anpassen» в списке заказов+сброс (golden-паритет цел, НЕ движок
  переходов). Детали — build-log. **Дальше по TZ (`cabinet-feedback-tz-2026-07-10`):**
  крупные FB-8 (единое управление продаваемыми сущностями в кабинете) и FB-3+FB-4b (движок
  статусов заказа/услуги/брони с правилами переходов) — план-доком до кода; отложенные
  FB-1/FB-9/FB-13/FB-14 — ждут контекста владельца.
- **Самое свежее (2026-07-12, вечер): FB-3 Вариант B (полноценные кастом-статусы) — ЗАВЕРШЁН
  ЦЕЛИКОМ, 8 инкрементов, БЕЗ миграций.** Владелец создаёт СВОЙ статус (роль+переходы), он
  достижим через `apply()`, держит ёмкость (anti-oversell), двигает деньги/склад по роли,
  корректно отображается + редактор `/dashboard/status-manager/<kind>/`. Приём: снять завязку
  на литеральные коды → роль+флаги (реестр `apps/core/status_registry.py`; эффекты
  `apps/core/status_effects.py`; хранение `site_config['status_defs']`/`['status_edges']`).
  Встроенное поведение байт-в-байт (golden-замки). **Phase 0-4+6 в `main` (авто-мерж по правилу
  сессии); Phase 5 на ветке `claude/admin-simplification-handoff-dfawis`, вливается по зелёному
  CI.** Правило сессии (владелец): после зелёного CI сразу мержить в main. Ограничение:
  кастом-статусы scoped на order/booking/stay. План — `docs/fb3-variant-b-full-plan-2026-07-12.md`.
  **Дальше по TZ:** отложенные FB-9/FB-13/FB-14 (ждут контекста); прочее — за решением владельца.
- **Самое свежее (2026-07-12, продолжение): FB-1 + FB-4b + FB-3 — в `main`, БЕЗ миграций.**
  **FB-1** пищевая маркировка только для гастро (вкладка «Kennzeichnung» скрыта у не-гастро,
  поля в DOM). **FB-4b** свои имена статусов услуг/броней (generic `core/status_labels.py`,
  endpoint `status-labels-save/<kind>/`, панели на booking/stays, тег на календарях/
  booking_detail; на доске кабинета — но НЕ в клиентском аккаунте). **FB-3** конфигуратор
  правил переходов (Вариант A: FSM жёсткий пол, владелец лишь СКРЫВАЕТ не-danger переходы;
  danger/отмена всегда; `core/transition_rules.py` + `siteconfig.normalize_transitions` +
  панель `_transition_rules_panel.html` + endpoint `transitions-save/<kind>/`). Планы —
  `docs/fb3-status-engine-plan-2026-07-12.md`, `docs/fb8-unified-sellable-cabinet-plan-2026-07-12.md`.
  Свои НОВЫЕ статусы (FB-3 Вариант B) — отдельная волна за решением владельца.
- **Самое свежее (2026-07-12, продолжение): FB-8 (Angebote) — на ветке, БЕЗ миграций.**
  Единый экран `/dashboard/angebote/` со всеми продаваемыми сущностями (товар/услуга/
  номер/событие/комбо): обзор + тумблер видимости + переход к родной форме (единый CRUD
  НЕ делаем — Вариант A). `apps/core/sellable_manage.py` + пункт «📦 Angebote» в сайдбаре
  (виден при любом активном sellable-модуле, в т.ч. отелю в Простом). jobs — не sellable.
  **Дальше по TZ (`cabinet-feedback-tz-2026-07-10`):** отложенные FB-9/FB-14 (ждут
  контекста владельца). Крупные TZ-эпики закрыты (FB-1/FB-3/FB-4/FB-8/FB-10/FB-11).
- **Самое свежее (2026-07-12, поздний вечер): редактор — живые изменения блоков + канва БЕЗ
  видимой перезагрузки (двойная буферизация) + FB-13/тёмная тема/frame-escape кнопки.** Мелкие
  фиксы (main `965ddce`): курсор-«рука» на 📷/🗑 (`.sf-photo-edit`), тёмная тема — читаемые
  поля/плейсхолдеры нативных инпутов (`color-scheme:dark` + цвета), C-блок «Button» с внешним
  URL — `target="_top"` (не ловит XFO DENY в канве редактора). Редактор (этап 1 main `1f20ab8`
  + этап 2): `push()` не навигирует видимый кадр — `swapPreview()` грузит черновик в скрытый
  iframe-буфер (обычная навигация → window-гарды витрины живы; document.write отвергнут) и
  атомарно подменяет с переносом прокрутки; оптимистичные мутации drop/видимости — мгновенно;
  фолбэк `hardReloadPreview` (сеть/таймаут/не-http). `instrumentFrame` (гейт about:blank —
  травил previewPath; guard по body). Стенд Playwright 13/13 (вкл. живой календарь наличия
  после свопа); план `docs/editor-live-inplace-plan-2026-07-12.md`. БЕЗ миграций. Грабля:
  Django 5.1 кэширует шаблоны и в DEBUG — после правки шаблона рестартовать runserver.
- **Самое свежее (2026-07-13): i18n-фиксы кабинета + регистрация 5 языков + Branchen-страницы.**
  (1) Статусы брони/вкладки доски/панели статусов переводятся во всех 5 языках
  (gettext_lazy на choices StayBooking/ServiceBooking + KIND_LABEL; en-fuzzy починены;
  БЕЗ миграций — choices-метки схему не меняют). (2) Регистрация бизнеса: полноэкранный
  сплит-редизайн + переключатель DE/EN/RU/TR/UK (public-роут `/sprache/`,
  `set_public_language` по CABINET_LANGUAGES); базовый msgid — НЕМЕЦКИЙ (de.po нет —
  откачен владельцем ранее), переводы в 4 .po. (3) **Branchen-Landingpages**:
  `/branchen/` + `/branchen/<slug>/` (14 архетипов) — hero + проверенные хайлайты
  (workflow research+adversarial verify против кода) + сетка модулей из REGISTRY +
  CTA `?type=` предвыбор в регистрации; всё немецкими msgid, i18n-ready
  (`apps/tenants/archetype_pages.py`, `tenants/industry.html`). Редактор: **правый
  инспектор (A+мелочи из B) СДЕЛАН** — настройки (Template-области и лента блока) в
  панели 380px справа во всю высоту, канва сжимается (right+ResizeObserver→applyDevice),
  вертикаль экрана свободна; легаси syncRibbonPad (paddingTop=высота попапа) убит —
  схлопывал канву; стенд 11/11 (план `docs/editor-right-inspector-plan-2026-07-13.md`); + свёртка
  (шеврон, bld-panel-min) и ресайз ширины (280–640, --bld-panel-w, localStorage,
  Pointer Capture) — стенд 7/7. **Главная платформы = /branchen/** (корень; регистрация
  → /registrieren/, ?ref ловится на корне), общий хром `_public_header/_footer`,
  страницы /ueber-uns/ + правовые ПЛАТФОРМЫ /impressum/ /datenschutz/ /agb/
  (заготовки, реквизиты-[ПЛЕЙСХОЛДЕРЫ] на владельце), sitemap += 16 URL.
- **Самое свежее (2026-07-13): AB6.1 ✅ — движок шагов мастера (state v2 + рельса ✓/⏭ + ?step=).**
  Отмашка владельца «приступай». `apps/tenants/onboarding.py`: state v2 (слаги) в opaque
  `onboarding` + консервативный легаси-маппинг int→slug (completed не понижается), реестр
  `SETUP_STEPS`, `goto`/`steps_with_status`; НОВЫЙ `apps/core/setup_steps.py` (реестр HANDLERS:
  post/context/preview/live per-слайд; сюда переехали `apply_business_type`+`save_hero`);
  `setup_view` — тонкий диспетчер (глобальные action'ы + `?step=`); AB5-редирект на v2;
  `setup.html` → каркас с рельсой (✓/⏭, клик = дозаполнить) + партиалы `setup/_step_*.html`
  (вёрстка 1:1); app.css пересобран. Без миграций.
- **Самое свежее (2026-07-16): ВОЛНА СКЛАД-2 (U-D2W) ЗАКРЫТА ЦЕЛИКОМ в объёме v1 — E1+E3+E2,
  main `4564e0c`, ⚠️ миграции `inventory/0002..0004` ждут деплоя.** Решения владельца: «все 3
  эпика», порядок E1→E3→E2, сразу полный FEFO; архитектура Вариант A (счётчик = ИТОГО-истина,
  партии/локации = разбивка поверх, реконсиляция) — движки заказов НЕ переписаны. **E1 Chargen/
  MHD:** модель `Lot` + FEFO-сервис (consume/restore/writeoff) + врезки в атомики (orders
  `_reserve_stock`/`_restore_stock`, jobs `_commit_stock`; паритет байт-в-байт без партий,
  185 order/job-тестов зелёные) + кабинет (тумблер `lots_enabled`, приёмка Charge+MHD, MHD-обзор
  с бейджами, Verderb-списание) + демо-партии bakery/butcher (`DemoKit.enable_lots`). **E3
  Закупки/M12 v1:** `Lieferant`/`Bestellung`(BE-код)/`BestellPosition` (EK-снимок из T5
  cost_price) + `purchasing.py` (create/add_line/set_status/receive_po_line — приёмка через
  единственный складской путь, source="purchase", частичные приёмки, авто-received) + кабинет
  `/dashboard/purchasing/` «Einkauf» (вкладка хаба Sortiment/Erweitert; «Aus Bestellvorschlägen»;
  чекбокс «EK übernehmen») + демо. **E2 Мультисклад v1:** `StockLocation` + `StockMovement.
  location` (NULL = основной → история валидна без бэкфилла) + `locations.py` (баланс: дефолт =
  счётчик − Σ недефолтных → Σ==счётчик по построению; `transfer` = пара движений Σ=0) + кабинет
  (Standorte, Umlagerung, селектор локации на приёмках stock+purchasing, разбивка в drill-down);
  ленивая активация UI при локациях > 1. Продажа-с-локации/Lot.location/демо-E2 — v2 по спросу.
  `apps/inventory` 84 зелёных. Планы: `sklad-2-plan` + `sklad-2-e3-purchasing-plan` +
  `sklad-2-e2-multilocation-plan` (все 2026-07-16).
- **Самое свежее (2026-07-14): AB6.2 (все 9 слайдов наполнены) + AB7 (блочная главная) — в
  `main`, БЕЗ миграций.** **AB6.2** — новая карта слайдов + наполнение: business (escape-hatch,
  gate) · start (rich-demo) · company (название/город/логотип) · stil (галерея шаблонов) · menu
  (виды шапки) · **offer** (мини-форма первой сущности по архетипу товар/услуга/номер/событие +
  список «✏️» + пресеты акций) · **category** (раскладка каталога мокапами → catalog_layout) ·
  home (hero) · **payment** (форма W4-3 через партиалы `_payment_fields`/`_payment_connect` +
  извлечённые `save_payment_settings`/`payment_settings_context` — паритет-замки целы) · texts.
  **AB7** — блочная главная `/dashboard/`: **B1** тело канбан-доски вынесено в `core/_board_body.html`
  (рендер 1:1, `board.html` = обёртка); **B2** `apps/core/dashboard.py::dashboard_tiles` (плитки
  задач на язык задач + бейдж «Not set up»→`?step=` из реестра шагов, гейты по модулям/
  simple_hidden) + встроенный канбан на главной (`manage_sections_for` limit=20) + «Full view».
  Ветка `claude/server-review-setup-wizard-sw6ems`, FF-мержи в main по зелёному CI. Дальше по
  плану `master-slides-v3` — доводка `_step_done`/динамические слайды меню (v2) либо иной трек.
- **Предыстория трека (2026-07-11): старт AB6/AB7 «анти-Битрикс v3» — план-док.**
  Запрос владельца: мастер-СЛАЙДЫ наполнения сайта (компания+лого → вид меню → вид страницы
  товара + первый товар/номер/услуга мини-формой → главная → оплата/доставка → тексты; ✓/⏭-рельса,
  дозаполнение пропущенного `?step=`) + блочная главная кабинета (плитки задач + канбан внизу);
  Эксперт остаётся. Решения владельца: мини-форма в слайде · деталь v1 = стиль карточек+секции ·
  демо обогащаем (фото+баннер+меню/тексты). **AB6.0 (обсуждение слайдов) ЗАВЕРШЁН** — 4 развилки
  решены (план §0b): название/город первыми полями слайда 2 · налог/право-реквизиты в слайде 7 ·
  меню v1 = чипы+общие слайды (динамические per-страница — v2) · демо-позиции списком в слайде 4
  с «✏️»-мини-формой. **Код ⏸ до отмашки владельца** («продолжаем AB6» → старт AB6.1 движок шагов).
  Ядро: единый реестр `SETUP_STEPS` (питает рельсу мастера, чек-лист AB4-фасадом и бейджи плиток
  AB7), state v2 в opaque-ключе `onboarding` — БЕЗ миграций и БЕЗ правок golden. SOURCE OF TRUTH —
  `docs/master-slides-v3-plan-2026-07-11.md` (карта слайдов §3, решения §0b, инкременты §5).
- **Самое свежее (2026-07-18): AB5.1 регистрация с ПОДТВЕРЖДЕНИЕМ ПОЧТЫ + AB6.10 мастер по
  порядку владельца + шаблоны страниц товара/«О компании».** (ветка
  `claude/registration-email-confirmation-698nwb`; план `docs/signup-confirm-wizard-plan-2026-07-17.md`).
  **AB5.1 (⚠️ миграция `tenants/0026`):** POST /registrieren/ → `SignupRequest` (пароль хэшем,
  тенант НЕ создаётся) → письмо → `/registrieren/bestaetigen/<token>/` → прежний фоновый
  провижининг; идемпотентно, slug-гонка → страница ошибки; honeypot + rate-limit (боты без
  почты не плодят Tenant/Domain — класс T-5); env-флаг `SIGNUP_EMAIL_CONFIRMATION` (default on),
  console-бэкенд показывает ссылку на странице (⚠️ для реальных писем нужен RESEND_API_KEY —
  Stage 0). allauth EmailAddress НЕ используется (SHARED vs TENANT-User). **AB6.10 (без
  миграций):** порядок слайдов = запрос владельца (Sprachen ПЕРЕД Firma; Zahlung — в конец);
  НОВЫЕ слайды `detail` «Produktseite» (3 пресета стиля карточек site_defaults + чекбоксы
  секций detail_sections → `<module>_detail.hidden`; превью = деталь первой сущности, гейт по
  primary-модулю) и `about` «Über uns» (тексты + 4 шаблона страницы = пресеты C-блоков
  `page_blocks["info"]`, id `pb-about-*` — идемпотентная замена, чужие блоки целы; превью
  /ueber-uns/); texts слим-нут до правового. setup.html: слайд задаёт `preview_url`.
  i18n: 29 новых msgid переведены в en/tr/ru/uk .po. Тесты: 9 signup + 72 wizard зелёные.
- **Самое свежее (2026-07-18, вечер): КОНЦЕПТЫ «Studio» + «Живая продажа/Finder» приняты
  владельцем + FD-1 (движок Finder) реализован.** Решения («действуй автономно»): очередь —
  **FD → LS-3 (Sofort-Angebot) → LS-1/2 (видео = WhatsApp, без записи §201) → ST-1 (3 Look'а
  × 14 архетипов) → ST-4 (админ-хоум 5 хабов) → ST-3 (Studio-оболочка)**; Finder — ОПЦИЯ;
  SVG-иконсет; имя «Studio». Доки: `studio-concept-2026-07-18.md`,
  `live-selling-finder-concept-2026-07-18.md` (+LS-5 Care-цикл, LS-6 «Прямая линия»),
  `fd1-finder-plan-2026-07-18.md`; мокапы — артефакт «SiteAdaptor Studio — концепт».
  **FD-1 ✅ (без миграций):** `normalize_finder` (ключ presence-minimal), движок
  `apps/core/finder.py` (пресеты деревьев по архетипам + скоринг words/slug/price по
  display_fields, топ-3, лучший в середине), витрина `/finder/` (серверные шаги без JS,
  404 пока не включён), `enable_finder` в демо-китах baeckerei/friseur, 9 тестов.
  **FD-3-lite ✅** кабинет `/dashboard/finder/` (тумблер опции + превью дерева; вкладка
  Marketing/Erweitert; targeted-write — кастом-вопросы целы). **FD-2 ✅** секция-CTA
  «finder» на главной (реестр SECTIONS, ВЫКЛ по умолчанию; чипы первого вопроса → шаг 2;
  ⚠️ ОСОЗНАННАЯ голден-регенерация 4 эталонов — normalize дописывает известные секции).
  **Страховка редизайна ✅** (запрос владельца): тумблер «Klassische Ansicht»
  (`site_config["classic_ui"]`, карточка на «Funktionen», контекст в processor);
  первый потребитель — главная кабинета без плиток/канбана AB7; ЖЕЛЕЗНОЕ ПРАВИЛО трека
  ST — каждый редизайн уважает флаг (`studio-concept §8b`). **ПОЛНОЕ ТЗ треков
  FD/LS/ST — `docs/next-gen-master-tz-2026-07-19.md` (SOURCE OF TRUTH очереди:
  этапы A LS-3→LS-1/2 · B ST-1→ST-4→ST-3→ST-2 · C LS-6→LS-4→LS-5 · D своды;
  правила исполнения §4, ops §5).** Дальше: LS-3 (план-док обязателен).
- **Самое свежее (2026-07-19): LS-3 «Sofort-Angebot» ✅ ЦЕЛИКОМ (этап A1 ТЗ; ⚠️ миграция
  `orders/0015`).** План `docs/ls3-sofort-angebot-plan-2026-07-19.md`; развилка решена:
  НЕ обобщаем jobs.Job — новая лёгкая модель `orders.Offer`+`OfferLine` (jobs не тронут ни
  файлом). Флоу: тред inbox → «💶 Angebot senden» → композер (пикер FB-8 `sellable_manage`
  с редактируемой ценой + `price_value` в `ManagedSellable`; свободные строки; срок/заметка)
  → карточка в обоих тредах + письмо клиенту с прямой ссылкой → публичная `/o/<token>/`
  (принятие без логина; пикер оплаты при >1; БЕЗ гейта модуля orders — страница сама служит
  подтверждением: Vorkasse-реквизиты, Stripe success/cancel, «Jetzt bezahlen») → обычный
  `Order` через `create_order(custom_lines=...)` (цены заморожены; product-строки — сток/
  леджер по обычным правилам) → канбан + `Conversation.ref` на заказ. `OfferSM` open→
  accepted/declined/cancelled; всё идемпотентно. 25 новых тестов; 40 msgid в en/tr/ru/uk.
  Урок: ручной скрипт-пробник на keepdb-тест-БД наследил (стрей-строки уронили чужой тест)
  → после пробников прогонять `--create-db`. Дальше по ТЗ: **A2 · LS-1 Video-Beratung**.
- **Самое свежее (2026-07-19, продолжение): LS-1 «Video-Beratung» v1=WhatsApp ✅ ЦЕЛИКОМ
  (этап A2 ТЗ; ⚠️ миграции `booking/0017`+`tenants/0027`).** План
  `docs/ls1-video-beratung-plan-2026-07-19.md`; решения: `Service.is_video` МИГРАЦИЕЙ (свободного
  dict-JSON нет, site_config дороже), номер — `Tenant.whatsapp_number` (не site_config — normalize).
  Хелпер `apps/core/whatsapp.py::wa_link`. Кабинет: WhatsApp-Nummer в настройках (W0-инвариант),
  чекбокс видео в форме услуги (presence-сентинел). Витрина: скрываемая секция `video` детали
  («Per Video zeigen lassen», гейт is_video+номер) + авто-чип/фасет `?video=1` на /termin/.
  Письма confirmed/reminder: wa.me с датой (fail-safe без номера). §201 — записи нет. 10 тестов;
  8 msgid в 4 .po. Дальше по ТЗ: **A3 · LS-2 «Jetzt erreichbar»**.
- **Самое свежее (2026-07-19, продолжение): LS-2 «Jetzt erreichbar» ✅ — ЭТАП A ТЗ ЗАКРЫТ ЦЕЛИКОМ
  (БЕЗ миграций).** План `docs/ls2-jetzt-erreichbar-plan-2026-07-19.md`. `site_config["presence"]`
  presence-minimal (`normalize_presence`; auto=дефолт без ключа — golden цел), резолвер
  `apps/core/presence.py` (off/on/auto→`openinghours.open_status`), витрина: тег `presence_fab`
  в `_base.html` — зелёная пилюля «Jetzt erreichbar — Video-Anruf» → wa.me (гейт
  `whatsapp_number`; недоступен → фолбэк = чат-FAB/бронь), кабинет: карточка Auto/An/Aus на
  главной + endpoint `set-presence` (targeted-write). 5 тестов; 8 msgid в 4 .po. CI-фикс LS-1:
  замок hidden-секций билдера дополнен video (как B3 upsell). Дальше по ТЗ: **Этап B · ST-1
  «Каталог Look'ов»** (3 Look'а × 14 архетипов; classic_ui-страховка обязательна).
- **Самое свежее (2026-07-19, продолжение): ST-1a + ST-1b/1 (движок и галерея Look'ов) —
  в `main` `fe00e5f` (БЕЗ миграций).** План `docs/st1-looks-plan-2026-07-19.md`. **ST-1a:**
  `LOOK_FAMILIES` (Klar/Warm/Nacht-тёмный) × `ARCHETYPE_LOOK_ACCENTS` (14 палитр) = 42 Look'а;
  `apply_look`/`looks_for` в sitetemplates; ключ `theme`="dark" presence-minimal + тёмный
  дефолт витрины (посетительский localStorage-тумблер сильнее). **Попутно исправлен латентный
  баг класса W6:** apply_template строил конфиг с нуля → стирал ui_mode/board/seo/page_blocks;
  теперь общая `_apply`-база = полная копия. Адверсариальный замок: 42 Look'а apply→normalize
  идемпотентно, golden целы (test_looks, 22). **ST-1b/1:** stateless-превью
  `?preview=1&look=<family>` (оверлей пачки ключей в context.py, read-only — N iframe не делят
  session-слот) + 3 Look-карточки с ленивыми scaled-iframe на слайде мастера `stil` (classic_ui
  → только легаси-галерея; POST look приоритетнее template). **ST-1b/2 (той же датой, main
  `ccf5a28`) — ВОЛНА ST-1 ЗАКРЫТА ЦЕЛИКОМ:** фieldset «✨ Look» в области «Тема» билдера
  (гейт classic_ui) — клик выставляет все контролы дизайна + hidden `theme` и шлёт change →
  живой draft-канал перекрашивает канву БЕЗ перезагрузки (паттерн UC6-6h), Undo/Save штатные;
  билдер-Look = только визуал (секции курируют канвой; полный Look — слайд мастера); theme
  по всему циклу (round-trip W0, save presence-guard W6, draft-канал, payload; DE-грабля
  чисел учтена — stringformat:"g" + численный матчинг опций). Замки: 24 test_looks + 194
  смежных. Детали — build-log. Затем ST-4 (админ-хоум 5 хабов, ТЗ §3 B2, план-доком).
- Миграции: последний полный деплой — **2026-07-08 (владелец)** — применены ВСЕ миграции по состоянию на тот момент, включая `catalog/0014` (T5 склад: cost_price/reorder_point/reorder_target на Product+ProductVariant) + `inventory/0001` (U-D3 StockMovement) + всю ранее ожидавшую пачку (partners/0001, tenants/0023, aggregator/0014, promotions/0021, loyalty/0004, orders/0014, booking/0016, stays/0022, events/0022, reviews/0003, orders/0013 и ранее — B1/E-7/U-A/U-B/L3). **2026-07-09 (владелец):** задеплоен `tenants/0024_alter_tenant_business_type` (S6a — новые choices business_type). **⚠️ ОЖИДАЕТ ДЕПЛОЯ:** `catalog/0015` (Ф2 overlay) + `tenants/0025` (online_shop) + `catalog/0016_category_images` (FB-6, AddField) + `inventory/0002` (Склад-2 E1 — модель `Lot` Chargen/MHD) + `inventory/0003` (Склад-2 E3 — Lieferant/Bestellung/BestellPosition) + `inventory/0004` (Склад-2 E2 — StockLocation + location в леджере) + `tenants/0026` (AB5.1 — SignupRequest, double-opt-in регистрации) + `orders/0015` (LS-3 — Offer/OfferLine, Sofort-Angebot) + `booking/0017` (LS-1 — Service.is_video) + `tenants/0027` (LS-1 — Tenant.whatsapp_number). Плюс пересборка образа (rosetta + msgfmt .mo) и `seed_demo_tenants --recreate` (фото демо + демо-партии еда-китов). Полный список — в build-log.

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
