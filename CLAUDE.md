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
- **Самое свежее (2026-07-19, продолжение): ST-4a «Админ-хоум» ✅ — в `main` `9038d9b`
  (БЕЗ миграций).** План `docs/st4-admin-home-plan-2026-07-19.md`. Хоум отвечает на «что
  сегодня»: **виджеты** `home_widgets` (digest-паттерн: гейты модулей+simple_hidden+_safe) —
  Umsatz heute + 7-дневный SVG-спарклайн (первый чарт кабинета), Abholbereit (orders ready),
  Marketing-Puls v1 (views акций+погашения кампаний; featured отложен — кросс-схема),
  Bewertungen (owner_overview). **5 хаб-плиток + Website** `hub_tiles` (SVG-спрайт
  `tenant/_icons.html` + тег `{% icon %}` — старт Р5): Bestellungen/Angebot/Marketing/
  **Integrationen (НОВЫЙ лендинг `/dashboard/integrationen/`** — карточки-входы по модулям)/
  Einstellungen/Website. Task-плитки AB7 заменены (замки обновлены осознанно;
  `dashboard_tiles` остаётся). classic_ui — прежний вид (Р7, замок). **ST-4b (сайдбар
  5+Website, Sortiment/Kunden → Erweitert) — ЖДЁТ ЧЕКПОИНТА ВЛАДЕЛЬЦА** (план §2).
  Параллельно допустимо: план-док ST-3 (Studio-оболочка).
- **Самое свежее (2026-07-19, продолжение): ST-3 «Studio-оболочка» ✅ ЦЕЛИКОМ — в `main`
  `adce86d` (БЕЗ миграций) + план-док LS-6 готов.** План `docs/st3-studio-shell-plan-2026-07-19.md`;
  вывод разведки: полноэкранный хром УЖЕ был (SE-6 оверлей, правый инспектор, тулбар UC6-10,
  двойная буферизация, Look ST-1b) → ST-3 = переупаковка: **ST-3a** рейка уровней `#st-rail`
  (Look/Seiten/Blöcke/Medien — обёртки над showArea/инсертером/медиа; SVG +ic-pages/ic-media;
  брендинг «Studio» в топ-баре) · **ST-3b** page-лента `#st-pages` снизу (чипы preview_pages,
  актив по `#bld-page-path`, клик = `?page=`) · **ST-3c** кросс-фейд свопа канвы (opacity
  180мс поверх двойной буферизации, hardReload-страховка цела). Всё под classic_ui-гейтом
  (Р7, замок); существующие id целы (104 замка home_builder). Desktop-first (мобайл — прежние
  кнопки тулбара, ограничение v1). Урок: context-processor modules_nav → {} при
  schema_name="public" — тесты кабинетного хрома создают тенанта с обычной схемой.
  **План LS-6 «Прямая линия» — `docs/ls6-direct-line-plan-2026-07-19.md`** (следующий
  незаблокированный пункт очереди). ST-4b (сайдбар) — ждёт владельца; далее B4 ST-2.
- **Самое свежее (2026-07-19, поздний вечер): ЭТАП C ТЗ ЗАКРЫТ — LS-6 + LS-4 v1 + LS-5 v1
  в `main` (БЕЗ миграций).** **LS-6 «Прямая линия»** (план `ls6-direct-line-plan`):
  «⚠️ Etwas stimmt nicht?» на 6 поверхностях сделок + 4 confirmed-письмах → ДОВЕРЕННЫЙ
  problem-гейт contact (high только с ref; сырой priority игнорируется) → high-тред +
  Telegram-пуш владельцу (dedupe на тред) · полоса «Problem — Kunde wartet» на канбане
  (`Transaction.has_problem`, ОДИН batch-запрос на секцию — N+1-замок) · SLA v1 без миграции
  (⚡ реакция треда + ⌀ Reaktionszeit 30 дней в списке) · recovery «Alles wieder gut?» при
  resolve high-треда (дедуп + UWG-гейты). **LS-4 «Слой доверия» v1:** имя сотрудника над
  staff-пузырём публичного треда + живая подпись в письме-ответе; публичный бейдж
  «Antwortet in ~N Min» на контакт-странице ТОЛЬКО при ⌀ ≤ 2 ч (честность важнее украшения);
  фото сотрудника — v2. **LS-5 «Care-цикл» v1:** развилка настроения в 4 «Wie war's?»-письмах
  (👍 отзыв / 👎 → прямая линия LS-6 — перехват ДО публичного отзыва) + вкладка «Care-Zyklus»
  в Marketing-хабе → матрица UD4-2; ДР — v2. Уроки: rl:*-Redis — публичные POST-тесты с
  уникальным IP; автоэскейп & в plain-text письмах → `|safe` для URL с параметрами.
  **Открытые решения владельца: (1) ST-4b сайдбар 5 хабов, (2) счётчики «продано N» (LS-4).**
  Остаток очереди ТЗ без владельца: B4 · ST-2 «Шаблоны всех страниц» → этап D.
- **Самое свежее (2026-07-19, ночь): ST-2 «Шаблоны всех страниц» ✅ ЦЕЛИКОМ (этап B4 ТЗ;
  БЕЗ миграций).** План `docs/st2-page-templates-plan-2026-07-19.md`. Разведка: листинги
  услуг/номеров/событий уже на LAYOUT_PRESETS, меню — 3 пресета UC6-6h, детали — AB6.10;
  реально без пресетов были «О нас» (вне мастера), корзина, контакт. Сделано: НОВЫЙ
  `apps/core/page_presets.py` — реестр `PAGE_PRESETS` {host: prefix+пресеты} (обобщение
  _ABOUT_PRESETS: C-блоки page_blocks[host] + плоские ключи; идемпотентный
  `apply_page_preset` — блоки владельца целы; `presets_for` recommended_for-первыми),
  about-слайд мастера делегирует реестру байт-в-байт; билдер: action
  `use_page_preset:<host>:<id>` + карточки пресетов в scoped-строках панели (info/cart;
  работает и в classic_ui, Studio достигает через page-ленту); корзина 3 пресета;
  контакт — SECTION_STYLES += contact (split/map_first/compact, карта в
  `_contact_map.html`); мастер: чекбокс «Auch für andere Listen übernehmen» (слайд
  category → листинги активных модулей). Новых normalize-ключей НЕТ, golden целы.
  Тесты: test_page_presets (9) + contact-стили + apply-all; 1 msgid → 4 .po.
  **Очередь ТЗ дальше: этап D** (ST-5/6/7, FD-3 полный, FD-4) — первым план-док
  следующего незаблокированного пункта; ST-4b и «продано N» — ждут владельца.
- **Самое свежее (2026-07-19, ночь, продолжение): ST-5 «Списки → визуал» ✅ ЦЕЛИКОМ
  (этап D1 ТЗ; БЕЗ миграций).** План `docs/st5-lists-visual-plan-2026-07-19.md`.
  **ST-5a** Angebote карточным гридом (aspect-video фото из `ManagedSellable.image_url`,
  фолбэк; тумблер/Bearbeiten как у строки; classic_ui → divide-y список, гейт во
  вьюхе). **ST-5b** НОВЫЙ `apps/core/orders_view.py` — Канбан⇄Календарь⇄Лента:
  архетип-дефолт (booking|stays→Kalender, catalog→Liste, прочее→Board; недостижимое→
  kanban), ключ `orders_view` presence-minimal в normalize, сеттер `set-orders-view`
  (targeted-write), тег `orders_view_switch` — сегмент-контрол на board/списке
  заказов/календарях booking+stays (classic → пусто), хаб-плитка «Bestellungen»
  уважает выбор; v1 — навигационный (без встраивания движков). **ST-5c** CRM-карточки
  (аватар-инициал, теги, LTV «Σ € · N×» — ОДИН annotate-запрос RevenueEntry на
  страницу 25); ?q/Show more целы. Тесты: +2 sellable, test_orders_view (6), +2 crm,
  смежные 354 зелёные; 2 msgid → 4 .po. Урок CI #1551: новые шаблоны гонять через
  замок template_comments (многострочный `{# #}` запрещён). Дальше по этапу D:
  **D2 · ST-6 Marketing-центр** (план-доком) → D3 ST-7 → D4 FD-3 → D5 FD-4.
- **Самое свежее (2026-07-19, ночь, продолжение 2): ST-6 «Marketing-центр» ✅ ЦЕЛИКОМ
  (этап D2 ТЗ; БЕЗ миграций).** План `docs/st6-marketing-center-plan-2026-07-19.md`.
  **ST-6a** НОВЫЙ `apps/core/marketing_home.py` + лендинг `/dashboard/marketing/`
  (паттерн integrations_home): карточки ROI-порядка (гейт по модулям) + read-only
  обзор авто-касаний (reminder-события матрицы UD4-2 + строка B4 win-back) + панель
  результатов (views активных акций / ★-показы·клики Sum по
  AggregatorListing.tenant_schema / кампании issued·redeemed / отзывы ⌀·N; все
  блоки _safe, только чтение); хаб-плитка «Marketing» → центр; HUB_TABS не тронут.
  **ST-6b** `publishing.services.republish_promotion` (идемпотентная обёртка веера
  активации) + экран `/promotions/<pk>/teilen/` (статусы Publication по каналам +
  POST «Jetzt überall veröffentlichen», гейт active+publishing + входы
  email-кампании (только переход, UWG §7) и ★ Feature) + «📣 Teilen» в списке акций.
  Тесты 5+4, смежные зелёные; 28 msgid → 4 .po. Остаток этапа D: **D3 · ST-7**
  (10 видов блоков — наполнение реестров) → D4 FD-3 → D5 FD-4; ST-4b и
  «продано N» — ждут владельца.
- **Самое свежее (2026-07-19, ночь, продолжение 3): ST-7 — 7a+7b+7c-фундамент ✅
  (этап D3 ТЗ; БЕЗ миграций).** План `docs/st7-block-variants-plan-2026-07-19.md`.
  Разведка: «10 видов на блок» УЖЕ закрыт UC6-8 (5 типов ≥10). Дозакрыто: **7a**
  spacer 4 высоты (data.height presence-minimal, "" = py-6; миниатюра в
  variantThumb) · **7b** SECTION_STYLES += cta/about/usp_bar/reviews по 4 вида
  (лейблы реюзятся, 0 msgid; "" = байт-в-байт прежний вид) · **7c-фундамент**
  `site_defaults.card_style` (overlay|compact, presence-minimal; golden+looks
  целы). **ОСТАТОК 7c:** ветки `_product_card`/`_sellable_card` + селект билдера
  + draft-канал — отдельным инкрементом С характеризационными замками ДО правок
  (шаблоны переплетены с inline-edit/quick-add). Урок-повтор: template_comments
  снова словил многострочный `{# #}` — гейт в каждом шаблонном батче.
  Дальше этапа D: **D4 · FD-3 полный редактор Finder** → D5 FD-4; ST-4b и
  «продано N» — ждут владельца.
- **Самое свежее (2026-07-19, ночь, финал): решения владельца + ST-7c-рендер ✅
  (ST-7 ЦЕЛИКОМ) + ДЕМО «по новой идеологии» + тест-гид.** Решения: ST-4b ДА
  (план `st4b-sidebar-plan-2026-07-19.md`) · «продано N» ДА (честный порог) ·
  ST-7c ДА · UC2-3 per-page секции ДА (пакет разблокирован) · Pro/de.po/FB-мелочь
  отложены · **деплой очереди миграций сделан владельцем**. **ST-7c-рендер:**
  card_style ЦЕЛИКОМ — ветки overlay/compact в `_product_card`/`_sellable_card`
  (характеризационные замки ДО правок, "" байт-в-байт; sellable_card →
  takes_context), processor `storefront_card_style`, селект «Kartenform» в
  билдере (draft-канал). **Демо-волна (план `demo-new-ideology-plan`):** поля
  DemoKit look/card_style/whatsapp+presence/orders_view/section_styles/
  page_presets/spacers/seed_inbox/winback; носители: friseur (warm+видео+
  presence+инбокс-демо: тред с Sofort-Angebot + high-«Problem») · mode
  (nacht+overlay) · cafe (compact+стили+win-back) · restaurant (стили секций) ·
  retreat (spacer) · shop/bakery (пресеты страниц) · werkstatt (orders_view) ·
  aktionsmarkt (4 discount_style). **Тест-гид** `docs/demo-test-guide-2026-07-19.md`.
  ⚠️ ops: `seed_demo_tenants --recreate` после мержа. Очередь: ST-4b →
  «продано N» → UC2-3(b) → FD-3 → FD-4.
- **Самое свежее (2026-07-20): ST-4b сайдбар ✅ + «Verkauft N diese Woche» ✅ —
  оба «делаем» владельца закрыты; ЭТАП B ТЗ ЗАКРЫТ ЦЕЛИКОМ (в main).**
  **ST-4b:** `modules.sidebar_nav` — компактный плоский сайдбар (Übersicht ·
  Verkäufe · Angebote · Marketing→marketing-home · Integrationen · Website ·
  Einstellungen; catalog=core → Angebote всегда); classic_ui → прежние группы
  AB1 (легаси-ветка шаблона цела, замок); бейдж inbox на якоре Marketing;
  мобильный таб-бар = первая четвёрка; НОВЫЙ хаб `sellables` (Angebote +
  Erweitert: Produkte/Kategorien/Lager/Einkauf/Kombi/Import — дубль-вход) +
  Marketing-хаб += Erweitert Kontakte/Nachrichten/Telegram; integrations_home —
  свой nav-ключ. Осознанно обновлён замок AB1-групп (test_cabinet_nav).
  **«Продано N» (LS-4 v2):** `apps/core/social_proof.py` — sold_last_week
  (committed-статусы 4 kind, окно 7 дней, ЧЕСТНЫЙ порог ≥5 → иначе None),
  тег `sold_badge` на 4 детальных ВНЕ _buybox (паритет-замки целы); 3 msgid →
  4 .po. Урок-повтор CI-1116: `ruff format --check .` ЦЕЛИКОМ перед пушем.
  Дальше очереди: **пакет UC2-3(b) per-page секций (владелец дал ДА)** → FD-3
  → FD-4.
- **Самое свежее (2026-07-20, продолжение): UC2-3(b) + FD-3 + FD-4 ✅ — ОЧЕРЕДЬ ТЗ
  `next-gen-master-tz-2026-07-19.md` (этапы A–D) ИСЧЕРПАНА ЦЕЛИКОМ (всё БЕЗ миграций).**
  **UC2-3(b) вариант A** (план `uc23b-page-sections-plan-2026-07-20.md`): ссылочные
  типы блоков `PAGE_REF_BLOCKS` (faq_ref/team_ref/gallery_ref/testimonials_ref)
  ТОЛЬКО для `page_blocks` (в home-sections отбрасываются → golden целы) — секция
  на любой странице = рендер готового партиала с ГЛОБАЛЬНЫМИ данными site.<key>;
  вариант B (per-page ДАННЫЕ) — отдельное решение владельца. **FD-3 полный**
  (план `fd3-finder-editor-plan-2026-07-20.md`): редактор «Eigene Fragen» в
  `/dashboard/finder/` — слоты вопросов + чипы с маппингами Wörter/slug-СЕЛЕКТ из
  живых Category|Collection (dead-slug prevention; events без slug)/€ min-max,
  сохранение через normalize_finder (капы/валидация бесплатно), «Branchen-Vorlage
  laden», слоты дорастают после Save (без JS). **FD-4** (план
  `fd4-aggregator-finder-plan-2026-07-20.md`): платформенный Finder
  `/entdecken/finder/` (движок `apps/aggregator/finder.py`: вертикаль → город →
  3 листинга; честный фолбэк; роут выше city catch-all; кэш только шага 1);
  **UWG §5a** — органический порядок (featured НЕ поднимается) + «★ Anzeige» из
  общего `_cards`, замками. CTA-вход на /entdecken/. **Попутно закрыт i18n-долг
  Finder-трека:** 32 msgid (FD-1/2/3/4) добавлены в en/tr/ru/uk .po (все
  инкременты шли без .po; немецкий фолбэк маскировал). **Остаток бэклога — только
  owner-gated (Pro D1, T-1 de.po, variant B, FB-мелочь) и external-gated (LLM-
  Finder, WhatsApp Business API, OTA-API и пр.); см. ТЗ §3-финал + task-catalog.**
- **Самое свежее (2026-07-27/28): PMS-этап по спекам TravelLine — G12 + фидбэк-фиксы +
  волна PMS-R + PMS-B1/B2 + CP-1 (всё в main, автономные FF-мержи по зелёному CI).**
  Gap-анализ 5 разведчиков — `docs/pms-gap-analysis-2026-07-27.md` (очередь волн §5);
  решения владельца: физические номера ДА · корпоративный контур ДА · цены конкурентов ДА.
  Сделано: **G12 Verkaufsregeln** (сезонный min/max-stay, CTA/CTD по дням недели, окно
  бронирования; гейт ТОЛЬКО витрина; ⚠️ `stays/0024`) · багфиксы календарей (drop по всей
  строке Belegungsplan + grab-offset; кросс-месячный выбор дат витрины) · ресторан/запись
  без перезагрузок (`?box=1`-фрагменты селектора слотов) · «Verkäufe» отеля = Belegungsplan
  (entry ST-5b) · фиксы формулы G9 (rooms/блокировки/кастом-статусы →
  `counted_statuses_for`) + Online-Checkin-ссылка в письмах · **фидбэк владельца**: форма
  «Buchung bearbeiten» (даты/гости/номер/заметка, action=update) + карточка брони ПОД
  календарём (`?buchung=<pk>&box=1`) · **волна PMS-R ЦЕЛИКОМ** (план `pms-rooms-plan`):
  R1 `stays.Room` + синк ёмкости (⚠️ `stays/0025`) · R2 назначение номера (`free_rooms_for`/
  `assign_room`, «Ohne Zimmer»; ⚠️ `stays/0026`; попутно фикс: reprice-ветка move_stay не
  сохраняла смену юнита) · R3 шахматка построчно по комнатам + drop-назначение
  (`room_lane_rows`) · R4 хаускипинг-lite (выезд→dirty→«Sauber»; ⚠️ `stays/0027`; демо-отель
  с комнатами 101–104) · **PMS-B1** чекбокс согласия UWG в 3 формах брони → Double-Opt-In
  (+фикс `marketing_opt_in_at` в ЛК/CRM) · **PMS-B2** авто-fulfilled beat (LTV/win-back
  отеля живы) · **CP-1 Marktposition** (позиция цены среди отелей города из агрегатора,
  без рекомендаций) · багфиксы CRM-аудита (win-back TypeError, DSGVO-purge stays-гостей).
  Планы дальше: `pms-corporate-competitor-plans-2026-07-28.md` (CO-1/CO-2 корпоративный
  контур — следующие). ⚠️ ops: после деплоя `seed_demo_tenants --kit hotel --recreate`.
- **Самое свежее (2026-07-29/30): фидбэк-батч «акции явными» (aktionsmarkt) — 3 инкремента,
  всё в main, БЕЗ миграций.** (1) Типы акций явными: чипы механики на карточках/детали
  (`part="flags"`/`part="savings"` в `_discount_display.html`: 🆕/📦 reservieren/🔁 повтор/
  📅 срок + «Sie sparen X €»), секции групп на /aktionen/ (безгрупповые в конце), демо-кит
  += Mystery-Deal + галереи Kaffee/Bio-Kiste (`spec["images"]` списком). (2) Деталь акции:
  форма брони в ПОПАПЕ за CTA (тот же `_buybox` в DOM — паритет-замки целы; авто-открытие
  при ошибках POST), галерея миниатюр под главным фото (`Promotion.gallery_images`, свап
  кликом). (3) Блок цены по референсу владельца: крупная итоговая → зачёркнутая старая +
  пилюля `data-price-badge` → «Sie sparen» → строка наличия → промо-баннер группы с
  СЕГМЕНТНЫМ отсчётом Tage|Std|Min|Sek (`data-cd`, page-тикер; карточки листинга держат
  прежний `data-countdown`); стили UE2-2 уважены; регресс-фикс: процент-акция без цен —
  крупный «−N %» вместо цены. 3 замка обновлены осознанно. ⚠️ ops: после деплоя
  `seed_demo_tenants --kit aktionsmarkt --recreate` (галерея демо).
- **Самое свежее (2026-07-30, ночь): фидбэк отеля/услуг + первый экран ВСЕХ архетипов +
  M4-B Lookbook + старт i18n-волны.** (1) **Отель ×4:** мультисезонный расчёт ПРОВЕРЕН
  (`quote_total_cents` идёт по ночам — дефекта не было) + прозрачность `price_breakdown`
  («Preis pro Nacht anzeigen» на карточке брони) + **Lücken-Deal per-Zimmer**
  (⚠️ `stays/0030`). (2) **Страница услуги** `booking:service-edit` (зеркало
  `stays:unit-edit`) — «Bearbeiten» больше не высаживает в общий список. (3) **Навигация
  к «календарю цен»** (разведка дала карту 12 пробелов): вход `?tab=einstellungen&sec=preise`
  с Belegungsplan/отчёта/страницы номера, «🕒 Öffnungszeiten & Ressourcen» + плашка
  «Noch keine Öffnungszeiten hinterlegt» на страницах услуг (причина витринного «keine
  freien Termine» раньше не называлась); убран мёртвый `hub_tabs "stays"`. (4) **Первый
  экран для всех архетипов** — НОВЫЙ реестр `apps/core/hero_tiles.py` (7 архетипов ×
  плитки, гейты модуля/акции, fail-safe на мёртвом url) + тег `{% hero_tiles %}`,
  подключён `{% else %}`-веткой `_hero_widget.html` (кастомные ветки целы); слайдеры
  `heroes` у 10 китов; whitelist → `siteconfig.HERO_WIDGETS`. (5) **M4-B Lookbook**
  (⚠️ `catalog/0020` + `collections/0002`): `Product.collections` + `Collection.images`,
  `/lookbook/<slug>/`, фасет `?kollektion=` в каталоге, кабинет подборок открыт каталогу,
  демо CLOTHING. (6) **i18n**: 3 разведки → план `docs/i18n-full-coverage-plan-2026-07-30.md`;
  `.po` формально полны и **de.po существует**, но **~1100 строк не доезжают до `.po`**;
  **I18N-1 ✅** — 216 меток `choices` в 22 файлах обёрнуты в lazy (+107 msgid × 5 .po),
  миграции не нужны; исправлен `%%` в msgstr (рендерился бы буквально), de.po досинхронизирован.
  Дальше по плану: I18N-2 (конструктор сайта) → I18N-3 (шаблоны кабинета) → I18N-4..8.
- **Самое свежее (2026-07-31): волна i18n ЗАКРЫТА (кроме owner-gated PDF) + волна M4
  бутика ЗАКРЫТА ЦЕЛИКОМ.** **I18N-2..8 ✅** — конструктор сайта (76 меток реестров в lazy;
  грабля: lazy в JSON → `DjangoJSONEncoder` в `core/seo._dumps`, иначе «+»-инсертер падал),
  шаблоны кабинета, формы/мастер, `messages`/вьюхи, Finder (`localize_tree` только для
  пресетов — кастом владельца остаётся его текстом), качество переводов (14 смысловых
  правок), дымовой замок `test_smoke_i18n`. **I18N-7a ✅** — 41 письмо (owner/job/offer/
  inbox/installment/gift/waitlist), +116 msgid × 5 .po; дайджест владельца получил
  НАСТОЯЩИЕ плюралы (у ru/uk 4 формы). Урок: msgid из шаблонов тянуть через
  `translation.template.templatize` (то же, что makemessages), свой regex врёт.
  **⏸ I18N-7b (PDF/счета/постеры) — за решением владельца** (DATEV-заголовки переводить
  нельзя; рекомендация — гибрид). **M4-C ✅** Merkzettel (сессия, 0 миграций, DSGVO-чисто).
  **M4-A ✅** (⚠️ `catalog/0021`) — `size`/`color`/`images` на ProductVariant РЯДОМ с label
  (label держат склад/заказы/PDF/фид/импорт), единый резолвер фасета
  `size_axis = Coalesce(NullIf(size,""), label)` (смешанный каталог не теряет товары),
  оси data-атрибутами поверх ЕДИНСТВЕННОГО `select name="variant"` + подмена фото,
  CSV-импорт по `(product, size, color)` с фолбэком на label, демо CLOTHING 3×2 и 4×2.
  ⚠️ ops: после деплоя `seed_demo_tenants --kit clothing --recreate`.
- **Самое свежее (2026-07-31, продолжение): I18N-9 — «обёрнуто» ≠ «переведено».**
  Стенд кабинета демо на ru показал немецкие «Sichtbar»/«Bearbeiten». Причина
  системная: **`makemessages` падал** (конфликт msgid: одна строка как singular и
  как plural) → `.po` велись руками → сотни `{% trans %}` без записей молча шли
  по-немецки. Снят конфликт (`_buybox` → count-форма; попутно строка не
  переводилась даже на de), сверка кода с `.po`: из 3891 msgid отсутствовал
  **401**, из них **177 UI переведены на 5 локалей**; 224 — маркетинговая копия
  Branchen-лендингов (SEO под DACH) → **осознанно в allowlist**, перевод за
  решением владельца (рекомендация — начать с en; план §3). Регресс ловит
  `scripts/i18n_gap.py` + шаг CI «i18n coverage». **Демо-витрины:** словари
  `demo_i18n_<loc>.json` не знали китов, добавленных после DL-волны → первый
  экран/доверие (81 строка) переведены на en/ru/uk/tr; не переводим названия
  заведений, имена, ключи фото и тексты отзывов. Остаток (~478 строк — описания
  отдельных позиций) — по спросу. Также снят дрейф состояния миграций после
  I18N-1 (`aggregator/0015`, choices-only, DDL не порождает).
- **Самое свежее (2026-07-31, вечер): I18N-7b «документы» ЦЕЛИКОМ (решение владельца
  «полный»).** Пять генераторов (Rechnung/Angebot/Lieferschein/Teilnehmer-Infoblatt/
  QR-Poster) переведены полностью; общий слой `apps/core/documents.py` — язык
  документа (`?lang=` → язык поверхности → LANGUAGE_CODE, валидация по локалям
  тенанта), регистрация TTF, локале-зависимые деньги/кол-во/даты. **Шрифт:**
  встроенный Helvetica = WinAnsi, кириллицы нет вовсе, турецкие ı/ş рвут слово
  («Açıklama» → «A ç n klama») → в образ добавлен `fonts-dejavu-core`, а без шрифта
  язык честно понижается до английского. Кабинет: пилюли языков рядом с кнопкой
  скачивания (`{% doc_langs %}`); памятка гостя — на языке витрины. **НЕ переводим:**
  DATEV-экспорт (машинный формат) и `USt-IdNr.`/`Steuernummer`/§ 19 UStG.
  **Стенд нашёл 3 дефекта, невидимых тестам:** (1) `gettext` внутри f-строки
  xgettext НЕ извлекает — строка молча не переводилась И не попадала в гейт I18N-9
  (правило: `title = _("…")`, потом f-строка); (2) омонимы DeepL в счёте — «Net» →
  «Nicht»/«Değil»/«Нет»/«Ні» (отрицание!), «Quote» → «Zitat»/«Цитата», «Ticket» →
  «Fahrkarte», «Draft» → «Проект»; (3) жёсткое «Entwurf» в `number_display`.
  19 msgid × 5 локалей, 8 замков. ⚠️ ops: пересобрать образ (новый пакет шрифтов).
- **Самое свежее (2026-07-31, ночь): ВОЛНА HF (фидбэк отеля, 14 пунктов) ЗАКРЫТА ЦЕЛИКОМ —
  HF-0…HF-6 + попап формы + демо.** БЕЗ миграций, всё в `main` (`0cd2b2e5`).
  **HF-6c мультивыбор времён услуги:** времена-переключатели, состояние в URL
  (`?slot=A&slot=B`, без JS, живёт в iframe и переживает fetch-своп); бронь через
  `services.book_many` (N `Booking` + общий `group_code`, всё-или-ничего). Стенд вскрыл
  три дыры сверх плана: выбор терялся при переходе на соседний день (форма исчезала,
  в POST шёл только текущий день) → `buybox_ready` по ЛЮБОМУ отмеченному времени и
  hidden-поля несут весь набор; сетка предлагала неисполнимый выбор, когда услуга ДЛИННЕЕ
  шага расписания (демо-прокат 480 мин при шаге 30) → пересекающиеся старты
  `data-slot="blocked"`; мусор/протухшие `?slot=` роняли весь заказ. **HF-6d:**
  подтверждение, письма (гостю+владельцу) и календарь кабинета показывают всю группу.
  **Попап формы контактов** (номер+услуга, флаг `buybox_in_modal`; форма остаётся в DOM →
  паритет-замки целы; правая колонка номера 899→286 px). Две грабли: скрипт внутри
  свапаемой зоны умирал после первого fetch (`innerHTML` не исполняет `<script>`) → вынесен
  наружу; диалог заперт в stacking-контексте `lg:sticky` → шапка рисовалась ПОВЕРХ
  затемнения → портируется в `<body>`. **«Описание съехало»:** `mx-auto` центрировал тело
  детали внутри `max-w-5xl` → описание на 128 px правее фото; левые края выровнены.
  **Демо:** `translate_tenant_content` НЕ обходил акции (39 переводов лежали и не
  применялись) → добавлен проход + 8 записей ×4 словаря; фото трём акциям отеля; полные
  описания+attributes/FAQ четырём услугам. ⚠️ ops: `seed_demo_tenants --kit hotel --recreate`.
  Ограничение «`Service.attributes`/`faq` и `Promotion.group` без overlay» — **закрыто
  2026-08-01** (см. запись ниже).
- **Самое свежее (2026-08-01): витринный батч по фидбэку + находимость демо + i18n свободного
  текста владельца.** (1) **Переключатель «список ↔ плитка» на ВСЕХ сетках** (`_grid_view.html`
  + один делегированный обработчик; ключ сетки в localStorage → «список» на акциях не
  переключает каталог; режим списка = CSS-класс поверх любых `grid-cols-*` layout-движка) +
  **кнопка «Фильтры»** на каталоге (на телефоне панель фасетов занимала весь первый экран;
  применённый фильтр не прячем, счётчик активных — на кнопке) + фикс наплывания на
  overlay-карточке (quick-add лежал поверх названия/цены, сердечко — поверх бейджа).
  (2) **Блок «Примеры по функциям» на `/branchen/`** — владелец не нашёл демо с акциями, хотя
  `aktionsmarkt` есть: демо подписаны видами бизнеса, не возможностями. Реестр
  `apps/tenants/feature_demos.py` (8 записей «функция → конкретная страница живого демо»,
  гейт по засеянным хостам → мёртвых ссылок нет). (3) **i18n свободного текста** (план
  `docs/i18n-owner-content-plan-2026-08-01.md`): `apps/core/i18n_seq.py` (поэлементный оверлей
  списков; база задаёт длину, пустое = фолбэк) → `Service.attributes_i18n`/`faq_i18n`
  (⚠️ `booking/0020`) и `Promotion.group_i18n` (⚠️ `promotions/0024`; ключ фасета `?gruppe=`
  остаётся плоским, переводится только метка) + per-locale ввод метки группы в форме акции +
  засев демо (66 строк × 4 словаря). Остаток класса — метки вариантов/опций/Extra (за
  решением владельца). Форма attributes/faq — ЗАКРЫТА тем же днём (см. ниже).
- **Самое свежее (2026-08-01, продолжение): богатая карточка услуги заполняется владельцем +
  O-волна «виды отображения опций» + матрица склада «размер × цвет» — всё в main, одна
  миграция.** (1) **Ввод attributes/FAQ услуги** (план `service-rich-card-editing-plan`):
  Details — textarea «пункт на строку», FAQ — пары полей (слоты дорастают после Save, как в
  FD-3); сентинелы `*_present` (компактная строка списка не стирает наполнение, W0); переводы
  выравниваются по ВЫЖИВШИМ пунктам (`apply_seq_overlay`; замок). Грабля: хелперы, вставленные
  между `@login_required` и вьюхой, съели декоратор — вьюха осталась без авторизации; поймано
  своим тестом, правило в build-log. (2) **O-волна** (план `option-display-styles-plan`, ответ
  на вопрос владельца про учёт опций): реестр `catalog/option_styles.py` — варианты списком/
  кнопками/цветными кружками/фото-плитками/строками/двумя осями (цвет+размер); модификаторы
  плитками с фото/строкой/пилюлями; `Product.variant_style` + `ModifierGroup.display_style` +
  `ModifierOption.image` (⚠️ `catalog/0022`) + дефолт `site_defaults.variant_style`; фото
  варианта/опции грузится из кабинета (починена мёртвая функция M4-A). Свотчи не шлют полей
  (паритет-замок формы корзины) — управляют скрытым селектом; цвет кружка ТОЛЬКО по словарю.
  (3) **Матрица склада** (`inventory/matrix.py`, без миграций): «размер × цвет» с итогами по
  обеим осям («сколько всего синего / размера M»), фильтры Größe/Farbe плоской таблицы,
  колонки осей в CSV; пустая ячейка ≠ ноль, stock=None ≠ ноль (замки); Zählliste следует
  фильтру с предупреждением, матрица — нет (она обзор). ⚠️ ops: `seed_demo_tenants --recreate`
  для демо-стилей (mode=axes, cafe=buttons, гастро=chips/list).
- **Самое свежее (2026-08-01, вечер): аудиты месяца/июня + M22b оживлён — БЕЗ миграций.**
  Аудит выявил, что очередь миграций в этом файле устарела на ~3 недели (сверено с прод-
  `showmigrations`, см. ниже) и что за июнь потеряна ровно ОДНА работа: два коммита от 25.06
  на `claude/m20-retreat-pages` не долетели до main. **M22b оживлён** (план
  `docs/m22b-revive-plan-2026-08-01.md`, решение владельца «отдельным инкрементом»): плашка
  «бизнес на связи» по часам работы в треде клиента (серверный рендер; часы не заданы → плашки
  нет) + индикатор «печатает» на кэш-флаге (TTL 6 с, троттлинг пинга 3 с, ключ по UUID треда —
  БЕЗ модели: состояние обязано теряться) — едет в СУЩЕСТВУЮЩЕМ поллинге, новых запросов на
  чтение нет. Не cherry-pick (~7 конфликтов, inbox с тех пор +868 строк), а ручной перенос ~60
  строк в текущий код. 42 замка в `apps/inbox` + стенд обеих сторон. Грабля: кабинетные
  эндпоинты дают 403 не только без CSRF, но и без `Membership` (`has_cabinet_access`
  fail-closed — `@login_required` его не заменяет). SSE остаётся отложенным (roadmap §Отложено).
  **Доводка 2026-08-03 (ревью+браузерный стенд):** пинг «печатает» из НАСТОЯЩЕГО браузера не
  отправлялся вовсе — скрипт выше формы, прямой `querySelector` по textarea = null (curl-стенд
  сервера этого не видит; правило: JS-фичи гейтить Playwright'ом) → делегирование на `document`
  (как Ф1) + регресс-замки на оба шаблона; попутно закрыты ПРЕД-существующие дыры: кабинетные
  `thread_poll` (тела сообщений, запись unread) и `unread_count` были без `@login_required` —
  аноним получал 200 (Membership-middleware анонима не трогает); оба `thread_typing` — POST-only.
  **T-7 `migration_state` ✅** (следом, без миграций): команда сверки миграций ПО ВСЕМ СХЕМАМ
  (public + все тенанты), вывод сгруппирован по миграции, схема-строка-без-Postgres — отдельный
  диагноз «СХЕМЫ ОТСУТСТВУЮТ» (не «не применено»: иначе владельца отправило бы чинить не то);
  шаг добавлен в `deploy.sh` этап 8 → каждый деплой сам печатает вердикт, очередь ниже больше
  не может тихо устареть. Проверка одной командой: `python manage.py migration_state`.
- **Самое свежее (2026-08-03): ВОЛНА VERKÄUFE V1–V4 ЦЕЛИКОМ — единая страница продаж**
  (план `docs/unified-sales-page-plan-2026-08-03.md`, решения владельца §4; БЕЗ миграций).
  `/dashboard/verkaeufe/`: вкладки по kind (primary всегда — у отеля Belegungsplan; прочие
  с первой продажей, `kinds_with_sales` exists-гейт; reservation — в Marketing), в каждой
  вкладке Kalender/Board/Liste с persist'ом (`sales_views` presence-minimal). Календари
  встроены партиализацией 1:1 (`stays/_belegungsplan_body` + context-фны; booking-Tagesplan;
  рендер байт-в-байт). Generic-Liste закрыла «списка нет» у stay/booking/job/ticket.
  **V3 Auftragsbuch**: календарь заказов по дням выдачи (`Order.pickup_slot`, 14 дней,
  «Ohne Termin»-блок). **V4**: вход «Verkäufe» (сайдбар/плитка/хоум) → новая страница
  (classic_ui — прежний вход, замки), «Alte Ansicht · Alles auf einer Seite» на 5 старых
  страницах, ЧЕСТНЫЕ счётчики колонок доски (агрегат по БД + resolve кастом-статусов —
  раньше врали при >50). Замки ST-5b/ST-4b обновлены осознанно (легаси-маппинг под classic).
  **Решения владельца на след. волну:** акции — ВСЕ сразу на рельсы «ценовой слой над
  базовой сущностью» (зависимость от реального наличия товара/номера/услуги-слота-мастера,
  закрытие стандартным Order/Booking/Stay, клиент в CRM); наборы — расширяем Combo.
  План-доком следующей сессией (`unified-sales-page-plan §6`, task #75).
- **Самое свежее (2026-08-03/04): ВОЛНА PL «Акция = ценовой слой над базовой сущностью»
  ЗАКРЫТА ЦЕЛИКОМ (P1–P7)** — решения владельца «переводи все сразу»; план
  `docs/promo-price-layer-plan-2026-08-03.md`. **Модель (⚠️ миграции `promotions/0025` +
  `booking/0021` + `stays/0031`, аддитивные):** FK-цели `service`/`stay_unit`/`combo` +
  `target_rules` (weekdays/hour_from-to/resource_id | stay_from/stay_to, fail-closed
  матчер) + `Booking.promotion`/`StayBooking.promotion`. **Два счётчика с разными
  ролями:** `available_quantity` = лимит кампании (conditional UPDATE как был),
  физическое наличие — ШТАТНЫЕ движки целей; двойное списание в одной atomic,
  OutOfStock/SlotTaken откатывают оба, возврат лимита при отмене ровно один раз
  (FSM-хуки + зеркало status_effects; no_show НЕ возвращает). **Чекауты:**
  товар/combo/свободная → `services.purchase` = `create_order(custom_lines)` (6-й
  элемент — modifiers-маркер {"promo": id}; склад/леджер штатно); услуга —
  промо-цена применяется АВТОМАТИЧЕСКИ в `service_book` (одиночная бронь, лучшая
  цена, правила «счастливых часов»); номер — кандидат `pricing.auto_discount(extra=)`
  в `book_stay` (max, не суммируем — как G4/Lücken). **Витрина акций (P5):**
  /p/<uuid>/ диспатч по цели, эндпоинт `/p/<uuid>/kaufen/` → штатное подтверждение
  заказа; kind reservation НЕ порождается (легаси доживает, /r/<code>/ цел).
  **Витрина целей (P6):** деталь/карточка товара — rose-баннер/бейдж со ссылкой на
  акцию; сетка слотов услуги — подсветка действующих времён + промо-цена в форме;
  номер — quote/тарифы/«ab …» считают акцию тем же кандидатом, что чекаут (ФИКС
  расхождения «показали дороже, списали дешевле») + бейдж до дат. **Демо:** спека
  китов += service/stay_unit/rules/limit (второй проход после сидинга модулей);
  friseur Happy Hours (Mo–Mi 10–14) + hotel Frühbucher → Doppelzimmer Seeblick
  (демо-брони сами списывают лимит — инвариант в ките-тесте). **Аналитика (P7):**
  `deal_counts` (заказы по маркеру + брони по FK, отменённые не в счёт) → плитка/
  колонка «Verkäufe», конверсия по (сделки+резервы)/просмотры. Проверено Playwright
  на стенде. ⚠️ ops: `seed_demo_tenants --kit friseur|hotel --recreate` после деплоя.
- **Самое свежее (2026-08-04, фидбэк владельца): месячный календарь кабинета Termine +
  «артикулы везде» + Zusammenführen.** (1) Сетка месяца над Tagesplan (`booking/_month_grid.html`,
  счётчик броней/день одним запросом, история доступна, клик по дате = прежний день-список;
  работает и во вкладке Kalender Verkäufe). (2) Артикулы: SKU варианта редактируется из
  кабинета; `ModifierOption.sku` (⚠️ `catalog/0023`); снимок `OrderItem.sku`
  (⚠️ `orders/0017`) → Art.-Nr. в подтверждении/кабинете/письмах/PDF; витрина-деталь
  показывает Art.-Nr. и меняет с выбором варианта; фид mpn per-variant. (3) «Als Varianten
  zusammenführen»: чекбоксы списка товаров → выбор главного → прочие становятся вариантами
  (`apps/catalog/merge.py`; артикул/EAN/цена/остаток/EK/фото переезжают, леджер сходится
  с обеих сторон, старые гаснут с историей). Урок: инвариант-ассерты на демо-сидере считать
  по АКТИВНЫМ сделкам (отменённой FSM возвращает лимит, FK остаётся) — флак CI #1836.
- **Самое свежее (2026-08-05): W-v3 — полный АУДИТ КАБИНЕТА (воркфлоу 14 агентов, все
  находки адверсариально верифицированы) + план унификации W7–W12.** Запрос владельца
  «опять каша; базовые настройки отдельно, дополнительные по типам в табы; изучить
  TravelLine/Битрикс/CS-Cart». Диагноз (7 системных причин): 4 несинхронизированных
  реестра навигации; 3 поколения поверхности продаж; Простой режим НЕ работает в новом
  UI (sidebar_nav без simple_hidden_modules — требование st4b-плана потеряно);
  classic_ui = вторая IA; подсветка 7 из 44 nav-значений + сломан поиск меню;
  опасные save-пути (normalize теряет `notify`/`low_stock_threshold`/`lots_enabled`;
  голый tenant.save() в settings_view; notifications затирает выключенные модули);
  сироты billing (подписка!)/Blog/Newsletter/Finanzen/Auswertungen(404). Поведенческое:
  «Versendet» с доски без трек-номера; «Abgeholt» доставочному; резерв с доски без
  таймстемпов; акцию на услугу/номер нельзя создать из UI. Доки:
  **`docs/cabinet-audit-2026-08-05.md`** (+папка отчётов) + план
  **`docs/cabinet-unification-plan-2026-08-05.md`** (W7 предохранители → W8 единый
  реестр NavEntry → W9 Settings-хаб «базовые+по типам в табах» → W10 Verkäufe
  единственной поверхностью → W11 Marketing+Kunden → W12 честные режимы; всё БЕЗ
  миграций). **Решения Р-1..Р-8 ✅ (2026-08-05): classic_ui УДАЛИТЬ (волна W-CL до W8) ·
  Marketing+Kunden слить · Integrationen → вкладка Einstellungen · Reservierungen в
  Verkäufe · Newsletter вкладкой · Ctrl+K в W8 · Team в W9 · порядок W7→W-CL→W8→…**
  **W7 ✅ ЦЕЛИКОМ (той же датой): a** save-пути (normalize-passthrough notify/склада +
  замки; merge матрицы уведомлений; settings_view update_fields; мёртвые POST-ветки
  order-settings/billing-payments-methods; presence-guard мастера) · **b** навигация
  (починен поиск меню; входы-сироты Finanzen/Auswertungen/Abrechnung/Blog/Newsletter/
  Kollektionen; возврат «Angebote»; мёртвый nav_key care; гейты hub_tiles; 404
  Marketing-Puls; offer_cta jobs; CTA «Belegungsplan» только отелю) · **c** продажи
  (is_delivery-фильтр доски; shipped_at/таймстемпы резервов в FSM; next=-провод —
  действия из встроенных календарей не выбрасывают на легаси; гейт primary-kind;
  Liste по дате события). 30+ замков; детали — build-log 2026-08-05. **W-CL ✅ (той же датой): classic_ui
  СНЕСЁН ЦЕЛИКОМ** (план `wcl-classic-ui-removal-plan-2026-08-05.md`): тумблер/endpoint/
  классик-сайдбар (группы AB1)/classic-ветки вьюх и шаблонов/NAV_GROUPS/
  grouped_active_modules/nav_task_label; entry «Verkäufe» = всегда единая страница;
  board-хаб урезан до Tickets/Aufträge; normalize ДРОПАЕТ ключ; правило §8b
  studio-concept отменено. **Перенос:** simple-скрытие меню переехало из классик-
  сайдбара в hub_tabs (module_key ∈ simple_hidden_modules; каталожным табам
  module_key="catalog") — Простой режим впервые работает в новом UI. Classic-замки
  сняты осознанно (карта — build-log). **W8 ✅ (той же датой): единый реестр навигации**
  (`apps/core/nav_registry.py`: ANCHORS+ENTRIES; HUB_TABS/sidebar_nav — производные,
  прежняя форма целa) + **подсветка «где я» на всех экранах** (фильтр `nav|nav_anchor`,
  карта nav→якорь) + **инвариант-замки** («каждый nav-литерал имеет якорь» — скан
  исходников; «каждая запись reverse'ится») + **палитра Ctrl+K** (🔍 в шапке, индекс из
  реестра, гейты модулей/Простого). hub_tiles в реестр не сведены (осознанно, W9/W11).
  W7+W-CL смержены в main (`ce69b78`, БЕЗ миграций). Дальше: **W9 (Settings-хаб
  «базовые + по типам в табах» + Team)** → W10 → W11 → W12. Ветка
  `claude/cabinet-audit-optimization-vkcxs4`.
- **Самое свежее (2026-08-05, продолжение): ВОЛНА W9 (Settings-хаб) ЗАКРЫТА ЦЕЛИКОМ
  W9-1..W9-11, всё БЕЗ миграций** (план `w9-settings-hub-plan-2026-08-05.md §4`).
  Табы Einstellungen «базовые + по типам»: Mein Geschäft · Sprachen · Recht & Steuern
  (W9-5: налоговые реквизиты переехали из формы бизнеса, единственный писатель) ·
  Zahlung & Lieferung · Benachrichtigungen & Kanäle (W9-7: пресеты «Alle Kanäle»/«Nur
  E-Mail» + read-only статус бизнес-бота) · **Abläufe (W9-8: НОВЫЙ экран
  `/dashboard/ablaeufe/` — имена статусов/переходы/колонки доски в одном месте;
  копия формы в order_list и ветка orders:order-settings удалены, мёртвый stays-
  контекст снят)** · Website & Domains (W9-4) · **Integrationen (W9-9, Р-3: якорь
  ушёл из сайдбара 7→6, карточки со статусами Stripe/бот/домен/каналы fail-safe)** ·
  Finanzen · Auswertungen · Abo & Rechnung · **Team & Zugriff (W9-10, Р-7: инвайт
  Redis-токеном одноразовым TTL 7 дней, принятие `/team/beitreten/<token>/`,
  guard'ы последнего owner; РОЛЕВОЙ ГЕЙТ ВПЕРВЫЕ РАБОТАЕТ — owner-only префиксы
  billing/recht/team в CabinetOwnerAccessMiddleware)** + Erweitert (Zusatzleistungen/
  Medien/Funktionen/Finder/Hilfe). Предохранители W9-3: SEO/Finder — targeted-write.
  Дальше по плану унификации: **W10** (Verkäufe единственной поверхностью) → W11
  (Marketing+Kunden, Р-2) → W12 (честные режимы).
- **Самое свежее (2026-08-05, вечер): ВОЛНА W10 (Verkäufe единственной поверхностью)
  ЗАКРЫТА ЦЕЛИКОМ W10-1..W10-6, всё БЕЗ миграций** (план `w10-verkaeufe-plan-2026-08-05.md`).
  **W10-1** одна модель переключения видов (persist `sales_views`; сегмент ST-5b удалён,
  переключение вида сохраняет GET через next=). **W10-2** (Р-4) Reservierungen — вкладка
  по общему правилу «с первой продажей». **W10-3** паритет order-Liste (фильтр статуса +
  поиск + KDS/QR) + «＋» из любого вида + смерть hub_tabs["board"]-огрызка (реестр жив —
  палитра/подсветка) + входы ticket/job в полные экраны. **W10-4** kind-агностичный вид
  «📆 Heute» (`?view=heute`: Anreisen/Abreisen/Im Haus/Termine/Abholbereit/Lieferungen;
  виджеты главной deep-link'аются сюда). **W10-5** единый `transactions.apply_action`
  (спец-поля в extra: tracking_code при shipped пишется ДО apply — письмо с Sendungsnummer;
  поле трек-номера на канбан-карточке заказа-доставки). **W10-6** легаси-редиректы с
  GET-carry (`sales_page.legacy_redirect`): order-list/booking-calendar/stays-calendar/
  stays-today → 302 на вкладки Verkäufe; ДО схлопывания закрыт паритет («Im Haus» в Heute);
  events:list/jobs:list/board/stay_new НЕ редиректятся; 4 шаблона-обёртки удалены,
  ~30 тестовых колл-сайтов переписаны. Дальше: **W11** (Marketing+Kunden, Р-2) → W12.
- **Самое свежее (2026-08-05, ночь): ВОЛНА W11 (Marketing+Kunden) ЗАКРЫТА в объёме
  W11-1..W11-4, всё БЕЗ миграций** (план `w11-marketing-plan-2026-08-05.md`). **W11-1**
  (Р-2) хаб «Kunden» удалён — Kontakte/Nachrichten прямыми табами Marketing, Telegram в
  Erweitert; crm/inbox/telegram рендерят единый хаб. **W11-2** marketing_home слим —
  только состояние (авто-касания + результаты) + кросс-вход Care-Zyklus. **W11-3**
  вкладка «Über den Betrieb» на Bewertungen — портальные BusinessReview видны владельцу
  (v1 read-only; ОТВЕТ требует миграции SHARED-поля — решение владельца). **W11-4**
  акция на услугу/номер/комбо из UI: PromotionForm += FK-цели PL (гейт по модулям),
  GET-префилл, «% Aktion» на карточках Angebote. **W11-5 (Website-свод в Studio) —
  разведка сделана, код отложен свежей сессией с план-доком** (site.html функционален:
  quick-start/галерея/тексты; слив = правка site_home 3400 строк + стенд). Остаток
  программы аудита: **W12** (честные режимы, план унификации §2.7).
- **Самое свежее (2026-08-05, ночь, финал): ВОЛНА W12 «честные режимы» ЗАКРЫТА
  (W12-1..3, БЕЗ миграций) — ПРОГРАММА АУДИТА КАБИНЕТА W7..W12 ИСПОЛНЕНА ЦЕЛИКОМ**
  (план `w12-modes-plan-2026-08-05.md`). **W12-1** экран «Ansicht»
  (`/dashboard/ansicht/`): Einfach/Experte + честный список «что скрыто у вас»
  (карточка на Funktionen — слим). **W12-2** Простой прячет из ящика «Erweitert»
  продвинутые инструменты (module None); функции активных модулей остаются
  (замок S6b: werkstatt держит Produkte/Lager). **W12-3** константы
  SIMPLE_HIDDEN_MODULES/ARCHETYPE_SIMPLE_HIDDEN удалены — ось живёт в ModuleSpec
  (simple_hidden/simple_hidden_for), паритет 1:1 замком по всем 15 типам; честно:
  автоматика из recommended_for невозможна без нового сигнала у core-модулей.
  **Итог программы W-v3 (один день, всё БЕЗ миграций):** W7 предохранители →
  W-CL classic снесён → W8 единый реестр навигации+Ctrl+K → W9 Settings-хаб
  (11 табов, Abläufe, Team+ролевой гейт) → W10 Verkäufe единственной поверхностью
  (Heute, apply_action, легаси-редиректы) → W11 Marketing+Kunden (один хаб,
  Über den Betrieb, акция из UI) → W12 честные режимы. **Хвосты за решением
  владельца:** ответ на BusinessReview (миграция SHARED-поля) · де-факто новые
  экраны — прогнать глазами на стенде.
- **Самое свежее (2026-08-06): решения владельца 1а/3/4а/5а по хвостам аудита — в main
  `5e9a38f`.** **1а** ответ владельца на портальные BusinessReview: reply_text/replied_at
  (**⚠️ миграция `aggregator/0016`, SHARED, аддитивная — деплой `./scripts/deploy.sh
  single`**), форма на вкладке «Über den Betrieb» + показ на портале; анти-кросс-тенант
  (чужой pk = 404, замок). **4а** Reservierungen без дубля в Marketing — одна поверхность
  (вкладка Verkäufe с первого резерва, W10-2). **5а** CI ставит зависимости строго из
  `uv.lock` (`uv sync --locked --extra dev`; pytest-django пин `<4.13` — релиз 4.13.0
  уронил CI); грабля: uv.lock был в .gitignore → первый прогон не нашёл лок, лок теперь
  ЖИВЁТ В РЕПО, обновление зависимостей = осознанный `uv lock` в коммите. **3** роли
  admin/staff пока идентичны (решение «оставить как есть»). **2а** W11-5 Website-свод — исполнен
  (запись ниже).
- **Самое свежее (2026-08-06): W11-5 «Website-свод в Studio» ✅ ЦЕЛИКОМ — ВОЛНА W11
  ЗАКРЫТА (БЕЗ миграций).** Решение владельца 2а (полный свод). План
  `docs/w11-5-website-studio-plan-2026-08-06.md`. Страница `/dashboard/site/`
  умерла → 302 на Studio с переносом GET (прецедент W10-6), `site.html` удалён,
  все входы «Website» (карандаш шапки · Anchor реестра W8 · чек-лист онбординга ·
  NavItem спеки) ведут в билдер. Перенесено: **область «⚡ Start»** рейки
  (шаблоны витрины + демо-контент; ветки early-return ДО main-save — иначе
  fall-through пересобрал бы `sections`), **hero_image** (Banner) и **quick_add**
  (Theme) в `#home-form` с presence-guard/сентинелом + live-черновик,
  **gallery_video** — форма области «Медиа» (targeted-write). Дубли НЕ плодили:
  галерея фото/hero-тексты/контент-секции в Studio были и раньше, about_* правится
  на канве. Сироты-экраны (SEO/обложки/раскладки/превью) получили входы из области
  «Шаблоны». **Playwright-стенд 28/28 нашёл дефект, невидимый серверным тестам:**
  quick_add попал в `data-expert` блок → в Простом режиме был недоступен (на «Site»
  доступен всегда) → вынесен + замок. Замки умершей ветки переписаны осознанно
  (карта — build-log); уточнён инвариант W6: «не ронять» относится к ЧУЖИМ ключам
  (ui_mode/board/seo/page_blocks), а typography/site_defaults/font билдер ВЛАДЕЕТ.
  Грабли стенда: Django кэширует шаблоны и в DEBUG (рестарт runserver); панель
  инспектора после входа схлопнута (канва-first W1).
- **Самое свежее (2026-08-06, вечер): АУДИТ ПЕРЕВОДОВ + волна I18N-10 «параметры товара»
  (⚠️ миграция `catalog/0024`).** Запрос владельца «проверь переводы демо-сайтов, админки,
  характеристик и параметров»; решение — «делаем всё, включая миграции». **Аудит:** хром
  закрыт (4014 msgid × 5 локалей; пустые msgstr только identity — показов чужого языка ноль;
  гейт I18N-9 держит регресс), демо-сущности переводятся с DL-волны; **дыры — ровно в
  параметрах**: метки вариантов (`label/size/color`) и модификаторов (`ModifierGroup.name`,
  `ModifierOption.label`) без оверлеев вообще; `material/care/origin/ingredients_i18n`
  существовали, но демо-обход их не заполнял; `Category.size_table` без i18n. Как с акциями
  в HF-волне, часть переводов уже лежала в словарях мёртвым грузом. **Сделано (P1–P4):**
  оверлеи + `*_localized`; витрина (пикер всех видов, корзина, Anprobe/Warteliste,
  модификаторы, Größentabelle); ввод переводов из кабинета (тег `overlay_i18n_inputs`,
  свитчер Ф1, presence-guard); демо-обход + 37 строк в 4 словаря. **ИНВАРИАНТ волны:
  переводится ТОЛЬКО показ** — снимок заказа (`OrderItem.variant_label`/`modifiers`) и
  ключи учёта (склад, CSV-импорт, оси фасета `data-color`) остаются на базовом языке
  (замки). **Стенд Playwright 12/12 (демо mode/cafe) нашёл два дефекта:** составная метка
  «S · Blau» своего перевода не имеет → `label_localized` собирается из переведённых осей;
  подпись свотча бралась из ключа → разделены `name` (ключ) и `label` (подпись). Замок
  проекта «без identity-записей в демо-словарях» поймал 13 записей вида S→S — убраны.
  **Грабля среды:** локально нет `gettext`, поэтому ~9 тестов падали на немецких ассертах;
  `.mo` собраны через `polib` — после этого локальный прогон совпал с CI.
- **Самое свежее (2026-08-06/07): АУДИТ ДЕМО-КОНТЕНТА → ST-8 (страницы витрины) + акции
  во всех китах + починка меню — БЕЗ миграций.** Запрос владельца: «у каждого демо должны
  быть основные модули, меню — выходы в них, страницы галереи/отзывов/мастеров ОТДЕЛЬНЫМИ
  страницами, а не разделами главной»; отдельно — «не везде есть акции, засеять все типы
  акций во всех китах». **ST-8** (план `docs/st8-storefront-pages-plan-2026-08-06.md`):
  страницы `/galerie/`, `/team/`, `/bewertungen/` (гейт по НАЛИЧИЮ контента: пусто → 404 и
  пункт меню гаснет, архетип-whitelist не заводим — он врал бы при пустом разделе); отзывы
  собирают ДВА источника (портальные `BusinessReview` + кураторские `testimonials`); секции
  главной остались тизерами со ссылкой «Все …». **Акции:** 14 наборов `promotions_spec` —
  теперь у каждого кита 4–17 акций, вместе покрывающих все 9 стилей (percent/strikethrough/
  festpreis/ab/badge/countdown/mystery/surprise/легаси), оба типа (discount+reservation) и
  все виды целей PL (товар/услуга/номер/свободная); `promotions` дополнительно включён у
  werkstatt/handwerker/tours. **Меню (аудит как данные — 6 классов дефектов):** у ресторана
  СВОЕГО меню не было вовсе (шапка выводилась из легаси-`nav`) → `RESTAURANT_MENUS`;
  у ретрита из шапки нельзя было попасть в размещение и заявки (модули активны, узлов нет);
  у отеля «Buchen» вёл на `/#buchen`, которого на его главной НЕТ (`hero_widget="stays"`
  гасит секцию поиска); у туров/Handwerker «Kontakt» ссылался на страницу `contact`, которой
  не было в `_PAGE_URL_NAMES` (узел молча выпадал); якоря «Aktionen»/«Sale» → страница
  `/aktionen/` (работает с любой страницы, а не только с главной); 6 китов имели акции без
  пути к ним; страница `/lookbook/<slug>/` не имела НИ ОДНОЙ ссылки с витрины → ссылка у
  выбранной подборки с фото. **Замки:** новый `apps/tenants/tests/test_demo_menus.py` (84) —
  меню кита проверяется КАК ДАННЫЕ: каждая цель резолвима, каждый архетип активен у типа
  бизнеса, каждый якорь существует на главной ЭТОГО кита, наполненный модуль выведен в меню.
  Именно этот инвариант ловит весь класс «узел молча выпал». **Тот же класс на ПЕРВОМ ЭКРАНЕ:**
  сплошная сверка `HERO_TILE_SETS` с гейтами вьюх нашла три плитки, ведущие в 404 —
  «Geschenkgutschein» (страница требует ещё и настроенной оплаты, `gift_purchase_active`),
  «Rückruf» (вьюха требует модуль jobs, гейта не было), «Aktuelle Deals» + все `gate="deal"`
  (`/aktionen/` требует модуль promotions, а живая акция в БД этого НЕ гарантирует); замок
  теперь проверяет реестр целиком — его первая версия молча пропускала `/aktionen/`.
  **Побочно:** контент-гейт ST-8 стоил запроса в БД на КАЖДЫЙ рендер меню (`resolve_menu`
  зовётся из шапки, нижнего меню и контекст-процессора кабинета) — поймал чужой замок
  `test_nav_hides_disabled_modules` (зелёный на main, красный на ветке); мемоизация на
  объекте тенанта + `.exists()`, пробники fail-closed. **Проверено вживую** (14 демо после
  пересева): мёртвых ссылок в меню нет, страницы ST-8 отдают 200 где есть контент и 404 где
  нет, акции видны у всех, подписи меню и заголовки переводятся на 5 языках; платформенный
  `/branchen/` — 14 отраслей из 14 (кроме намеренного `other`) + 8 живых демо-примеров.
  ⚠️ ops: `seed_demo_tenants --recreate` после деплоя. **Попутно исправлено в CLAUDE.md:** §7 помечен архивом (порядок
  работ от 01.07 разобран), снята закрытая долговая запись про XSS в карте агрегатора
  (`_map.html` строит попап через DOM с проверкой схемы), статус языкового модуля от 30.06
  свёрнут в историю (противоречил коду).
- **Самое свежее (2026-08-07): фидбэк витрины (5 пунктов) + Branchen-модули — всё в main,
  БЕЗ миграций** (план `docs/storefront-feedback-2026-08-07.md`; build-log-запись дописана
  2026-08-10). Дропдауны шапки: «Mehr» и группы меню открываются ТАПОМ (hover/focus-within
  не работали на таче) + клик вне возвращает `hidden`. /aktionen/: секцию получает группа
  от 2 акций (`MIN_GROUP_SECTION`), одиночные — блоком «Weitere Angebote» (пустые ⅔ строки
  ушли). Диета — селект в панели фильтров (+`diet_chips` в гейте показа панели). Каталог:
  комбо-тизер под сетку, категории — фото-плитки общим `_category_tile.html` (без фото —
  чипы), размер плитки из Studio через `SECTION_STYLES["categories"]` (square/tall/wide,
  без нового ключа) + демо-фото категорий. Меню демо: «о нас»-разделы свёрнуты в подменю
  «Über uns» по ШИРИНЕ строки (`_menu_row_width` ≤ 788px, производное при сидинге) +
  редактор меню кабинета знает ВСЕ страницы (`PAGE_TARGET_LABELS`; был захардкожен
  {home,about} — чужая цель после Save вела на главную). Branchen: 4 отраслево-нейтральных
  модуля (Auswertung/Kanäle/Finanzen/Telegram) — среди прочих карточек в порядке реестра
  (решение владельца: НЕ отдельным блоком «есть у всех»).
- **Самое свежее (2026-08-10): волна SM «один функционал для всех + Verkäufe по модулям» —
  в main, БЕЗ миграций** (план `docs/sm-single-mode-plan-2026-08-10.md`). **SM-1: режим
  Простой/Эксперт снесён ЦЕЛИКОМ** (прецедент W-CL/classic_ui): ui_mode/is_simple/
  simple_hidden_* + поля ModuleSpec, экран Ansicht, тумблер шапки, гейты плиток/табов/
  палитры/формы товара; normalize ДРОПАЕТ `ui_mode`; замки W6-класса переведены на
  probe-ключ `notify`; новый замок `test_simple_expert_mode_is_gone`. Einfach/Experte
  РЕДАКТОРА (UC6-10, свёртка настроек блока на канве) ОСТАВЛЕН — решение владельца.
  **SM-2a: Verkäufe** — вкладка на КАЖДЫЙ активный модуль сразу (решение владельца;
  замки W10-2/Р-4 переписаны осознанно), виды (Kalender/Board/Liste) + ＋/«⚙️ Abläufe»
  ВНУТРИ вкладки (фидбэк «кнопки как будто над верхним уровнем»), сводка «📆 Heute»
  переехала на главную кабинета (Übersicht; `?view=heute` жив для deep-links).
  **SM-2b: паритет настроек статусов всем 6 kind** — `_STATUS_LABEL_KINDS` и
  `_status_kinds_for` += job/ticket/reservation (имена статусов + правила переходов;
  доска/списки были generic изначально); замок паритета с `status_registry.BUILTIN`.
- **Самое свежее (2026-08-10, продолжение): SM-3 — кастом-статусы (FB-3 B) на ВСЕХ шести
  направлениях ✅ ЦЕЛИКОМ, БЕЗ миграций** (решение владельца «делаем»; план
  `docs/sm3-custom-status-all-kinds-plan-2026-08-10.md`; разведка — воркфлоу 10 агентов).
  Находка: SM-2b уже открыл трубопровод (normalize/редактор/FSM гейтятся одним
  `_STATUS_LABEL_KINDS`) — инкремент закрыл КОРРЕКТНОСТЬ: anti-oversell билетов через
  `active_statuses_for("ticket")` (4 литерала — была двойная продажа мест) · правило
  «рёбер ИЗ cancelled-роли не бывает» (терминальный терминален; закрывает двойной возврат
  склада/лимита, вкл. двухшаговый un-cancel-обход, найденный адверсариальной сверкой;
  слой чтения + эффекты + редактор sources/targets) · зеркала эффектов (job done →
  `commit_stock` идемпотентно; ticket cancel → стоп рассрочки R10e) · `def_from_role`
  kind-aware (done-роль билета держит место — паритет attended) · кламп кода до 20
  (varchar(20) у всех шести — DataError-дыра всех kind) · re-save редактора хранит
  продвинутые флаги · правила Варианта A управляют только builtin-целями (кастом-цели
  всегда видимы; normalize_transitions больше не прячет кастом-кнопки — класс W7a) ·
  purge/max_per_customer/дайджест/Heute/верификация отзывов (`cancelled_statuses_for`)
  через реестр · читаемые подписи Reservation (`builtin_status_labels`) + `status_label`
  на per-app экранах. Замки ДО фиксов (18 красных на дырах); стенд Playwright 13/13
  (touren, полный цикл создать→рёбра→доска→перевод); broad 2903 passed. Квирки — план §2.
- **Самое свежее (2026-08-11): gap-анализ goodkarma-catering.de + ВОЛНА AF (AF-1+AF-2) ✅.**
  Анализ `docs/goodkarma-catering-gap-analysis-2026-08-11.md` (14 агентов, 24 пробела
  адверсариально верифицированы): сайт-референс собирается уже сегодня; реальные гэпы —
  Tier 1 C-1..C-4. По отмашке владельца («C-2+C-3, свободно в другие архетипы,
  индивидуально наполнять») закрыта **волна AF** (план `af-inquiry-wave-plan-2026-08-11.md`,
  ветка `claude/goodkarma-catering-analysis-fea071`): **AF-1** (⚠️ миграция `jobs/0013`,
  аддитивная) — `Job` += event_date/guest_count/event_type; `normalize_anfrage`
  (`site_config["anfrage"]` presence-minimal: fields ⊆ date|guests|event_type +
  event_types ≤12); форма /anfrage/ — fieldset за гейтом (fail-soft дата/гости,
  тип fail-closed из списка владельца); панель «⚙️ Anfrage-Formular» на списке Aufträge
  (targeted-write) — любой архетип включает и наполняет сам; префилл `?betreff=` из
  buybox-CTA; пресеты китов restaurant/pranasy/bakery/butcher; карточка/список/письмо
  владельцу; 9 msgid × 5 .po. **AF-2** (без миграций) — общие партиалы
  `_anfrage_form`/`_message_form` (характеризационные замки ДО извлечения; `action=` →
  форма постит в штатный приёмник с любой страницы; попутно закрыта дыра «вьюха
  принимала phone, инпута не было») + ref-блоки `anfrage_ref`/`message_ref` в
  PAGE_REF_BLOCKS (гейты jobs/inbox, base «message» — НЕ «contact», коллизия с
  home-секцией) + 2 записи библиотеки блоков билдера. Замки: `test_anfrage_config`,
  `test_form_ref_blocks`, +6 витринных, panel probe-notify, dead-config китов.
  Остальные гэпы анализа (C-1 архетип Catering · C-4 полоса цифр · Tier 2 usp-pillars/
  testimonials-фото/inline-newsletter/соцссылки) — за решением владельца.
- **Самое свежее (2026-08-11, продолжение): GK-1 «архетип Catering» + GK-4 «полоса цифр» ✅**
  (отмашка «делаем C-1 и далее»; план `gk1-catering-archetype-plan-2026-08-11.md`, та же ветка).
  **GK-1** (⚠️ миграция `tenants/0028`, choices-only): BUSINESS_TYPES += catering; пресеты
  модулей (jobs primary + promotions/crm + универсальные; orders/booking выкл — Speisekarte
  browse-only); FOOD_BUSINESS_TYPES += catering; JSON-LD FoodEstablishment; Look-акценты +
  шаблон витрины + hero-плитки + карточка мастера; /branchen/catering (6 реальных фич) +
  feature_demos; демо-кит «Grüne Tafel Catering» (jobs-primary, anfrage_form AF-1, Speisekarte
  с диетами, 4 акции, 2 сметы, 27 переводов × 4 словаря); счётчики-замки обновлены осознанно
  (SLUGS 15, Looks 45, sitemap 22). **GK-4** (без миграций): C-блок `stats` — 2–4 пары
  «число+подпись» (ключ данных `rows`, НЕ items — метод dict; санитайзер ест и textarea
  «wert | label» — этим живёт live-draft, collect() += rows), рендер/редактор/демо/варианты/
  variantThumb; 15 msgid × 5 .po суммарно. Уроки среды: два pytest параллельно на одной
  reuse-db → ложные падения (гонять серийно); фоновые прогоны НЕ обрезать `| tail`.
  **Дальше: GK-5..9 Tier 2** (usp-pillars · testimonials фото/рейтинг · founder-пресет ·
  inline-newsletter · соцссылки).
- **Самое свежее (2026-08-11): SM-4 — раскрывающиеся ПОДПУНКТЫ разделов в сайдбаре
  («выпадающий список слайдером слева в меню», решения владельца по 4 развилкам) — БЕЗ
  миграций.** Принцип: подпункты якоря = advanced-состав его хабов из `nav_registry`
  (единый реестр W8 — гейты/палитра/подсветка даром); `sidebar_children` +
  `children` в `sidebar_nav` + шеврон-слайдер в `_base_dashboard.html` (активный
  раздел раскрыт с сервера; поиск меню раскрывает блоки с совпавшими подпунктами).
  Переезды: **Auswertungen+Finanzen из Настроек под «Verkäufe»** (+ Berichte
  `stays:reports` — бывший сирота, + Abläufe дубль-записью); **новый site-хаб**:
  SEO (nav "site"→"seo") · Website & Domains (из main-табов настроек) · Medien (из
  advanced) — подпункты «Website»; настройки слимятся 12→9 табов; каталожные страницы
  — компакт-бар как у Angebote (Lager/Kombi/Import → advanced); «⚙️ Abläufe» убрана
  из тулбара Verkäufe; с 5 переехавших страниц снят settings-таб-бар (site_seo рисовал
  чужой без активного таба с W9). Замки: test_sidebar_st4b +3, test_hub_tabs +2,
  осознанные переписки W9/W7b/SM-2-замков. Стенд Playwright 25/25 (hotel;
  finance/analytics у ВСЕХ демо выключены — для стенда включались временно). Грабля:
  двухстрочный `{# #}` утёк текстом на страницу (пойман скриншотом стенда; гнать
  template_comments в каждом шаблонном батче). +msgid «Berichte» ×5 .po; app.css
  пересобран. План `docs/sm4-sidebar-children-plan-2026-08-11.md`.
- **Самое свежее (2026-08-11, поздний вечер): GK-5..9 «Tier 2 витринная косметика» ✅ —
  ВСЕ гэпы goodkarma-анализа закрыты** (план `gk59-tier2-plan-2026-08-11.md`; детали —
  build-log). **GK-9** (⚠️ миграция `tenants/0029`, аддитивная): Tenant += 5 соцпрофилей
  («handle или URL», прецедент whatsapp_number) + `social_links()` → иконки-ряд в футере
  (`_social_icons.html`, инлайн mono-SVG) + `sameAs` в JSON-LD. **GK-8**: C-блок
  `newsletter` (форма всегда, данные — presence-minimal оверрайды; POST → штатный DOI
  /newsletter/; v1 уводит на /newsletter/ — PRG/next нет). **GK-7**: пресет
  «Gründer-Zitat» image_text (11-й вариант, без новых data-ключей). **GK-5**: usp_bar +=
  optional `text` + стиль `pillars` (3-part textarea «icon | label | text»; кит catering
  — «3 столпа философии»). **GK-6**: `clean_testimonials` (stars 1..5 + photo
  presence-minimal; общий _clean_pairs НЕ тронут — faq/process), 4-part textarea, фильтр
  `stars`, звёзды+аватары в 5 стилях, trust — аватар-ряд «Zufriedene Kunden»
  (фото/инициалы). app.css пересобран (-space-x-2). Голдены целы во всех пяти.
- **Самое свежее (2026-08-11, ночь): GK-11 «Google-рейтинг» + GK-13 «PDF-Speisekarte» ✅ —
  goodkarma-трек ИСЧЕРПАН ЦЕЛИКОМ (AF + GK-1..13).** **GK-11** (⚠️ миграция `tenants/0030`,
  аддитивная; план `gk11-google-rating-plan-2026-08-11.md`): Tenant += `google_place_id` +
  кэш rating/count/updated_at (ToS ≤30 дней → beat `refresh_google_ratings`, stale-фильтр
  7 дней, per-tenant try/except); сервис `apps/tenants/google_places.py` (Places API New,
  FieldMask 2 поля = Basic-SKU; ПЛАТФОРМЕННЫЙ ключ через secrets-стор/env); кабинет —
  карточка ⭐ в Integrationen + `/dashboard/settings/google-bewertungen/` («Jetzt
  aktualisieren»); витрина — честная строка «★ X,X · N Google-Bewertungen» в trust РЯДОМ
  с внутренним рейтингом; **в JSON-LD Google-рейтинг НЕ кладём** (политика Google).
  **⚠️ EXTERNAL-блокер: без `GOOGLE_PLACES_API_KEY` (Places API + billing) фича молчит.**
  **GK-13** (без миграций): `apps/catalog/pdf.py::build_menu_pdf` поверх documents-слоя
  (язык/деньги по локали, аллергены буквенными сносками + LMIV-легенда, диеты, ≤2 строки
  описания, многостраничность) + публичный `/speisekarte.pdf` (гейт FOOD-тип+активные
  товары, `?lang=`) + кнопка «📄 Speisekarte als PDF» на каталоге. Живые данные — ноль
  ручной работы владельца. 22 теста суммарно; детали — build-log.
- **Самое свежее (2026-08-12): ВОЛНА DS «дизайн-шаблоны» — DS-1..DS-4 ЦЕЛИКОМ (без миграций).**
  **DS-1/2:** первые self-hosted шрифты (Playfair 600/Nunito 800, OFL, latin+ext+cyrillic,
  лениво) + `site_defaults.page_bg` (фон страницы, html:not(.dark)) + семейства **Fein**
  (Playfair на креме) и **Natur** (Nunito на песке) — 5 семейств × 15 типов = 75 Look'ов
  (акцент-кортежи 15×5, замок «ровно 5»); пилоты catering=fein → pranasy=natur.
  **Решения владельца:** «Look = кожа · ВИД ВЫВОДА per-модуль · в мастере готовые СБОРКИ»;
  концепт-артефакт «Look Fokus» одобрен. **DS-3a:** вид «Preisliste» — товары строками
  (секция главной `SECTION_STYLES["products"]` + страничный пресет `catalog_layout`
  через НОВЫЙ `PAGE_EXTRA_PRESETS`/`normalize_layout(extra_presets)` — только каталог,
  LAYOUT_PRESETS не раздут; фасеты/поиск UB целы). **DS-3b:** `HERO_STYLES += "split"`
  (текст слева + фото справа + строка доверия ★ Google/Seit; слайдер при split не
  крутится v1) · `nav.cta` presence-minimal (CTA шапки из primary_item; мобильно —
  акцент пункта таб-бара, НЕ вторая липкая кнопка) · секция **anfrage** в SECTIONS
  (выкл дефолт, jobs-гейт, ⚠️ осознанная golden-регенерация +строка) · trust +=
  "compact" (рейтинг+2 цитаты+marks одной полосой). **DS-3c:** `BUNDLES`/`apply_bundle`
  (сборка «Fokus» для сервисных типов; идемпотентность — адверсариальный замок 15×) +
  карточки Startpaket в мастере «Stil» и области «✨ Look» билдера (action `use_bundle:`).
  **DS-4:** кит catering → Fokus-пилот (kit-generic `enable_anfrage_section`/`config_patch`;
  hero-плитки убраны — их работу несут CTA шапки + форма на главной); «Fein» остаётся в
  галерее. Проверено стендом (скриншоты = одобренный макет). Уроки: hero в SECTIONS
  выключен по умолчанию (тесты главной включают явно); новые arbitrary Tailwind-классы
  ТРЕБУЮТ пересборки app.css (невидимое hero-фото). Планы: `ds1-design-templates-plan`
  + `ds3-fokus-output-views-plan` (2026-08-12). Дальше по треку — виды вывода услуг/
  номеров/событий (прайс-с-длительностью · пакеты-колонки · полоса-разворот · афиша) —
  за отмашкой владельца; ops: `seed_demo_tenants --kit catering|pranasy --recreate`.
- **Самое свежее (2026-08-13): I18N-11 — АУДИТ ПЕРЕВОДОВ ДЕМО-ВИТРИН + доперевод (БЕЗ
  миграций; ветка `claude/demo-sites-localization-analysis-jstvo7`, отребейзена на main
  поверх MEN-волны).** Запрос владельца: «процент перевода демо на основные языки, потом
  выполнить перевод; параллельно идёт разработка — не помешать». Инструмент замера —
  **`scripts/demo_i18n_gap.py`** (раскладывает строки 15 китов на ROUTED / GAP «пути
  перевода нет» / «перевод не требуется»; иначе процент врёт в обе стороны).
  **Было** en 78 / ru 81 / uk 81 / tr 80 % (+319 строк без пути) → **стало en 96.2 /
  ru 99.9 / uk 99.8 / tr 98.1 %** (остаток — Espresso/Tiramisu/S-M-L/названия заведений:
  identity-записи запрещены замком, поэтому в словарь не пишутся). Ключевой вывод: дефект
  НЕ один, а три класса — **A** нет записи в словаре (~330 строк → ~1150 записей в 4
  словаря); **B** обход не берёт ключ (anfrage/before_after · C-блоки главной `sections`
  и страниц `page_blocks` · `Category.description` лендингов DS-7a · `siteui.page_blocks`
  читал ГОЛЫЙ normalize) — закрыто; **C** перевод есть, а шаблон печатает базовое поле
  (Combo, buy-box услуги, «похожие номера», подтверждения броней/билетов/абонементов) —
  переведены на `*_localized`. C-блоки: точечный обход `_tr_cblock_data` (только текстовые
  поля данных) + **индексы из НОРМАЛИЗОВАННОГО списка** (оверлей мерджится позиционно, а
  `normalize_sections` дописывает фикс-секции в конец — иначе перевод сядет на чужой блок).
  Виды мероприятия: тег `anfrage_event_choices` — value `<option>` остаётся немецким (ключ
  записи `Job.event_type`), переводится показ. Замки — `test_demo_i18n_pipeline.py` (6);
  стенд catering/ru: кириллица 74–85 %. **Остаток ⏸ за решением владельца — ~287 строк у
  моделей БЕЗ `*_i18n` (Event.details ретрит-лендинга, отзывы демо, Job/сметы, блог,
  лояльность, Extras/ваучеры/ComboGroup, opening_hours_text/service_area_note, Teacher/
  Resource): нужны МИГРАЦИИ, намеренно не делал — параллельная ветка.** Попутно найдено
  вне демо: **de.po** 137 английских msgid без немецкого перевода (~36 прозы UI, 32 из них
  переведены в ru/tr/uk → на немецкой витрине местами английский) и **SEO-мета**
  (`core/seo_meta.py` DEFAULTS) без gettext. Уроки: валидатор чисел должен сверять ДЕНЬГИ И
  ПРОЦЕНТЫ, а не все числа (en законно даёт «ab 17 Uhr» → «from 5 pm», tr пишет «%25»);
  локально нет gettext → до `polib`-компиляции `.mo` стенд показывает немецкий ХРОМ (ложная
  тревога). Доки: `docs/demo-i18n-audit-2026-08-13.md`. ⚠️ ops: миграций нет, но **после
  деплоя нужен `seed_demo_tenants --recreate`** — перевод накладывается при сидинге.
- **Самое свежее (2026-08-13, продолжение): I18N-12 — остаток аудита ЗАКРЫТ по решению
  владельца «делай всё» (⚠️ ДЕВЯТЬ аддитивных миграций).** `events/0023` · `booking/0022` ·
  `core/0007` · `loyalty/0005` · `catalog/0026` · `reviews/0004` · `aggregator/0018` (SHARED) ·
  `jobs/0014` · `tenants/0031` (SHARED) — только новые JSONField-оверлеи. Переводимы стали:
  ретрит-лендинг `Event.details` (+program/questions), Teacher, BlogPost, Resource (мастер/стол/
  зал), PassPlan, Extra, LoyaltyProgram, Voucher, ComboGroup, отзывы, Job/JobLine, часы работы
  и зона выезда тенанта. Для вложенного JSON появился ТРЕТИЙ слой семейства —
  `apps/core/i18n_json.py` (скаляры = `I18nMixin.get_overlay`, плоские списки = `i18n_seq`,
  вложенный JSON = `overlay_json`): база задаёт форму, переводятся только листья-строки,
  фото/ссылки — базовые, списки мерджатся ПОЗИЦИОННО → оверлей строится по нормализованной
  форме (`Event.landing`). **Инвариант волны: переводится ПОКАЗ, а не запись** — оверлей
  отзывов/заявок заполняет ТОЛЬКО демо-сидер (у живого тенанта пусто → подлинный текст гостя),
  ключ ответа анкеты остаётся базовым немецким вопросом. Перевод: 241 строка × 4 локали.
  **Итог: строк «без пути перевода» — 0** (было 319); en 96.6 / ru 99.7 / uk 99.7 / tr 98.2 %,
  остаток — Espresso/Tiramisu/S-M-L/названия заведений. Попутно закрыты обе находки вне демо:
  **de.po** — 20 английских msgid получили немецкий (на НЕМЕЦКОЙ витрине был английский:
  «Blocked», «All collections», «Check-in is not possible…»; правка точечная, 3 теста с
  английским ассертом в DE-рендере переведены), **SEO-мета** — `core/seo_meta.py` DEFAULTS
  обёрнуты в lazy (+4 msgid × 5 каталогов, плейсхолдеры сохранены), теперь `<title>`/
  `description` идут на локали посетителя. ⚠️ ops: деплой миграций + `seed_demo_tenants
  --recreate`. Доки: `docs/demo-i18n-audit-2026-08-13.md §6`.
- **Самое свежее (2026-08-04→13): архетип «мото/квадро-туры» (семейство MT) — РЕШЕНИЯ ВЛАДЕЛЬЦА
  ПРИНЯТЫ, идёт автономная разработка.** Разведка 4 агентов: ~70% в коде (Event = тиры/депозит/
  рассрочка/waiver/анкета/QR/проживание-к-билету; блог CM-1; magic-link ЛК; apps/secrets; CRM 360°;
  Leaflet). Решения (§0b плана): демо-кит на `tour_operator` (без нового business_type) · файлы
  50 МБ · шифрование файлов + proxy-выдача ДА · **тур-продукт с заездами (T6) строим сразу** ·
  EUR+оригинал валюты · «учёт времени» = хронометраж в итинерарии · **TG-мост двусторонний** ·
  чат v1 на поллинге. **Сквозная модель видимости (уточнение владельца): маршрут — IP гида,
  каждая точка/запись логистики несёт private|participants|public, дефолт private; закупочные
  цены не отдаются наружу никогда.** Волны MT-1..MT-6 — `docs/moto-tours-archetype-plan-2026-08-04.md §4`.
- Миграции: **⚠️ ЖДЁТ ДЕПЛОЯ: `catalog/0024`** (I18N-10, аддитивная — оверлеи переводов
  параметров) **+ `jobs/0013`** (AF-1, аддитивная — событийные поля заявки) **+
  `tenants/0028`** (GK-1, choices-only) **+ `tenants/0029`** (GK-9, аддитивная —
  соцпрофили) **+ `tenants/0030`** (GK-11, аддитивная — Google-рейтинг). После деплоя: `seed_demo_tenants --kit
  restaurant|pranasy|baeckerei|metzgerei --recreate` (демо-пресеты Anfrage-Formular) +
  `seed_demo_tenants --kit catering --recreate` (демо «Grüne Tafel»: pillars, 5★-отзывы,
  включает кнопку «Demo ansehen» карточки Catering). После деплоя — `seed_demo_tenants --recreate` (демо-акции/меню/переводы).
  **ПРОВЕРЕНО 2026-08-01 по `showmigrations` на проде** — очередь в этом файле была устаревшей примерно на три недели: она числила ~30 миграций «ожидающими», тогда как владелец деплоил регулярно. Фактическое состояние прод-схемы: `catalog` [X] по `0022`, `stays` [X] по `0030`, `booking` [X] по `0020`, `inventory` [X] по `0004`, `tenants` [X] по `0027` — то есть применено ВСЁ, включая миграции, смерженные 2026-08-01. Прежние записи «последний полный деплой 08.07» + «деплой очереди сделан владельцем (19.07)» были верны; неверен был список ожидающих. **Не подтверждено этой проверкой** (не входили в запрос, все TENANT-апп): `core/0006` (data-миграция backfill_owner_membership), `promotions/0024`, `orders/0015`/`0016`, `crm/0002`, `promotions/0022`/`0023`, `collections/0002`, `finance/0006`, `jobs/0012`. **Нюанс django-tenants:** `manage.py showmigrations` без tenant-контекста читает `django_migrations` схемы **public**; у TENANT-апп (catalog/stays/booking/inventory/promotions/…) своя таблица в КАЖДОЙ схеме тенанта, поэтому строгая проверка — по схемам (`migrate_schemas` в `deploy.sh` их и гоняет). Команда полной сверки — в build-log записи 2026-08-01 «аудит месяца». **Правило впредь:** очередь в этом файле — гипотеза до сверки с `showmigrations`; не помечать миграции «ожидающими» дольше одного деплой-цикла.

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

## 7. Дальше — ⚠️ РАЗДЕЛ-АРХИВ (порядок от 2026-07-01, разобран)

> **Сверено 2026-08-06.** Волны, перечисленные ниже (L, U-A…U-E, E-7, M20, спринты A–G),
> **закрыты** — статус см. §3, хронологию — `docs/build-log.md`. Раздел оставлен ради
> ссылок на планы и рыночную аналитику; **как очередь работ он больше не действует**.
> Актуальная очередь живёт в `docs/task-catalog.md` и в последних записях §3; открытый
> бэклог — только owner-gated (Pro-тариф D1, массовый de.po T-1, per-page ДАННЫЕ секций —
> вариант B UC2-3) и external-gated (Stripe live, OTA-API, Shopify/Woo, Ads, Push/Wallet —
> `docs/external-integrations-backlog.md`).

**🔍 АУДИТ 2026-07-01 (план↔факт + рынок A1–A9 + security) — `docs/audit-2026-07-01.md`.** Пробелы
вплетены в ТЗ: **master-track §7** («что недостаёт» по очереди волн 0→4), `…-ua-plan §7` (остаток U-A:
`_buybox`/UA3-2/AutoRepair/демо-A9/reviews-email не сделаны — «U-A закрыта» неточна), `…-L-plan §10`
(остаток L3-ввод+демо/L4/L5), pointer'ы в ub/uc/ud-планах. Приоритет №1 после багфиксов — **E-7
платёжный микс DACH** (6 архетипов, вне волн). ~~Security: 2× HIGH XSS в карте агрегатора~~ —
**закрыто** (сверено 2026-08-06: `_map.html` строит попап через DOM с проверкой схемы href,
данные идут через `json_script`; см. комментарий в шаблоне).

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

**Языковой модуль — ⚠️ ЗАПИСЬ НИЖЕ УСТАРЕЛА (сверено с кодом 2026-08-06), оставлена
как история.** Фактическое состояние: волна L закрыта (L1–L5), хром переведён на 5
языков (`CABINET_LANGUAGES` de/en/tr/ru/uk, ~4080 msgid в каждом каталоге, .mo
компилируются в образ), кабинет «Sprachen» есть, письма локализованы (L4), правовое —
через `LegalDoc` (L5), демо переводятся словарями `demo_i18n_<loc>.json`, регресс ловит
`scripts/i18n_gap.py` в CI. Из исходной записи верна только заметка про публичный домен.
<details><summary>Историческая запись от 2026-06-30</summary>
фундамент НА ВИТРИНЕ тенанта уже есть — переключатель DE/EN (`set_language`+
`storefront-set-language`+`_base.html`), оверлей `siteconfig.localize`, модельная i18n
`{de,en}`, поля `Tenant.default_locale/enabled_locales`. НЕ работает: `enabled_locales`/
`default_locale` не читаются в рантайме; `.po/.mo` пусты; хром/письма/правовое — DE-only;
EN-контент только у `pranasy`; нет кабинетного UI языков; на ПУБЛИЧНОМ домене
переключателя нет. План достройки — L1…L6 (§6.4 дока).
</details>

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
