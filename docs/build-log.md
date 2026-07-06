# Build-log — siteadaptor-platform

Хронология завершённых задач. Извлечено из `CLAUDE.md §3` (2026-06-22) для
облегчения памяти проекта. **Source of truth по сделанному.** Краткий верхнеуровневый
статус и «дальше» — в `CLAUDE.md`. Срез/оценка — `docs/audit-2026-06-22.md`.

**Конвенция:** завершая инкремент, дописываем строку СЮДА (а не раздуваем CLAUDE.md §3).

---

## Сделано (хронология)

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
- **Track B — DE quick wins (в работе):**
  - B1 GBP-адаптер (✅ в `main`, 3030af0): тип канала google_business, адаптер
    Google Posts (publish/remove, OAuth refresh-token из config), конфиг в
    кабинете; настройка — `docs/gbp-setup.md`. Боевое — после Google API-доступа.
  - B2 «Überraschungstüte»/анти-waste (✅ в `main`, 9edc310): `Promotion.is_surprise`
    (миграция 0009) + бейдж на витрине и в агрегаторе (`AggregatorListing.is_surprise`,
    aggregator/0002). Поверх обычной брони, отдельной механики нет. Нужен деплой.
  - B3 Recurring + пресеты по вертикалям (✅ в `main`, b052fef): B3a
    `apps/promotions/presets.py` (`?preset=<key>` пред-заполняет форму по
    business_type, кнопки быстрого старта); B3b `Promotion.recurrence`
    (—/daily/weekly, миграция 0010) + beat `roll_recurring_promotions` (раз в час)
    — завершившаяся повторяющаяся акция даёт один scheduled-наследник со сдвигом
    окна, recurrence уходит к наследнику (цепочка не ветвится). Нужен деплой.
  - B4 QR-постер PDF (✅ в `main`, f9d38f1):
    `apps/promotions/poster.py` (`build_shop_poster_pdf` — segno QR→PNG + reportlab
    A4), вьюха `shop_poster_pdf` + `/promotions/poster/`, кнопка на странице акций;
    QR несёт `?ch=schaufenster` (атрибуция). Новая зависимость `reportlab`.
  - B5 Local SEO (✅ в `main`, 6cf697a+2187527): `apps/core/seo.py`
    (localbusiness_ld/offer_ld/itemlist_ld); LocalBusiness в `<head>` витрины
    (тег `{% localbusiness_jsonld %}`) + Offer на акции + ItemList на странице
    города; `sitemap.xml`/`robots.txt` для витрины (субдомен) и агрегатора
    (основной домен) без django.contrib.sites (домен из request).
  - Track B завершён (B1–B5), ВЕСЬ в `main` (e5fa29a, CI зелёный). Нужен деплой
    (миграции promotions 0009/0010, aggregator 0002 + зависимость reportlab).
- **Phase 2 — P2.1 мульти-доменные порталы (в работе):** подход согласован
  (2026-06-10): поддомены `*.siteadaptor.de`, kind city/vertical/combo, фильтры
  city+business_type через сем `listings_for`; custom-домены позже через
  verify-domain. Детали — roadmap §P2.1.
  - P2.1a (✅ в `main`, 2d28be2): модель `AggregatorPortal` (SHARED, миграция
    aggregator/0003) + `AggregatorPortalMiddleware` (host→`request.portal` на
    public-схеме, Redis-кэш карты хостов + сигнал-сброс) + тесты.
  - P2.1b (✅ в `main`, 4d09b76+c9f79b2): middleware подменяет `request.urlconf`
    → `config/urls_portal.py` (portal-home `/`, уточнение `/<facet>/` по
    свободной оси: city-портал → тип, vertical → город, combo — без; health-пробы,
    media-фолбэк); `portal_views.portal_home` (сем `listings_for`, курсорная
    пагинация, мусорный facet → 404); брендированный `portal_base.html`
    (title/tagline/intro/logo/primary_color) + `portal_home.html`; карточки
    листингов в общем `_cards.html`. Без миграций. Смотреть пока не на что:
    нужен AggregatorPortal + строка Domain(host→public) — провижининг в P2.1d.
  - P2.1c (✅ в `main`, 18c1c09+5e27113): SEO портала — canonical на хост
    портала, meta description (tagline→intro→title), JSON-LD CollectionPage с
    ItemList (`apps/core/seo.py::collectionpage_ld`), `sitemap.xml`/`robots.txt`
    по хосту портала (корень + страницы свободной оси; домен из request).
  - P2.1d (✅ в `main`, 223de16+c5f6e8c): unfold-админка `AggregatorPortal`
    (admin на public) + команда `create_portal` (валидация kind/фильтров,
    атомарно портал + `Domain(host→public)`; чужой домен → отказ) +
    `docs/portal-setup.md` (DNS/Caddy/custom-домены) + тесты команды.
  - **P2.1 завершён (a–d), весь в `main`, без новых миграций после
    aggregator/0003.** Нужен деплой; после него портал заводится одной
    командой `create_portal` (см. docs/portal-setup.md).
  - Дальше по плану Phase 2: P2.2 SEO/контент порталов → P2.3 клиентские
    аккаунты → P2.4 монетизация (порядок — roadmap).
- **Hardening, код-часть (✅ в `main`, 8c43a43+549bc9c+b6b84a4+be36f06,
  CI runs 52/54/55 зелёные, без миграций):**
  - H8 rate-limit: `apps/core/ratelimit.py` (атомарный Redis INCR, fail-open) —
    бронь/waitlist 5/10мин на IP+акцию, QR-вьюхи кодов 60/10мин на IP → 429.
  - H6 нагрузочный: `scripts/load/anti_oversell.js` (k6) + `scripts/load/README.md`
    (прогон на железе — на владельце) + кейс конкурентности с остатком 7.
  - H7 DSGVO: команда `dsgvo_customer --schema --email [--delete]` (экспорт
    Art. 15/20 / стирание Art. 17) + `docs/dsgvo-review.md` (орг-пункты — AVV
    и пр. — на владельце).
- **Фиксы/мелкое (✅ в `main`):** ресинк листинга агрегатора при правке активной
  акции (aa9db2c — фото/цены подтягиваются без смены статуса; post_save-сигнал).
- **Self-service custom-доменов (✅ в `main`, b9c321c+d338441, CI run 62
  зелёный, миграция tenants/0005):** `/dashboard/domains/` — владелец добавляет
  домен → ставит A-запись на наш IP → «Проверить»; владение = A-запись указывает
  на `CUSTOM_DOMAIN_TARGET_IP` (нужно прописать в `.env.prod`, см.
  `.env.prod.example`), тогда создаётся `Domain(домен→тенант)` и Caddy выпускает
  сертификат. Модель `CustomDomain` (заявка pending/active/failed) отдельно от
  `Domain` — чужой домен занять нельзя. Логика — `apps/tenants/domains.py`.
  Canonical-политика (какой хост главный для SEO) — отложено (roadmap §Отложено).
- **P2.2 — SEO/контент порталов (✅ в `main`, a573b35+75ba11d, CI runs 64/65
  зелёные, без миграций):**
  - P2.2a: OpenGraph/Twitter-теги на порталах (логотип как og:image) и
    страницах агрегатора; canonical на городских страницах; перелинковка сети:
    городская страница → портал города + соседние города, портал → остальные
    активные порталы. hreflang сознательно не делаем (язык в cookie, не в URL).
  - P2.2b: кэш публичной выдачи `apps/core/pagecache.py` (HTML в Redis, GET
    без query, ключ host+path+язык, `PUBLIC_PAGE_CACHE_TTL` default 120с,
    в тестах 0) — на portal_home / city_listing / discover_index.
- **P2.3 — клиентские аккаунты (в работе, разбивка a–d согласована):**
  - P2.3a (✅ в `main`, 5730386, CI run 68 зелёный, миграция aggregator/0004):
    `PortalUser` (public, отдельно от auth.User) + magic-link вход по
    `docs/references/patterns/magic-link-auth.md` (Redis-токен SHA-256/15мин/
    одноразовый, анти-энумерация, honeypot, лимиты email 3/час + IP 5/10мин);
    `/konto/` на порталах (login/verify/logout, страница-задел), письмо —
    Celery `send_magic_link_email`, контекст-процессор `portal_user` + шапка.
  - P2.3b (✅ в `main`, 6ac2af0+279b417, CI run 71 зелёный, миграция
    aggregator/0005): избранное `FavoriteListing` — сердечки на карточках
    выдачи (только вошедшим; pagecache пропускает непустые сессии мимо кэша),
    toggle `/konto/favoriten/`, раздел в `/konto/`.
  - P2.3c (✅ в `main`, 2d97db7, CI run 72 зелёный, без миграций): история
    броней в `/konto/` по всем бизнесам — кросс-схемный сбор по email-связке
    (`account_services.reservations_for_email`, кэш 60с); бронь по-прежнему
    без аккаунта.
  - P2.3d (✅ в `main`, f61b35e, CI run 89 зелёный, миграция aggregator/0006):
    настройки уведомлений в `/konto/` — `PortalUser.marketing_opt_out`
    («Отписаться от всех / Подписаться снова») + Celery-синк
    `apply_marketing_opt_out` в per-tenant `Customer.unsubscribed`;
    транзакционные письма (бронь) не затрагиваются.
  - **P2.3 завершён (a–d), весь в `main`.**
- **P2.4 — монетизация портала (в работе, разбивка с учётом Track D):**
  - P2.4a (✅ в `main`, c6ad8f9+2befa88, CI run 94 зелёный, миграция
    aggregator/0007): featured-листинги — `AggregatorListing.featured_until`,
    закрепление сверху первой страницы выдачи (портал + /entdecken) с бейджем
    «★ Empfohlen», без дублей в keyset-ленте; админка листингов → продажа
    продвижения вручную уже возможна; sync срок не трогает.
  - **P2.4b — самообслуживание featured-продвижения через Stripe (✅ ветка
    `claude/hopeful-sagan-mo0ttp`, aa1a58e, CI run 134; без миграций):** владелец
    активной акции из кабинета покупает закрепление листинга наверху агрегатора/
    порталов разовым Stripe-Checkout (`mode="payment"`, inline `price_data` — без
    Price в дашборде). `apps/billing/featured.py` — планы 7/14/30 дн. (9/15/25 €,
    решение владельца), env-оверрайд `BILLING_FEATURED_PRICES`; services
    `create_featured_checkout_session` + `apply_featured_purchase` (продление
    `AggregatorListing.featured_until` от `max(now, текущий)`); вебхук различает
    разовый платёж по `metadata.kind=="featured"` (подписочный путь не затронут,
    идемпотентность — дедуп по event.id). Кабинет: `/promotions/<pk>/feature/`
    (планы/статус) + карточка «Bewerben/Verlängern» на активной акции. Гранулярность
    — на одну акцию (её листинг). Настройка — `docs/billing-stripe-setup.md §4`.
  - Известное ограничение (roadmap «Отложено»): featured живёт на строке листинга
    — завершение акции раньше срока удаляет листинг и оплаченное продвижение.
  - Дальше по плану: P2.5 (платежи конечного клиента) — порядок по roadmap.
- **Track C — витрина сайта, конструктор v1, CRM-минимум (решение владельца
  2026-06-11, разбивка — roadmap §Track C; чат покупатель↔бизнес — в Отложено):**
  - C1 (✅ в `main`, be17d17+d2ece12, CI run 77 зелёный, без миграций): витрина
    товаров — `/sortiment/` (чипы категорий, курсорная пагинация) + страница
    товара (цена/описание/контакты, related) + секция и навигация на главной +
    товары в sitemap. Без корзины: покупка офлайн.
  - C2 (✅ в `main`, ffe4628+c84a0b3, CI run 81 зелёный, миграция tenants/0006):
    конструктор витрины v1 — главная из секций (hero/акции/товары/о нас/
    контакты+часы) по `Tenant.site_config` (`apps/tenants/siteconfig.py`,
    normalize переживает расширение схемы); кабинет `/dashboard/site/`
    (порядок числом + чекбоксы + тексты hero/about), пункт меню «Site»;
    шаблоны секций — `templates/storefront/sections/`.
  - C3 (✅ в `main`, 2d8f4ae, CI run 84 зелёный, миграции crm/0001 +
    promotions/0011): CRM-минимум «Клиенты» — `apps/crm` (TENANT): кабинет
    `/crm/` (список с поиском вкл. по тегу, карточка: контакты/теги/заметки
    CustomerNote, брони readonly), ручное добавление клиента без брони;
    `Customer.tags`; tags/crm_notes — в DSGVO-экспорте/стирании.
  - **Track C завершён (C1–C3), весь в `main`.** Нужен деплой (миграции
    tenants/0006, promotions/0011, crm/0001). Дальше — возврат к плану: P2.3d.
- **Track D — Business OS (в работе; ТЗ — ветка claude/peaceful-cerf-bgifg8,
  код по решению владельца 2026-06-12 пишет эта сессия):**
  - D0a (✅ в `main`, 008a3f7, CI run 96 зелёный, миграция tenants/0007):
    реестр модулей кабинета `apps/core/modules.py` (ModuleSpec: nav_items,
    url_prefixes, depends_on, recommended_for, core/premium; core: dashboard/
    catalog+imports/settings/billing) + `Tenant.disabled_modules` (выбор
    владельца; формула «Активно = (entitlement ∩ реестр) − disabled», core —
    всегда; loyalty/analytics зависят от promotions); навигация кабинета из
    реестра (CP `apps.core.context.modules_nav`, `_base_dashboard.html` —
    цикл вместо 16 хардкод-ссылок); `ModuleGatingMiddleware` — путь
    неактивного модуля → 404, матчинг по самому длинному префиксу.
    Отступление от ТЗ: entitlement (`enabled_modules`) применяется только к
    premium-модулям (пока таких нет) — иначе строгое пересечение выключило бы
    loyalty/analytics/crm у существующих тенантов.
  - D0b (✅ в `main`, 8dd12f0, CI run 98 зелёный, без миграций): дефолты
    модулей по вертикали — `modules.default_disabled_for(business_type)`
    (опциональные − recommended_for; bakery/butcher/grocery/cafe/restaurant →
    promotions+loyalty, retail/clothing/other → promotions, hotel/tour_operator
    → crm), `create_business` инициализирует `disabled_modules` (существующие
    тенанты не затронуты: [] = всё включено); страница `/dashboard/modules/`
    («Modules» в settings-модуле) — тумблеры опциональных блоков с
    `description_de`, бейджи Recommended/inactive, подсказка зависимостей,
    core задизейблены; read-only при gated — существующий SubscriptionGating.
  - D0c (✅ в `main`, 4a177b4, CI run 100 зелёный, без миграций):
    Onboarding-Wizard `/dashboard/setup/` — 5 шагов (тип бизнеса → предвыбор
    блоков; тумблеры модулей; basics адрес/часы/контакты; первый контент через
    пресеты `?preset=` B3a + «Produkt anlegen»; Geschafft), каждый шаг
    пропускаем, резюмируется; состояние — `Tenant.site_config["onboarding"]`
    (`apps/tenants/onboarding.py`; siteconfig.normalize и site_view ключ
    сохраняют); плашка «Setup-Fortschritt N/5» на дашборде до завершения.
  - **D0 завершён (a–c), весь в `main`** (миграция только tenants/0007 из D0a).
  - **D1 CRM-lite (✅ в `main`, b27c1d1+c57e5c4, CI runs 102/103 зелёные,
    миграция promotions/0012):** дельта поверх Track C3 (список/карточка/
    заметки/теги уже были): `Customer.marketing_opt_in` (UWG §7, чекбокс в
    форме, DSGVO-экспорт, стирание отзывает согласие) + `created_source`
    (reservation/manual/import/order; ручное создание → manual); карточка 360°
    — блок карт лояльности; `/crm/export.csv` (фильтр ?q= общий со списком).
    Ваучеры в 360° отложены: Voucher не связан с клиентом (standalone-коды).
  - **D2a — Click&Collect, витрина (✅ в `main`, 714140c+55121af+c4b0258,
    CI run 107 зелёный, миграции orders/0001 + promotions/0013):** apps.orders
    (TENANT): Order (UUID-pk, customer PROTECT, код O-XXXXXX, payment_state
    вручную, total/снимки в OrderItem) + OrderSM (new→confirmed→ready→
    picked_up, +cancelled); витрина — кнопка на странице товара (при активном
    модуле) → корзина-сессия `/warenkorb/` → checkout (honeypot+rate-limit) →
    `/bestellung/<code>/`; Customer reuse по email, новый → created_source=
    order; модуль «orders» в реестре (recommended: bakery/butcher/grocery/
    retail/clothing). Решения ТЗ: v1 без stock и без онлайн-оплаты.
  - D2b — кабинет заказов (✅ в `main`, 86aefce, CI run 110 зелёный, без
    миграций): `/dashboard/orders/` (nav «Orders» из реестра) — список с
    фильтром по статусу, карточка (позиции/итог/клиент), действия Confirm/
    Ready/Picked up/Cancel (кнопки из `allowed_targets`) + «Mark as paid»;
    письма клиенту на created и каждый переход (`OrderSM.on_transition` →
    `enqueue_order_email`, дедуп `order:{id}:{event}:{role}`), владельцу — на
    новый заказ; DE-шаблоны `emails/order_*.txt`; блок «Orders» в 360° CRM.
  - **D2 завершён (a–b), весь в `main`** (миграции orders/0001 +
    promotions/0013 из D2a).
  - D3a — Booking, ядро (✅ в `main`, 6e50811+76555c7, CI run 114 зелёный,
    миграция booking/0001): apps.booking (TENANT) — Resource (тип, capacity =
    параллельные записи), AvailabilityRule (недельные окна + шаг слота),
    ClosedDate, Booking (интервал, party_size, код T-XXXXXX, reminder_sent_at
    под beat D3c); services.book — anti-double-book (select_for_update на
    ресурсе + пересечения [start,end) < capacity), отмена освобождает слот;
    BookingSM (pending→confirmed→fulfilled, cancelled, no_show); модуль
    «booking» в реестре (recommended: cafe/restaurant/hotel/tour_operator).
    Урок run 112: тесты дефолтов сверять с default_disabled_for, не хардкодом.
  - D3b — публичная запись /termin/ (✅ в `main`, 7badd30, CI run 117 зелёный,
    без миграций): availability.free_slots (сетка правил − ClosedDate −
    занятость − прошедшее), флоу без JS: ресурс → день (±, горизонт 30 дн.) →
    слот (?slot= раскрывает форму) → POST buchen (honeypot+rate-limit, слот
    валидируется по сетке, гонку закрывает services.book) → /t/<code>/;
    ссылка «Book» в шапке витрины при активном модуле (флаг в CP modules_nav).
  - D3c — кабинет-календарь + письма/напоминания (✅ в `main`, e57bf8f, CI run
    119 зелёный, без миграций): `/dashboard/booking/` (nav «Booking») —
    календарь-день, Confirm/Arrived/No-show/Cancel, перенос (services.move,
    anti-double-book без себя), ручная запись (сразу confirmed);
    `/dashboard/booking/ressourcen/` — ресурсы/недельные правила/выходные;
    письма клиенту (created/confirmed/cancelled через BookingSM) и владельцу
    (новая заявка), напоминание за `BOOKING_REMINDER_HOURS` (default 24) —
    beat `send_booking_reminders` раз в час, одно на запись.
  - **D3 завершён (a–c), весь в `main`** (миграция только booking/0001 из D3a).
  - Hotfix после деплоя D0–D3 (✅ в `main`, 11560f5+7ca5b83, CI run 122
    зелёный, без миграций): мастер не сбрасывает модули настроенных/легаси
    тенантов (пресет — только если текущий набор == пресету прежнего типа);
    кнопка «Zurück» на шагах 2–5 (`onboarding.back`); gunicorn timeout 60→180
    (создание схемы нового бизнеса ~1 мин и растёт). Решения владельца
    (2026-06-12): модули — ГИБРИД (пресет по типу + у каждого модуля список
    подходящих типов + предупреждение при включении неподходящего);
    фоновая регистрация — делать СЕЙЧАС, до D4.
  - Гибрид модули↔тип (✅ в `main`, 0dc51e6, CI run 124 зелёный, без
    миграций): `ModuleSpec.suited_for` (кому подходит сверх пресета; пусто+
    пусто = универсальный), `is_suited_for`/`suited_label` («Geeignet für: …»),
    секции «Weitere Bausteine» с ⚠ на /dashboard/modules/ и шаге 2 мастера,
    warning при включении неподходящего (не запрет); смена типа на шаге 1
    заново применяет пресет вертикали, тот же тип — конфигурацию не трогает.
  - Фоновая регистрация (✅ в `main`, 779c09a, CI run 126 зелёный, миграция
    tenants/0008): `Tenant.provisioning_status`; регистрация отвечает мгновенно
    → `/anmeldung/<slug>/` (спиннер, meta-refresh 4с) → Celery
    `provision_business` (схема + владелец, пароль хэшем в брокер) → редирект
    на логин + письмо «Ihre Website ist bereit». Email-бэкенд: Resend → свой
    SMTP (EMAIL_HOST/USER/PASSWORD, напр. Hostinger-ящик) → console.
    `create_business` (синхронный) остался для тестов/CLI.
  - **D4a — журнал выручки (✅ в `main`, 65bc660, CI run 128 зелёный,
    миграция finance/0001):** apps.finance (TENANT): RevenueEntry (source
    order/reservation/manual + source_ref — уникальность пары = идемпотентность
    хуков; amount брутто, vat_rate 19/7/0, date, customer SET_NULL, note);
    record_revenue (повтор хука = no-op, amount<=0 не пишем); хуки OrderSM
    picked_up → order.total и ReservationSM fulfilled → new_price×quantity
    (без цены — записи нет); кабинет `/dashboard/finance/` — журнал за период
    (von/bis, default месяц), итог + разбивка по НДС, ручное добавление.
    Модуль «finance» в реестре: универсальный, по умолчанию выключен.
  - D4b — Rechnung + PDF (✅ в `main`, da8123d, миграции finance/0002 +
    tenants/0009): Invoice (снимок позиций/получателя §14 UStG, net/vat/gross,
    InvoiceSM draft→issued→paid + Storno с сохранением номера), InvoiceCounter
    — номер только при issue под select_for_update (черновики без номера →
    нумерация без дыр, GoBD), issued иммутабелен; PDF (reportlab, водяной
    знак STORNIERT); Tenant.small_business (§19, НДС 0 + Hinweis) +
    tax_number в Settings; кабинет /dashboard/finance/rechnungen/.
  - D4c — экспорт (✅ в `main`, b6f352d+dae0acf, CI run 132 зелёный, без
    миграций): кнопки CSV (utf-8-sig) и DATEV в журнале — упрощённый
    Buchungsstapel (`;`, десятичная запятая, Belegdatum TTMM, cp1252,
    SKR03: Kasse 1000 → 8400/8300/8195 по ставке), период общий с журналом.
  - **D4 завершён (a–c) → ВЕСЬ Track D (D0–D4) закрыт, всё в `main`.**
    Деплой: миграции tenants/0008+0009, finance/0001+0002 (+ всё с прошлого
    деплоя). Дальше по плану: ✅ P2.4b (featured-оплата Stripe, см. §P2.4) → P2.5.
- **Карта микробизнес-вертикалей (✅ в `main`, 2026-06-13):**
  `docs/micro-business-verticals.md` — ~40 типов микробизнесов DACH по 3 «движкам»
  (retail/каталог · booking по времени · booking по датам), потребности каждого до
  «логической полноты» + сквозной бэклог G1–G9. Source of truth по вертикалям.
- **Retail-пакет R4 — LMIV (✅ в `main`, 60f703f, CI run 141):** маркировка товара —
  `Product.allergens` (14 EU, `apps/catalog/food.py`) + `origin` + `ingredients`
  (миграция catalog/0002), форма + вывод на витрине только при заполнении. Остаток
  retail по порядку: R1 варианты → R2 Grundpreis/весовая цена (PAngV) → R3 остаток
  с atomic-списанием.
- **P2.5 Онлайн-оплата — старт (✅ в `main`, 51b0c74, CI run 144, миграция
  tenants/0010):** Stripe Connect, аккаунты **Standard** (онбординг OAuth) — клиент
  платит бизнесу напрямую. `apps/billing/connect.py`: OAuth (authorize/complete),
  `set_connect_status` (вебхук `account.updated` → `Tenant.payments_enabled`),
  application fee **по типу бизнеса** (`BILLING_APPLICATION_FEE_PERCENT`, сейчас 0);
  кабинет `/dashboard/billing/payments/`. **Монетизация = вариант B** (решение
  2026-06-13): комиссию выставляем продавцу строкой «Nutzungsgebühr» в счёте за
  систему, в платеже клиента НЕ удерживаем (application_fee=0; A — хук на будущее;
  option 3 «платформа собирает + payout» — резерв под маркетплейс). Инфра:
  `STRIPE_CONNECT_CLIENT_ID` + Connect в Stripe (`docs/billing-stripe-setup.md §5`;
  caveat redirect-URI субдоменов — roadmap §Отложено).
- **P2.5b — депозит за бронь/термин (✅ в `main`, 08853d9+64cc3dc, CI run 149,
  миграция booking/0002):** anti-no-show. `Resource.deposit_cents` +
  `require_manual_confirm`; `Booking.deposit_cents/payment_state/
  stripe_payment_intent`. `connect.connected_checkout_session` (Checkout на
  connected account бизнеса; application_fee только при ненулевом % — вариант B
  даёт 0) + `connect.refund`; `booking.payments.mark_deposit_paid` (вебхук
  `checkout.session.completed kind=booking_deposit`, кросс-схемно: paid +
  авто-confirm, либо pending при `require_manual_confirm`). Витрина `/termin/`:
  депозит → Stripe Checkout, иначе обычная бронь; кабинет: настройка депозита/
  флага у ресурса, бейдж оплаты, **отмена оплаченной → refund (анти-фрод)**.
- **P2.5c — предоплата Click&Collect (✅ в `main`, e2d9541, CI run 153, миграции
  tenants/0011 + orders/0002):** опциональная онлайн-предоплата C&C. `Tenant.
  orders_prepay` (тумблер в кабинете заказов); `Order.stripe_payment_intent` +
  payment_state «refunded». `orders.payments`: `order_checkout_url` (Checkout на
  connected account, вариант B → application_fee=0) + `mark_order_paid` (вебхук
  `kind=order_payment`, кросс-схемно: paid + new→confirmed). Витрина: при
  orders_prepay+payments_enabled оформление → Stripe Checkout, иначе оплата при
  получении; статус на `/bestellung/<code>/`. Кабинет: бейджи paid/refunded,
  **отмена оплаченного → refund**.
- **P2.5-fee — Nutzungsgebühr строкой в счёт (✅ в `main`, 56a4744, CI run 157,
  миграция billing/0001):** помесячная плата за пользование (вариант B). Оборот
  через платформу (`finance.RevenueEntry` source order+reservation) × % по типу
  бизнеса → `services.create_usage_invoice_item` (Stripe InvoiceItem в счёт
  подписки). `billing.usage` (period_bounds/previous_period/tenant_gmv_cents
  кросс-схемно/bill_tenant идемпотентно), `billing.UsageFeeRecord` (запись на
  tenant+период = идемпотентность beat'а + аудит), beat `bill_usage_fees` (раз в
  сутки, прошлый месяц, активные тенанты). **Сейчас % = 0 → не начисляется**;
  включается через `BILLING_APPLICATION_FEE_PERCENT`. **Весь P2.5 (a/b/c/fee)
  закрыт.** Дальше: retail R1 варианты → R2 Grundpreis/весовая цена → R3 остаток.
- **Retail R1 — варианты товара (✅ в `main`, 1feb5db+c03d98e, CI run 162,
  миграции catalog/0003 + orders/0003):** `ProductVariant` (FK Product, `label`
  «100 g»/«M», цена-оверрайд пусто→base_price, `stock_quantity` под R3, `sku`,
  уникальность product+label); `Product.has_variants`/`price_from`. Кабинет — CRUD
  вариантов на странице товара. Витрина — селектор + цена «ab X €». Корзина C&C
  variant-aware (ключ `pid:vid`), `OrderItem.variant`+`variant_label` снимок,
  `create_order` принимает (product,variant,qty) и (product,qty) (обратная совм.).
  Дальше: R2 Grundpreis/весовая цена (PAngV) → R3 остаток с atomic-списанием.
- **Retail R2 — Grundpreis/весовая цена, PAngV (✅ в `main`, 7b6798d, CI run 166,
  миграция catalog/0004):** цена за базовую единицу (€/kg|l) рядом с ценой —
  закон для еды/фасовки. `Product.unit` (—/g/kg/ml/l) + `content_amount`;
  `ProductVariant.content_amount` (своя или товара). `apps/catalog/pricing.py::
  grundpreis(price,unit,content)` → (value,'kg'|'l')|None (g→/kg, ml→/l; Stück/
  пусто/0 → None); `Product.grundpreis`/`Variant.grundpreis`. Кабинет: unit+content
  в форме товара и у вариантов. Витрина: Grundpreis под ценой и в опциях вариантов,
  на карточке. Дальше: R3 остаток с atomic-списанием.
- **Retail R3 — остаток с atomic-списанием (✅ в `main`, 4c5ea8c, CI run 170, без
  миграций):** anti-oversell для Click&Collect. `services._reserve_stock` —
  атомарное списание под `select_for_update` при создании заказа (нехватка →
  `OutOfStock` → откат, заказа нет); `null` = без учёта; учитывает вариант или
  товар. `OrderSM` cancelled → возврат остатка (`F()`, только по позициям с
  учётом). `Product/Variant.in_stock`; витрина — «Nur noch X»/«ausverkauft», блок
  кнопки, disabled-опции распроданных вариантов, бейдж на карточке. **Весь
  retail-пакет R1–R4 закрыт.** Дальше (вне retail): date-range booking
  (отели/ретриты), отзывы+гео (агрегатор).
- **Track E — date-range booking / Übernachtung (G5, ✅ ВЕСЬ в `main`):** движок
  «по ночам» для размещения (отели/ретриты/Ferienwohnung) — параллель `apps.booking`
  (по времени суток). Разбивка E1–E4, каждая ветка → CI зелёный → FF в `main`:
  - E1 ядро (✅ `33f9b18`, CI run 174, миграции stays/0001 + tenants/0012):
    `apps.stays` (TENANT) — `StayUnit` (тип/`quantity` идентичных юнитов/цена-ночь
    `price_cents`/`min_nights`/`max_guests`/депозит) + `UnitBlock` (блок дат, ночи
    включительно) + `StayBooking` (`arrival`/`departure` DateField, код S-XXXXXX,
    снимок цены, payment-поля); `services.book_stay` — atomic anti-overbook
    (`select_for_update` на юните + пер-ночная занятость `range_available` <
    quantity; день выезда свободен) + `move_stay`; `StayBookingSM`
    (pending→confirmed→fulfilled, cancel, no_show). tenants/0012 — opt-out
    существующих не-hotel тенантов из модуля (лёгкий старт). `apps.stays` в
    TENANT_APPS.
  - E2 кабинет (✅ `508a471`, CI run 176, без миграций): модуль «stays» в реестре
    (`recommended_for=hotel`, `suited_for=tour_operator/other`, nav «Stays»,
    `/dashboard/stays/`); `/dashboard/stays/` — Belegungskalender (юниты × ночи,
    свободно/занято/блок, `availability.occupancy_grid`) + список броней окна +
    действия по FSM (confirm/checked-out/no_show/cancel) + перенос дат + ручная
    бронь (auto-confirm); `/dashboard/stays/units/` — CRUD юнитов + блокировки дат.
    Обновлены хардкод-наборы дефолтов в test_modules (добавлен stays).
  - E3 витрина + письма + finance (✅ `0e8f996`+фикс `c774afc`, CI run 180,
    миграция finance/0003): публичная `/unterkunft/` (список → юнит: GET-форма дат
    → цена/доступность → POST buchen honeypot+rate-limit → `/s/<code>/`), гейтинг
    модуля → 404; `StayBookingSM.on_transition`: confirmed/cancelled → письмо
    клиенту (Notification dedupe), fulfilled (выезд) → выручка в `finance`
    (**НДС 7 % Beherbergung**, идемпотентно); `apps/stays/notifications.py` +
    DE-шаблоны `emails/stay_*`; beat `send_stay_reminders` (раз в сутки,
    `STAY_REMINDER_DAYS` default 1, одно на бронь); finance source «stay»; ссылка
    «Übernachten» в шапке витрины. **Урок:** floatformat рендерит цену в локали de
    («270,00»), тесты витрины проверяют стабильный URL формы, не число.
  - E4 онлайн-депозит (✅ `d3d6671`, CI run 180 зелёный, без миграций): зеркало
    P2.5b — `payments.stay_deposit_checkout_url` (Checkout на connected account,
    metadata `kind=stay_deposit`, вариант B → application_fee=0) +
    `mark_stay_paid` (вебхук кросс-схемно: paid + авто-confirm или pending при
    `require_manual_confirm`); ветка вебхука в `apps/billing/webhooks.py`; витрина
    при депозите+`payments_enabled`+Connect → Stripe Checkout, отмена оплаченной →
    refund (кабинет). Гейтится `payments_enabled` + Connect, как весь P2.5.
  - **Деплой Track E:** миграции stays/0001, tenants/0012, finance/0003.
- **G6 — Aufträge & Angebote / смета Handwerker (A7, ✅ ВЕСЬ в `main`):** новый
  движок `apps.jobs` (TENANT) для выездного сервиса (Maler/Elektriker/SHK/Garten/
  Umzug/Catering…): цикл **Anfrage → Angebot (Kostenvoranschlag) → Auftrag →
  Rechnung** одной моделью Job. Разбивка F1–F3, ветка → CI зелёный → FF в `main`:
  - F1 ядро (✅ `831cbcb`, CI run 184, миграции jobs/0001 + tenants/0013):
    `Job` (customer PROTECT, код A-XXXXXX, title/description/site_address, status,
    public_token, valid_until, снимок net/vat/gross, invoice_id) + `JobLine`
    (позиции, целочисленный qty) + `JobSM` (new→quoted→accepted→done→invoiced +
    declined/cancelled); `services` create_job (reuse Customer) / set_lines
    (суммы через `finance.compute_totals`, §19 → НДС 0) / lines_snapshot.
    tenants/0013 — opt-out существующих из модуля (opt-in универсальный, как finance).
  - F2 кабинет (✅ `843b744`, CI run в стеке 186, без миграций): модуль «jobs»
    (nav «Jobs», `/dashboard/auftraege/`); список по статусу + ручная заявка;
    карточка — конструктор позиций сметы (до 12 строк, vat 19/7/0, valid_until),
    действия FSM, **Angebot-PDF** (`apps/jobs/pdf.py::build_quote_pdf` — зеркало
    finance.pdf), **«Rechnung erstellen»** (done→invoiced) → `finance.Invoice`
    (draft) из позиций (`services.quote_to_invoice`).
  - F3 витрина + публичное Angebot + письма (✅ `f671d5a`, CI run 186 зелёный,
    без миграций): `/anfrage/` (форма заявки honeypot+rate-limit → Job(new) +
    письмо владельцу) + `/angebot/<token>/` (клиент принимает/отклоняет смету
    онлайн без аккаунта → JobSM); `JobSM.on_transition` (quoted → письмо клиенту
    со ссылкой; accepted/declined → владельцу), DE-шаблоны `emails/job_*`; ссылка
    «Request a quote» в шапке витрины.
  - **Деплой G6:** миграции jobs/0001 + tenants/0013.
- **G4 — Доставка / Versand (✅ ВЕСЬ в `main`):** расширение `apps.orders`
  (Click&Collect был только самовывоз) доставкой по адресу — открывает интернет-
  магазин (A2). Разбивка G4a/G4b, ветка → CI зелёный → FF в `main`:
  - G4a backend + кабинет (✅ `d39ac5d`, CI run в стеке 191, миграции tenants/0014
    + orders/0004): `Tenant` конфиг доставки (`delivery_enabled`/`fee_cents`/
    `free_cents` бесплатно-от/`min_cents` Mindestbestellwert/`area` текст; зоны по
    PLZ — отложено); `Order` += `fulfillment` (pickup/delivery), `shipping_address`/
    `shipping_cents`/`tracking_code`/`shipped_at` + статус `shipped`; `OrderSM`
    ready→shipped (finance-выручка + письмо клиенту и на shipped; доставка в total);
    `services.shipping_cost` + `create_order(fulfillment/адрес/доставка)`. Кабинет
    `/dashboard/orders/`: настройки доставки (отдельная форма — не сбрасывает
    prepay), бейдж 🚚, блок доставки + «Versandt» с трек-номером; DE-шаблон
    `order_shipped`.
  - G4b витрина (✅ `9fb6554`, CI run 191 зелёный, без миграций): checkout
    `/warenkorb/` — выбор Abholung/Lieferung (при `delivery_enabled`), адрес
    (Straße/PLZ/Ort), серверный расчёт `shipping_cost` + проверка Mindestbestellwert,
    итог с доставкой; подтверждение показывает способ/адрес/трек. Предоплата (P2.5c)
    уже считает total с доставкой.
  - **Деплой G4:** миграции tenants/0014 + orders/0004.
- **G8 — Отзывы/рейтинги + гео-карта агрегатора (A8, ✅ ВЕСЬ в `main`):** довёл
  агрегатор до доверия/маркетплейса. Разбивка G8a/G8b/G8c:
  - G8a отзывы + страница бизнеса (✅ `0a6b513`, CI run в стеке 197, миграция
    aggregator/0008): `BusinessReview` (SHARED; автор=`PortalUser`, привязка к
    бизнесу `tenant_schema`, rating 1-5, comment, status published/hidden; unique
    author+бизнес) + `BusinessRating` (денорм avg+count, `reviews.recompute_rating`/
    `ratings_for`). Портал `/unternehmen/<slug>/` — хаб (контакты + листинги +
    отзывы + форма, только вошедшему PortalUser, как favorites); unfold-админка
    BusinessReview (модерация hidden → recompute). verified-бейдж — отложено.
  - G8b звёзды в выдаче (✅ `8a27972`+фикс `fae428f`, CI run 197 зелёный, без
    миграций): `reviews.attach_ratings(cards)` → звёзды «★ avg (count)» на
    карточках `/entdecken` и порталов; на порталах ссылка «★ Reviews» →
    `/unternehmen/<slug>/` (сиблинг карточки, без вложенных `<a>`). **Урок (снова):**
    `{{ Decimal }}` в локали de = «4,50» — тесты проверяют счётчик (int), не avg.
  - G8c гео: карта + «рядом» (✅ `cb3c38a`, CI run 201 зелёный, миграция
    aggregator/0009): `AggregatorListing` += lat/lng (denorm из Tenant в
    `sync_listing`; бэкофилл — `sync_aggregator`); `geo.py` (haversine/parse_latlng/
    nearest/map_points); city_listing + portal_home — near-режим при `?lat&lng`
    (ближайшие сверху) + `_map.html` (Leaflet/OSM, маркеры + «Near me» по
    геолокации). pagecache не мешает (GET с query не кэшируется). JSON-LD
    AggregateRating — отложено.
  - **Деплой G8:** миграции aggregator/0008 + 0009 (+ прогон `manage.py
    sync_aggregator` для бэкофилла lat/lng в существующие листинги).
- Werkstatt (A9) зафиксирован в `micro-business-verticals.md` (симбиоз booking+
  catalog+orders+jobs) + бэклог G10 bookable services / G11 расходники catalog→job.
- **G10 — Bookable services / услуга = цена+длительность (A3, A9; ✅ ВЕСЬ в
  `main`):** онлайн-запись на платную услугу («Ölwechsel 30 мин, 49 €») —
  обобщает A3 (Friseur/Massage/Werkstatt). Разбивка G10a/G10b:
  - G10a ядро (✅ `1a11cb5`, миграции booking/0003 + finance/0004): модель
    `Service` (TENANT: name/duration_minutes/price_cents/deposit_cents,
    бизнес-уровень — не привязана к мастеру); `Booking.service` (SET_NULL) +
    `price_cents` (снимок); `availability.free_slots(…, duration_minutes)` +
    `service_slots` (объединённые старты по всем активным ресурсам) +
    `assign_resource` (первый свободный); `services.book(service=, price_cents=)`;
    `BookingSM` fulfilled → выручка в `finance` (НДС 19 %, source «booking»,
    идемпотентно), без цены — записи нет.
  - G10b кабинет + витрина (✅ `ec73569`, CI run 206 зелёный, без миграций):
    `/dashboard/booking/leistungen/` (nav «Services») — CRUD услуг (депозит — при
    создании, инлайн-правка только длительность+цена); витрина `termin_index` при
    активных услугах → выбор услуги (иначе прежний выбор ресурса), новые
    `service_slots`/`service_book` (honeypot+rate-limit, валидация старта по
    сетке, авто-подбор ресурса, снимок цены, депозит → Stripe Checkout как
    P2.5b) → `/t/<code>/`; маршруты `termin/leistung/<uuid:pk>/[buchen/]`.
  - **Деплой G10:** миграции booking/0003 + finance/0004. **A9 Werkstatt → ~85 %,
    остаётся G11 (расходники catalog→job/stock).**
- **G11 — расходники сметы → каталог + остаток (A7, A9; ✅ ВЕСЬ в `main`):**
  замыкает Werkstatt-симбиоз — детали (Teile) в смете Handwerker берутся из
  каталога и списываются со склада. Разбивка G11a/G11b:
  - G11a ядро (✅ `004a9db`, миграция jobs/0002): `JobLine.product`/`variant`
    (FK catalog, SET_NULL — смета это снимок text/цены, переживает удаление
    товара) + `Job.stock_committed` (гард идемпотентности); `set_lines`
    принимает привязку расходника на строку; `services.commit_stock(job)` —
    атомарное списание (select_for_update, R3-паттерн) по строкам-расходникам с
    учётом склада: работа выполнена → не блокируем, клампим в 0, null = без
    учёта, идемпотентно; `JobSM` erledigt (accepted→done) → commit_stock один
    раз (возврата при отмене нет — cancelled достижим только до done).
  - G11b кабинет (✅ `cb43d76`, без миграций): в конструкторе сметы
    `/dashboard/auftraege/<pk>/` на каждую строку пикер расходника из каталога
    (товары/варианты, остаток в подписи); выбор + пустой текст/цена → снимок
    названия и цены; подсказка «склад спишется при Erledigt» / «✓ gebucht».
    Урок: каталог на UUID-PK → резолв пикера по str(pk), без int-каста.
  - **Деплой G11:** миграция jobs/0002. **A9 Werkstatt → ~95 % (симбиоз
    booking+catalog+orders+jobs закрыт); весь бэклог G1–G11 закрыт, кроме G9
    (курс с вместимостью + абонемент).**
- **G9 — Курс с вместимостью + Mehrfachkarte (A3, A6; ✅ ВЕСЬ в `main`):**
  последний пункт сквозного бэклога. Движок брони уже атомарно держит capacity
  (`Resource.capacity` + `services.book`), G9 — дельта поверх. Разбивка G9a/G9b:
  - G9a групповые курсы, видимая вместимость (✅ `2c08f5c`, без миграций):
    `availability.free_slots_with_spots` → [(start, end, spots_left)] (`free_slots`
    стал тонкой обёрткой, прочие вызывающие не затронуты); витрина `/termin/` при
    capacity>1 показывает «N spots» на слоте; бронь до заполнения уже атомарна.
  - G9b Mehrfachkarte / 10er-Karte (✅ `d77d572`, миграция booking/0004): модель
    `Pass` (TENANT: customer/label/code «K-XXXXXX»/credits_total+used/valid_until;
    credits_left + is_valid) + `Booking.card` (SET_NULL); `issue_pass` +
    `redeem_pass` (атомарно select_for_update, guard → PassInvalid); кабинет
    `/dashboard/booking/karten/` (выпуск/баланс X/N/ручное −1/деактивация); витрина —
    опц. поле «Mehrfachkarte-Code» в форме записи (термин+услуга): валидный код
    гасит визит вместо депозита/оплаты, невалидный → бронь остаётся, на оплату не
    уводим. Онлайн-продажа карты (Stripe) и привязка карты к курсу — отложено.
  - **Деплой G9:** миграция booking/0004. **Весь сквозной бэклог G1–G11 закрыт
    целиком.**
- **Отложенные quick-wins (✅ ВЕСЬ в `main`, выбор владельца после G9):** мелочи
  из roadmap §Отложено, каждая — отдельный инкремент с CI-зелёным.
  - JSON-LD AggregateRating (G8, ✅ `98a1ed4`, без миграций): звёзды бизнеса в
    Google-сниппете — `seo.localbusiness_ld(aggregate_rating=(avg,count))`; витрина
    (тег `{% localbusiness_jsonld %}` тянет BusinessRating тенанта ленивым импортом,
    core не зависит от aggregator на уровне модуля) + страница `/unternehmen/<slug>/`
    (block structured_data).
  - Booking-полировка (✅ `7d4d324`, миграция booking/0005): (1) бронь, оплаченная
    Mehrfachkarte, авто-confirm (если ресурс не require_manual_confirm) — карта =
    оплачено; (2) `Resource.counts_party_size` — групповой курс считает места по
    СУММЕ party_size («ich + 3 Freunde» = 4), default False (столы/мастера/залы не
    затронуты: бронь = 1 единица); учтено в `free_slots_with_spots` и
    `services.book/move` (`_would_overfill`), тумблер в кабинете ресурсов.
  - Verified-бейдж отзывов (G8, ✅ `38534b9`, без миграций): «✓ Verified guest»,
    если у автора есть Customer в схеме бизнеса (`reviews.verified_emails` —
    кросс-схемно через schema_context, ошибки гасим). Бейдж на `/unternehmen/<slug>/`.
  - Ваучеры в CRM 360° (D1, ✅ `cd72e93`, миграция promotions/0014):
    `Voucher.customer` (SET_NULL — код переживает удаление клиента) +
    `generate_vouchers(customer=)`; блок «Vouchers» и форма выдачи в карточке
    `/crm/<pk>/`.
  - **Деплой quick-wins:** миграции booking/0005 + promotions/0014.
- **Мастер-план + архитектурные швы (✅ в `main`, 2026-06-14):** новый канонический
  `docs/master-plan.md` (сводит vision+roadmap+verticals; модули M1–M23; стадии
  архетипы→100% + Phase 2 → глобальные; M22 чат/поддержка/тикеты, M23 маркетинг/
  соцсети/реклама). Порядок работ (владелец): швы → M22 → M23 → A4 Gastro.
  - Швы (✅ `8bfd3ae`, миграции core/0001 + orders/0005): `apps.core.Membership`
    (роли owner/admin/staff, TENANT) + `roles.role_of()` (дефолт owner, без
    backfill; владелец = owner при провижининге) — шов M6 multi-user, гейтинг во
    вьюхах пока не включён; `Order.parent_order` (self-FK) + `supplier_tenant_schema`
    — пассивные хуки dropshipping/маркетплейс (M11→M14/M15). Логики нет — только швы.
  - **Деплой:** миграции core/0001 + orders/0005.
- **M22 — Чат/поддержка/тикеты (в работе):** новый `apps.inbox` (TENANT).
  - M22a ядро + кабинет (✅ `37916be`, CI run в стеке, миграция inbox/0001):
    `Conversation` (тред=тикет: customer/subject/status-FSM/priority/assignee/
    channel/ref_* мягкая привязка/public_token/unread_for_staff; швы realtime/AI
    — `ai_handled`/`external_ref`) + `Message` (staff/customer/system);
    `ConversationSM` (open↔pending↔resolved→closed, reopen); `services.
    start_conversation`/`post_message` (reuse Customer по email; ответ клиента в
    resolved/closed переоткрывает тред + unread). Кабинет `/dashboard/inbox/`
    (nav «Inbox», бейдж непрочитанного, тред+ответ+статус+приоритет). Модуль
    «inbox» — универсальный, из коробки (recommended_for=все типы). **Урок:**
    новый optional-модуль → обновить хардкод-наборы в test_modules (disabled).
  - M22b витрина + публичный тред + письма (✅ `02b4ba7`, без миграций): публичная
    форма `/nachricht/` (honeypot+rate-limit, гейтинг inbox) → тред (reuse Customer
    по email, привязка ref из `?kind/id/label`) → публичный `/nachricht/<token>/`
    (клиент видит/отвечает по токену); письма `apps/inbox/notifications.py` (дедуп
    `inbox:msg:<id>:role`): ответ владельца → клиенту, вопрос клиента → владельцу,
    вшито в `post_message`. Ссылка «Ask a question» в шапке витрины
    (`storefront_inbox_enabled`) + «Frage zum Produkt» на товаре.
  - M22c платформенная техподдержка (✅ `25949dc`, миграция support/0001):
    SHARED-app `apps.support` (`SupportThread` tenant↔SiteAdaptor + `SupportMessage`
    owner/platform); кабинет владельца `/dashboard/help/` (nav «Help» в core-модуле
    settings) — создание/список/ответ своих тикетов; платформа отвечает из
    unfold-админки на public. Отдельно от inbox (клиент↔бизнес).
  - **M22 закрыт (a+b+c).** Деплой: миграции inbox/0001 + support/0001. Дальше по
    плану владельца: M23 (соц-постинг акций) → A4 (Gastro-модификаторы).
- **M23 — Маркетинг/соцсети (в работе; расширяет M3 publishing, P2.9):**
  - M23a соц-постинг акций Facebook/Instagram (✅ в `main`, `1880e9c`, CI run 247
    зелёный, миграция publishing/0003): новые типы `Channel` facebook/instagram
    поверх фреймворка `apps.publishing` (паттерн B1 GBP) — на активации акции
    PromotionSM ставит публикацию, на завершении снимает. `adapters`: `_fb_publish`
    (page `/feed`, либо `/photos` при фото — ссылка в `link`/тексте) + `_fb_remove`
    (DELETE поста; нет ref / 404 = no-op); `_ig_publish` (контейнер `/media` →
    `/media_publish`, **требует фото**, URL текстом в подписи — IG без кликабельных
    ссылок) + `_ig_remove` (**no-op** — Graph API не удаляет органические IG-посты);
    `_promo_image_url` достраивает относительный `/media` доменом арендатора.
    Кабинет Channels: конфиг facebook (`page_id`/`access_token`) и instagram
    (`ig_user_id`/`access_token`), пустое не затирает секрет. `settings.
    META_GRAPH_API_VERSION` (default v21.0). Токены — per-канал, вводятся вручную
    (как GBP; in-app OAuth — следующая итерация). Тесты `test_meta` (Graph API
    застаблен), настройка — `docs/meta-social-setup.md`. **Боевое — после доступа
    Meta** (App Review prod-permissions). Деплой: миграция publishing/0003.
  - M23b каталог-фид (✅ в `main`, CI зелёный, без миграций): витрина отдаёт
    product-feed `/feed/google.xml` (RSS 2.0 namespace `g:`, ест Google Merchant
    Center и Meta Commerce Manager по URL). `apps/catalog/feed.py::build_google_feed`
    (чистый билдер: URL-функции снаружи — домен из request, мульти-тенант); вьюха
    `promotions.public_views.product_feed_xml` + маршрут `storefront-product-feed`.
    Активные товары; варианты R1 — отдельные `item` с общим `g:item_group_id`;
    наличие из R3; цена base/variant; фото абсолютизируется доменом арендатора.
    Тесты `catalog/test_feed`. Подключение — `docs/meta-social-setup.md §M23b`.
  - M23 доп.каналы Telegram-канал + Pinterest (✅ в `main`, CI зелёный, миграция
    publishing/0004): новые типы `Channel` telegram/pinterest поверх того же
    фреймворка. `_tg_publish` (Bot API sendPhoto при фото, иначе sendMessage,
    ссылка в тексте; бот = админ канала; external_ref «chat_id:message_id») +
    `_tg_remove` (deleteMessage; нет ref / 400 = no-op); `_pinterest_publish`
    (API v5 POST /pins, **требует фото**, board_id+ссылка) + `_pinterest_remove`
    (DELETE /pins/{id}, 404 = no-op). Кабинет Channels: конфиг telegram
    (`bot_token`/`chat_id`) и pinterest (`access_token`/`board_id`). Токены —
    per-канал вручную (как GBP/Meta). Тесты `test_channels_extra`. Боевое — после
    Telegram-бота/Pinterest-токенов. Деплой: миграция publishing/0004.
  - **Telegram-бот для бизнесов (в работе; решение владельца: свой бот на тенанта +
    боты агрегатор-порталов, объём v1 = Mini App):**
    - TG1 ядро бизнес-бота (✅ в `main`, CI зелёный, миграция telegram/0001): новое
      `apps.telegram` (TENANT) — модель `TelegramBot` (token из @BotFather,
      bot_username, webhook_secret, is_active; одна строка на тенанта). Публичный
      webhook `/tg/<secret>/` (csrf-exempt, на домене арендатора — TenantMain
      резолвит схему по хосту; опц. заголовок X-Telegram-Bot-Api-Secret-Token;
      всегда 200). `webhook.handle_update`: на /start (и любое сообщение) бот шлёт
      кнопку «Open shop» с `web_app` → витрина как **Telegram Mini App**. Кабинет
      `/dashboard/telegram/` (nav «Telegram»): ввод токена → getMe + setWebhook,
      тумблер connect/disconnect. Модуль «telegram» — universal opt-in (как
      finance/jobs, выкл. по умолчанию). DSGVO: chat_id/переписка = PII (не-EU),
      в AVV; v1 чат не хранит. Тесты `test_telegram`. **Урок (снова):** новый
      optional-модуль → дополнить хардкод-наборы в test_modules (+telegram).
    - TG2 Mini App polish (✅ в `main`, CI зелёный, без миграций): витрина
      подключает Telegram Web App SDK (`telegram.org/js/telegram-web-app.js`) в
      `storefront/_base.html`; внутри Telegram (есть `initData`) — `ready()`+
      `expand()` и класс `in-telegram` на `<html>` (хук под стили); вне Telegram —
      no-op. Тест в `catalog/test_storefront`. MainButton/тема per-page — позже.
    - TG3 уведомления в Telegram + привязка клиента (✅ в `main`, CI зелёный,
      миграции telegram/0002 + notifications/0002): модель `TelegramLink`
      (Customer↔chat_id, `link_token` url-safe для deep-link); `apps/telegram/
      notify.py` — `deep_link(customer)` (t.me/<bot>?start=<token>), `link_from_start`
      (на /start <token> webhook проставляет chat_id), `send_to_customer` (ставит
      Notification channel=telegram, если клиент привязан и бот активен; дополняет
      email, не заменяет). Канал `telegram` в `apps.notifications` (+ адаптер
      `_send_telegram` — токен бота арендатора, recipient=chat_id). Заказы
      (`enqueue_order_email`) дублируют событие в Telegram; на странице
      подтверждения заказа — кнопка «Get updates on Telegram». Тесты `test_notify`.
    - TG4 боты агрегатор-порталов (✅ в `main`, CI зелёный, миграция aggregator/0010):
      `PortalBot` (SHARED, OneToOne AggregatorPortal: token/bot_username/
      webhook_secret/is_active); `apps/aggregator/telegram_bot.py` — webhook
      `/tg/<secret>/` на хосте портала (urls_portal, csrf-exempt), на /start бот
      открывает выдачу портала как Mini App (`web_app`→portal-home); `connect_bot`
      (getMe+setWebhook на `https://<portal.host>/tg/<secret>/`) / `disconnect_bot`.
      Generic Bot API переиспользован из `apps.telegram.services`. unfold-админка
      `PortalBot` (public) с действиями Connect/Disconnect (токен — write-only
      поле). Тесты `test_portal_bot`. Боевое — после токена бота портала.
    - TG3+ booking/stays-уведомления в Telegram (✅ в `main`, CI зелёный, без
      миграций): `enqueue_booking_email`/`enqueue_stay_email` дублируют событие
      клиенту в Telegram (`send_to_customer`, дедуп `booking|stay:{id}:{event}:tg`);
      кнопка «Get updates on Telegram» на страницах подтверждения брони/
      Übernachtung (общий partial `storefront/_telegram_cta.html`, заказ тоже на
      нём). Тесты `test_notify_booking_stays`.
    - **Деплой TG:** миграции telegram/0001+0002+0003 + notifications/0002 +
      aggregator/0010 + `apps.telegram` в TENANT_APPS.
  - Дальше M23 после Telegram: M23c платная реклама (Campaign/AdInsight). TikTok
    отложен (видео + аудит API — низкий fit).
- **Зашифрованные ключи интеграций в админке (✅ в `main`, CI зелёный, миграция
  secrets/0001):** новое SHARED-приложение `apps.secrets` — модель `PlatformSecret`
  (key + value зашифрован Fernet + description). Управляется в unfold-админке на
  public: значение **write-only** (PasswordInput, в UI не показывается; пустой ввод
  не затирает), список — признак «задан» + дата. `apps/secrets/crypto.py` (Fernet;
  мастер-ключ `SECRETS_ENCRYPTION_KEY` из .env, фолбэк из SECRET_KEY для dev/CI;
  битый токен → '' без падения). Аксессор `apps/secrets/store.py`: `get(key)` и
  `get_or_setting(key, settings_attr)` — **читает в schema_context("public")**
  (безопасно из схемы арендатора), **фолбэк на settings/.env** (прод не ломается,
  пока секрет не задан). Первый потребитель — GBP Google OAuth client_id/secret
  (`_gbp_access_token` → `get_or_setting`). Платформенные ключи, читаемые в рантайме
  нашим кодом, мигрируются в стор по мере надобности (Stripe/email читаются
  сторонними либами на старте — остаются в .env). Тесты `secrets/test_secrets`.
  Деплой: миграция secrets/0001 + `apps.secrets` в SHARED_APPS; в проде задать
  `SECRETS_ENCRYPTION_KEY` (Fernet.generate_key()).
- **Per-tenant токены — шифрование at-rest (✅ в `main`, CI зелёный, миграция
  telegram/0003):** `apps/secrets/fields.py::EncryptedTextField` — прозрачное
  Fernet-шифрование в БД, открытый текст в Python, **толерантно к легаси-
  плейнтексту** (нерасшифровываемое читается как есть, шифруется при следующем
  save — ленивая миграция без data-миграции; не фильтровать по значению —
  Fernet недетерминирован, только `exclude(field="")`). Применено к
  `TelegramBot.token`. Для `Channel.config` (jsonb, тип не меняем) — секретные
  подключи (`refresh_token`/`access_token`/`bot_token`) шифруются точечно:
  `apps/publishing/secrets.py` (`SECRET_KEYS`, `decrypted_config` — адаптеры
  читают расшифрованным; кабинет шифрует только новые значения, не двойно).
  Тесты `secrets/test_fields`, `publishing/test_config_secrets`. Деплой:
  миграция telegram/0003.
- **In-app OAuth подключение каналов — OAuth-A (✅ в `main`, CI зелёный, без
  миграций):** «Connect одной кнопкой» для **GBP** и **Pinterest** (выбор
  владельца после пропуска рекламы M23c). `apps/publishing/oauth.py`: реестр
  PROVIDERS (authorize/token URL, scope, креды из стора/.env, какое поле токена
  и куда в config), подписанный `state→схема` (signing, 10 мин), authorize из
  кабинета → провайдер → **единый callback на основном домене** `/oauth/<prov>/
  callback/` (urls_public; обходит redirect-URI-на-субдоменах, master-plan §8) →
  `exchange_code` (Google — params, Pinterest — Basic auth) → токен в
  `Channel.config` **зашифрованным** (как ручной ввод) → редирект назад на каналы
  арендатора. Вьюхи `oauth_start`(кабинет)/`oauth_callback`(public); кнопки
  «Connect with Google/Pinterest» в кабинете каналов (ручной ввод остаётся
  фолбэком). Креды: `pinterest_client_id/secret` (стор/.env), `OAUTH_CALLBACK_BASE`
  (пусто→https://TENANT_DOMAIN_BASE). Тесты `publishing/test_oauth`. **Боевое —
  после регистрации OAuth-приложений у Google/Pinterest** (redirect_uri = callback).
- **OAuth-B — Meta (FB/IG) one-click (✅ в `main`, CI зелёный, без миграций):**
  один поток подключает оба канала. Провайдер `facebook` в реестре OAuth
  (authorize `facebook.com/{version}/dialog/oauth`, scope pages_*/instagram_*);
  диспетчер `oauth.complete()` для Meta вызывает `_meta_complete`: code →
  short-lived user-токен → long-lived (`fb_exchange_token`) → `/me/accounts`
  (fields id,name,access_token,instagram_business_account) → **первая страница**
  (мультивыбор — следующая итерация): page_id + page-токен в канал facebook, при
  наличии IG-аккаунта — ig_user_id + тот же page-токен в канал instagram, токены
  **зашифрованы at-rest**. Кнопка «Connect with Facebook (also links Instagram)»
  в кабинете. Креды `meta_app_id`/`meta_app_secret` (стор/.env META_APP_ID/SECRET).
  Тесты `publishing/test_oauth_meta`. Боевое — после Meta App Review + регистрации
  redirect_uri. **Дальше (опц.):** UI выбора страницы при нескольких страницах.
- **A6 — событие/ретрит: платный билет + ростер (в работе; крупнейшая дыра
  архетипа A6 ~60 %→):**
  - A6a ядро (✅ в `main`, CI зелёный, миграции events/0001 + finance/0005): новое
    `apps.events` (TENANT) — `Event` (title/starts_at/ends_at/`capacity` 0=безлимит/
    `price_cents` за место/`questions` анкета/status draft-published-cancelled/
    require_manual_confirm) + `Ticket` (event/customer PROTECT, код E-XXXXXX,
    `quantity` мест, снимок price_cents, `answers` анкеты, payment-поля, status
    pending-confirmed-attended-cancelled; ACTIVE_STATUSES занимают места);
    `EventSM`/`TicketSM` (core.fsm); `services.book_ticket` — анти-овердрафт мест
    под `select_for_update` на Event (capacity vs Σ quantity активных; безлимит=skip),
    reuse Customer; `auto_confirm` создаёт pending и проводит FSM-ом (срабатывает
    finance-хук). `TicketSM` confirmed → выручка в finance (source «event», **НДС
    19 %**, идемпотентно; бесплатные/amount 0 — пропуск). Модуль «events» —
    universal opt-in (как finance/jobs; suited_for tour_operator/other) + минимальный
    кабинет `/dashboard/events/` (список; полный CRUD/ростер — A6b). Тесты
    `events/test_events`. **Урок (снова):** новый optional-модуль → дополнить
    хардкод-наборы test_modules (+events). Деплой: миграции events/0001 +
    finance/0005 + `apps.events` в TENANT_APPS.
  - A6b кабинет (✅ в `main`, CI зелёный, без миграций): `/dashboard/events/` —
    CRUD событий (`EventForm`: цена в € → cents, анкета построчно → questions,
    datetime-local), карточка с ростером участников + действия EventSM
    (publish/unpublish/cancel) и TicketSM (confirm/attended/cancel) + «mark paid»
    (payment_state=paid, авто-confirm pending), ручная запись участника
    (book_ticket auto_confirm), CSV-ростер (utf-8-sig, колонки по вопросам анкеты).
    Тесты `events/test_cabinet`.
  - A6c витрина + оплата + письма (✅ в `main`, CI зелёный, без миграций):
    публичная `/veranstaltung/` (список опубликованных будущих) → `/veranstaltung/
    <pk>/` (страница + форма билета: имя/почта/тел/кол-во + поля анкеты `q0..`) →
    POST `buchen/` (honeypot+rate-limit, гейтинг events). Бесплатное → сразу
    confirmed; платное + `payments_enabled` + Connect → Stripe Checkout на счёт
    бизнеса (metadata `kind=event_ticket`, вариант B), иначе pending; вебхук
    `mark_ticket_paid` (кросс-схемно: paid + авто-confirm, если событие не требует
    ручного). `/e/<code>/` — подтверждение (код/статус/Telegram-CTA).
    `events/notifications.py` + DE-шаблоны `emails/ticket_*`: TicketSM на
    confirmed/cancelled шлёт письмо клиенту (+ Telegram TG3), на created — клиенту
    и владельцу. Ссылка «Events» в шапке витрины (`storefront_events_enabled`).
    Тесты `events/test_storefront`.
  - **A6 завершён (a+b+c) →архетип A6 ~60 %→~90 %.** Деплой: миграции events/0001
    + finance/0005 + `apps.events` в TENANT_APPS.
- **A5 — Übernachtung: тарифы + iCal-синхронизация (✅ a+b, ~80 %→~95 %):**
  - A5a движок цен (✅ в `main`, CI зелёный, миграции stays/0002+0003): `SeasonRate`
    (юнит/диапазон дат [start,end]/цена-ночь — перебивает базу и выходные) +
    `StayUnit.weekend_price_cents` (Fr+Sa, 0=как база); `apps/stays/pricing.py`
    (`nightly_price_cents` приоритет season→weekend→base, `quote_total_cents`
    сумма по ночам). `StayBooking.total_cents` теперь **хранимое поле** (было
    свойство price×nights) — `book_stay`/`move_stay` считают через quote_total;
    backfill старых броней (stays/0003). Витрина-quote и finance-хук берут новый
    total. Кабинет `/dashboard/stays/units/`: weekend-цена + CRUD сезонных тарифов.
    Тесты `stays/test_pricing`. Деплой: миграции stays/0002+0003.
  - A5b iCal экспорт/импорт (✅ в `main`, CI зелёный, миграция stays/0004):
    канал-менеджмент без внешних либ (`apps/stays/ical.py` — build_feed/
    parse_events, all-day VEVENT). **Экспорт:** подписной фид занятости юнита
    (брони ACTIVE + блоки) по подписанному токену `/stays/ical/<token>.ics`
    (`public_views.unterkunft_ical`, гейтинг stays) — Booking.com/Airbnb/Google
    подписываются и блокируют даты. **Импорт:** `ICalSource` (внешний фид на юнит) →
    `services.sync_ical_source` тянет requests, заводит `UnitBlock` на занятые
    диапазоны (DTEND эксклюзивно → end_date=DTEND−1 включительно), помечает
    `UnitBlock.source_id_ref=str(pk)`; идемпотентно (пересоздаёт ТОЛЬКО свои блоки,
    ручные source_id_ref="" не трогает), сбой сети/парса → last_status, блоки
    целы. Beat `sync_ical_sources` раз в час по всем схемам. Кабинет
    `/dashboard/stays/units/`: копируемый экспорт-URL + CRUD источников + «Sync
    now». Тесты `stays/test_ical` + export-вьюха в `test_public`. Деплой:
    миграция stays/0004.
  - A5c авто-Rechnung на бронь (✅ в `main`, CI зелёный, миграция stays/0005):
    `services.stay_to_invoice(booking, small_business=)` → черновик `finance.Invoice`
    из брони. Цена брони — **брутто** (вкл. 7 % Beherbergung), нетто вычисляется
    обратным счётом (gross/(1+rate) → net, vat=gross−net), чтобы итог счёта совпал
    с оплаченным; §19 → НДС 0. `StayBooking.invoice_id` (UUID) — гард от двойного
    счёта (повтор вернёт существующий). Кабинет `/dashboard/stays/`: кнопка «Create
    invoice» у confirmed-броней (гейтинг модуля finance, `_finance_active`) →
    редирект на finance invoice-detail; бейдж «✓ Invoice created». Тесты в
    `stays/test_pricing` (back-out НДС/идемпотентность/§19) + `test_cabinet`
    (action + гейтинг). Деплой: миграция stays/0005.
  - Дальше A5: листинг date-range в агрегаторе (крупный отдельный инкремент —
    агрегатор завязан на promotions/promo_uuid).
- **A5/A6 — date-range листинг отелей/событий в агрегаторе (✅ в `main`,
  решение владельца 2026-06-15: расширить
  AggregatorListing, без фильтра доступности stays в v1, авто-листинг как акции):**
  главная дыра A5/A6 — размещение (apps.stays) и события (apps.events) не попадали
  в `/entdecken`/порталы (агрегатор был завязан на акции через promo_uuid).
  - A5/A6-1 ядро + sync (✅ в `main`, миграция aggregator/0011): `AggregatorListing`
    += `listing_kind` (promotion/stay/event) + `source_ref` (единый ключ источника,
    str pk); `promo_uuid` → nullable; новый unique `(tenant_schema, listing_kind,
    source_ref)` + backfill (`source_ref=str(promo_uuid)`); `save()` выводит
    source_ref из promo_uuid (инвариант, защита legacy-создания). Sync-задачи
    `sync_stay_listing`/`sync_event_listing` (кросс-схемно, зеркало sync_listing,
    гейтинг по `is_module_active`): stay = «ab price_cents/Nacht» пока `is_active`;
    event = published + будущее, цена за место + `starts_at`. Хуки: `StayUnit`
    post_save/post_delete, `EventSM.on_transition` (published→upsert, draft/
    cancelled→remove) + `Event` post_save (правка). `reconcile_schema` +
    `sync_aggregator` покрывают все три вида. `listings_for`/featured/гео/звёзды/
    порталы/SEO — без изменений (один пул). Тесты `test_stay_event_listings`.
  - A5/A6-2 выдача + карточки + фильтр (✅ в `main`, без миграций): `listings_for(kind=)`
    фильтрует вид + всегда скрывает истёкшие события (`starts_at<now`); `discover_index`
    принимает `?kind=` (мусор игнор), чип вида (Angebote/Übernachten/Events) в
    `_search_form`; `_cards.html` — бейдж 🛏/🎫 по `listing_kind`, stay → «ab X €/
    Nacht», event → цена + дата. Тесты `test_kind_filter`.
  - A5/A6/A8-хвосты (✅ в `main`, 2026-06-15; T1+T2 без миграций, T3 — events/0002):
    - **T1 P2.7+ рекомендации (A8):** `apps/aggregator/recommendations.py::ending_soon`
      — акции с близким `ends_at` + события с близким `starts_at` в порядке
      срочности; рейл «Ending soon» на `/entdecken` (landing). Тесты
      `test_recommendations`.
    - **T2 фото карточек stays/events (A5/A6):** карточка без своего фото берёт
      `Tenant.logo_url` (фолбэк вместо placeholder, `_logo_image` в sync). Своё
      фото юнита/события — позже.
    - **T3 «Programm» ретрита (A6):** `Event.program` (список пунктов агенды,
      построчно в форме как questions) + блок «Programme» на странице события.
  - Фильтр доступности stays по датам — отложено (тяжёлый кросс-схемный календарь;
    карточка ведёт на витрину `/unterkunft/`); единая корзина агрегатора — Stage 3.
  - **Деплой A5/A6:** миграции aggregator/0011 + events/0002 + один раз
    `manage.py sync_aggregator` (бэкофилл листингов stays/events).
- **A4 — Gastro-модификаторы/Extras блюда (в работе; главная дыра A4, ~70 %→):**
  - A4a ядро + кабинет (✅ в `main`, `3377125`, CI run 251 зелёный, миграция
    catalog/0005): `ModifierGroup` (FK Product, `name`, `min_select`/`max_select`,
    sort, is_active) + `ModifierOption` (FK group, `label`, `price_delta` Decimal —
    надбавка к цене позиции, sort, active). Правило выбора: min>=1 — обязательная;
    max==1 — одиночный (radio); max>1 — до N (checkbox); max==0 — без предела
    (валидация на витрине — A4b). `Product.has_modifiers`/`modifier_groups_active`;
    `ModifierGroup.is_required`/`is_multi`/`active_options`. Кабинет: CRUD групп и
    опций на странице товара (`catalog/product_form.html`, паттерн variant CRUD),
    вьюхи `modifier_group_*`/`modifier_option_*` + URLs. Модификаторы — часть
    catalog (core-модуль), без нового модуля; для не-гастро просто пусто. Тесты
    `test_modifiers`. Деплой: миграция catalog/0005.
  - A4b витрина + корзина + заказ (✅ в `main`, `9238d7b`, CI run 256 зелёный,
    миграция orders/0006): `apps/catalog/modifiers.py` — `validate_selection`
    (серверная проверка min/max/required по группам), `options_from_ids`
    (восстановление из корзины), `options_delta`. Витрина (product_detail):
    селекторы — single (max==1) через `<select>`, multi через checkbox, оба шлют
    `mod` (без JS); скрыто без модификаторов. Корзина: ключ `pid:vid:o1,o2`
    (**разделитель опций — запятая, НЕ дефис: UUID содержит дефисы**), разные
    наборы Extras = разные позиции; `_cart_items` восстанавливает опции,
    `_line_price` учитывает надбавки; выбор показан в корзине.
    `create_order(items=(product,variant,qty,options))` — `unit_price` = base +
    Σ delta; `OrderItem.modifiers` снимок `[{label,delta}]` + `modifiers_label`
    в подтверждении/кабинете заказов/письмах. Тесты `test_modifier_flow`.
  - **A4 завершён (a+b).** A4 ~75 %→~90 %: доставка гастро уже есть (reuse orders
    G4), остаётся опц. KDS. Деплой: миграции catalog/0005 + orders/0006.
  - A4 KDS — Küchen-Display (✅ в `main`, без миграций):
    экран кухни `/dashboard/orders/kitchen/` — доска активных заказов (new/confirmed,
    FIFO по created_at) с HTMX-поллингом каждые 8с (`_kitchen_board` партиал) +
    кнопки Annehmen (new→confirmed) и Fertig (confirmed→ready) через `kitchen_action`
    → OrderSM, возврат обновлённого партиала (swap без перезагрузки), illegal-
    переход = no-op (другой экран мог сменить статус). Кнопка «Kitchen Display» на
    `/dashboard/orders/`. Поверх apps.orders, гейтинг модуля orders. Тесты
    `orders/test_kitchen`. **A4 ~90 %→~100 %.**
- **Ресторанный пакет — Gastro UX + комбо + промокоды (✅ ВЕСЬ в `main`, 2026-06-19):**
  усиление архетипа A4 поверх готовых orders/catalog. Разбивка по веткам → CI → FF:
  - T2a QR-Bestellung am Tisch (миграция orders/0008): `Order.table_number`; захват
    `?tisch=N` в сессию (context-processor `storefront_table`, как `?ch=`), checkout
    пишет стол (кроме доставки); вывод на KDS/карточке заказа/письме владельцу/в
    корзине; кабинет `/dashboard/orders/tisch-qr/` — печатный лист QR столов (segno).
  - T2b мобильный нижний таб-бар (без миграций): `_storefront_bottom_nav` развивает
    P1 action-bar — Speisekarte · Aktionen(#aktionen) · 🛒 Korb (акцент+бейдж) ·
    Anruf, адаптивно по модулям, cap 5. ТЗ настройки в кабинете — roadmap §Отложено.
  - T2c быстрый заказ с карточки (без миграций): «+» на карточке → bottom-sheet
    модалка-конфигуратор (vanilla fetch, без HTMX ради CWV) с размером/ингредиентами;
    общий партиал `_add_to_cart_form.html`; простой товар → «+» = прямое добавление.
    Тоггл `site_config.quick_add` в кабинете Site («как раньше» = карточка→страница).
  - Комбо-наборы (миграции catalog/0008 + orders/0009): `Combo`/`ComboGroup`/
    `ComboOption` (catalog) — фикс-цена + группы выбора (фикс = 1 опция, выбор =
    несколько, надбавка за апгрейд); `apps/catalog/combos.py` (price/validate/snapshot);
    кабинет `/catalog/combos/` (nav «Combos»); витрина `/kombi/` + конфигуратор →
    `combo_cart` в сессии → заказ одной OrderItem (product=null, combo FK, состав в
    modifiers). Сток компонентов комбо v1 не списываем (отложено).
  - Промокоды = расширение `Voucher` (миграции promotions/0015 + orders/0010): по
    решению владельца переиспользуем существующий Voucher, не новая модель.
    `Voucher.discount_percent/discount_cents/min_order_cents` + `discount_for()`;
    кабинет «Gutscheine» — поля скидки %/€; на чекауте поле кода → `create_order
    (voucher_code=)` считает скидку и гасит код под блокировкой (анти-двойное-
    списание), `Order.voucher_code/discount_cents`; скидка в корзине/подтверждении/
    кабинете. Пустые поля скидки = прежний ручной ваучер-метка (без регрессии).
  - **Деплой:** миграции orders/0008+0009+0010, catalog/0008, promotions/0015.
- **Личный кабинет клиента на витрине (CA1–CA4, ✅ ВЕСЬ в `main`, 2026-06-19):**
  ЛК клиента **на витрине бизнеса** (per-tenant, отдельно от PortalUser агрегатора
  и auth.User владельца). Личность = существующий `promotions.Customer` по email —
  новых моделей нет. `apps/account` (TENANT, без моделей; app label=customer_account,
  т.к. «account» занят allauth). Решение владельца: ЛК **отключаемый** — витрина-
  визитка / заказ в зале без регистрации → ЛК не нужен.
  - CA1 ядро (тумблер + вход): модуль-тумблер `customer_account` в реестре — **ВКЛ
    по умолчанию у транзакционных типов** (recommended_for), **ВЫКЛ у чистых витрин**
    (other → default_disabled_for); владелец переключает в `/dashboard/modules/`
    («Kundenkonto»). Вход без пароля (magic-link, зеркало агрегатора:
    `apps/account/auth.py`, Redis-токен SHA-256/15мин/одноразовый, сессия
    account_customer_id, get_or_create Customer; анти-энумерация + rate-limit
    email/IP, honeypot). Маршруты `/konto/` (login/verify/logout/home), шаблоны
    `templates/konto/` (НЕ templates/account — там allauth). Письмо — Celery
    `send_customer_magic_link`. Ссылка «Account» в шапке + 👤 в нижнем таб-баре при
    активном модуле. Data-миграция **tenants/0017**: существующим
    нетранзакционным тенантам дописать customer_account в disabled_modules.
  - CA2 содержимое (`account_data.sections_for`): разделы Bestellungen (orders),
    Termine + Mehrfachkarten (booking), Übernachtungen (stays), Tickets (events),
    Angebote & Aufträge (jobs), Rechnungen (finance), Reservierungen + Gutscheine
    (promotions), Bonuskarten (loyalty), Nachrichten (inbox) — каждый виден только
    при активном модуле; ссылки на существующие публичные страницы статуса (по
    коду/токену); каждая выборка в try/except (сбой не рушит ЛК).
  - CA3 профиль + DSGVO (`/konto/profil/`): имя/тел (email=логин read-only),
    Marketing-Opt-in (UWG §7), экспорт (Art. 15/20 JSON) и удаление/анонимизация
    (Art. 17) — переиспользуют `_export_payload`/`_erase` из команды
    dsgvo_customer; привязка Telegram (deep_link).
  - CA4 действия: повтор заказа (reorder → корзина, комбо/модификаторы v1 не
    переносим), отмена брони из ЛК (BookingSM cancel + возврат депозита Stripe
    Connect, как в кабинете), автозаполнение формы чекаута именем/почтой/тел
    вошедшего (context `account_customer`; бронь/событие — следующая итерация).
  - **Деплой:** миграция tenants/0017 + `apps.account` в TENANT_APPS (без моделей).
- **Витрина — UX-итерация R1–R5 + точки самовывоза (✅ ВЕСЬ в `main`, 2026-06-19):**
  серия правок витрины/корзины по запросам владельца. Разбивка по веткам → CI/локал → FF:
  - R1 AJAX-добавление в корзину (без миграций): «+» на карточке добавляет без
    перехода — `cart_add` при `X-Requested-With: fetch` отдаёт JSON `{ok,count}`
    (`_added_response`/`_add_error`); иконка корзины в шапке + бейдж (data-cart-badge),
    «прыжок» бейджа + тост; модалка закрывается после добавления. Без JS — обычная
    отправка (прогрессивное улучшение). `context.storefront_cart_count`/`_cart_count`.
  - R2 нижний таб-бар компактнее (min-h 56→48, спейсер 64→48, читабельнее).
  - R3 демо-ресторан богаче (+3 товара с вариациями, 4 акции, скидки +30 %).
  - R4 корзина: 2 колонки с ЛИПКОЙ сводкой (lg:sticky), промокод+итог+акцентный
    CTA (submit через `form=checkout-form`), компактнее, лучше empty-state.
  - R5 полировка (без миграций): бейдж без красного (акцент/белый кружок); тёмная
    тема — фиксы `.dark .bg-white/95|/90` (иконки/подписи меню видны на тёмном);
    символ валюты фильтром `siteui.cursym` (EUR→€) во всех витринных шаблонах;
    карточка — цена+кнопка в одну линию в подвале (кнопка вне `<a>`), имя в одну
    строку; корзина — ингредиенты переносятся на мобайле; **реактивная доставка**
    (выбор Abholung/Lieferung меняет адрес-показ и стоимость/итог, JS + центы в
    data-атрибутах), адрес только для доставки; **dine-in** (QR-стол) — свёрнутая
    корзина без способа/адреса/контактов, checkout подставляет «Tisch N».
  - Точки самовывоза (миграции tenants/0018 + orders/0011): `Tenant.pickup_locations`
    ([{name,address}], свойство `pickup_points`) + `Order.pickup_location` (снимок).
    Кабинет Orders — textarea «Name | Adresse» построчно; корзина при >1 точке —
    селектор «Pick up at» (скрыт при доставке), checkout валидирует выбор, 1 точка
    авто-применяется; вывод в подтверждении/кабинете/письме. **Лёгкая версия** —
    полные филиалы (своё меню/остаток/часы) отложены (roadmap).
  - **Отложено (roadmap §Отложено):** скидка от активной акции на плитке товара
    (требует, чтобы заказ Click&Collect тоже считал цену со скидкой — иначе
    расхождение; отдельный инкремент); автозаполнение форм брони/события вошедшим;
    полные филиалы.
  - **Деплой:** миграции tenants/0018 + orders/0011 (R1–R5 — без миграций).
- **Админка + кабинет — UX-переработка (✅ в `main`, S1+S2 `9c8da4d`, S3 `05ad375`,
  CI зелёный, без миграций):** платформенная админка `/admin` (django-unfold) была
  не настроена (словаря `UNFOLD` не было) → голый список приложений Django; tenant-
  разделы ломались на public-схеме. (unfold сам подменяет `admin.site` на
  `UnfoldAdminSite` в своём app-ready, поэтому `SIDEBAR`/`DASHBOARD_CALLBACK` читаются.)
  - S1 конфиг + чистка: `UNFOLD` в `config/settings/base.py` — брендинг (акцент
    indigo, как кабинет), `SITE_*`, сгруппированный сворачиваемый мобильный сайдбар
    (Geschäfte / Aggregator / Support / Plattform), только SHARED-модели. Tenant-
    модели (catalog, promotions) сняты с регистрации в public-админке (их таблиц нет
    в схеме) — снятие в `CoreConfig.ready()` ПОСЛЕ `admin.autodiscover`
    (`apps/core/admin.py::tidy_platform_admin`; apps.core грузится позже этих TENANT-
    приложений, поэтому на уровне импорта снять нельзя).
  - S2 KPI-дашборд: `apps/core/admin_dashboard.py::dashboard_callback`
    (`UNFOLD["DASHBOARD_CALLBACK"]`) + `templates/admin/index.html` (переопределяет
    пакетный index unfold) — карточки Betriebe / Aktive Abos / Im Test / Offene
    Tickets (+ алерт при past_due/trial_expired/suspended) и списки «Neueste
    Betriebe» / «Offene Tickets». Все данные — SHARED-модели на public. **Урок:**
    классы в `templates/admin/index.html` — только из скомпилированного CSS unfold
    (нет JIT: `sm:`-сетки нет, есть `md:`/`lg:`; токены base/primary/font-*).
  - S3 кабинет: `templates/tenant/_base_dashboard.html` — иконки модулей
    (`ModuleSpec.icon`) у пунктов + групп-заголовки (`label_de`) для многопунктовых
    модулей; адаптивность (бургер/оверлей) без изменений.
  - Шаблоны витрины под тип бизнеса — **вынесены вперёд как ранний срез M20**
    (решение владельца 2026-06-15, см. отдельный пункт «Шаблоны витрины» ниже);
    полноценный drag-drop конструктор остаётся Stage 3.
  - Тесты `apps/core/tests/test_admin_dashboard.py` + `test_cabinet_nav.py`. Без
    миграций → деплой обычный (`deploy.sh single`), новых зависимостей нет.
- **Шаблоны витрины — галерея (ранний срез M20, ✅ в `main`, CI зелёный, без
  миграций):** на `/dashboard/site/` сверху галерея из 5 готовых раскладок под тип
  бизнеса/архетип (`apps/tenants/sitetemplates.py`): Klassischer Laden · Café &
  Restaurant · Dienstleister & Termine · Übernachtung & Gastgeber · Minimal.
  Шаблон = пресет `site_config` поверх секционного движка Track C2 (набор/порядок
  секций + дефолтные hero/about). `apply_template` переписывает раскладку, **пустые
  тексты заполняет, непустые тексты владельца и onboarding не трогает**, и выставляет
  ВСЕ известные секции явно (иначе `siteconfig.normalize` дописал бы выключенные со
  своим дефолтом-вкл). Рекомендованные типу — первыми, с бейджем. Полноценный
  drag-drop конструктор — по-прежнему Stage 3. Тесты
  `apps/tenants/tests/test_sitetemplates.py`.
  - Акцентный цвет + стиль hero: каждый шаблон несёт `accent` (→ `Tenant.primary_color`)
    и `hero_style` (`plain`/`accent`); витрина `_base.html` задаёт `--accent` из
    primary_color, `sections/_hero.html` рисует цветной баннер при `hero_style=accent`.
    Гейтим цветной фон ФЛАГОМ `hero_style`, а не самим primary_color (у легаси он
    `#000000` → без флага витрина как раньше, без регрессии). `siteconfig.normalize`
    добавил `hero_style` (default `plain`). Кабинет «Site»: палитра цвета + чекбокс
    «цветной баннер» в форме hero (валидация `#rrggbb`); фото-hero — на будущее.
  - Хотфикс S3: многострочный `{# … #}` в `_base_dashboard.html` Django НЕ считает
    комментарием — текст утекал в сайдбар; заменён на `{% comment %}…{% endcomment %}`
    + регрессия в `test_cabinet_nav.py`. **Урок: многострочные шаблонные комментарии —
    только `{% comment %}`, `{# #}` строго однострочный.**
- **M20 UX-итерация — конструктор/демо/навигация (в работе, ветка
  `claude/stage1-finish-tkf22i`; запрос владельца 2026-06-15, порядок ③→④→⑤):**
  - ①② прокрутка + информативность (✅ `3b521f1`, без миграций): сайдбар кабинета
    `_base_dashboard` получил `overflow-y-auto/overscroll-contain` (на мобильном
    нижние пункты больше не обрезались); галерея шаблонов `/dashboard/site/` —
    мини-превью раскладки (стопка блоков в порядке секций, hero акцентом) вместо
    голых чипов.
  - ③ демо-контент (✅ `7d38333`, без миграций): `apps/tenants/demo.py` —
    `load_demo` создаёт показательный каталог (категория + 3-4 товара по типу
    бизнеса, fallback для прочих) + активную демо-акцию; id в `site_config["demo"]`
    (normalize теперь хранит ключ `demo`, как `onboarding`). `clear_demo` —
    hard-delete (all_objects) ровно их + зачистка листинга агрегатора; чужое не
    трогает; идемпотентно. Кнопки «Demo laden/löschen» на «Site» (отдельно от
    шаблона — решение владельца). Тесты `test_demo`.
  - ④ конфигуратор навигации витрины (✅ `12bd2f3`, без миграций): `site_config.nav`
    (`style` classic/centered/minimal + `sticky` + пункты с порядком/вкл).
    Реестр `siteconfig.NAV_ITEMS`; `context._storefront_nav` резолвит готовые
    пункты (включённые ∩ активный модуль, в порядке владельца); `_base.html` —
    шапка по стилю + **мобильный бургер** (раньше ссылки теснились); кабинет
    «Site» → fieldset «Navigation menu». Легаси без `nav` → classic/sticky/все
    включены (без регрессии). Тесты `test_nav`.
  - ⑤a контент-секции (✅ `c2aa18f`, без миграций): новые секции `cta`/
    `testimonials`/`faq` в реестре (по умолчанию ВЫКЛ → легаси не затронут);
    `normalize` санитайзит контент (faq/testimonials — пары, cap 12; cta —
    title/text/button), helpers `pairs_to_text`/`text_to_pairs`. Шаблоны
    `storefront/sections/_cta|_testimonials|_faq.html` (CTA — акцентный баннер,
    FAQ — нативный `<details>`). Кабинет «Site» — построчный ввод `A | B` для
    FAQ/Testimonials + 4 поля CTA. Тесты `test_content_sections`.
  - ⑤b фото-галерея (✅ `0c0a054`, без миграций): секция `gallery` (по умолчанию
    выкл); хранится FileRef-списком в `site_config["gallery"]` (БЕЗ новой модели —
    переиспользует `catalog.images.save_product_image`/`delete_stored_image`,
    Pillow-валидация + storage, cap 24). Секция `_gallery.html` (адаптивная
    сетка); кабинет — отдельная multipart-форма загрузки + миниатюры с удалением.
    **Фикс:** несубмиченный порядок секции → в конец (default 999), не в начало.
    Тесты `test_gallery` (+ правка `test_siteconfig` под новый набор секций).
  - **M20-итерация ①–⑤ закрыта** (без миграций). Осталось опц.: drag-drop порядка
    секций (владелец выбрал «позже»), фото-hero. Деплой — обычный (без миграций).
- **Демо-сайты по архетипам (showcase, в работе; решение владельца 2026-06-15/16):**
  отдельные демо-тенанты на субдоменах с полным наполнением.
  - hero-фото (✅ в `main`): `site_config.hero_image` (URL) → фон-баннер; full-bleed
    + ~⅓ экрана; витрина шире (`max-w-7xl`); страница брони тематична (акцент).
  - Фреймворк китов (✅ в `main`, `apps/tenants/demo_kits.py`): `DemoKit` + хелпер
    тематичных фото `demo_image` (loremflickr, внешний — решение владельца) +
    кит «Restaurant» (4 кат., 30 блюд с фото/вариантами/аллергенами, акции,
    галерея, FAQ, отзывы, CTA, **бронь столика** Resource+расписание, команда,
    «как мы работаем», знаки доверия, часы); `apply_kit` собирает каталог+
    site_config; команда `seed_demo_tenants [--kit/--recreate/--delete]` (reuse
    create_business) → `<kit>-demo.<base>`. Логин `<kit>-demo@example.de` /
    `demo-12345678`. Тесты `test_demo_kits`.
- **Конструктор витрины-из-архетипов (S1–S8 + D, ✅ ветка
  `claude/restaurant-site-features-egvl5p`, CI зелёный, миграция только
  promotions/0016):** превращает готовые архетипы в компонуемый конструктор —
  каждый модуль живёт сам по себе ИЛИ собирается на одной витрине; главная кратко
  агрегирует разделы. Решение владельца: «по правильному» на базе реестра модулей
  (лёгкое, масштабируется — новый архетип подключается одной декларацией).
  - **S1** витринный слой реестра: `ModuleSpec.storefront_*` (label/blurb/landing/
    icon/teaser) + `modules.storefront_archetypes(tenant)` — источник правды для
    тизеров и меню. **S2** секция «Unsere Bereiche» (сетка тизеров активных
    архетипов, оверрайды `site_config["archetypes"]`) + **отдельный конструктор
    главной** `/dashboard/site/home/` (порядок/видимость блоков). **S3** обложки
    разделов: intro+hero (a) + галерея на раздел (b) — рендер в `_base.html` по
    `url_name` (`modules.archetype_by_landing`), кабинет `/dashboard/site/sections/`.
    **S4** режим корня `storefront_root` (standalone ↔ общая главная). **S5**
    публичная лояльность `/treue/` (loyalty стал архетипом). **S6** `Promotion.group`
    + `/aktionen/` с фильтром-чипами (Fastfood/Fertiggerichte). **S7** многоуровневое
    меню `site_config["menus"]` (top/bottom, дерево узлов archetype/category/
    promo_group/page/url/anchor/group, глубина 2; `apps/tenants/menu.py` резолвер
    с гейтингом; легаси `nav`→`menus` без регрессии) + витрина с подменю (hover) +
    визуальный JS-билдер `/dashboard/site/menu/`. **S8** страница «О компании»
    `/ueber-uns/`.
  - На `/dashboard/site/` — карточки-ссылки Homepage builder / Navigation menu /
    Section covers + блок Design (шрифт, quick-add); старый плоский nav-редактор
    убран (меню правится в билдере). Всё на коде+JSON.
  - **D** демо-кит «Pranasy» (vegan Fastfood, `subdomain="pranasy"` →
    pranasy.<base>): Fastfood/Fertiggerichte, группы акций, бронь столика, события-
    ретриты, Catering/Vorbestellung (jobs), лояльность, многоуровневое меню с
    подменю, обложки разделов, секция «Bereiche». DemoKit += enable_archetypes_section/
    archetype_covers/menus/group_promos_by_category/storefront_root/subdomain (пустые
    → старое поведение, Restaurant-кит не затронут). Деплой демо:
    `manage.py seed_demo_tenants --kit pranasy` (+ DNS/Caddy для pranasy.siteadaptor.de).
  - Урок: новая секция в `siteconfig.SECTIONS` → обновить хардкод-список в
    `test_siteconfig`; оверрайды архетипа (S2/S3) с exact-match в тестах — дописывать
    новые поля; после правок шаблонов с новыми классами — `npm run build:css`.
  - Дальше (отложено): визуальный drag-drop/inline-редактор (заложена основа —
    JSON-схема + реестр секций + live-preview-эндпоинт следующим этапом).
- **Модернизация витрины (тренды 2025–2026; deep-research → план P1–P5; в работе):**
  направления: F производительность/CWV, C мобильная конверсия, A+B шрифты+
  анимации, D+E тёмная тема+доверие. Порядок «всё по порядку».
  - **P1 мобильная конверсия (✅ в `main`):** P1a — липкий мобильный action-bar
    (`context._storefront_actions`: звонок tel: / главное действие по модулю /
    маршрут; `_action_bar.html`, fixed bottom, цели ≥56px). P1b — структурные
    часы `Tenant.opening_hours_structured` (миграция tenants/0016) +
    `apps/tenants/openinghours.py` (open_status/today_label) + live-бейдж
    `_open_badge.html` «Jetzt geöffnet/geschlossen» в контактах + редактор 7 дней
    в кабинете «Settings». Тесты `test_action_bar`, `test_opening_hours`.
  - **P2 типографика+анимации (✅ ветка):** P2a — `site_config.font`
    (system/serif/rounded, ТОЛЬКО системные стеки → GDPR-safe; Google Fonts через
    CDN = риск GDPR в DE, источник в research) + `siteconfig.FONTS/font_stacks` →
    CSS-переменные `--font-body/--font-head`; выбор шрифта в «Site». P2b —
    scroll-reveal (IntersectionObserver под `.js-reveal`, head-скрипт без
    мигания; gating `prefers-reduced-motion` = WCAG 2.3.3) + hover-lift карточек
    (`motion-safe:`). Тесты `test_typography`.
  - **P3 доверие (✅ ветка):** секция `trust` (выкл по умолч.): авто-звёзды из
    SHARED `BusinessRating` (тег `business_rating`) + «Seit …» + знаки
    (Meisterbetrieb/Bio/TÜV); кабинет-редактор. **Тёмная тема (D+E) перенесена в
    P5** — чистое покрытие `dark:` только со сборкой Tailwind (сейчас CDN).
  - **P4 контент (✅ ветка):** секции `process` («как мы работаем», нумерованные
    шаги) и `team` (имя/роль/фото); кабинет-редакторы; в демо-ресторане включены.
  - **P5 производительность/CWV (в работе):**
    - P5a Tailwind-сборка вместо CDN (✅ в `main`, `0252db4`, CI run 353 зелёный,
      без миграций): витрина/кабинет/агрегатор грузили `cdn.tailwindcss.com` (JIT
      в рантайме — бьёт по Core Web Vitals) → собранный purged CSS. `package.json`
      (`npm run build:css`) + `tailwind.config.js` (content `templates/**`+`apps/**/
      templates/**`, `darkMode:"class"` под тёмную тему) + `static/src/app.css`
      → минифицированный `static/css/app.css` (артефакт коммитим — прод без Node).
      4 base-шаблона: `<script cdn>` → `<link {% static 'css/app.css' %}>`. CI:
      Node 22 + `npm ci` + `npm run build:css` + `git diff --exit-code` (гейт
      свежести). `test.py`: `STORAGES["staticfiles"]=StaticFilesStorage` (тесты
      рендерят `{% static %}` без collectstatic). `.gitignore`: `node_modules/`.
    - P5b responsive images (✅ ветка): hero-фото = LCP, но `background-image`
      браузер находит поздно → `<link rel=preload as=image fetchpriority=high>` в
      `<head>` витрины (контекст `storefront_hero_preload`: URL только при
      включённой секции hero); главное фото товара `fetchpriority=high
      decoding=async` (LCP страницы товара, eager); карточки/галерея/промо/листинги
      агрегатора/команда — `decoding=async` к уже стоявшему `loading=lazy`. Тесты
      `test_responsive_images`. Без resize-пайплайна (одно хранимое фото) `srcset`
      по плотностям отложен — нужен генератор миниатюр.
    - P5c тёмная тема витрины (✅ ветка): `darkMode:"class"`. Вместо `dark:`-
      вариантов в ~40 шаблонах — **централизованная карта переопределений** в
      `static/src/app.css` (`.dark .bg-white{…}` и т.п.; специфичность `.dark .x`
      (0,2,0) > утилиты (0,1,0)). Класс `.dark` ставит только витрина (no-FOUC
      init в `<head>`: localStorage `sf-theme` → системная тема), кабинет/
      агрегатор грузят тот же CSS, но `.dark` не выставляют → светлые.
      Переключатель ☀️/🌙 в шапке (persist в localStorage). Карта покрывает фон/
      текст/границы/плашки сообщений; акценты (var(--accent)/indigo) не трогаем.
      Тесты `test_dark_mode`. **P5 закрыт (a+b+c).**
    **Урок:** новая секция в `siteconfig.SECTIONS` → обновить хардкод-список в
    `test_siteconfig::test_normalize_empty_gives_defaults`. **Урок:** Google Fonts
    только self-host (GDPR DE). Деплой P1: tenants/0016; P5 — без миграций.
- **A2 Versand → 100% (✅ ВЕСЬ в `main`; Stage 1 архетип A2 ~85 %→~100 %):** добили
  доставку поверх готового G4 (apps.orders). Разбивка A2a/A2b/A2c:
  - A2a — PLZ-зоны + отдельный мин самовывоза (✅ в `main`, CI зелёный, миграция
    tenants/0015): `Tenant.delivery_zones` (JSON `[{plz,fee_cents,free_cents,
    min_cents}]`) + `delivery_restrict_to_zones` + `pickup_min_cents`. `services.
    delivery_quote(tenant, subtotal, plz)` — зона с самым длинным совпавшим PLZ-
    префиксом переопределяет плоский тариф/порог/мин; при restrict и непустых зонах
    без совпадения → `deliverable=False`; `shipping_cost` стал обёрткой (обратная
    совместимость, 2 арг.). Витрина checkout: недоставляемый PLZ → отказ, отдельная
    проверка Mindestbestellwert для самовывоза. Кабинет заказов: таблица зон (6
    строк) + чекбокс «только эти PLZ» + мин самовывоза. Тесты `test_delivery`.
  - A2b — Lieferschein-PDF + адресная этикетка (✅ в `main`, CI зелёный, без
    миграций): `apps/orders/pdf.py::build_delivery_note_pdf` (reportlab, зеркало
    jobs.pdf) — шапка-отправитель из Tenant, получатель/адрес из Order, позиции
    (кол-во + название, без цен) + вырезаемая адресная этикетка; вьюха
    `delivery_note_pdf` + маршрут `…/lieferschein.pdf` + кнопка в карточке заказа.
  - A2c — возвраты/Widerruf (✅ в `main`, CI зелёный, миграция orders/0007):
    `Order.STATUS_RETURNED`; `OrderSM` picked_up/shipped → returned. on_transition
    returned → возврат остатка (общий `_restore_stock`, R3) + **сторно выручки**
    (`finance.services.record_reversal` — отрицательная запись, source_ref
    `{id}:return`, идемпотентно → нетто 0) + письмо клиенту (`order_returned`).
    Кабинет: кнопка «Mark as returned» (из allowed_targets), оплаченный заказ →
    Stripe-refund (как отмена). Тесты `test_delivery`.
  - **A2 завершён (a+b+c).** Деплой: миграции tenants/0015 + orders/0007.
- **A7 Handwerker → 100% (в работе; Stage 1 архетип A7 ~85 %→):** добиваем смету/
  Auftrag поверх apps.jobs. Разбивка A7a–d:
  - A7a — дробные часы/единицы (✅ в `main`, CI зелёный, миграция jobs/0003):
    `JobLine.qty` → Decimal(7,2); `finance.compute_totals` считает qty как Decimal
    (через `_to_decimal`; целочисленные вызовы не затронуты); `lines_snapshot`
    отдаёт qty строкой (JSON-safe в `Invoice.lines`); `finance.pdf`/`jobs.pdf`
    рендерят qty без хвостовых нулей; кабинет — input `step=0.01`, парс Decimal
    0,01..9999; `commit_stock` (G11) списывает `ceil(qty)` (склад целочисленный).
    Тесты `test_jobs_core` (3,5 Std × 50 = 175).
  - A7c — онлайн-Anzahlung за смету (✅ в `main`, CI зелёный, миграция jobs/0004):
    зеркало P2.5b. `Job.deposit_cents`/`payment_state`/`stripe_payment_intent`;
    `apps/jobs/payments.py` — `deposit_checkout_url` (Checkout на connected account
    бизнеса, metadata `kind=job_deposit`, вариант B → application_fee=0) +
    `mark_deposit_paid` (вебхук кросс-схемно: paid + принятие сметы quoted→accepted,
    идемпотентно). Ветка `job_deposit` в `apps/billing/webhooks.py`. Публичное
    Angebot: при депозите + `payments_enabled` + Connect «Annehmen» → Stripe
    Checkout (принятие — после оплаты), иначе прямой accept. Кабинет сметы: поле
    Anzahlung (€) + бейдж paid. Тесты `test_public`.
  - A7b — фото к заявке (✅ в `main`, CI зелёный, миграция jobs/0005): модель
    `JobPhoto` (FK Job, ImageField `job_photos/%Y/%m/`); публичная `/anfrage/` —
    multipart-форма, до 5 изображений ≤8 МБ (`services.add_job_photos` фильтрует
    по content_type/размеру); кабинет сметы показывает миниатюры. Тесты
    `test_public` (фото создаётся; не-изображение отброшено).
  - A7d — привязка Termin↔Job (✅ в `main`, CI зелёный, миграция jobs/0006):
    `Job.booking` FK → `booking.Booking` (SET_NULL); кабинет сметы — привязать/
    отвязать выездной Termin клиента (выпадающий список броней этого клиента),
    показ даты/кода привязанной записи. Тест `test_cabinet` (link/unlink).
  - **A7 завершён (a+b+c+d) → архетип A7 ~85 %→~100 %.** Деплой: миграции
    jobs/0003+0004+0005+0006.
- **P2.7 — поиск/фильтры в агрегаторе (A8, ✅ в `main`, CI зелёный, без миграций):**
  `listings_for(…, q=)` — текстовый поиск по business_name + title (JSON icontains) +
  city; `discover_index` стал страницей результатов при `?q=`/`?city=`/`?type=`
  (featured сверху + keyset-пагинация, base_qs сохраняет фильтры в «More»; без
  параметров — прежний индекс городов; cache_public_page кэширует только GET без
  query, поэтому результаты не кэшируются). Общий партиал `_search_form.html`
  (поиск + город + тип) на индексе и в результатах `search.html`. Тесты
  `aggregator/test_search`. **A8 ~85 %→~95 %** (единая корзина — Stage 3).
- **A9 — поле Fahrzeug/Kennzeichen на Job (✅ в `main`, CI зелёный, миграция
  jobs/0007):** Werkstatt — `Job.vehicle` (свободный текст «VW Golf · M-AB 1234»);
  поле в публичной `/anfrage/`, ручной заявке и форме сметы кабинета + показ в
  карточке. `create_job(vehicle=)`. Тест `test_cabinet`. **A9 ~95 %→~100 %**
  (опц. подменный авто — отложено).
- **A1 — EAN/GTIN (✅ в `main`, CI зелёный, миграция catalog/0006):** `Product.gtin`
  + `ProductVariant.gtin` (штрихкод); поле в форме товара (ProductForm) и в строках
  вариантов; Google-фид отдаёт `g:gtin` (вариантный перебивает товарный) и
  `identifier_exists` учитывает gtin. Галерея фото в кабинете уже была (мульти-
  загрузка + primary/delete). Тесты `catalog/test_feed`. **A1 ~95 %→~99 %**
  (остаётся опц. массовый импорт вариантов CSV).
- **A1 — массовый импорт вариантов из CSV/Excel (✅ в `main`, без миграций):**
  новый `ProductVariantProcessor`
  (`resource_type=product_variant`) в wizard'е `apps.imports`: родитель ищется по
  `product_sku`/`product_name_de`, вариант — upsert по (товар, label) (естественный
  ключ R1 `variant_product_label_uniq`, повтор импорта не плодит дубли); поля
  label/sku/gtin/price(пусто=base_price)/content_amount/stock/is_active. `VARIANT_FIELDS`
  + пункт «Produktvarianten» в выборе ресурса импорта. Тесты `imports/
  test_variant_processor`. **A1 ~99 %→~100 %.**
- **A3 — онлайн-продажа Mehrfachkarte + привязка к курсу (✅ в `main`, CI зелёный,
  миграция booking/0006):** `PassPlan` (покупаемый тариф: label/credits/price_cents/
  valid_days/service) + `Pass.service` (привязка карты к услуге) + `Pass.
  stripe_payment_intent` (идемпотентность выпуска). `pass_payments`: зеркало P2.5b —
  `pass_checkout_url` (Checkout на connected account, metadata `kind=pass_purchase`)
  + `purchase_pass` (вебхук кросс-схемно: выпуск Pass + письмо с кодом, идемпотентно
  по payment_intent). `redeem_pass` гасит бронь только совпавшей услуги (карта с
  `service` ≠ бронь другой услуги → PassInvalid). Витрина `/karten/` (список тарифов
  → форма имя/почта → Stripe; иначе «купить на месте») + ссылка с `/termin/`. Кабинет
  `/dashboard/booking/karten/`: CRUD тарифов (+ привязка к услуге). Тесты `test_passes`.
  **A3 ~95 %→~100 %.**
- **Бэклог из аудита китов #1–#7 (✅ ВЕСЬ в `main`, ветка
  `claude/restaurant-site-features-egvl5p`, CI зелёный):** закрытие пробелов
  showcase-китов (baseline — `docs/kit-archetype-coverage.md`).
  - #1 retail-кит `shop` (Hofladen, A1/A2): варианты/Grundpreis/остаток/GTIN/Versand-зоны.
  - #2 обогащение демо: hotel (депозит+сезон), friseur (Mehrfachkarte).
  - #3 ценовые тиры билета (Frühbucher/Standard/Kind) — `Event.tiers`, миграция events/0004.
  - #4 выбор конкретного мастера/ресурса на `/termin/`.
  - #5 ЛК клиента включён в friseur/werkstatt/retreat-китах.
  - #6 блок отзывов на витрине бизнеса (+демо-отзывы).
  - #7 **универсальные Extras** (`apps.core.Extra`, миграция core/0002): один движок
    доп-услуг к брони на все архетипы (scope stays/booking/events/all, per_night),
    `apps/core/extras.py` (active_for/snapshot/total_cents), кабинет `/dashboard/extras/`.
    Подключено к stays (StayBooking.extras, stays/0007), booking (Booking.extras,
    booking/0007, finance по total_cents), events (Ticket.extras, events/0005,
    оплата/auto-confirm по total). Общий партиал `storefront/_extras.html`. Демо:
    hotel/friseur/retreat. Деплой #1–#7: миграции events/0004, core/0002, stays/0007,
    booking/0007, events/0005 + кит `shop` (seed_demo_tenants) + DNS shop.<base>.
- **Оптимизация документации (✅ 2026-06-22):** CLAUDE.md §3 (1236 строк истории)
  извлечена в `docs/build-log.md` (этот файл) — CLAUDE.md 1377→~170 строк (быстрее
  грузится как память проекта). Добавлен `docs/audit-2026-06-22.md` (срез/оценка),
  `kit-archetype-coverage.md` помечен закрытым. Конвенция: новые инкременты — строкой сюда.
- **Рефактор ядра — apps.loyalty (✅ в `main`, `3c9242d`, CI зелёный, миграции
  promotions/0017 + loyalty/0001 state-only):** штампы+ваучеры (Voucher/
  LoyaltyProgram/LoyaltyCard/StampEvent) вынесены из перегруженного promotions
  (8→4 модели) в новое TENANT-приложение apps.loyalty. db_table сохранены
  (promotions_*), перенос через SeparateDatabaseAndState БЕЗ DDL (данные тенантов
  целы). Customer — общая идентичность, остаётся в promotions. Сервисы/вьюхи
  лояльности пока в promotions (импортируют модели из loyalty). 1143 теста зелёные.
- **M20 WYSIWYG-билдер (✅, начало этапа M20):** инлайн-правка текста перенесена со
  страницы Preview в сам конструктор главной (`site_home.html`): клик по заголовку/
  тексту в live-preview-iframe → contenteditable → save на blur (`site-inline-edit`).
  Ревизия показала: live-preview + drag-drop порядка секций + inline hero/about уже
  были в коде (M20a/b). Инлайн-правка расширена на секцию **CTA** — вложенные поля
  `cta.title`/`cta.text` через белый список `siteconfig.NESTED_TEXT_FIELDS` (dotted
  path в `site_inline_edit`), `data-edit` в `_cta.html`. Тесты test_inline_edit
  (nested save/reject + cta-маркеры). Без новых моделей. Осталось по M20: палитра
  секций + панель свойств в билдере (M20d), медиа (M20e), тема вживую (M20f).
- **M20f — тема вживую (✅):** контролы дизайна (акцент-цвет / шрифт / стиль hero)
  добавлены в конструктор `site_home.html` с live-preview. Ключевое: context-
  процессор `modules_nav` сделан preview-aware — под `?preview=1` шрифт/hero/акцент
  берутся из черновика сессии (раньше превью отражало только секции/тексты, не
  дизайн). Акцент = поле Tenant.primary_color → в черновике override `_accent`,
  `_base.html` берёт `storefront_accent|default:primary_color`. site_preview_draft
  принимает font(FONTS)/hero_style(HERO_STYLES)/accent(hex); home_builder_view
  сохраняет font+hero_style в site_config и accent в Tenant.primary_color. Тесты:
  draft includes/rejects design, modules_nav preview, home_builder saves design.
- **M20d — свойства секций в билдере (✅):** контент-секции (CTA/Testimonials/How-it-
  works/Team/Trust/FAQ) вынесены в общий партиал `tenant/_section_fields.html` и
  теперь правятся прямо в конструкторе главной (`site_home.html`), не только на «Site».
  Единый парсер `siteconfig.parse_content_sections(get)` (+ список `CONTENT_FIELDS`)
  используется тремя точками: формой «Site» (рефактор — без дублирования логики),
  `home_builder_view` (сохранение) и `site_preview_draft` (live-preview, с presence-
  guard — отсутствие полей не трёт сохранённое). collect() в билдере шлёт контент-поля.
  Тесты: builder сохраняет cta/faq/testimonials, draft отражает/не-трёт, site_view-
  рефактор покрыт test_content_sections. Осталось по M20: M20e (медиа в билдере).
- **M20e — медиа в билдере (✅):** загрузка/удаление фото галереи прямо в конструкторе
  главной (`site_home.html`) — отдельные multipart-формы (action=upload_gallery/
  delete_gallery_image в `home_builder_view`), общие хелперы `_upload_gallery_images`/
  `_delete_gallery_image` с «Site» (Pillow-валидация, FileRef в site_config.gallery).
  Левая колонка билдера обёрнута, превью-колонка не задета. Тест:
  test_home_builder_gallery_upload_and_delete. **M20 закрыт по основным слоям.**
- **H1 — тарифы отеля (Rate Plans) + питание (✅, A5/hotel):** новая модель
  `stays.RatePlan` (на тенанта, применима ко всем номерам): `percent_adjust` (±%),
  `surcharge_cents` (надбавка за ночь, напр. завтрак), `meal_plan` (ohne/Frühstück/
  Halb-/Vollpension), `cancellation` (flexibel/nicht erstattbar + `free_cancel_days`),
  `is_active`/`sort_order`. `pricing.apply_rate_plan` (процент → надбавка, клампим в 0)
  + `quote_total_cents(rate_plan=…)`. `services.book_stay(rate_plan=…)` пишет FK
  (`StayBooking.rate_plan`, SET_NULL) + снимок `rate_snapshot` (несёт модификаторы для
  пересчёта); `move_stay` пересчитывает по живому RatePlan или из снимка. Витрина
  `/unterkunft/<unit>/`: выбор тарифа (radio) с ценой за диапазон + условия отмены/
  питание ВИДНЫ до брони (ТЗ §20); подтверждение `/s/<code>/` показывает выбранный
  тариф. Кабинет `/dashboard/stays/units/`: секция «Rate plans» (CRUD + toggle).
  Demo-kit `hotel`: 4 тарифа (Basis/Frühstück/Halbpension/Sparpreis nicht erstattbar),
  применены к демо-броням. Миграция `stays/0008`. Тесты: `test_rate_plans.py` (pricing,
  снимок, extras-сумма, move с живым тарифом и из снимка после удаления). План —
  `docs/hotel-archetype-plan.md` (H1 из H1–H8).
- **H2 — поиск размещения с главной + список доступных номеров (✅, A5/hotel):**
  `/unterkunft/` теперь принимает диапазон (von/bis/gaeste) и показывает ВСЕ номера
  с доступностью и ценой «ab …€ total» за выбранный период (дешёвый тариф H1 →
  cheapest; недоступные — с причиной min_nights/guests/занято, серым). Доступные —
  вперёд, дешевле сверху; карточка — диплинк на номер с прокинутыми датами.
  Один юнит без дат — прежний редирект; с датами — остаётся на результатах. Новая
  секция главной `stay_search` (реестр `siteconfig.SECTIONS`, партиал
  `sections/_stay_search.html`, гейт `storefront_stays_enabled`) — быстрый поиск под
  hero (ТЗ §2.1); demo-кит `hotel` включает её (`_kit_sections` при `stay_units`).
  Тесты: `test_public` (поиск листит доступные с итогом, один юнит с датами не
  редиректит), `test_siteconfig` (порядок реестра с `stay_search`). План — H2.
- **H3 — богатая карточка номера + похожие номера (✅, A5/hotel):** `StayUnit`
  получил `area_sqm` (м²), `bed_type` (свободный текст) и `amenities` (список ключей
  из каталога `stays.models.AMENITIES`: WLAN/TV/Bad/Balkon/Klima/Küche/Parkplatz/
  Haustiere/Barrierefrei…). Витрина номера: блок «ключевые факты» (гости/площадь/
  кровать) + сетка иконок Ausstattung (`unit.amenity_badges`); условия отмены/питание
  уже видны до брони из H1. Добавлен блок «Similar rooms» (другие активные юниты, тот
  же тип вперёд, до 3; диплинк с датами). Кабинет `/dashboard/stays/units/`: поля
  площади/кровати + чек-лист удобств в формах создания и настройки. Demo-кит `hotel`:
  у 4 номеров заполнены area/bed/amenities. Миграция `stays/0009`. Тесты —
  `test_rooms.py` (порядок/фильтр бейджей, рендер фактов+Ausstattung, похожие номера
  тем же типом вперёд, отсутствие блока у одиночного). План — H3.
- **H5 — гости: взрослые + дети (✅, A5/hotel, минимально):** `StayBooking.adults`/
  `children` (вместимость = adults+children ≤ max_guests); `guests` остаётся итогом
  для совместимости. `book_stay(adults=, children=)` (фолбэк на legacy `guests`).
  Витрина (поиск на `/unterkunft/`, секция главной, форма номера) и диплинки — поля
  «Erwachsene»/«Kinder» (`erw`/`kinder`, фолбэк `gaeste`). Подтверждение показывает
  разбивку. БЕЗ возрастных тарифов (ТЗ §5.2). Миграция `stays/0010`.
- **H9 — Kurtaxe / Tourismusabgabe (✅, A5/hotel, DACH-обязательное):** настройка на
  тенанта `stays.StaySettings` (синглтон, `load()`): сбор за взрослого за ночь
  (`kurtaxe_cents`, дети бесплатно). `pricing.kurtaxe_total_cents(adults, nights)`;
  `book_stay`/`move_stay` считают и кладут снимок `StayBooking.kurtaxe_cents`, сумма
  включена в `total_cents`. Витрина: «inkl. X € Kurtaxe» в котировке и подтверждении.
  `stay_to_invoice` выставляет Kurtaxe отдельной строкой без 7 % (durchlaufender
  Posten; база Beherbergung = итог − Kurtaxe). Кабинет `/dashboard/stays/units/` —
  карточка настройки Kurtaxe. Demo-кит `hotel`: 2,50 €/Erw./Nacht. Тесты —
  `test_kurtaxe.py` (разбивка гостей, вместимость, legacy-контракт, расчёт сбора,
  пересчёт при переносе, отдельная строка в счёте без НДС). План — H5+H9.
- **H4 — промокоды + самоотмена брони (✅, A5/hotel):**
  **H4a промокод:** переиспользован `apps.loyalty.Voucher` (percent/cents/min/лимиты)
  и атомарное гашение `promotions.services.redeem_voucher`. `book_stay(voucher_code=)`
  применяет скидку к проживанию+услугам (НЕ к Kurtaxe), кладёт снимок
  `StayBooking.discount_cents`/`voucher_code`, гасит ваучер в той же транзакции
  (откат при сбое); код задан, но не применим → `PromoInvalid`. Поле промокода на
  витрине брони, скидка видна на подтверждении. `move_stay` держит снимок скидки.
  **H4b самоотмена:** подписанная ссылка `/stornieren/<token>/` (signing, как iCal/
  unsubscribe) → страница с политикой отмены (из снимка тарифа H1) → POST отменяет
  через `StayBookingSM`; при бесплатной отмене (flexible до `free_cancel_days`) и
  оплаченном депозите — возврат через Stripe Connect. `services.cancellation_state`
  (can_cancel/free). Ссылка «Stornieren» в письмах created/confirmed и на
  подтверждении. Demo-кит `hotel`: промокод `SOMMER10` (−10 %). Миграция `stays/0011`.
  Тесты — `test_promo_cancel.py` (скидка не на Kurtaxe, гашение, невалидный/исчерпан,
  политика отмены flexible/non-refundable/неактивная, подпись токена). План — H4.
- **H6 — SEO (Hotel JSON-LD) + Hausordnung (✅, A5/hotel):**
  **SEO:** `core.seo.localbusiness_ld` расширен `price_range`/`image`; тег
  `localbusiness_jsonld` для отеля (активный stays) добавляет в `Hotel`-разметку
  `priceRange` («ab …€»/диапазон по активным номерам) и `image` (фото номера) —
  helper `_stays_seo`. Тип `Hotel`/гео/`aggregateRating` уже были (B5/G8).
  **Hausordnung:** `StaySettings.house_rules` (текст) + публичная страница
  `/hausordnung/` (гейт stays; пусто → 404), ссылка в футере витрины
  (`{% house_rules_present %}`), редактирование в кабинете
  `/dashboard/stays/units/` (объединённая карточка «Kurtaxe & house rules»).
  Demo-кит `hotel`: заполнены Check-in/out, Ruhezeiten, Haustiere, Rauchen,
  Kaution, Kinder, Stornierung. Миграция `stays/0012`. Тесты —
  `test_seo_hausordnung.py` (priceRange/image в JSON-LD; страница 200/404/гейт). План — H6.
- **H8a — агрегатор отелей (вертикальный портал «Hotelsuche») (✅, A5/hotel):**
  поверх готового движка порталов (`AggregatorPortal kind=vertical`,
  `business_type="hotel"`) и пула `KIND_STAY`. `portal_views._collapse_hotels`:
  для hotel-портала листинги номеров схлопываются в **одну карточку на отель**
  (дешевейший номер «ab …€», заголовок = имя отеля, `room_count` = типов номеров),
  не-stay карточки не трогаются, порядок сохраняется. Бейдж «N Zimmertypen» в
  `_cards.html`. `seed_demo_tenants` теперь после `apply_kit` вызывает
  `reconcile_schema` (материализация листингов в пул) и `_ensure_hotel_portal`
  (идемпотентно создаёт `hotels.<base>`), так что **одна команда после деплоя**
  поднимает и сайт отеля, и агрегатор. Тесты — `aggregator/tests/test_hotel_portal.py`
  (схлопывание: cheapest/порядок/не-stay; рендер портала — одна карточка на отель).
  Демо-дока — `docs/hotel-demo.md` §1/§5a. H8b (живой поиск по датам) — следующее.
- **H8b — живой поиск по датам на портале отелей (✅, A5/hotel — H8 закрыт):**
  модуль `aggregator/hotel_search.py`: `hotel_availability(schema, von, bis, guests)`
  идёт в схему отеля (`schema_context`), считает дешевейший свободный номер на
  диапазон (анти-овербукинг `range_available` + min_nights + вместимость + тарифы H1
  cheapest), кеширует в Redis (TTL 300 с). `portal_views.portal_home`: на hotel-портале
  форма Anreise/Abreise/Gäste; при датах — после схлопывания (H8a) фильтрует отели по
  доступности, ставит цену за диапазон (`range_total_eur`/`range_nights`) и диплинк в
  прямое бронирование с датами (`_with_dates`). `cache_public_page` пропускает кэш при
  непустом query → выдача всегда свежая. Шаблоны: форма в `portal_home.html`,
  «X € / N Nächte» в `_cards.html`. Тесты — `test_hotel_portal.py` (доступность:
  cheapest/занято/min_nights/вместимость; рендер портала с датами — фильтр+цена+диплинк).
  **H8 (агрегатор отелей) полностью закрыт; план H1–H9 выполнен (H7 свёрнут).**
- **G1 — Geschenkgutscheine (подарочные сертификаты) (✅, A5/hotel, growth):**
  новая `loyalty.GiftVoucher` (buyer/recipient/сумма/сообщение/payment_state/
  stripe_payment_intent/выпущенный `voucher`). `loyalty/gift.py`:
  `create_gift_voucher` (валидация суммы 10–2000 €), `mark_gift_voucher_paid`
  (вебхук, кросс-схемно, идемпотентно: выпускает `Voucher` фикс-сумма/1 исп. + письмо).
  Витрина `/gutschein/` (форма с пресетами → Stripe Connect Checkout → `/gutschein/danke/`),
  оплата подтверждается тем же вебхуком, что депозиты (`billing.webhooks`, kind=
  `gift_voucher`). Погашение — уже готовой механикой H4a (поле промокода в брони).
  Письмо покупателю (`emails/gift_voucher.txt`). Ссылка «🎁 Gutschein verschenken» на
  `/unterkunft/` при включённой онлайн-оплате. Гейт: stays + payments + Stripe Connect.
  Миграция `loyalty/0002`. Тесты — `loyalty/tests/test_gift.py` (валидация, выпуск+
  идемпотентность, погашение как промокод). План — `docs/hotel-growth-plan.md` (G1).
- **G2 — post-stay письмо + запрос отзыва (✅, A5/hotel, growth):** beat-задача
  `stays.tasks.send_stay_post_stay` (раз в сутки, по всем схемам) шлёт ровно одно
  письмо после выезда (`StayBooking.post_stay_sent_at`, окно подхвата 7 дней,
  только confirmed/fulfilled). Шаблон `emails/stay_post_stay*` — благодарность +
  приглашение бронировать напрямую + **ссылка на отзыв** (`_review_url`: страница
  бизнеса в hotel-портале, читается под `schema_context('public')`, best-effort).
  Pre-stay reminder уже был (E3). Расписание в `CELERY_BEAT_SCHEDULE`
  (`STAY_POSTSTAY_DAYS`, дефолт 1). Миграция `stays/0013`. Тесты —
  `test_post_stay.py` (одно письмо, окно, отмена/старое — пропуск). План G2.
- **G9 — отчёты загрузки/выручки (✅, A5/hotel, growth):** чистый модуль
  `stays/reports.py::occupancy_report(start, end)` — Belegung % (проданные/доступные
  ночи), ADR (Zimmer-Umsatz/ночь), RevPAR, Zimmer-Umsatz (итог − Kurtaxe − Extras),
  общий Umsatz; выручка через границы периода пропорциональна ночам; считаются
  pending/confirmed/fulfilled, отменённые/no-show исключены. Кабинет
  `/dashboard/stays/reports/` (помесячно, ←/→) + ссылка с календаря. Тесты —
  `test_reports.py` (occupancy/ADR, пропорция через край месяца, исключения
  Kurtaxe/Extras/cancelled) + рендер во `test_cabinet`. План G9.
- **G10 — booking-виджет/iframe для своего сайта отеля (✅, A5/hotel, growth):**
  режим `?embed=1` для витрины брони (`/unterkunft/`, номер, бронь, подтверждение):
  минимальный шаблон `storefront/_embed_base.html` (без шапки/футера/нав), ответ
  помечается `xframe_options_exempt` → встраивается на чужом домене несмотря на
  `X_FRAME_OPTIONS=DENY`. Параметр embed протаскивается через формы (hidden) и
  ссылки/редиректы (`embed_qs`, `_back_to_unit`, success/deposit). Кабинет
  `/dashboard/stays/units/` — карточка с готовым `<iframe>`-сниппетом (`embed_url`).
  Тесты — `test_embed.py` (chrome-less + frameable, проброс embed, обычный режим без
  exemption). План G10.

- **Hotel-демо: фикс утечки комментариев + полное меню (ТЗ §15).** Многострочные
  `{# … #}` (Django их НЕ поддерживает — утекают текстом на витрину) в
  `sections/_stay_search.html` и `_embed_base.html` заменены на
  `{% comment %}…{% endcomment %}`. В `home.html` секции обёрнуты якорями
  (`#buchen/#zimmer/#galerie/#bewertungen/#stimmen/#faq/#kontakt/#ueber-uns`,
  `scroll-mt-24`) — чтобы пункты меню типа `anchor` вели на разделы главной.
  `HOTEL_MENUS` расширено до полноценного меню отеля: Start / Zimmer & Preise /
  Galerie / Bewertungen / Hausordnung / FAQ / Über uns / Kontakt / Jetzt buchen
  (низ — таб-бар Zimmer/Galerie/Bewertungen/Buchen). Gutschein намеренно вне меню
  (404 без Stripe Connect). `npm run build:css` (добавлен `scroll-mt-24`).

- **Витрина: фикс нижнего таб-бара + лайтбокс галерей + чистые карточки номеров.**
  `_action_bar.html`: убран `backdrop-blur` (фильтр на fixed-баре вызывал
  «подпрыгивание» при инерционном скролле в iOS Safari) → непрозрачный фон +
  лёгкая тень; нижний отступ сжат до `max(2px, safe-area)`, спейсер считает
  высоту бара + safe-area (контент не прячется). Добавлен общий лайтбокс в
  `_base.html` (клик по `img[data-lightbox]` → фото на весь экран, закрытие
  фон/×/Esc); подключён в секции галереи (`_gallery.html`) и в галерее номера
  (`stay_detail.html`). Карточки номеров (`stay_index.html` поиск+обзор,
  «похожие» в `stay_detail.html`) переведены на единый бокс `aspect-[4/3]` +
  `bg-gray-100` + `object-cover` — без цветных полей/искажений на любой картинке
  и мобильных. `npm run build:css`.

- **Витрина отеля: 2-колоночная карточка номера, номера на главной, фикс билдера
  меню.** Карточка номера (`stay_detail.html`) переверстана в две колонки: слева
  галерея (кликабельна, лайтбокс), справа — название, цена и опции (выбор дат +
  тарифы + бронь, sticky на десктопе), описание/оснащение/похожие — ниже по
  ширине контейнера. Новая секция главной `stay_rooms` (реестр + партиал
  `_stay_rooms.html` + контекст home-view) — карточки номеров прямо на главной;
  включена в hotel-ките (вместо тизер-секции «Bereiche», теперь
  `enable_archetypes_section=False`). Списки номеров (`stay_index.html`, главная)
  растянуты на всю ширину контейнера (`grid-cols-1 sm:grid-cols-2 lg:grid-cols-3`,
  без `max-w-3xl`). Фикс билдера меню (`site_menu.html`): `.f-enabled` лежит
  внутри `<label>`, а `syncFromDom` искал его как прямого ребёнка
  (`:scope > div > .f-enabled`) → `querySelector` возвращал null и кидал ошибку,
  из-за чего сохранение меню не срабатывало вовсе. Теперь ищем по строке.
  `npm run build:css`. ⚠️ Секция «номера на главной» — изменение демо-кита →
  нужен reseed `--kit hotel --recreate`.

- **G4 — авто-скидки на проживание (LOS / Frühbucher / Last-Minute).** Надстройка
  над `pricing`/`RatePlan`, без параллельной инфраструктуры. Конфиг на тенанта в
  `StaySettings` (новые поля los_min_nights/los_discount_percent, early_bird_days/
  percent, last_minute_days/percent; 0 = выкл). `pricing.auto_discount()` считает
  лучшую (максимальную) применимую скидку на проживание (без Extras/Kurtaxe);
  промокод H4a применяется поверх. `book_stay`/`move_stay` считают и пишут снимок
  `StayBooking.auto_discount_cents` + `auto_discount_label` (включён в total).
  Витрина: «ab … €» в поиске и итог/тарифы на странице номера уже отражают скидку
  (показ = к оплате), подпись скидки на карточке номера и в подтверждении. Кабинет
  `/dashboard/stays/` — блок «Automatic discounts» в форме настроек. Демо hotel:
  7+ ночей −10 %, Frühbucher ≥30 дней −8 %, Last-Minute ≤3 дня −12 %. Миграция
  `stays/0014`. Тесты — `test_auto_discount.py`. ⚠️ Демо-конфиг → reseed `--kit
  hotel --recreate` (или задать в кабинете). План — G4 в `hotel-growth-plan.md`.

- **G7 — гибкая предоплата по тарифу (0 / частично / 100 %).** Поле
  `RatePlan.prepayment_percent` (0 = оплата на месте, 100 = полная Vorkasse).
  `pricing.prepayment_cents(total, rate)` — сумма онлайн-предоплаты от итога.
  В брони: предоплата по выбранному тарифу (если задана) → Stripe Checkout на счёт
  бизнеса; нет предоплаты → фолбэк на депозит юнита (E4). Витрина: на тарифе бейдж
  «X % deposit / Vorkasse · сумма €», общий note про оплату в след. шаге. Кабинет
  `/dashboard/stays/` — поле предоплаты в форме тарифа + бейдж в списке. Методы
  оплаты (PayPal/Klarna/Karte) Stripe Checkout предлагает автоматически по тому,
  что бизнес включил в своём Stripe-аккаунте (код методов не фиксирует). Демо: тариф
  «Sparpreis (nicht erstattbar)» → 100 % Vorkasse. Миграция `stays/0015`. Тесты —
  `test_prepayment.py`. ⚠️ Демо-конфиг → reseed `--kit hotel --recreate`.

- **G5 — мультикомнатное бронирование (семьи/группы).** Одна `StayBooking` с полем
  `rooms` (число номеров этого типа) вместо родитель-/дочерних броней — отмена и
  оплата работают как есть. Анти-овербукинг: `availability.range_available(...,
  needed=N)` суммирует `rooms` пересекающих броней и проверяет `quantity − занятость
  ≥ N` на каждую ночь; `occupancy_grid` тоже суммирует. `book_stay(rooms=N)`:
  вместимость `max_guests × N`, проживание × N (авто-скидка/предоплата считаются от
  итога × N; Kurtaxe — по гостям; депозит-фолбэк × N). Витрина: селектор «Zimmer»
  на странице номера (если quantity > 1), число номеров в подтверждении. Миграция
  `stays/0016`. Тесты — `test_multiroom.py`. План — G5 в `hotel-growth-plan.md`.

- **G6 — Online-Checkin + цифровой Meldeschein (BMG).** Модель
  `stays.GuestRegistration` (1:1 к брони): Ф.И.О., дата рождения, гражданство,
  адрес, тип/номер документа (иностранцы, §30 BMG), Mitreisende, простая подпись
  (Ф.И.О. печатью + время + IP). Публичный флоу по подписанной ссылке
  `/checkin/<token>/` (`storefront-stay-checkin`): форма с префиллом из брони →
  сохранение → статус «выполнено»; ссылка на странице подтверждения брони. Кабинет
  `/dashboard/stays/checkins/` — обзор заполненных Meldescheine. Retention (DSGVO,
  хранение 1 год): beat `purge_old_registrations` (ежедневно) удаляет записи >365
  дней после выезда. Миграция `stays/0017`. Тесты — `test_checkin.py`. План — G6.

- **G8 — фид цен/наличия для метапоиска (Google Free Booking Links).** Публичный
  машиночитаемый эндпоинт `/stays/feed.json` (`storefront-stay-feed`): на каждый
  активный номер — посуточно на 60 дней вперёд число свободных юнитов и базовая
  цена за ночь (сезон/выходные), deep-link на прямую бронь номера + шаблон
  deep-link поиска с датами. Источник для Google Hotel Center / channel-партнёров
  (Free Booking Links ведут сразу в наш движок). Кабинет `/dashboard/stays/units/`
  — блок «Metasearch & Google (rates feed)» с URL фида. Подключение Hotel Center —
  шаг владельца (нужен Google-аккаунт), как Stripe live. Доступность также
  экспортируется по iCal (A5b). Тесты — `test_feed.py`. Без миграций. План — G8.

- **G3 — рассылки гостям с Double-Opt-In (UWG §7).** `Customer.marketing_opt_in_at`
  (доказательство согласия) + модель `NewsletterCampaign` (subject/body/status/
  sent_at/recipient_count). Витрина: `/newsletter/` — подписка → DOI-письмо с
  подписанной ссылкой `/newsletter/bestaetigen/<token>/` (срок 14 дней) ставит
  согласие; ссылка «Newsletter» в футере. Рассылка (`newsletter.send_campaign`)
  уходит только подтвердившим (marketing_opt_in, не unsubscribed, с e-mail) через
  `notifications` (idempotent по кампании+клиенту), one-click отписка (RFC 8058) в
  каждом письме. Кабинет `/promotions/newsletter/` — создание/отправка/удаление
  черновиков + счётчик согласных. Миграция `promotions/0018`. Тесты —
  `test_newsletter.py`. План — G3.

- **Демо-данные для G3–G8 + согласование агрегатора.** Агрегатор отелей
  (`hotel_search.hotel_availability`) теперь применяет G4-авто-скидку к «ab … €»,
  чтобы цена на портале совпадала с ценой на сайте отеля (раньше показывал без
  скидки). Демо hotel-кита наполнен: мультикомнатная бронь (G5, rooms=2,
  «Reisegruppe»), цифровые Meldescheine (G6) для первых броней
  (`/dashboard/stays/checkins/`), согласия на рассылку (G3, marketing_opt_in на
  демо-клиентах) + 2 кампании (отправленная + черновик). G4/G7-данные уже были в
  ките (авто-скидки + 100 % Vorkasse). Тесты demo_kits расширены проверками
  G3/G5/G6. ⚠️ Нужен reseed `--kit hotel --recreate`.

- **Демо отеля: больше примеров.** Брони расширены до 7 с разными статусами
  (pending/confirmed/fulfilled/cancelled), промокодом SOMMER10 (G4a), Extras,
  мультикомнатной (G5) и прошлой (для отчётов/ADR + G2). 4 цифровых Meldescheine
  (G6). Рассылка: +3 «чистых» подписчика (DOI) и 3 кампании (2 sent + 1 draft).
  Тесты demo_kits усилены (статусы, промокод, ≥3 Meldescheine/согласных, ≥2 sent).

- **G4 многоступенчатые авто-скидки + по 2 примера каждого типа скидок (демо).**
  `StaySettings`: 6 полей (los/early/last × порог/процент) заменены на список правил
  `auto_discount_rules` ({kind, threshold, percent}) — можно несколько правил на
  тип. `pricing.auto_discount` перебирает правила, берёт максимальный применимый
  процент. Кабинет `/dashboard/stays/units/` — список правил + добавить/удалить
  (actions autodiscount_add/_delete). Демо отеля: **по 2 правила** на каждый тип
  (LOS 7+/14+ → 10/15 %, Frühbucher 30/60 дн → 8/12 %, Last-Minute 3/7 дн →
  12/8 %), **2 тарифа с предоплатой** (30 % и 100 %), **2 промокода** (SOMMER10 −10 %
  + WILLKOMMEN20 −20 €). Миграция `stays/0018`. Тесты обновлены (multi-tier,
  demo «по 2»). ⚠️ reseed `--kit hotel --recreate`.

- **G11a+G11b — фундамент Channel Manager (vendor-agnostic).** Полный 2-way с
  Booking/Expedia/Airbnb требует партнёрских аккаунтов/сертификации (шаг владельца,
  как Stripe live) — план и честный scope в `docs/hotel-channel-manager-plan.md`.
  Сделан код-фундамент: модель `stays.Channel` (Booking/Airbnb/Expedia/other +
  статус/лог) + `StayBooking.external_ref`; `services.import_external_booking`
  (идемпотентный занос брони из канала, конфликт → UnitBlock); кабинет
  `/dashboard/stays/channels/` (каналы + ручной импорт брони + список). Демо: 2
  канала + импортированная бронь. Миграция `stays/0019`. Тесты `test_channels.py`.
  Отложено (G11c–e): реальный ARI-push/reservations-API OTA — с партнёрством.
  ⚠️ reseed `--kit hotel --recreate`. M20 Site Builder — следующий (полный аудит).

- **M20-аудит + кабинет UX (адаптивность/нативность).** Аудит билдера: критичных
  багов нет (сохранения переживают через `normalize`); главный пробел — отсутствие
  переключателя ширины предпросмотра на «Build your homepage» → добавлен
  (Desktop/Tablet/Mobile) + переключатель **Editor/Preview** для планшета/мобайла
  (раньше превью было `hidden lg:block`). Кабинет (`tenant/_base_dashboard.html`):
  быстрый **поиск по меню** в сайдбаре (фильтр пунктов, скрытие пустых групп),
  **мобильный таб-бар** (первые разделы + «Menu», из `nav_primary` —
  context.modules_nav), липкая шапка + ссылка «Website», нижний отступ под таб-бар.
  Без новых моделей. M20 план — `docs/m20-site-builder-plan.md`.

- **Ретрит R1 — лист ожидания события + структурированная анкета участника.**
  Архетип «Ретрит» (A6+), план — `docs/retreat-archetype-plan.md`. Добавлено:
  модель `EventWaitlistEntry` (event+email уникально, party_size, notified) —
  зеркало `promotions.WaitlistEntry`; витрина распроданного события показывает
  форму листа ожидания (`/veranstaltung/<pk>/warteliste/`, honeypot+rate-limit);
  отмена билета в кабинете авто-уведомляет лист ожидания (`notify_event_waitlist`,
  одно письмо на запись, дедуп `event_waitlist:{id}:available`) + ручная кнопка
  «Notify of free spots». Шаблоны письма `event_waitlist_available.*`. Анкета:
  пресет-поля `Event.registration_fields` (страна/ДР/экстренный контакт/питание/
  опыт/аллергии/мед., каталог в `apps/events/registration.py`) — чекбоксы в форме
  кабинета, рендер на витрине, ответы в `Ticket.answers` по ключу поля, колонки в
  CSV-ростере. Миграция `events/0006`. Демо retreat: анкета на Wochenend-Retreat +
  2 записи в лист ожидания. Тесты `test_waitlist_registration.py` (11). ⚠️ reseed
  `--kit retreat --recreate`. Дальше — R2 (таксономия типов/направлений + фильтры
  витрина+агрегатор).

- **Ретрит R2a — таксономия событий + фильтры каталога витрины.** Поля
  `Event.city/category/level/language` (пресеты — `apps/events/taxonomy.py`:
  направления yoga/meditation/ayurveda/…, уровни, языки) + выводимая
  `duration_kind` (Tag/Wochenende/Mehrtägig). Витрина `/veranstaltung/` —
  каталог с server-side GET-фильтрами (направление/город/длительность/уровень/
  язык/месяц), фасеты показывают только реально присутствующие значения; карточки
  обогащены (фото, бейджи, «ab X €», свободные места). Кабинет-форма: селекты
  направления/уровня/языка + город. Миграция `events/0007`. Демо retreat:
  таксономия на 4 событиях. Тесты `test_taxonomy_filters.py` (10). Дальше — R2b
  (агрегатор: фильтр по направлению/городу/датам).

- **Ретрит R2b — агрегатор: фильтр по направлению/городу/месяцу.** В
  `AggregatorListing` добавлено поле `category` (направление event-листинга;
  пусто у promotion/stay) + индекс. `sync_event_listing` наполняет `category` и
  `city` из события (город события переопределяет город бизнеса). `listings_for`
  получил фильтры `category` + `month` (YYYY-MM); discover-поиск проксирует
  GET-параметры `cat`/`month`, фасет направлений `_distinct_event_categories`
  (метки из `events.taxonomy`); селект «Richtung» в форме поиска. Миграция
  `aggregator/0012`. Тесты `test_event_category_filter.py` (6). Этим закрыт
  явный пункт владельца «агрегатор: собирать по каталогам/направлениям + город/
  даты». Дальше — R3 (преподаватели + календарь) либо R5 (проживание events⊕stays).

- **Ретрит R5 — проживание events ⊕ stays (выбор типа номера).** Многодневный
  ретрит (Event с ends_at) может предлагать выбор номера через архетип «Отель»
  (`apps.stays`): `Event.offers_accommodation` + M2M `accommodation_units` (типы
  номеров). На витрине события — радиоблок «Unterkunft» с ценой за весь срок и
  наличием по датам (анти-овербукинг stays). При брони билета выбранный тип
  создаёт привязанную `StayBooking` (`Ticket.stay_booking` + снимок
  `accommodation_cents`) в той же транзакции: номер занят реальным анти-
  овербукингом, цена входит в `total_cents` — одна оплата (StayBooking.payment_state
  =none). Недоступный номер → откат всей брони. Отмена билета освобождает номер;
  CSV-ростер — колонка «Unterkunft». Кабинет-форма: чекбокс + выбор типов номеров.
  Миграция `events/0008`. Демо retreat: модуль stays + 3 типа номера (Mehrbett/
  Doppel/Einzel), привязаны к Wochenend-Retreat. Тесты `test_accommodation.py` (8).
  ⚠️ reseed `--kit retreat --recreate`. Дальше — R3 (преподаватели + календарь),
  затем R4/R6.

- **Ретрит R3a — преподаватели (Teacher) как сущность.** Модель `events.Teacher`
  (имя/титул/био/фото-URL/website/instagram/sort_order/is_active) + M2M
  `Event.teachers`. Кабинет: CRUD преподавателей (`/dashboard/events/teachers/`)
  + выбор ведущих в форме события; кнопка «Teachers» на списке событий. Витрина:
  страница списка `/lehrer/` + карточка преподавателя `/lehrer/<pk>/` (био,
  соцсети, ближайшие ретриты); фильтр каталога **по преподавателю**; на странице
  события структурные ведущие (ссылки) вместо/поверх free-text hosts. Миграция
  `events/0009`. Демо retreat: 2 преподавателя (Mara/Felix) с био, связаны со
  всеми событиями, пункт меню «Lehrer». Тесты `test_teachers.py` (8). Дальше —
  R3b (календарь ретритов на год + iCal-экспорт).

- **Ретрит R3b — календарь ретритов + iCal-экспорт.** Витрина:
  `/veranstaltung/kalender/` — события, сгруппированные по месяцам (DE-подписи),
  с ценой/городом/«Sold out». iCal без внешних зависимостей (`apps/events/ical.py`,
  RFC 5545, CRLF, экранирование, UTC): `/veranstaltung/<pk>/ical` («Zum Kalender
  hinzufügen» на странице события) + фид-подписка `/veranstaltung/feed.ics` (все
  опубликованные будущие; «Subscribe (iCal)» на календаре). Ссылка «Calendar» в
  каталоге. Тесты `test_calendar_ical.py` (6). Этим R3 (преподаватели + календарь)
  закрыт. Дальше — R4 (частичная оплата/депозит + подарочный сертификат) или
  R6 (карта + памятка + корп-запрос).

- **Ретрит R4 — частичная оплата (депозит) + подарочный/промо-код на билет.**
  `Event.deposit_percent` (0 = полная оплата; 1..99 = онлайн-депозит, остаток на
  месте; 100 = полная). На билете снимки `voucher_code`/`discount_cents`/`deposit_cents`
  + свойства `payable_cents`/`amount_due_now_cents`/`balance_cents`. При брони
  применяется подарочный/промо-код (Voucher, атомарно гасится — переиспользуем
  `loyalty.gift`/`promotions.redeem_voucher`; невалидный → PromoInvalid), затем
  считается депозит от суммы после скидки. Stripe Checkout берёт `amount_due_now`
  (депозит или вся payable); вебхук `mark_ticket_paid` ставит `deposit` (остаток
  на месте) либо `paid`. Витрина: поле «Gutscheincode» + подсказка про депозит;
  подтверждение показывает скидку/депозит/остаток. Кабинет-форма: поле «Anzahlung
  online %». Geschenkgutschein-покупка уже доступна (stays-гейт `/gutschein/`).
  Миграция `events/0010`. Демо retreat: Wochenend-Retreat с депозитом 30 %. Тесты
  `test_voucher_deposit.py` (11). Этим R4 закрыт; остался R6 (карта/памятка/корп) и
  R7 (блог, отложен).

- **Ретрит R6 — карта + памятка-PDF + корп-запрос; + полноценное демо.** На
  странице события: OSM-карта (cookieless embed + «Route planen») по координатам
  события `Event.latitude/longitude` (фолбэк на гео тенанта); «Teilnehmer-Infoblatt»
  PDF (`apps/events/memo.py`, reportlab) на `/e/<code>/memo.pdf` (программа, что
  взять, проживание, контакт) + ссылка на подтверждении; групповой/корп-запрос —
  блок «Für Gruppen & Firmen» → `/anfrage/?betreff=…` (jobs prefill, движок Angebote).
  Миграция `events/0011`. **Полное демо retreat:** модуль `jobs` включён; 6 событий
  (добавлены Frauen-Retreat и Ayurveda-Detox на +90/+160 дн — фуллнес календаря,
  направления, депозиты 30/40 %, проживание); координаты на событиях. Доки —
  `docs/retreat-demo.md`. Тесты `test_map_memo_corp.py` (8) + расширен retreat-demo
  тест. Этим архетип «Ретрит» (R1–R6) закрыт; R7 (блог) — отложен (общеплатформенный).

- **Ретрит R8 — Waiver + Gesundheits-Selbstauskunft с e-подписью.** `Event.waiver_required`
  + `waiver_text` (пусто = `DEFAULT_WAIVER_TEXT`); модель `events.TicketWaiver`
  (OneToOne→Ticket: снимок текста, health_confirmed, signed_name/at/ip — простая
  eIDAS-подпись, как `stays.GuestRegistration`). `book_ticket(..., waiver_signed_name,
  health_confirmed, signed_ip)`: при `waiver_required` без подписи → `WaiverRequired`
  (откат брони), иначе создаёт `TicketWaiver` атомарно. Витрина: блок waiver на форме
  (текст + accept + health + подпись именем); ростер-CSV колонка «Waiver»; memo-PDF —
  строка о подписи. Кабинет-форма: `waiver_required` + `waiver_text`. Не авто-чистим
  (срок исковой давности). Миграция `events/0012`. Демо: waiver на Waldlicht/Ayurveda
  + подписанные билеты в seed_records. Тесты `test_waiver.py` (7). План — `docs/retreat-waiver-plan.md`.
  Дальше по бэклогу R7+ — R9 (pre/post-event авто-письма).

- **Ретрит R9 — pre/post-event авто-письма (drip).** `Ticket.reminder_sent_at` +
  `post_event_sent_at` (по одному письму на билет, idempotent + БД-дедуп). Beat-задачи
  `apps/events/tasks.py`: `send_event_reminders` (за `EVENT_REMINDER_DAYS`=7 до события,
  подтверждённые билеты) + `send_event_post_event` (после конца события, `EVENT_POSTEVENT_DAYS`
  =1, окно подхвата 7 дн; Coalesce(ends_at, starts_at)). Зеркало `stays` E3/G2; письма
  через `events.notifications` (новые шаблоны `ticket_reminder` / `ticket_post_event` —
  напоминание со ссылкой на памятку; post-event — благодарность + отзыв). Beat
  зарегистрированы в `CELERY_BEAT_SCHEDULE` (раз в сутки). Миграция `events/0013`.
  Тесты `test_drip.py` (6). Дальше по бэклогу R7+ — R11/R12 (per-tier вместимость /
  политика отмены) или R10 (рассрочка, крупная).

- **Ретрит R11 — вместимость per-tier.** Каждый ценовой тир (`Event.tiers`) несёт
  опц. `capacity` (3-й столбец формы «Label | Preis | Kontingent»; 0 = без отдельного
  лимита — как раньше). Парс/сериализация — `details.normalize_tiers`/`tiers_to_text`
  (схема только JSON, **без миграции**). Анти-овердрафт тира — в `book_ticket` под той
  же блокировкой строки Event, что и общий `Event.capacity` (срабатывает строжайший);
  `SoldOut(available=…)`. Модель: `tier_sold_map`/`tier_seats_left`; `tiers_display`
  даёт per-tier `seats_left`/`sold_out`/`is_default`; `is_sold_out`=True, когда
  распроданы все тиры с лимитом (нет безлимитных) → лист ожидания. Витрина: бейдж
  «ausverkauft»/«N frei» на тире, disabled-radio, предвыбор первого доступного.
  Per-room вместимость уже даёт реальный анти-овербукинг `stays`. Демо: Frauen-Retreat
  (Frühbucher 4 / Mehrbett 6 мест, Standard без лимита). Тесты `test_tier_capacity.py`
  (11), events-сьют 110 зелёный. Дальше R7+ — R12 (политика отмены) или R10 (рассрочка).

- **Ретрит R12 — гибкая политика отмены билета.** На событии — `Event.cancellation`
  (flexible / non_refundable) + `free_cancel_days` (зеркало `stays.RatePlan`); миграция
  `events/0014`. `services.cancellation_state(ticket)` → {can_cancel, free, deadline}:
  flexible бесплатна до N дней до начала, non_refundable — отмена без возврата,
  attended/cancelled — нельзя. Самостоятельная отмена гостем по подписанной ссылке
  `/e/storno/<token>/` (зеркало stays `/stornieren/`): FSM cancel + освобождение
  привязанного номера (R5) + уведомление листа ожидания (R1); при free + онлайн-оплате
  (paid/deposit) — возврат через Stripe Connect, `payment_state=refunded`. Ссылка на
  отмену — на странице подтверждения (`event_confirmation`) и в письмах created/confirmed.
  Кабинет-форма: `cancellation` + `free_cancel_days` (необязательны, фолбэк на flexible/0).
  Демо: Frauen-Retreat (flexible, 14 дн), Ayurveda (non_refundable). Тесты
  `test_cancellation.py` (10); events-сьют 137 зелёный. Дальше R7+ — R10 (рассрочка, L)
  или R13 (медиа-отзывы).

- **Ретрит R13 — медиа-отзывы + истории «до/после» + значки сертификации.** Trust-блоки
  на ретрит-лендинге (`Event.details`, курирует организатор). Расширена схема
  `details._SCHEMA`: отзывы `name|city|text|photo|rating` (фото-аватар + 1–5 звёзд),
  новые блоки `before_after` (`vorher|nachher|text`) и `certifications` (`name|issuer|icon`).
  `Event.landing_testimonials` отдаёт отзывы со строкой звёзд (rating клампится 0–5).
  Старые 3-кортежные отзывы валидны (photo/rating пустые) — **без миграции** (JSON).
  Витрина `event_detail`: фото+звёзды в отзывах, секции «Before & after» (две картинки
  рядом) и «Certifications» (значки). Кабинет-форма: 3 построчных поля. Демо:
  Waldlicht-лендинг (2 отзыва с фото+5★, история «до/после», 2 значка). Тесты
  `test_media_reviews.py` (8); events-сьют 126 зелёный. Ретрит-бэклог R7+ закрыт,
  кроме R10 (рассрочка, L, high-risk — отложено по решению владельца).

- **Ретрит R10 — план рассрочки (Ratenzahlung), dormant до Stripe-теста.** Killer-фича
  для дорогих ретритов: гость платит билет частями (Stripe Connect, мандат +
  off-session списания). Решения владельца — `docs/retreat-installments-plan.md`.
  **R10a** (модель/график): `Event` конфиг (`allow_installments`, `installment_mode`
  until_event/fixed, `installment_count/min_cents/lead_days`); `InstallmentPlan`
  (OneToOne→Ticket) + `InstallmentCharge`; `installments.py` (чистая логика:
  `installments_available`, `split_amounts` — остаток центов на первые доли,
  `schedule_dates` fixed/until_event, `build_schedule`). Миграция `events/0015`.
  **R10b** (первый платёж+мандат): `connect.installment_checkout_session`
  (`customer_creation=always`+`setup_future_usage=off_session`), вебхук
  `kind=event_installment` → `create_installment_plan` → `create_plan` (1-я доля
  paid, мандат из PI, билет confirmed); витрина — чекбокс «in Raten» (`pay_mode`).
  Миграция `events/0016` (Ticket.payment_state += installment). **R10c** (списания):
  beat `charge_installments` (по тенантам с Connect) → `charge_due_installments`
  off-session `PaymentIntent`; успех → `mark_charge_paid` (план/билет→paid при
  полной оплате); отказ → attempts++ + письмо, после `INSTALLMENT_MAX_ATTEMPTS` →
  failed + эскалация владельцу (`installment_failed`/`_owner`); **без авто-отмены**.
  **R10d** (мин.): строка «Rate k/N» в кабинет-ростере. **R10e**: отмена билета →
  стоп плана (хук `TicketSM.on_transition`; покрывает кабинет + self-cancel R12).
  Демо: Ayurveda (fixed 3), Frauen-Retreat (until_event 4). Тесты
  `test_installments.py` (12) + `test_installment_payment.py` (8). **Код спит без
  Stripe-ключей** (как оплата билетов); сквозная проверка списаний — на Stripe test
  (Stage 0). Ретрит-бэклог R7+ (R8–R13) полностью закрыт.
- **2026-06-25 — M20U «унификация страниц» (план `m20-retreat-pages-plan.md`).**
  Сквозная идея «архетип = главный товар + способ покупки» поверх JSON-конфига, без
  новых моделей. **M20U-2 (главная):** слайдер баннеров `heroes[]`, секции `categories`
  и `events` (layout-движок), реестр `apps/core/archetypes.py` (`primary_item`:
  магазин→товары/ретрит→события/отель→номера; `primary_module/section`), hero-CTA на
  «главный товар» (accent/photo + слайды без своей кнопки). **M20U-3 (каталог):**
  подкатегории-первыми; фильтры ретритов свёрнуты/скрыты на маленькой витрине
  (`_FILTER_MIN_EVENTS`). **M20U-5 (способ покупки):** реестр `purchase_mode`
  (cart/booking/reserve/request) + `purchase_label` (DE) + тег `{% purchase_label %}`;
  пилюли действия на карточках событий/номеров; мобильная липкая панель `_detail_buybar.html`
  на всех детальных. **M20U-4 (единая детальная):** каркас `storefront/detail.html`
  на блоках-наследования (`detail_back/gallery/aside/body/wide/buybar`, base_template-aware
  для embed); product/stay/event_detail сведены на него без регрессии. **M20U-7 (билдер):**
  селектор пресета раскладки (Список/2-4/Галерея) секций-сеток в конструкторе главной →
  `layout.preset` в конфиге; live-preview отражает пресет. Визнастройка в django-admin
  отсутствует (кураторские fieldsets) — пункт «убрать из admin» закрыт. Тесты:
  archetypes(10)/layout/hero_slider/media_gallery + storefront/детальные/builder/live-preview.
  Осталось по M20U: per-page билдер (каталог/детальная), хвосты каталога events/stays,
  общий Category/Tag (опц.), realtime-чат (отдельный трек).
- **2026-06-25 — M20U-7 (билдер, продолжение): пер-секционные контролы + per-page +
  вкладка «Pages».** Конструктор главной: на каждую секцию-сетку — пресет раскладки,
  число элементов (products/events), свой заголовок, источник товаров
  (featured_first/newest/featured_only), тоггл «View all» — всё с live-preview.
  Layout-движок (`{% grid_classes %}`) подключён ко ВСЕМ секциям-сеткам
  (products/stay_rooms/categories/events/archetypes/team/testimonials/reviews/gallery/
  promotions) — пресет honor везде. **Per-page раскладки** (layout-движок на страницах
  листингов): каталог `/sortiment/` (`catalog_layout`), номера `/unterkunft/`
  (`stay_index_layout`, обе сетки, embed сохранён), события `/veranstaltung/`
  (`events_index_layout`: дефолт «список» без регрессии / опц. сетка), «похожие
  товары» на детальной (`detail_related_layout`). **Вкладка «Pages»**
  (`/dashboard/site/pages/`, `pages_view` + `site_pages.html` + карточка в хабе Site)
  собирает per-page раскладки, показывая только активные модули. archetype-aware
  дефолт главной (`archetypes.primary_section` включает секцию главного товара, если
  владелец не настраивал композицию). Тесты: test_layout/test_home_builder/
  test_pages_view/test_live_preview + storefront/events/stays. Реестр/порядок
  тематических секций детальной — отложен (секции и так скрываются при пустых данных;
  ценность = переупорядочивание, рисковый рефактор event_detail).
- **2026-06-25 — Рыночный анализ по архетипам + «анти-Битрикс»-блюпринт.** Девять
  детальных отчётов (по архетипу A1–A9 + сквозной билдер) в `docs/market-analysis/`,
  сведены в `docs/archetype-market-analysis.md`. Вывод: бэкенд-движки почти закрыты
  (75–100%), фронт работ — визуал/UX витрины, «анти-Битрикс» конструктор/онбординг
  (~55–60% к цели) и точечный правовой долг (Widerruf с 19.06.2026). Заведён
  пошаговый `docs/archetype-ux-execution-plan.md` (Спринты A–F, по файлам, с
  критериями приёмки и статусами) — source of truth этапа. Обновлён §6
  `retreat-archetype-plan.md` (визуально-UX-трек RV1–RV4 + RT*).
- **2026-06-25 — Спринт A.1: блок «Leistungen & Preise» (services) для A3.** Новая
  секция витрины `services` (`siteconfig.SECTIONS`, выкл по умолчанию) — primary item
  архетипа `booking` (Friseur/Massage/Werkstatt-Termin). `archetypes.PRIMARY_SECTION
  ["booking"]="services"` + `booking` поднят в `_PRIORITY` выше `catalog` (у салона
  главный товар — услуга, не мерч). Партиал `_services.html` (карточки с цена/
  длительность + CTA «Jetzt buchen» → выбор времени `storefront-service-slots`),
  ветка в диспетчере `home.html`, `services_preview` в `storefront_home` (гейт:
  модуль booking активен). Layout-пресет `cols2`, настраиваемый заголовок + «View all»
  → `/termin/`. Тесты: `test_services_section.py` (реестр/грид/рендер/пусто) +
  `test_archetypes.py` (booking→services, booking ≻ catalog). Без миграций (JSON).
  Осталось опц.: богатая карточка услуги (поля `Service.description/image`) — A.1b.
- **2026-06-25 — Спринт A.2: отзывы на витрине в демо-китах.** Блок `reviews`
  (`_reviews.html` ← SHARED `BusinessReview`) уже существовал и авто-включается при
  `reviews_seed`. Засеяли реалистичные отзывы (rating/comment/@example.de) в
  RESTAURANT, PRANASY, AKTIONSMARKT, WERKSTATT, SHOP (у FRISEUR/HOTEL/RETREAT уже были)
  → блок отзывов теперь виден в showcase всех ключевых китов. Только демо (без кода/
  миграций). Тест `test_demo_kits` зелёный. CLAUDE.md §6/§7: ссылки на
  `archetype-ux-execution-plan.md` (source of truth этапа) и `archetype-market-analysis.md`.
- **2026-06-25 — Спринт A.3: Trust/USP-bar блок (T-B).** Новая секция витрины
  `usp_bar` — тонкая «полоса доверия» под hero: пункты {icon, label} (Versand ab X €,
  14 Tage Widerruf, sichere Zahlung, Meisterbetrieb…). Иконки — emoji по токену-реестру
  `siteconfig.USP_ICONS` (без внешних ресурсов, GDPR; как нижний таб-бар). Нормализация
  `clean_usp` (валидация иконки→фолбэк check, обяз. label, кап `_MAX_USP`=6),
  `text_to_usp`/`usp_to_text` для билдера, тег `{% usp_icon %}`. Партиал `_usp_bar.html`,
  ветка в `home.html` (сразу под hero). Билдер: textarea «icon | label» в общем
  `_section_fields.html` + initial-значения в обеих вьюхах (site/home) + поле в
  live-preview синке. Демо: `usp` засеян в SHOP/AKTIONSMARKT/RESTAURANT/WERKSTATT.
  **Заодно — фикс видимости A.1:** `_kit_sections` теперь включает `services` (booking)
  и `usp_bar` — иначе блоки не появлялись в демо (kit задаёт явные sections, минуя
  archetype-aware дефолт). Тесты `test_usp_bar.py` (нормализация/парс/рендер/реестр) +
  правка порядка секций в `test_siteconfig`. Без миграций (JSON).
- **2026-06-25 — Спринт A.4: полноэкранный лайтбокс галереи (T-E).** Универсальный
  партиал `_media_gallery.html` (его включают детальные товара/номера/события) получил
  полноэкранный лайтбокс: клик по большому фото → overlay (← → / Esc / клик по фону),
  навигация при >1 фото, lock body-scroll. Vanilla JS, идемпотентно, без внешних
  библиотек (GDPR). Один инкремент закрывает A1/A4/A5/A6 (товар/номер/событие) — все
  детальные через общий партиал. Тесты в `test_media_gallery.py` (zoom/лайтбокс/одно
  фото). Только шаблон+тест, без кода/миграций. build:css обновлён. **Спринт A закрыт.**
- **2026-06-25 — Спринт B.1 (анти-Битрикс Phase 1): демо-контент внутри мастера.**
  Шаг 4 онбординга «Dein erster Inhalt» получил карточку «Beispiel-Inhalte laden»
  (action=load_demo → `demo.load_demo`, обратимо clear_demo) — после мастера витрина
  НЕ пустая (главный психологический рычаг анти-Битрикс). Остаёмся на шаге 4, статус
  has_demo переключает загрузить/убрать. Без новой модели/шага (TOTAL_STEPS=5).
  Тест `test_step4_loads_and_clears_demo_content`. build:css обновлён.
- **2026-06-25 — Спринт B.4 (анти-Битрикс Phase 1): линейный мастер /willkommen/
  (7 шагов) + тема (B.2) + баннер с фото (B.3).** Онбординг переведён на линейный
  ≤10-шаговый флоу: 1 тип → 2 **Stil & Farbe** (выбор шаблона витрины карточками,
  `sitetemplates.apply_template`) → 3 модули → 4 Basics → 5 **Dein Banner** (hero-
  заголовок/подзаголовок + загрузка фото файлом через `catalog.images`) → 6 Inhalt
  (демо B.1 + пресеты) → 7 Geschafft. `TOTAL_STEPS=5→7`, новый алиас-маршрут
  `/willkommen/`. Тесты онбординга обновлены под новую нумерацию + добавлены
  `test_step2_shows_theme_picker`, `test_step5_banner_saves_hero_texts`,
  `test_step6_*`. Без миграций. **Спринт B (Phase 1) закрыт: B.1–B.4.** Осталось
  (опц., отдельно): объединение signup+provisioning в /willkommen/ (high-risk, гейт).
- **2026-06-25 — Спринт C (правовой долг A1/A2): Widerrufsbelehrung + онлайн-Widerruf.**
  C.2: `Tenant.withdrawal_text()` теперь archetype-aware — для дистанционной продажи
  товаров (`delivery_enabled`) генерит полноценную **Widerrufsbelehrung für Waren**
  (14-Tage-Frist § 355 BGB) + Muster-Widerrufsformular; для броней/услуг — прежний
  мягкий текст. C.1: онлайн-форма `/widerruf-formular/` (honeypot+rate-limit) —
  заявление уходит продавцу письмом + inbox-тредом (если модуль активен), клиенту —
  подтверждение. Кнопка «Widerruf online erklären» на странице /widerruf/ для
  товарных продавцов. Тесты `test_withdrawal.py` (текст для товара/брони/override +
  GET/POST/honeypot/валидация формы). Без миграций. **Спринт C закрыт** (C.3
  PayPal/Kauf auf Rechnung — отложен, гейт владельца).
- **2026-06-25 — Спринт D.1 (анти-Битрикс Phase 2): реестр секций `render_block`.**
  Хардкод if/elif (20 веток) в `storefront/home.html` заменён на реестр
  `siteui.BLOCK_TEMPLATES` (key→партиал) + тег `{% render_block %}` (якорь-обёртки
  #buchen/#zimmer/#leistungen/#bewertungen/#kontakt… сохранены). Главная теперь —
  `{% for s in sections %}{% render_block s %}{% endfor %}`. Это разблокиратор для
  C-блоков (D.2) и on-canvas инсертера «+» (E). Рефактор без регрессии (39+16 тестов
  зелёные). Тест `test_block_registry.py` (покрытие ключей/якоря/unknown→пусто).
- **2026-06-25 — Спринт D.2a (анти-Битрикс Phase 2): C-блоки (движок + рендер).**
  Введены повторяемые «простые блоки» `text/image/image_text/button/spacer`
  (`siteconfig.REPEATABLE_BLOCKS`) — живут в `site_config["sections"]` с собственным
  `id` и `data`, НЕ дедупятся по key (нормализация `_clean_cblock` + санитизация
  данных по типу, кап `_MAX_CBLOCKS`=30). `render_block` принимает и dict-блок
  (C-блок рендерится со своими данными), и строку-ключ (фикс-секция). Партиалы
  `_block_text/_image/_image_text/_button/_spacer.html`. Вьюха отдаёт `section_blocks`
  (включённые записи), главная — `{% for b in section_blocks %}{% render_block b %}`.
  Тесты `test_cblocks.py` (мульти-блоки/id/санитизация/кап/рендер каждого типа).
  Без миграций. **D.2b (билдер-CRUD добавления C-блоков) — в Спринте E** (инсертер «+»).
- **2026-06-25 — Спринт D.2b (анти-Битрикс Phase 2): билдер C-блоков.** Конструктор
  главной (`home_builder_view` + `site_home.html`) теперь умеет C-блоки: панель
  «Content blocks» (правка title/body/url/caption/side, позиция, видимость, удаление)
  внутри основной формы + отдельная форма «Add block» (action=add_block добавляет
  пустой блок). Сохранение слитно сортирует фикс-секции и C-блоки по позиции
  (interleaving сохраняется). **Фикс важного бага D.2a:** прежнее сохранение главной
  затирало C-блоки (пересобирало sections только из фикс-SECTIONS) — теперь round-trip
  (`cb_id`/`cb_type`/`order_cb`/`enabled_cb`/`delete_cb`, хелпер `_read_cblock_data`).
  GET аккуратно делит sections на фикс (с label) и cblocks (без KeyError). Тесты
  `test_cblocks_builder.py` (add/edit+round-trip/delete). **Спринт D закрыт** (D.3
  единый экран — опц., отложен). Без миграций.
- **2026-06-25 — M20U ЗАКРЫТ (pranasy + реестр секций детальной + клик-фокус).**
  **M20U-8 pranasy:** демо-кит на единой схеме — DemoKit поля heroes (слайдер 3 слайда:
  Karte/Catering/Online bestellen) / section_titles (Unsere Karte/Angebote/Events bei
  Pranasy) / page_layouts (события сеткой); apply_kit пробрасывает в site_config. Прочие
  киты не затронуты (поля пустые). **M20U-4 реестр тематических секций детальной:**
  EVENT_DETAIL_SECTION_KEYS (14 секций) + normalize_event_detail + event_detail_order;
  event_detail.html рендерит секции циклом через _event_thematic.html (if/elif по ключу,
  разметка дословно) → владелец задаёт порядок/скрытие; UI на вкладке Pages (номер+чекбокс
  на секцию). **M20U-7 (B) клик-фокус:** секции главной несут data-sf-section (display:
  contents); клик по секции в live-preview билдера → вкладка Editor + скролл/подсветка её
  контролов. Тесты: test_layout/test_pages_view/test_demo_kits/test_storefront (events:
  152 + reorder/hide). **Итог M20U:** единые страницы (главная/каталог/детальная) +
  сквозной визуальный конструктор (per-секционные контролы, per-page раскладки, вкладка
  Pages, реестр секций детальной, клик-фокус, live-preview). Вне ядра (отдельные треки):
  общий Category/Tag-дерево (M20U-6), realtime-чат, per-page блок-холст.
- **2026-06-25 — Интеграция Спринтов A–D в main (merge + фикс CI).** Ветка
  `claude/archetype-analysis-market-gaps-dkwo87` отстала от main на 8 коммитов
  (M20U-7/M22b: inbox-чат, live-поллинг, реестр секций детальной события,
  клик-фокус). Влили `origin/main` в ветку (merge-коммит, не FF — main разошёлся).
  **Конфликты (3):** `templates/storefront/home.html` — совместили мой реестр
  `render_block` (D.1) с обёрткой `data-sf-section` главной (M20U-7 B клик-фокус):
  `{% for b in section_blocks %}<div data-sf-section="{key|id}" style="display:contents">
  {% render_block b %}</div>`; `docs/build-log.md` — оба набора записей; `static/css/app.css`
  — пересобран `npm run build:css`. **CI merge-коммита упал 1 тестом** (1505 passed):
  `test_storefront_header_does_not_leak_template_comment` — в home.html остался
  МНОГОСТРОЧНЫЙ `{# #}` (Django его НЕ вырезает → текст «M20U-7…» утёк в шапку).
  Фикс: заменён на `{% comment %}…{% endcomment %}` (урок CLAUDE.md: многострочные —
  только `{% comment %}`). После фикса — ждём зелёный CI, затем FF-push `main`.
  Миграций в A–D нет (JSON/шаблоны/вьюхи) → деплой простой:
  `git pull origin main && ./scripts/deploy.sh single`.
- **2026-06-25 — Спринт E.1 (анти-Битрикс Phase 3 «on-canvas»): Undo/Redo.** Конструктор
  главной (`site_home.html`) получил отмену/повтор изменений: **клиентский** стек снимков
  состояния редактора (карта `name→value/checked` всех полей формы, N=20). Снимок при
  восстановлении переустанавливает поля формы и обновляет live-preview, поэтому «Отменить»
  влияет и на последующее Сохранение (не только на превью — отличие от чисто серверного
  `site_preview_history` из плана, выбран более корректный клиентский путь). Кнопки ↶/↷ в
  тулбаре превью + горячие клавиши Ctrl+Z / Ctrl+Shift+Z (Ctrl+Y) — в текстовых полях
  оставлена нативная отмена ввода. `record()` вшит в debounce-`push`; undo/redo выставляют
  `present` и пропускают запись. Тест `test_home_builder_get_renders_undo_redo` (кнопки +
  скрипт истории + подсказка клавиш). Только шаблон+тест, без кода/миграций. build:css свеж.
- **2026-06-25 — Спринт E.2 (анти-Битрикс Phase 3 «on-canvas»): click-to-edit → попап.**
  Клик по блоку в live-preview (`data-sf-section`) открывает плавающую карточку
  `#bld-block-popup` у превью и **переносит в неё реальный control-row блока** (фикс-секции
  — `.home-block` по `order_<key>`; C-блоки — новый маркер `.cb-row[data-cb-id]`). Попап
  размещён ВНУТРИ `#home-form`, поэтому правки идут в live-preview/сабмит/историю Undo-Redo
  без копий состояния; закрытие (✕/Esc) возвращает строку на место через anchor-комментарий.
  Фолбэк сохранён — прокрутка+подсветка контролов (M20U-7 B), если row не найден. Тест
  `test_home_builder_get_renders_block_popup` (контейнер попапа + `openBlockPopup` + cb-row).
  Только шаблон+тест, без кода/миграций. build:css обновлён (новые утилиты позиционирования).
- **2026-06-25 — Спринт E.3 (анти-Битрикс Phase 3 «on-canvas»): инсертер «+».** Между
  блоками live-preview инъектируются круглые зоны «+»; клик открывает плавающую библиотеку
  блоков `#bld-inserter` (типы из `block_types`), выбор типа POST-ит `add_block` с новым
  параметром **`add_after`** (ключ фикс-секции или id C-блока) → новый C-блок вставляется
  СРАЗУ ПОСЛЕ выбранного блока (а не только в конец), страница перерисовывается. Бэкенд:
  `home_builder_view`/add_block читает `add_after` и делает `sections.insert(idx+1)`
  (`normalize` сохраняет порядок present-секций; обратная совместимость — без `add_after`
  по-прежнему append). Тесты `test_add_block_after_inserts_at_position` (сервер) +
  `test_home_builder_get_renders_inserter` (рендер библиотеки/инъекции). build:css обновлён.
- **2026-06-25 — Спринт E.4 (анти-Битрикс Phase 3 «on-canvas»): drag-on-canvas. СПРИНТ E
  ЗАКРЫТ.** На каждый блок live-preview инъектируется drag-ручка ⠿ (нативный HTML5 DnD,
  без внешних библиотек — GDPR/no-SPA). Перетаскивание блока определяет before/after по
  Y-середине целевого блока и через `moveBlock` переносит соответствующий `.home-block`
  в редакторе к новой позиции + перенумеровывает `order-input` → тот же путь, что обновляет
  live-preview, Сохранение и историю Undo/Redo (E.1). Обёртки `display:contents` не дают
  drag-бокс, поэтому ручка крепится к первому элементу секции (position:relative при
  static). Тест `test_home_builder_get_renders_canvas_drag`. Только шаблон+тест.
  **Итог Спринта E (анти-Битрикс «on-canvas»):** E.1 Undo/Redo · E.2 click-to-edit→попап ·
  E.3 инсертер «+» (add_after) · E.4 drag-on-canvas — нативное редактирование прямо на
  превью, без SPA. Опц. оставлено: показ C-блоков в live-preview-черновике (сейчас draft
  фильтрует только фикс-секции), per-block undo-гранулярность.
- **2026-06-25 — Спринт F (наполнение архетипов): демо-кит A7 Handwerker.** Закрыт
  крупнейший пробел демо-витрины — у архетипа A7 (Handwerker) не было кита. Новый кит
  `handwerker` («Meisterbetrieb Krause» — Maler · Elektro · Sanitär, generic, без авто):
  ядро = `jobs` (Anfrage → unverbindliches Angebot/Festpreis, primary-CTA `/anfrage/`),
  `booking` даёт Leistungen с Festpreisen + бесплатную Vor-Ort-Beratung (0 €); БЕЗ shop
  (catalog скрыт, products/promotions-секции off — без пустых блоков). Контент: hero,
  USP-бар (Meisterbetrieb/24-7-Notdienst/Region/Festpreis-Garantie), процесс, команда
  (3 мастера), FAQ, отзывы (reviews_seed×3), 2 демо-Angebote (Wohnzimmer streichen /
  Bad modernisieren) c позициями и НДС, archetype_covers (jobs/booking), меню top+bottom,
  поддомен `handwerker.<base>`. Зарегистрирован в `KITS`; команда `seed_demo_tenants`
  подхватывает автоматически (доку-строка добавлена). Тест
  `test_apply_handwerker_kit_jobs_services_no_shop` (services/Festpreis, jobs с суммами,
  отсутствие shop, активные модули, секции витрины, CTA `/anfrage/`). Без миграций (демо-данные).
- **2026-06-25 — Спринт F (визуальный трек A6): RV3 грид-обложки событий + countdown.**
  Индекс ретритов/событий (`event_index.html`) в grid-режиме (`events_index_layout` != list)
  теперь рендерит **крупные карточки-обложки** (фото 4:3 сверху, hover-zoom, бейджи
  категории/sold-out/countdown оверлеем, мета снизу) — стиль BookRetreats, вместо
  горизонтальных строк (как было — грид-класс на тех же flex-карточках). Списочный режим
  сохранён без изменений. Добавлена **urgency-пилюля** «Heute/Morgen/In N Tagen» для событий
  ≤14 дней (на гриде — оверлеем, в списке — в ряду бейджей); `veranstaltung_index` размечает
  `starts_soon`/`countdown_label` по КАЛЕНДАРНОЙ разнице дат (localtime, без off-by-one).
  Демо: retreat получил `page_layouts={"events":"cols2"}` (у pranasy уже было) → грид виден
  в showcase. Тесты `test_index_grid_layout_shows_cover_cards_and_countdown` +
  `test_index_list_layout_has_no_cover_grid`. build:css обновлён (aspect-[4/3]). Без миграций.
- **2026-06-25 — Спринт F (визуальный трек A6): RV2 agenda-timeline.** Программа события
  (`Event.program` — плоский список строк) на детальной (`_event_thematic.html`, секция
  `program`) рендерится как **тайм-лайн день-за-днём**: вертикальная рельса слева + точки,
  ведущий маркер времени/дня (часть до тире «—/–/-») выделен индиго-жирным, остаток — описание;
  строки без тире — обычным текстом (фолбэк). Парсер `_parse_agenda(program)` в
  `veranstaltung_detail` отдаёт `agenda=[{lead, body}]` (generic — любой формат программы,
  не только демо). Тест `test_detail_program_renders_agenda_timeline`. build:css обновлён.
  Без миграций (рендер поверх существующего JSON).
- **2026-06-25 — Спринт F (A5 отель): разбивка цены PAngV на странице номера.** Карточка
  цены номера (`stay_detail.html`) при заданном диапазоне дат теперь показывает не только
  Gesamtpreis, но и **разбивку по PAngV**: «Nachtpreis × Nächte × Zimmer = Übernachtung-
  подытог», строку Kurtaxe (если есть, уже была) и пометку «inkl. MwSt.» Бэкенд
  `unterkunft_unit` добавляет в `quote` поля `accommodation_eur` (подытог проживания) и
  `nightly_eur` (ставка за ночь за номер = total/nights/rooms). Тест
  `test_detail_shows_pangv_price_breakdown` (90 € × 3 = 270 € + MwSt). Без миграций.
- **2026-06-25 — Спринт F (A5 отель): рейтинг бизнеса на странице номера.** Под названием
  номера (`stay_detail.html`) добавлен бейдж рейтинга — ★ + среднее (`avg_rating`) + число
  отзывов из SHARED `BusinessRating` через существующий тег `business_rating` (показывается
  только при `review_count>0`). Как у Booking/HRS — соц-доказательство у точки брони. Тест
  `test_detail_shows_business_rating_badge`. Без миграций/нового кода (переиспользован тег).
- **2026-06-25 — Спринт F (A4 Gastro): аллергены на карточке меню (LMIV).** Карточка товара
  витрины (`_product_card.html`) теперь показывает компактную строку аллергенов
  (`product.allergen_labels`, немецкие подписи Anhang II LMIV) под названием — видна ТОЛЬКО
  если у товара заданы аллергены (естественно гейтится на гастро; retail-товары без
  маркировки не зашумлены). Полный список + Herkunft/Zutaten — на детальной (как было).
  Тесты `test_storefront_card_shows_allergens_inline` + `_no_allergen_line_when_empty`.
  Только шаблон+тест, без кода/моделей/миграций. build:css обновлён.
- **2026-06-25 — Спринт F (A9/A7): прайс-блок «Festpreis» в блоке услуг.** У ремесла/
  автосервиса (активен модуль `jobs` — Angebot/Kostenvoranschlag) платные услуги в блоке
  «Leistungen & Preise» получают пометку **Festpreis** (зелёная пилюля у цены) — сигнал
  доверия (прозрачные фиксированные цены). Флаг `services_festpreis` = `is_module_active("jobs")`
  в `storefront_home`, партиал `_services.html` показывает пометку только при флаге; у Friseur
  (booking без jobs) — без пометки. Демо Werkstatt/Handwerker подхватывают автоматически.
  Тесты `test_services_section_shows_festpreis_for_trades` + `_no_festpreis_without_flag`.
  Без миграций.
- **2026-06-26 — A5 визуальный календарь наличия, инкремент C1 (данные).** Добавлен
  `availability.month_availability(unit, year, month, today=None)` — доступность номера на
  календарный месяц для будущего витринного календаря: список `{date, in_past, free, is_free}`
  по дням. `free` = quantity − занятость ночи (активные брони × rooms + блоки) — переиспользует
  `occupancy_grid` (один проход по броням/блокам, без N+1); `is_free` = свободно И не в прошлом
  (`today` через localdate). Без UI/вьюх/миграций. Тесты `test_month_availability.py` (все дни/
  поля, занятые ночи без дня выезда, частичная занятость quantity>1, блок включительно, прошлое
  не выбрать). План — `docs/hotel-availability-calendar-plan.md` (C1✅ → C2 вьюха → C3 выбор → C4 демо).
- **2026-06-26 — A5 визуальный календарь наличия, инкремент C2 (вьюха + партиал).** Новый
  GET-эндпоинт `unterkunft_unit_calendar` (`/unterkunft/<pk>/kalender/`, name
  `storefront-unterkunft-calendar`) → отдаёт self-contained фрагмент `_stay_calendar.html`:
  server-rendered месяц-сетка (Mo-первый, пустые ячейки до 1-го), заголовок «Monat Jahr»,
  кнопки ‹ › для перелистывания. Окно клампится: не раньше текущего месяца, не дальше
  `MAX_DAYS_AHEAD`. Свободные ночи — кликабельные кнопки с `data-date` (+«N×» при quantity>1);
  занятые/прошлые — некликабельны (line-through/серые). Перелистывание — **vanilla fetch**
  (делегированный обработчик, привязка один раз, свап `#stay-cal` через replaceWith) — htmx
  на витрине нет. Гейт — модуль stays (404). Маршрут в `config/urls_tenant.py`. Тесты
  `test_public.py::test_calendar_*` (грид, гейт-404, занятые/свободные дни, nav-ссылки
  month=±1, кламп прошлого месяца). Интеграция в страницу номера + выбор диапазона — C3.
- **2026-06-26 — A5 визуальный календарь наличия, инкремент C3 (интеграция + выбор диапазона).**
  Календарь встроен в страницу номера (`stay_detail.html`, под формой дат, в `<details open>`,
  свёртываемый на мобильном). Контекст партиала вынесен в общий хелпер
  `_calendar_context(unit, first, today)` — им пользуются и встроенный календарь
  (`unterkunft_unit`, начальный месяц = месяц заезда или текущий), и fetch-свап
  (`unterkunft_unit_calendar`). **Выбор диапазона кликом** (vanilla, делегировано на document,
  переживает свап месяца): 1-й клик по свободной ночи = заезд (подсветка), 2-й (позже) = выезд
  → заполняет `#id_von/#id_bis` и сабмитит форму дат (сервер считает `_quote`/тарифы — источник
  истины, JS не дублирует валидацию). ISO-даты сравниваются лексикографически. Тест
  `test_detail_embeds_availability_calendar`; регрессия `test_public.py` (21) зелёная.
- **2026-06-26 — A5 визуальный календарь наличия, инкремент C4 (демо/embed). ФИЧА ЗАКРЫТА
  (C1–C4).** Демо-брони HOTEL (in_days 3/6/12/20/35/50, разные статусы) уже наполняют
  визуальный календарь смесью свободно/занято — отдельный сид броней не нужен. Добавлен в
  hotel-сидер `UnitBlock` (Wartungs-Sperrung, +29..+30 дн) — показывает «belegt» БЕЗ брони
  (отличный от бронирований источник занятости; первый UnitBlock в демо вообще). Embed:
  перелистывание сохраняет `&embed=1` в nav-ссылках (виджет G10). Тесты:
  `test_calendar_embed_keeps_embed_in_nav` + assert UnitBlock в `test_apply_hotel_kit_*`.
  **Итог A5-календаря:** C1 `month_availability` (данные) · C2 вьюха `…/kalender/`+партиал
  (перелистывание vanilla-fetch) · C3 встроен в страницу номера + выбор диапазона кликом ·
  C4 демо-Sperrung + embed. Без новых моделей/миграций (поверх `availability`/`StayBooking`/
  `UnitBlock`). Сильнейший рычаг конверсии A5 закрыт.
- **2026-06-26 — Спринт F (A4 Gastro): видимость Kombo/Tagesgericht.** Меню (`products.html`)
  показывает вверху **тизер-карточки комбо** (Menü-Sets/Tagesgericht: имя/описание/цена/«Configure»,
  до 3) вместо одной текст-ссылки — апселл на виду. `product_list` отдаёт `combos_teaser`
  (`active_combos()[:3]`) только при активном orders, на 1-й странице каталога без выбранной
  категории (в категории/при пагинации — прежняя компактная ссылка, без дублей). food-hero-
  пресет признан избыточным (full-bleed фото-hero уже есть). Тесты
  `test_product_list_shows_combos_teaser` + `_combos_teaser_hidden_in_category`. Без миграций.
- **2026-06-26 — Спринт F (A8 Aggregator): сортировка выдачи города.** На городской странице
  агрегатора (`listing.html`) добавлен дропдаун сортировки «Neueste / Name (A–Z)»
  (`?sort=`, auto-submit при change). Бэк `city_listing`: `_LISTING_SORTS` (значение → поле
  keyset-пагинации + descending) — `neueste`=created_at↓ (дефолт), `name`=business_name↑;
  невалидный sort → дефолт. Featured-листинги остаются закреплены сверху; `sort` переносится
  в ссылку «Show more» (пагинация без сбоя). Режим гео-«рядом» сортировку не показывает.
  Тесты `test_city_listing_sort_by_name_orders_az` + `_default_sort_is_newest`. Без миграций.
- **2026-06-26 — Освежение опорных доков (continuity).** `docs/next-session-brief.md`
  (точка входа) переписан под текущее состояние: §1a (всё в `main` `90107c6`, без миграций,
  деплой ручной), §2 (Спринт E закрыт + кусок F: A7-кит/RV3/RV2/A5 PAngV+рейтинг+календарь
  C1–C4/A4 аллергены+Kombo/A9-A7 Festpreis/A8 sort), §3 (остаток F с пометками где нужна
  миграция). CLAUDE.md §3 «Последнее» + §7 «Дальше» обновлены (Спринт E ✅, F частично).
  Source of truth этапа остаётся `archetype-ux-execution-plan.md`. Docs-only.
- **2026-06-26 — Спринт F (A6 RT2): онлайн/Zoom-события.** Новые поля `Event.is_online`
  (bool) + `online_url` (URL) — миграция `events/0017_event_is_online_event_online_url`.
  Витрина: детальная и карточки индекса (грид+список) показывают «🖥 Online» вместо адреса/
  города, карта (OSM) для онлайн-события скрыта (`veranstaltung_detail`: гейт `not event.is_online`).
  **Ссылка доступа (online_url) — не публична:** показывается участнику только ПОСЛЕ брони —
  на странице подтверждения (`event_confirmation.html`, блок «Online access link») + в письмах
  `ticket_confirmed.txt`/`ticket_reminder.txt`. Кабинет: `is_online`/`online_url` добавлены в
  `EventForm.Meta.fields` (форма авто-рендерит). Демо: в retreat-кит добавлено онлайн-событие
  «Online: Morgen-Meditation per Zoom» (без города, Zoom-ссылка) — published-событий 6→7.
  Тесты `test_storefront.py::test_detail_online_event_shows_online_and_hides_map` /
  `_index_online_event_shows_badge` / `_confirmation_online_event_shows_access_link` + demo-assert.
- **2026-06-26 — ТЗ: трек «настоящий анти-Битрикс» (кабинет/админка + онбординг).** По фидбэку
  владельца оформлен план-док `docs/anti-bitrix-admin-plan.md` (Спринт G): AB1 пересборка меню
  кабинета (группировка по задачам Mein Geschäft/Verkaufen/Kunden&Marketing/Einstellungen + язык
  задач + «➕ Funktion») · AB2 страница «Module» v2 (секции рекомендовано/прочее/премиум + «Gut für:
  архетипы» + что даёт) · AB3 мастер онбординга v2 (прогресс/демо-дефолты/живое превью/язык задач) ·
  AB4 чек-лист готовности сайта на дашборде · AB5 регистрация→мастер (high-risk, последним). Цель —
  «чтобы ребёнок собрал и вёл магазин». Фундамент есть (реестр `ModuleSpec` recommended/suited/core/
  premium, мастер `/willkommen/`, живое превью) — переписываем подачу, не модели. Ссылки в
  execution-plan (Спринт G) + CLAUDE.md §7. Docs-only.
- **2026-06-26 — ТЗ: Спринт G перемещён в КОНЕЦ плана + список «остаток Спринта F».** В
  `archetype-ux-execution-plan.md` блок «Спринт G (анти-Битрикс кабинет/онбординг)» вынесен
  после раздела «Текущий статус/Рекомендованный порядок» (идёт ПОСЛЕ остатка F), добавлен явный
  список незакрытых пунктов F. По просьбе владельца «закончим предыдущий план, G — в конце».
- **2026-06-26 — Спринт F (A4 Gastro): диет-теги (vegan/vegetarisch/…) — иконки + фильтр меню.**
  Поле `Product.diets` (JSONField, миграция `catalog/0009_product_diets`) + реестр `food.DIETS`
  (vegan/vegetarisch/glutenfrei/laktosefrei/halal/bio, код+подпись+иконка) + хелпер `diet_badges`
  и property `Product.diet_badges`. Витрина: **иконки диет на карточке** меню (при наличии);
  **фасет-фильтр** `/sortiment/?diet=<код>` (чипы только встречающихся диет, `diets__contains`,
  keyset-совместимо, сохраняет категорию; невалидный код игнорируется). Кабинет: `diets`
  чекбоксами в `ProductForm` (авто-рендер). Демо: теги на 3 товара restaurant (Bruschetta vegan,
  Caprese vegetarisch/glutenfrei, Insalata vegan/glutenfrei). Тесты в `test_food_labels.py`
  (helper/property/иконки/фильтр/невалидный). build:css обновлён.
- **2026-06-26 — Спринт F (A3 Termin): богатая карточка услуги (Service.description).** Поле
  `Service.description` (TextField, миграция `booking/0008_service_description`). Витрина:
  описание «что входит» на карточке блока услуг (`_services.html`, line-clamp-2) + на странице
  выбора времени (`service_slots.html`). Кабинет `/dashboard/booking/services/`: описание в форме
  создания (textarea) и инлайн-обновлении (input) услуги (booking-вью create/update). Демо:
  Werkstatt-услуги получили описания (4-элементный кортеж `(name, min, price, desc)`; сидер
  поддерживает и 3-, и 4-элементный). Тест `test_services_section_shows_description`. build:css
  обновлён. Осталось A3b: фото услуги (image + загрузка) — отдельным инкрементом.
- **2026-06-26 — Багфикс: утечка многострочных `{# #}` комментариев в HTML.** Django НЕ
  вырезает многострочные `{# … #}` → текст утекал в рендер. Исправлены на `{% comment %}`:
  `storefront/_media_gallery.html` (КРИТИЧНО — публичная галерея на всех детальных: товар/
  номер/событие; светила «M20U: универсальная галерея…»), `tenant/site_home.html` (E.2 попап +
  M20d контент-секции), `tenant/_section_fields.html` (M20d поля). Регресс-тест
  `test_gallery_does_not_leak_template_comment` (детальные). Урок зафиксирован в next-session-brief §4.
- **2026-06-26 — Багфикс: `hotels.<base>` отдавал 404 (нет `Domain → public`).** Причина
  `hotels.siteadaptor.de → Not Found`: `seed_demo_tenants._ensure_hotel_portal` создавал
  `AggregatorPortal`, но НЕ строку `Domain(host → public)` — без неё django-tenants
  (`TenantMainMiddleware`) не знает хост и отдаёт 404 ЕЩЁ ДО портального middleware (которому
  нужна public-схема). `create_portal` это делает (Domain + Portal), а seed — забывал.
  Исправлено: `_ensure_hotel_portal` теперь идемпотентно заводит и `Domain(host→public,
  is_primary=False)` (с гардом «чужой домен не трогаем», как в create_portal). Тест
  `test_hotel_portal_seed_creates_portal_and_domain_to_public` (+ идемпотентность). **Деплой:**
  после `git pull && deploy.sh` нужно `seed_demo_tenants --kit hotel --recreate` (создаст Domain).
- **2026-06-26 — A7 before/after-Slider (остаток Спринта F).** Секция `before_after` —
  интерактивный слайдер сравнения «Vorher / Nachher»: «после» как фон, «до» обрезается по
  позиции ручки (`clip-path: inset`), перетаскивание мышь/тач + `<input type=range>` для
  доступности/клавиатуры. Vanilla JS, без библиотек (GDPR), идемпотентная инициализация.
  Реестр секций: `siteui.BLOCK_TEMPLATES["before_after"]` + якорь `#referenzen`;
  `siteconfig.SECTIONS` (выкл по умолчанию) + нормализация `before_after` [{before, after,
  text}] (обе картинки обязательны, текст опционален, потолок `_MAX_GALLERY`). DemoKit:
  поле `before_after` [(before_kw, after_kw, text)] → в config через `demo_image`; секция
  включается в `_kit_sections` при наличии данных. Handwerker-кит сеет 2 кейса (Bad-Sanierung
  / Anstrich). Тесты: `test_before_after_section_renders_slider`,
  `test_before_after_section_registered_default_off`, `test_normalize_before_after_requires_both_images`,
  `test_apply_handwerker_kit_*` (+ assert секции/данных). build:css обновлён. Без миграций.
- **2026-06-26 — A8 фасетные фильтры выдачи: рейтинг + «Jetzt geöffnet» (остаток Спринта F).**
  Городская страница агрегатора (`city_listing`): select минимального рейтинга (3/4/5★ — из
  денормализованного `BusinessRating` в public-схеме) и чекбокс «Jetzt geöffnet» (live-статус
  по `Tenant.opening_hours_structured` через `openinghours.open_status`). Ключевой приём: оба
  фасета сводятся к `pool.filter(tenant_schema__in=<множество схем>)` — keyset-пагинация не
  ломается, миграция не нужна (рейтинг/часы уже денормализованы/на SHARED Tenant). Хелперы
  `_rating_schemas(min)` / `_open_now_schemas(schemas)`; пороги `_RATING_THRESHOLDS=(3,4,5)`.
  UI: одна GET-форма (submit при change) — рейтинг-select + offen-чекбокс + сортировка; непустые
  sort/rating/offen собираются в `filter_qs` и проносятся в ссылку «Show more» (cursor +
  фасеты). Тесты: `test_city_listing_rating_facet_filters_by_min_stars`,
  `_invalid_rating_ignored`, `_open_now_facet_filters_by_hours`. build:css обновлён. Без миграций.
  Попутно: фикс задвоенной строки в `archetype-ux-execution-plan.md` (F-A8 «Дальше»).
- **2026-06-26 — A1/A2 отзывы о товаре, только верифицированные покупатели (остаток Спринта F).**
  Модель `catalog.ProductReview` (TENANT, миграция `catalog/0010`): FK Product, rating(1–5),
  author_name, email, comment, is_published; уникальность `(product, email)` + индекс
  `(product, is_published)`. Верификация покупателя `apps.catalog.reviews.has_purchased(product,
  email)` — есть `OrderItem` с этим товаром у заказа с этим email (≠ cancelled), email без
  регистра; модуль orders выключен/таблиц нет → False (fail-closed, никого не пускаем). Агрегат
  `summary` (avg/count по опубликованным) + `published_for`. Витрина `storefront/product_detail`:
  звёзды-бейдж у заголовка (ведёт к `#bewertungen`) + секция «Customer reviews» (список + форма
  отзыва в `<details>` с пометкой «только верифиц. покупатели»). Приём — `product_review_submit`
  → `POST /sortiment/<pk>/bewerten/` (`storefront-product-review`): рейтлимит по IP
  (`ratelimit.hit`, 10/час), валидация имя+email+rating(1–5), проверка `has_purchased`,
  `update_or_create` (один отзыв на email — повтор обновляет), redirect с message. Демо: поле
  кита `product_reviews` + `_seed_product_reviews`; shop-кит сеет 3 отзыва на первых товарах.
  Тесты: `apps/catalog/tests/test_product_reviews.py` (12 — верификация/агрегат/витрина/POST) +
  assert в `test_apply_shop_kit_retail_features`. build:css без изменений (новых классов нет).
  **Миграция** `catalog/0010` — деплой: `deploy.sh single`.
- **2026-06-26 — A3 богатая карточка услуги: фото услуги (остаток Спринта F).** Поле
  `booking.Service.image` (FileRef-конверт, миграция `booking/0009`) + свойство `image_url`
  (безопасно к не-dict). Витрина: миниатюра в секции «Leistungen» (`_services.html`), обложка
  3:2 + описание на лендинге `/termin/` (`service_index.html`), hero-фото 5:2 на детали
  `/t/<service>/` (`service_slots.html`). Кабинет `/dashboard/booking/leistungen/`: загрузка
  фото при create/update (helper `_service_image_from` → `catalog.images.save_product_image`,
  folder=services; кривой файл → None, CRUD не падает) + чекбокс «удалить»; формы получили
  `enctype=multipart/form-data`. Демо: спец услуги кита расширен до 5 элементов (name, min,
  price, desc, image_kw), Friseur-услуги получили описания+фото. Тесты:
  `test_service_image_url_property`, `test_service_slots_page_shows_photo`,
  `test_cabinet_service_photo_upload_and_remove` (booking) + `test_services_section_shows_photo`
  / `_no_photo_without_image` + assert в `test_apply_friseur_kit_booking_services`. build:css
  обновлён (`aspect-[3/2]`/`[5/2]`). **Миграция** `booking/0009` — деплой `deploy.sh single`.
  Дальше A3: профили мастеров (Resource type=staff + фото/био).
- **2026-06-26 — A3 профили мастеров (Resource staff) — A3 закрыт.** Поля
  `booking.Resource.title/bio/photo` (FileRef, миграция `booking/0010`) + свойство `photo_url`.
  Витрина `/t/<service>/`: пикер специалиста показывает аватар (round) + должность, под пикером —
  карточка-био выбранного мастера. Кабинет `/dashboard/booking/ressourcen/`: для ресурса
  `type=staff` — форма профиля (должность/био/фото upload+remove), действие `resource_profile`;
  generic-хелпер `_uploaded_image_ref(request, field, folder)` (рефактор из `_service_image_from`,
  reuse `catalog.images.save_product_image`, folder=staff). Демо: resource-spec кита расширен
  (title/bio/photo_kw), Friseur Lea/Jonas получили должность+био+фото. Тесты:
  `test_resource_photo_url_property`, `test_service_slots_picker_shows_master_profile`,
  `test_resource_profile_saves_title_bio_photo_and_removes` + assert в Friseur-ките. build:css
  обновлён. **Миграция** `booking/0010`. С этим A3 (богатая карточка услуги + профили мастеров)
  закрыт полностью.
- **2026-06-26 — A9 структурные данные авто (Werkstatt): Kennzeichen/HSN-TSN + AutoRepair LD.**
  Поля `jobs.Job.vehicle_plate/vehicle_hsn/vehicle_tsn` (миграция `jobs/0008`) — Schlüssel-
  nummern из Zulassungsbescheinigung (Feld 2.1/2.2) для точного подбора запчастей.
  `create_job` нормализует (upper/trim, обрезка 15/4/3). Флаг витрины `site_config.jobs_vehicle`
  (`siteconfig.normalize`, дефолт False): при включении публичная `/anfrage/` показывает
  структурные поля авто (модель/Kennzeichen/HSN/TSN, fieldset) вместо одного generic-поля +
  отдаёт schema.org `AutoRepair` JSON-LD (новый параметр `localbusiness_ld(schema_type=...)`
  перекрывает вывод из business_type). Кабинет `templates/jobs/detail.html`: деталь заявки
  выводит Kennzeichen + HSN/TSN. Демо: DemoKit-флаг `jobs_vehicle` (→ config), Werkstatt-кит
  `jobs_vehicle=True` + оба Kostenvoranschläge получили структурные данные (VW Golf DO-MV 1234
  0603/BNV · BMW 320d DO-SK 88 0005/CKA). Тесты: `test_public` (поля показ/скрытие + AutoRepair
  LD + сохранение upper), `test_seo` (schema_type override), `test_siteconfig` (флаг),
  Werkstatt-кит assert. Попутно: `_req` в `test_public` получил уникальный IP per-call —
  фикс flaky rate-limit «anfrage» (5/окно) при нескольких POST-тестах в одном прогоне (общий
  кэш). **Миграция** `jobs/0008`. С этим A9 закрыт.
- **2026-06-26 — A6 RT1: QR-билет + Check-in.** Поле `events.Ticket.checked_in_at` (миграция
  `events/0018`). Публичный QR-эндпоинт `/e/<code>/qr.svg` (`storefront-ticket-qr`, segno SVG,
  rate-limit 60/10мин) кодирует абсолютную ссылку Check-in в кабинете (`events:checkin`);
  страница подтверждения брони (`event_confirmation.html`) показывает QR с подписью «на входе»
  (скрыт для отменённого билета). Кабинет `views.checkin` (login_required) →
  `/dashboard/events/checkin/<code>/` (`templates/events/checkin.html`): GET — карточка
  гостя/события + кнопка «Einchecken»; POST — статус→attended (через TicketSM, фолбэк прямой
  set) + `checked_in_at=now`, идемпотентно (повторный скан не перезаписывает), отменённый билет
  не пускает. Защита: чужой без логина уходит на login. Тесты: `test_cabinet` (GET/POST/
  идемпотентность/lowercase/cancelled) + `test_storefront` (ticket_qr SVG+ссылка, QR на
  подтверждении, скрыт для cancelled). **Миграция** `events/0018`. Closes A6 RT1.
- **2026-06-26 — A6 RV1: 2-шаговый чекаут билета.** Форма брони события
  (`event_detail.html`) разбита на Schritt 1 «Auswahl» (тариф/места/проживание/Extras) →
  Schritt 2 «Ihre Daten» (контакты/анкета/Voucher/рассрочка/Waiver) с обзором выбора вверху
  шага 2 (собирается JS из `data-rv1-label`). Прогрессивное улучшение (vanilla JS, без
  внешних либ/Alpine): без JS оба `data-rv1-step` видимы, кнопки `data-rv1-next`/`data-rv1-back`
  спрятаны (`hidden`) — обычная одностраничная форма; JS включает пошаговый режим (валидация
  выбора тарифа, плавный скролл, summary). Бэкенд `veranstaltung_book` не тронут — единый POST
  со всеми полями по-прежнему бронирует (источник истины — сервер). Тесты `test_storefront`:
  рендер 2-шаговой структуры + регрессия (единый POST бронирует quantity=2). Без миграций.
  Closes A6 RV1.
- **2026-06-26 — A6 RT3: recurring-серии событий.** Поле `events.Event.series_id`
  (UUID, db_index, миграция `events/0019`) группирует повторы. Сервис
  `events.services.create_series(source, *, interval, count)`: клонирует событие
  (pk=None + копия всех полей/JSON + M2M teachers/accommodation_units; билеты НЕ
  копируются), сдвигая `starts_at`/`ends_at` по интервалу (`weekly`/`biweekly`/`monthly`;
  `_add_months` с поправкой на длину месяца — Jan31→Feb28); источник и копии получают
  общий `series_id`; потолок `_SERIES_MAX=52`, всё в `transaction.atomic`. Кабинет
  `views.event_series` (login+POST) → `events:series`; на детали события форма «Repeat this
  event (series)» (интервал + число повторов). Тесты `test_cabinet`: сдвиги/общий id/счётчик
  серии, biweekly+monthly, month-end, копирование M2M без билетов, view создаёт даты.
  **Миграция** `events/0019`. Closes A6 RT3.
- **2026-06-26 — A6 RT4: блог/новости — Спринт F закрыт.** Модель `events.BlogPost`
  (миграция `events/0020`): title/slug(unique)/excerpt/body/cover(FileRef)/is_published/
  published_at + `cover_url`, индекс (is_published, published_at). Публичные вьюхи
  `blog_index` (`/blog/`, только опубликованные) + `blog_detail` (`/blog/<slug>/`, 404 для
  черновика, + «More posts»). Кабинет `blog_list` (список + создание: slugify с дедупом
  `-2/-3…`, publish→published_at) + `blog_edit` (правка/обложка upload+remove/публикация/
  удаление; helper `_uploaded_cover`). Шаблоны `storefront/blog_index|detail.html` +
  `events/blog_list|edit.html`. Демо: DemoKit-поле `blog_posts`, `_seed_blog_posts` (gated
  на events), retreat-кит сеет 2 опубликованные записи + пункт меню «Blog» (/blog/). Тесты
  `test_blog.py` (8: публичный список/деталь/404 + кабинет create-slug/коллизия/edit/delete)
  + retreat-демо assert. build:css обновлён (`aspect-[16/9]`). **Миграция** `events/0020`.
  С этим закрыт остаток A6 и **весь Спринт F**. Дальше — Спринт G (анти-Битрикс кабинет/
  онбординг).
- **2026-06-26 — Спринт G AB1: меню кабинета по задачам (анти-Битрикс).** Сайдбар кабинета
  больше не плоский тех-список модулей, а 4 группы по задачам: «Mein Geschäft» (Übersicht) ·
  «Verkaufen» (catalog/orders/booking/stays/events/jobs) · «Kunden & Marketing» (crm/promotions/
  loyalty/publishing/inbox/telegram) · «Einstellungen» (analytics/finance/customer_account/
  settings/billing). `apps.core.modules.NAV_GROUPS` (порядок групп + ключи) +
  `grouped_active_modules(tenant)` → `[{key,label,modules:[ModuleSpec]}]` (пустые группы
  опускаются, модуль без группы → «Verkaufen»); `context.modules_nav` отдаёт `nav_groups`.
  `_base_dashboard.html` рисует заголовки групп + пункты активных модулей; live-поиск по
  пунктам (`data-label`) сохранён, пустые группы прячутся JS. Заметная «➕ Funktion hinzufügen»
  (border-dashed) → страница «Module» (`modules`). Без моделей/миграций. Тесты: `test_modules`
  (`grouped_active_modules` порядок/раскладка/пустые-группы, `nav_groups` в контексте) +
  обновлён `test_cabinet_nav` (рендер заголовков групп вместо пер-модульных). Closes AB1 —
  начало Спринта G (анти-Битрикс кабинет/онбординг).
- **2026-06-26 — Спринт G AB2: страница «Module» v2 (по архетипу vs общие + Premium).**
  `modules_view` переразбивает реестр в 3 секции в языке задач: «Für Ihr Geschäft empfohlen»
  (core + `is_suited_for(business_type)`, не premium) → `rows`; «Weitere Funktionen»
  (универсальные/прочие, не premium) → `other_rows`; «Premium» (`premium=True`) → `premium_rows`
  (фиолетовый бейдж «★ Premium» в `_module_row.html`; секция скрыта, пока premium-модулей нет).
  Карточка модуля уже несла иконку/описание_de/«Geeignet für: …»/Recommended/Core — добавлен
  Premium-бейдж. Заголовки секций — переводимые (`_module_row.html` без изменений логики).
  `templates/tenant/modules.html` — 3 секции. Тесты: `test_get_shows_task_sections` (empfohlen/
  weitere видны, premium скрыта) + обновлён `_warns_on_untypical_enable` («More functions»
  вместо «Weitere Bausteine»). Без миграций. Closes AB2.
- **2026-06-26 — Спринт G AB4: чек-лист готовности сайта на дашборде.** Хелпер
  `apps.tenants.onboarding.completeness(tenant)` считает готовность по РЕАЛЬНОМУ наполнению
  (не по шагам мастера): баннер/фото (`site_config.hero_image`/`gallery`), Öffnungszeiten
  (`opening_hours`/`_structured`), контакты (`public_email`/`public_phone`/`address`), первый
  товар для продажи (`_has_offering`: Product/Promotion/Service/Event/StayUnit — безопасно к
  выключенным модулям/отсутствию таблиц через try), Impressum (`address`) →
  `{percent, done, total, items:[{key,label,done,url_name}]}`. Дашборд (`dashboard.html`)
  показывает карточку «Your site is X% ready» с emerald-прогресс-баром и пунктами: выполненные
  зачёркнуты (✓), невыполненные — прямая ссылка на действие (`{% url item.url_name %}`).
  Мотивация допилить + путь к действию (анти-«пустой кабинет»). Тесты `test_onboarding`
  (структура/проценты пустого тенанта + отметка заполненных). Без миграций. Closes AB4.
- **2026-06-26 — Спринт G AB3: живое превью в мастере онбординга.** Мастер `/dashboard/setup/`
  (`setup.html`) получил 2-колоночную раскладку (`lg:grid`): слева пошаговый мастер (как было),
  справа — липкое (`lg:sticky`) живое превью витрины в `<iframe src="/">` (same-origin framing
  разрешён `@xframe_options_sameorigin` на `storefront_home`). После каждого шага POST→redirect
  перезагружает страницу → превью отражает сохранённое состояние (тема/баннер/контент/демо).
  Превью на контент-шагах 2–6 (не на выборе типа/финале) + кнопка «🌐 Website öffnen». Прогресс-
  бар «Step N of M» и язык задач (Was machst du?/Stil & Farbe/…) в мастере уже были; демо-дефолты
  (`load_demo`/пресеты) — на шаге 6. Тесты `test_onboarding_wizard`: превью-iframe на шаге 2,
  отсутствие на шаге 1, регрессия full-walkthrough. build:css (arbitrary grid/h-значения). Без
  миграций. Closes AB3. **Остаток Спринта G — только AB5 (регистрация→мастер, HIGH-RISK, гейт
  владельца).**
- **2026-06-26 — Спринт G AB5: регистрация → мастер онбординга (redirect-gate). Спринт G закрыт.**
  Свежезарегистрированный владелец больше не попадает в пустой кабинет: вьюха `dashboard`
  (`apps/core/views.py`) при нетронутом мастере (состояние `step==1, skipped==[], completed==False`)
  редиректит на `setup`. Любое действие в мастере (Weiter/Überspringen/Zurück двигают step/skipped)
  или завершение снимает гейт — остальная навигация кабинета не гейтится, петли нет (редирект
  только из самой `dashboard`, мастер рендерится свободно). Выбран минимальный обратимый
  redirect-gate в самой вьюхе — **без правок `start_business_provisioning`/`create_business`** и без
  миграций (HIGH-RISK снижен до уровня одной вьюхи). Тесты `test_onboarding_wizard`: свежий тенант →
  302 на `/dashboard/setup/`; тронутый (step 2) / skipped=[1] / completed → 200. `test_cabinet_nav`
  обновлён (тенант помечен `completed`, чтобы рендерить сайдбар, а не редиректиться). Closes AB5 →
  **весь трек «анти-Битрикс» (Спринт G AB1–AB5) завершён.**
- **2026-06-26 — Pranasy: полноценная двуязычная витрина (PR-A…H).** Запрос владельца —
  сделать демо-тенант pranasy полноценным + язык DE/EN. Платформенный i18n-фундамент +
  наполнение:
  - **PR-A** двуязычная витрина: тексты site_config «строка ИЛИ {de,en}», оверлей
    `config["i18n"][locale]`, `siteconfig.localize()` сворачивает к локали перед рендером
    (home/about/обложки разделов). DE-рендер не меняется (нулевая регрессия).
  - **PR-B** двуязычные `Event.title/description` (title_i18n/description_i18n + property
    title_text/description_text, миграция events/0021); шаблоны событий → на *_text.
  - **PR-IMG** локальные демо-фото: внешние сервисы (loremflickr) заблокированы/внешние
    (GDPR) → SVG-генератор (градиент+эмодзи+подпись), вьюха `/medien/demo.svg`; все киты
    без внешних зависимостей.
  - **PR-C** инфраструктура двуязычных китов: сидер каталога поддерживает ПОДКАТЕГОРИИ
    (parent/child), двуязычные имена/описания (`_i18n_text`), `DemoKit.i18n`-оверлей,
    `label_i18n` у узлов меню (menu._resolve выбирает по локали).
  - **PR-D…G** переписан PRANASY-кит (DE+EN): Restaurant (8 блюд: Burger/Pizza/Pita/Hotdog/
    Alaputra/Kofta/Schaschlik/Nori-Pakora + «Bald geöffnet», покупка включена) и Shop
    (подкатегории Würstchen×3 / Aufschnitt×3 / Süßes×6) — ДВЕ отдельные сущности (пункты
    меню + блоки главной); Catering (jobs cover + форма), Retreats (6 двуязычных событий +
    мастера + отзывы), лояльность, «О нас» (веган/аюрведа). Слайдер баннеров, обложки
    разделов, двуязычное меню.
  - **PR-H** тесты `test_pranasy_kit` (структура/двуязычность/меню/render-smoke DE+EN),
    обновлены старые pranasy-тесты под новую структуру. Миграция: events/0021.
  Деплой (на владельце): `git pull origin main && ./scripts/deploy.sh single` +
  `python manage.py seed_demo_tenants --kit pranasy --recreate`. План — `docs/pranasy-fullsite-plan.md`.

- **2026-06-27 — on-canvas редактор: SE-1f (режим Обычный/Эксперт) + SE-3d (визуальные
  параметры блока).** План — `docs/storefront-onsite-editor-plan.md`. **SE-1f:** в инспекторе
  блока (`#bld-block-popup`) тумблер «Обычный/Эксперт» (progressive disclosure, выбор в
  `localStorage` ключ `sf_editor_mode`); в обычном режиме скрыты экспертные контролы
  (`data-expert` + CSS `[data-mode=basic] [data-expert]{display:none}`) — порядок/заголовок/
  источник/«View all»/drag-ручка/точный radius/тень; в обычном остаются дружелюбные:
  видимость, раскладка, число, «Round corners». **SE-3d:** per-секция `site_config →
  visual={radius 0..24, shadow bool}` (normalize + `section_visual()`); парсинг в
  `home_builder_view` (источник — slider `visual_radius_px`, фолбэк basic-тоггл → 16px,
  клампинг); live-preview через `collect()`; рендер — класс `.sf-card` на карточках
  товаров/акций/событий/номеров/категорий/услуг + CSS `[style*="--sf-r"] .sf-card{...
  !important}` (обёртка `data-sf-section` несёт inline `--sf-r`/`--sf-sh` лишь когда
  значение задано) → **ненастроенные витрины без регрессии вида**. Тесты — парсинг
  slider/клампинг/фолбэк/тень/рендер контролов+тумблера (`test_home_builder.py`, 33 теста).
  Коммиты `e2eba38`→`decb4ce` (build:css)→`1d84657` (доводка после рассинхрона генерации:
  radius парсился как чекбокс → всегда 0; preview/`.sf-card` не были подключены)→`1ce1975`.
  Без миграций.

- **2026-06-27 — on-canvas редактор: SE-1c (доведение инспектора — перемещение ↑▼).**
  План — `docs/storefront-onsite-editor-plan.md`. После SE-1f drag-ручка и числовой порядок
  стали `data-expert` (скрыты в «Обычном»), поэтому добавлены дружелюбные кнопки **↑▼** в
  строке блока (видны в обоих режимах). Перестановка — **value-based**: правит `order_`-инпуты
  → `collect()` пере-сериализует черновик → live-preview (как описано в плане), без зависимости
  от DOM; `sortListByOrderValue()` синхронизирует DOM-список (в т.ч. при закрытии попапа),
  `updateMoveButtons()` гасит ↑ у первого / ▼ у последнего. Остальные базовые контролы
  (колонки/число/источник/скрыть) уже работали. Тест рендера кнопок. Без миграций.

- **2026-06-27 — on-canvas редактор: SE-2 (редактор на других страницах) — SE-2a-1 + SE-2a-2.**
  План/дизайн — `docs/storefront-onsite-editor-plan.md` (раздел «Дизайн SE-2»). **SE-2a-1:**
  переключатель страницы превью в тулбаре редактора (главная + лендинги активных архетипов;
  `preview_pages` резолвит URL во view); `previewPath`/`previewUrl()` параметризуют iframe —
  `push()` и переключатель грузят выбранную страницу с `?preview=1`. Чтение черновика уже
  page-agnostic (context-processor) → глобальные правки (шрифт/акцент/hero) видны на всех
  страницах. **SE-2a-2:** каталог `/sortiment/` на канве — `product_list` стал draft-aware
  (при `?preview=1` берёт `site_preview_draft` из сессии, как `storefront_home`); грид каталога
  получил `data-sf-section="catalog"`; per-page инспектор раскладки каталога (fieldset «Catalog
  page», контрол `data-page-key="catalog"` → `openBlockPopup` переносит его в попап по клику на
  грид; `collect()` шлёт `catalog_layout` в черновик; `home_builder_view` POST сохраняет
  `catalog_preset`). Инжекты «+»/drag (E.3/E.4) ограничены главной (на лендингах чужой контекст);
  клик-инспектор и инлайн-правка работают везде. Тесты: переключатель, draft-aware грид, маркер
  секции, GET/POST инспектора каталога (63 в core+catalog). Без миграций.
  **SE-2a-3 (категория)** — покрыта SE-2a-2: страница категории = тот же `product_list`
  (`?kategorie=`) и шаблон `products.html` (общий `data-sf-section="catalog"` + draft-aware грид).

- **2026-06-27 — on-canvas редактор: SE-2b-1 (лендинги событий и номеров на канве).** По
  образцу каталога: `veranstaltung_index`/`unterkunft_index` стали draft-aware (при `?preview=1`
  берут `site_preview_draft`); гриды получили `data-sf-section="events"`/`"stay_rooms"` (у
  событий — в обеих ветках список/грид; у номеров — в обзоре и результатах поиска); per-page
  инспектор раскладки расширен (fieldset «Landing pages»: каталог/события/номера, `data-page-key`
  → `openBlockPopup` переносит в попап; `collect()` шлёт `events_index_layout`/`stay_index_layout`;
  `home_builder_view` POST сохраняет `events_preset`/`stay_preset` единым циклом). Тесты:
  draft-aware гриды, маркеры секций, GET/POST инспекторов (76 в core+events+stays). Без миграций.

- **2026-06-28 — on-canvas редактор: SE-2b-2 (порядок/видимость секций детальной события
  на канве).** Тематические секции детальной (реестр `siteconfig.EVENT_DETAIL_SECTION_KEYS`,
  14 шт.) теперь правятся прямо на витрине, а не только на вкладке «Pages». `veranstaltung_detail`
  стал draft-aware (`event_detail_order` при `?preview=1` берёт `site_preview_draft`, как
  каталог/события/номера); `event_detail.html` получил обёртку `data-sf-section="event_detail"`
  (клик-цель инспектора). В `home_builder_view`: переключатель превью включает первое
  опубликованное событие (детальную можно открыть на канве); on-canvas инспектор раскладки
  расширен мини-формой `data-page-key="event_detail"` — value-based ↑▼ (`ed_order_*`) +
  чекбоксы «Show» (`ed_visible_*`); POST сохраняет `event_detail={order,hidden}` с
  presence-guard (без `ed_order_*` не трогает — частичный POST не гасит все секции).
  `collect()`/`edMove` в `site_home.html` сериализуют черновик; `site_preview_draft` принимает
  `event_detail` для live-preview. Тесты: draft-aware detail + обёртка (events), draft endpoint
  + GET-инспектор/превью-страница + POST-сохранение + presence-guard (78 в core+events+pages).
  Без миграций. CI #782 зелёный, FF-merge `a210cea..7b9825b`.

- **2026-06-28 — on-canvas редактор: SE-2c-1 (создание категории в редакторе витрины).**
  Мини-форма «+ Kategorie» в конструкторе главной (отдельная `<form>`, по образцу «Add block»):
  POST `action=add_category` в `home_builder_view` создаёт живую `Category` через `CategoryForm`
  (валидация/slug/parent переиспользуются), сразу `is_active=True` → категория видна чипом на
  канве каталога `/sortiment/`. Категории живут в БД, не в `site_config` → редактор редиректит
  на `site-home`. `sort_order` (обязателен в форме) дефолтится в копии POST, общая форма не
  трогается. GET отдаёт живые категории для parent-select. Тесты: создание, подкатегория под
  родителем, инвалидное имя, рендер формы. Без миграций.
- **2026-06-28 — on-canvas редактор: SE-2c-2 (ссылка правки категории на канве каталога).**
  В режиме редактора (`?preview=1`) каждый чип категории на `/sortiment/` получает ссылку «✎»
  на полную правку категории в кабинете (`catalog:category-edit`) — «добавил мини-формой →
  зашёл и поправил». На витрине посетителя ссылок нет (флаг `is_preview` из `product_list`).
  `data-cat-edit` — задел под инлайн-правку имени на канве (SE-2c-3). Тест: ссылка видна при
  `?preview=1` и скрыта без него. Без миграций. SE-2c-1+2c-2 слиты FF в main (`8616bed`).

- **2026-06-28 — CI-инкремент: ускорение прогонов.** `.github/workflows/ci.yml`:
  `concurrency: {group: ci-${{ github.ref }}, cancel-in-progress: true}` — частые пуши
  ветки отменяют устаревший прогон (на серийном раннере копится только последний;
  подтверждено: промежуточные прогоны #793–795 завершились `cancelled`). Кэш зависимостей:
  `setup-uv enable-cache` + `setup-node cache: npm`. xdist не добавляли (решение владельца).
- **2026-06-28 — on-canvas редактор: SE-2d-1 (фундамент scope «весь сайт»).** Вариант A:
  `siteconfig.normalize_site_defaults` (`card_radius` 0..24, `card_shadow`) + `normalize`
  кладёт `site_defaults` (дефолты 0/false = текущее поведение, без регрессии для legacy).
  Резолвер `effective_card_visual(config,key)`: пер-секционный override (radius>0 или shadow)
  побеждает глобальный дефолт, иначе наследуется `site_defaults`. Юнит-тесты (test_layout.py).
- **2026-06-28 — on-canvas редактор: SE-2d-2 (глобальный стиль карточек на весь сайт, рендер).**
  `context.py` отдаёт `storefront_card_radius/shadow` (normalize+draft-aware, live-preview);
  `_base.html` эмитит inline `--sf-r`/`--sf-sh` на `<body>` ТОЛЬКО при заданном глобале →
  существующий CSS `[style*="--sf-r"] .sf-card` применяет ко всем карточкам каталога/событий/
  номеров/главной. Пер-секционная переменная (ближе к карточке) переопределяет глобальную.
  Пустой `site_defaults` → нет inline-переменных → витрина без регрессии. Тесты (test_live_preview).
- **2026-06-28 — on-canvas редактор: SE-2d-3 (UI глобального стиля карточек).** В группе
  «Design» конструктора — контрол 🌐 «Card style (whole site)» (radius slider 0..24 + тень).
  `home_builder_view` POST пишет `config["site_defaults"]` (normalize клампит), GET отдаёт
  текущие; `collect()`+`site_preview_draft` принимают `site_defaults` → live-preview на любой
  странице под `?preview=1`. Пер-блочный visual (SE-3d) переопределяет глобальный. Тесты
  (test_home_builder + test_live_preview). SE-2d-1/2/3 + CI-инкремент слиты FF в main (`1b8f8dc`).

- **2026-06-28 — on-canvas редактор: SE-2d-5 (live-preview раскладки лендингов).**
  `site_preview_draft` теперь читает `catalog_layout`/`events_index_layout`/`stay_index_layout`
  из payload (collect() их слал, но хендлер игнорил → правка раскладки лендинга была видна
  только после Save). Валидация preset через `siteconfig.LAYOUT_PRESETS`. Тест.
- **2026-06-28 — on-canvas редактор: SE-2d-4 («применить раскладку ко всем лендингам»).**
  В инспекторе «Landing pages» — селектор пресета + кнопка «Apply»: ставит раскладку
  каталога/событий/номеров одним кликом (фронт: значения catalog/events/stay_preset →
  live-preview; Save сохраняет). Тест рендера. **SE-2d закрыт ✅** (1/2/3/4/5); полный
  мультивыбор страниц отложен. Опц. остаётся SE-2c-3 (инлайн-правка имени категории на канве).

- **2026-06-28 — on-canvas редактор: SE-2c-3 (инлайн-правка имени категории на канве).**
  Новый эндпоинт `catalog.category_inline_edit` (login_required/require_POST): JSON
  {category_pk, value} → `Category.name['de']` живой категории (en/прочее не трогает),
  url `catalog:category-inline-edit`. В редакторе (`?preview=1`) чип категории на
  `/sortiment/` несёт имя в `<span data-cat-edit>`; JS в site_home.html делает его
  contenteditable и сохраняет на blur (как `[data-edit]` для site_config). Пустое имя/
  битый pk → 400. Тесты (catalog/test_views). **SE-2c полностью закрыт** (2c-1/2c-2/2c-3).

- **2026-06-28 — on-canvas редактор: SE-3d (фон/отступы карточек).** Расширил визуальный
  механизм SE-2d/SE-3d на фон и внутренние отступы карточек, по тому же образцу наследования.
  `siteconfig`: общие чистилки `_clean_radius/_clean_padding(0..32)/_clean_bg(#rrggbb|"")` +
  `_clean_visual` → `visual={radius,shadow,background,padding}`; `normalize_site_defaults` +=
  `card_bg/card_padding`; `effective_card_visual` возвращает 4 поля с наследованием (override =
  любой заданный параметр секции > глобальный `site_defaults` > пусто=текущий вид). Рендер:
  ОТДЕЛЬНЫЕ CSS-селекторы `[style*="--sf-bg"]`/`[style*="--sf-pad"]` в `_base.html` (не
  объединять с `--sf-r`); `<body>` (site_defaults) и обёртка секции (`home.html`) эмитят
  `--sf-bg`/`--sf-pad` лишь когда заданы; `context.py` отдаёт `storefront_card_bg/padding`.
  UI: глоб. фон(тоггл use)+padding в «Card style (whole site)» + пер-секционные в visual-группе
  попапа; `collect()`/`site_preview_draft` (теперь несёт и пер-секционный `visual`)/POST+GET.
  Фон применяется лишь при включённом тоггле (color-input всегда шлёт значение). Тесты (siteconfig
  35 + home_builder/live_preview). SE-3d ✅ слит FF в main (`f5dcceb`). Без миграций.

- **2026-06-28 — on-canvas редактор: SE-3b (глобальная типографика).** Начертание заголовков
  (`weight_head` из набора 300..800) + межстрочный интервал тела (`line_height` 1.0..2.0).
  Намеренно БЕЗ абсолютного размера шрифта: витрина на Tailwind с фикс-классами `text-*` —
  единый размер сломал бы типошкалу (em-каскад почти не работает). `siteconfig.normalize_typography`
  + в `normalize()`; `context.py` отдаёт `storefront_font_weight_head/line_height` (draft-aware);
  `_base.html` :root эмитит `--fw-head`/`--lh-body` лишь когда заданы, применяет к `body`
  (line-height) и `h1-h3` (font-weight) через `var(…, inherit)`. **Баг пойман локальным тестом:**
  немецкая локаль рендерила `line-height: 1,6` (запятая — невалидный CSS) → `|unlocalize`.
  UI «Design»: селекторы начертания/интервала. Тесты (siteconfig/home_builder/live_preview,
  106 passed). SE-3b ✅ слит FF в main (`17df60f`). Без миграций. Per-section типографика — позже.

- **2026-06-28 — on-canvas редактор: SE-3a (микрошаблоны «Quick styles»).** 5 готовых обликов
  секции-сетки (minimal/soft/bold/magazine/gallery) = комбинация существующего layout-пресета +
  visual (radius/shadow/padding). `siteconfig.MICRO_TEMPLATES` + `micro_templates()`; инвариант:
  preset ∈ LAYOUT_PRESETS (`grid_class_string` purge-safe), radius/padding в клампах. UI: кнопки
  «Quick styles» в инспекторе секции-сетки → ФРОНТ распаковывает облик в обычные инпуты секции
  (layout_preset_/visual_radius_px_/visual_shadow_/visual_padding_) → live-preview; Save сохраняет
  распакованные значения (НЕ новое поле config). Тесты (реестр валиден, кнопки+обработчик). Без миграций.
- **2026-06-28 — DX: ускорение прогонов тестов.** (1) Локально — `--reuse-db` (CLAUDE.md §5):
  тест-БД переиспользуется → повторный прогон 69с→1.1с (вся стоимость была в пере-миграциях).
  (2) CI — **pytest-xdist** (`pytest -ra -n auto --dist loadscope`): полная сюита 1700 тестов на
  параллельных воркерах (django-tenants: тест-БД на воркер test_<db>_gwN, валидировано). CI-прогон
  ~17 мин → **~11 мин**, изоляция тестов в порядке. SE-3a + DX слиты FF в main (`79fa371`).

- **2026-06-28 — on-canvas редактор: SE-3c-min (пер-девайс число колонок).** Вариант C-min:
  явное число колонок секции-сетки на телефон/планшет/десктоп. `siteconfig.normalize_layout`
  += `tablet` (0..4; 0=авто=прежний планшетный вывод `_SM_FROM_COLS`, без регрессии);
  `grid_class_string` использует явный `tablet` если >0; `_GRID_SM` расширен до `sm:grid-cols-4`
  (purge-safe). home_builder POST/GET + `collect()`/`site_preview_draft` несут mobile/tablet/cols;
  UI — 3 мини-поля «📱/▭/🖥 колонок» в инспекторе грид-секции (expert). Тесты (siteconfig 43 +
  DB-suites 159 за 9с с --reuse-db). SE-3c-min слит FF в main (`bc64270`). Без миграций.
  **Ядро SE-3 закрыто** (SE-3a/3b/3c-min/3d). Остаток опц.: SE-3c-mid (скрыть-на-устройстве),
  C-full (порядок пер-девайс) — план в `storefront-onsite-editor-plan.md`.

- **2026-06-28 — on-canvas редактор: SE-4a (переиспользуемые блок-шаблоны).** Многоразовые
  C-блоки в `site_config["block_templates"]={id:{key,label,data}}` (без модели/миграций;
  `normalize_block_templates`, key ∈ REPEATABLE_BLOCKS, data санитизируется по типу, лимит 50,
  back-compat пусто={}). Save: «💾 Save as template» в cb-row → `action=save_block_template:<cb_id>`
  (#home-form, данные из POST через `_read_cblock_data` — ловит несохранённые правки; ранний
  return). Library: отдельная форма → `use_block_template:<tid>` (вставить deep-copy C-блока в
  конец) / `delete_block_template:<tid>`. Переиспользует механизм C-блоков (add_block). Тесты
  (siteconfig нормализация/санитайз + home_builder save/use/delete/GET, 101 passed --reuse-db
  6.5с). SE-4a ✅ слит FF в main (`ef23e6f`). Без миграций. SE-4b/4c — далее.

- **2026-06-28 — SE-3c-mid (скрыть секцию на устройстве 📱/▭/🖥).** Пер-девайс видимость
  секций главной: чекбоксы mobile/tablet/desktop в инспекторе билдера →
  `site_config["sections"][*]["hidden_on"]` (подмножество `_DEVICES`, санитайз `_clean_hidden_on`,
  в `_section` и `_clean_cblock`). На витрине обёртка секции (`home.html`) получает purge-safe
  `max-sm:hidden`/`sm:max-lg:hidden`/`lg:hidden`; `display:contents` вынесен в класс `contents`,
  чтобы классы скрытия переопределяли его на нужном брейкпойнте. `home_builder_view` POST читает
  `hide_<device>_<key>`, GET отдаёт `hidden_on`, `site_preview_draft` проносит в черновик. UI:
  3 чекбокса на секцию + сериализация в `collect()`. Заодно фикс реального бага: многострочный
  `{# #}` в `home.html` Django не парсит как комментарий (он однострочный) → текст тёк в HTML →
  заменён на `{% comment %}`. Тесты: нормализация/санитайз/legacy, POST/GET билдера, рендер
  витрины (есть/нет классов скрытия). Завершает SE-3c (C-min колонки + C-mid скрытие; C-full
  порядок — отложен). Слит FF в main (`56721e2`). Без миграций.

- **2026-06-28 — SE-4b (шаблоны страниц / page templates).** Именованный снимок ВСЕГО набора
  секций главной как многоразовый шаблон: `site_config["page_templates"] = {id: {label, sections}}`
  (`_MAX_PAGE_TEMPLATES=20`, `normalize_page_templates` прогоняет снимок через `normalize_sections`).
  Сохранить = снимок текущей компоновки ИЗ POST (ловит несохранённые правки порядка/видимости, как
  `save_block_template`); применить (`use_page_template:<id>`) = ЗАМЕНА всего набора секций deep-copy
  снимка (это шаблон СТРАНИЦЫ, не вставка) с JS-confirm; удалить (`delete_page_template:<id>`) — из
  библиотеки. Рефактор: тело сборки секций из `normalize()` вынесено в module-level
  `_section_entry`/`normalize_sections` (переиспользуется для снимков; поведение идентично — старые
  section/cblock/layout-тесты зелёные). `home_builder_view`: save в основном потоке (снимок из
  собранного `config["sections"]`), use/delete — ранний return; `page_templates` в GET-контексте.
  `site_home.html`: кнопка «🗂 Save page as template» в `#home-form` + библиотека (Apply с confirm /
  Delete). Тесты: нормализация/кап/санитайз снимка + идемпотентность `normalize_sections`;
  save/use/delete/GET билдера. Широкий прогон `apps/tenants`+`apps/core` 517 passed (рефактор без
  регрессий). Слит FF в main (`0ff18b7`). Без миграций. Завершает связку SE-4 (блоки 4a + страницы 4b).

- **2026-06-28 — SE-4c (вставка шаблона в позицию + индикатор drag на канве).** Улучшение
  on-canvas редактора (E.3/E.4). (A) Backend: `use_block_template:<tid>` принял опц. POST
  `insert_after` → вставка deep-copy шаблона ПОСЛЕ секции key/id (иначе append — back-compat).
  Логика «вставить после секции» вынесена в общий `_insert_after_section(sections, block, after)`
  (дедуп с `add_block`; поведение идентично — регрессионный `test_add_block_after_inserts_at_position`
  зелёный). (B) Канва: `#bld-inserter` дополнен списком сохранённых блок-шаблонов (`data-tpl` →
  `submitInsertTemplate` = POST use_block_template + insert_after) — «вставить шаблон в позицию»
  через надёжный клик-инсертер (нативный cross-iframe DnD parent→iframe в большинстве браузеров не
  срабатывает, поэтому НЕ через drag из библиотеки). (C) drag-on-canvas: видимая линия-индикатор
  позиции вставки (`showDropLine`/`hideDropLine`; dragover/dragleave/dragend/drop гасят/двигают).
  Тесты: use_block_template insert_after (в позицию / в конец); рендер инсертера (шаблоны +
  `submitInsertTemplate` + `showDropLine`). Слит FF в main (`fa4154b`). Без миграций. Завершает
  трек SE-4 (4a блоки + 4b страницы + 4c вставка/drag).

- **2026-06-28 — SE-5b-1 (история версий site_config + откат публикации).** Каждое явное
  «Сохранить» в билдере главной кладёт снимок ПРЕДЫДУЩЕЙ опубликованной версии в кольцевую
  историю `site_config["history"]=[{ts, config}]` (новейшая первая, кап `_MAX_HISTORY=8`).
  Откат — `restore_version:<idx>` (ранний return): заменяет текущий конфиг снимком, а текущую
  версию кладёт в начало истории → сам откат undoable. Снимок = опубликованный конфиг БЕЗ
  вложенного `history` (анти-рекурсия/раздувание). Точки отката = явные Save; инкрементальные
  действия (add_block/шаблоны/restore) основную историю не плодят. siteconfig: `normalize_history`
  (санитайз/кап/strip nested), `push_history(prev, existing, ts)` — чистая (ts параметром, без
  Date — тестируемо), `history` пронесён в `normalize()`. views: главный save-путь снимает текущую
  версию (`timezone.now().isoformat()`), `restore_version`, `history` в GET-контексте. UI:
  секция «Version history» (ts + Restore с confirm). Тесты: normalize_history/push_history
  (санитайз/кап 8/анти-рекурсия/пустой prev=no-op); save создаёт снимок, два save — порядок
  (новейшая первая), restore меняет конфиг и кладёт текущий в историю, невалидный idx no-op,
  GET рендерит список. Без миграций. SE-5b-2 (автосейв черновика в БД) — отложен (опц.).

- **2026-06-28 — SE-5a (кэш HTML витрины + сброс при публикации).** `cache_storefront_page`
  (apps/core/pagecache.py) кэширует отрендеренную главную витрины тенанта на
  `PUBLIC_PAGE_CACHE_TTL`=120с. Ключ `sfpage:{schema}:{path}:{lang}:v{version}` включает
  пер-тенантную версию; публикация инвалидирует мгновенно: сигнал `post_save` на Tenant (когда
  `site_config` в update_fields) → `bump_storefront_cache(schema)` инкрементит `sfver:{schema}` →
  ключ меняется, старые осиротевают и истекают по TTL (без delete_pattern). Мимо кэша (как
  `cache_public_page`): непустая сессия (владелец залогинен/корзина), query (?preview=1/?tisch=N),
  не-GET, public-схема → кэш обслуживает только анонимный сессионный GET (SEO/первый визит).
  Fail-open (недоступный Redis не валит). Декоратор под `@xframe_options_sameorigin` (X-Frame-Options
  сохраняется на кэш-хитах). В тестах TTL=0 → выключен (без регрессии 218 storefront-тестов).
  Слит FF в main (`0c65d5b`). Без миграций.
- **2026-06-28 — SE-5b-2 (автосейв черновика в БД).** Черновик редактора переживает закрытие
  браузера/смену устройства: `site_preview_draft` пишет его не только в сессию, но и в БД под
  `site_config["_draft"]`(+`_draft_ts`) через `Tenant.objects.update()` — (1) не триггерит сигнал
  сброса кэша SE-5a (опубликованный контент не менялся), (2) дешевле полного save(). На GET-загрузке
  редактора при наличии `_draft` форма открывается на черновике + сессия засевается (превью синхронно)
  + info-сообщение; явное «Сохранить» публикует и чистит `_draft` (normalize дропает служебный ключ).
  Изоляция: `_draft`/`_draft_ts`/`history` исключены из снимков истории (`_SNAPSHOT_EXCLUDE` в
  normalize_history/push_history) и из выдачи (normalize строит из известных ключей). Тесты:
  персист в БД (опубликованное не тронуто), GET-восстановление (форма+сессия), Save чистит,
  push_history/normalize исключают служебное. Слит FF в main (`e429714`). Без миграций. **SE-5 закрыт.**

- **2026-06-28 — Фикс: многострочные {# #} текли видимым текстом в билдере/витрине.** Django
  `{# #}` — однострочный комментарий; многострочный не сворачивается и рендерится как текст
  (владелец видел «{# SE-3a … #}», «{# SE-3c … #}» прямо в конструкторе). Все 16 многострочных
  переведены в `{% comment %}`: `site_home.html` (13), `_base.html` (кнопка «Edit design»),
  `event_detail.html`, `products.html` (превью-чипы). Регресс-гард
  `test_no_multiline_hash_comments_in_templates` сканирует весь `templates/`. Слит FF (`aeef1c9`).
- **2026-06-28 — SE-6: полноэкранный overlay-редактор (Вариант A).** Фидбэк владельца: «Edit design»
  вёл в узкий сплит-пейн кабинета (маленький iframe + форма, зажато сайдбаром-меню) → сайт не виден
  на 100%, править неудобно. Сделано: билдер `#bld-root` = `fixed inset-0 z-40` (перекрывает сайдбар
  кабинета → сайт на всю ширину как реальная витрина); инспектор `#bld-editor-pane` — плавающая
  шторка справа поверх канваса (`translate-x-full` тоггл «✏️ Edit panel» в топ-баре, ✕ закрыть,
  бэкдроп на мобайле, на ≥lg открыта по умолчанию); топ-бар (← в кабинет · заголовок · тоггл · Save
  через `form="home-form"`); канвас `#bld-preview-pane` = `absolute inset-0` с тонким тулбаром
  (Undo/Redo·страница·девайс·статус), iframe `h-full` (вместо 78vh). **Все id сохранены** → вся
  логика (collect/draft/клик-правка/drag/инсертер/шаблоны/история/undo) переиспользуется без правок;
  старый мобильный таб Редактор/Превью заменён drawer-тогглом, `activate("editor")` (click-to-edit)
  открывает шторку. Только перекладка `site_home.html` (shell + ~25 строк JS), без бэкенда/моделей/
  миграций. Тест SE-6 структуры. **Вариант B (in-page без iframe) — отложен.** Слит FF (`4627cf5`).

- **2026-06-28 — SE-7a: рейл областей + фокус-панель редактора (Вариант 3).** Редизайн панели
  по фидбэку владельца (уйти от перегруженных списков). Поверх SE-6: вместо одной длинной шторки —
  тонкий вертикальный РЕЙЛ иконок слева (🎨 Тема · 🧱 Секции · 📚 Шаблоны · 🖼 Медиа); клик
  открывает фокус-панель ТОЛЬКО этой области (`data-bld-area`, остальные скрыты) → без перегруза;
  повторный клик / ✕ сворачивает в рейл (сайт на всю ширину). Контент партиционирован: theme
  (дизайн/типографика/карточки), sections (блоки главной/лендинги/тизеры/C-блоки), library
  (шаблоны+история), media (категории+галерея). Все id/логика сохранены (click-to-edit `activate`
  открывает sections). Починен tag-mismatch из SE-6 (`<aside>`…`</div>`→`</aside>`). Только
  перекладка `site_home.html` + rail JS, без бэкенда/миграций. Слит FF (`9acd58c`).
- **2026-06-28 — SE-7b: миниатюры раскладок вместо выпадашек.** Селекты раскладки (`layout_preset_*`,
  catalog/events/stay/apply-all) помечены `data-thumb`; JS прячет `<select>` (sr-only, остаётся в
  форме) и рисует кликабельные мини-диаграммы (list/2/3/4/gallery — грид-ячейками `currentColor`,
  активная = индиго) — «как выбор разворота в фотокниге». Клик ставит `select.value` + dispatch
  change → live-preview/collect/quick-styles работают без правок бэкенда; quick-styles теперь тоже
  диспатчит change (синхрон миниатюр). Без миграций. Слит FF — см. след. коммит.

- **2026-06-28 — SE-7 review-фиксы + SE-7c (Меню как область).** (1) Adversarial review-workflow
  редактора (4 измерения×verify) нашёл 4 реальных бага → починены: попап настроек блока уезжал за
  экран при свёрнутой панели (transform-containing-block) → `openBlockPopup` открывает sections;
  попап перекрывал левую панель → позиц. справа (offsetWidth); «применить ко всем лендингам» не
  диспатчил change → миниатюры рассинхронивались; a11y `aria-pressed` на рейле (`774a5fe`, `c56a2c5`).
  (2) **SE-7c:** область ☰ «Меню» в рейле — стиль шапки (classic/centered/minimal, радио-кнопками)
  + sticky-чекбокс; пункты меню — ссылка в полный билдер `/dashboard/site/menu/`. home_builder
  GET отдаёт nav_style/nav_sticky/nav_styles; POST читает их с presence-guard (`if nav_style in POST`
  → пишем style/sticky, иначе config["nav"] как был — пункты не трогаем). Тесты: GET рендерит
  область+поля, POST сохраняет стиль/sticky, presence-guard не затирает nav. Без миграций.

- **2026-06-28 — SE-7d: Баннер + Подвал как области рейла (трек SE-7 завершён).** В рейл добавлены
  🖼 «Баннер» (заголовок/текст hero — `hero_title`/`hero_text`, картинка — на канве/в Медиа) и
  🔻 «Подвал» (видимость секции контактов + ссылки в Settings на контакты/часы/Impressum — это
  поля Tenant, не дублируем формы). Иконка Медиа 🖼→🗂 (чтобы не путать с Баннером). home_builder
  GET отдаёт hero_title/hero_text; POST читает их с presence-guard. Тесты: GET рендерит области+поля
  (pre-filled), POST сохраняет hero, presence-guard. Без миграций. **Итог SE-7 (Вариант 3, рейл
  иконок + фокус-панель): 7a каркас · 7b миниатюры раскладок · ревью-фиксы (4 бага) · 7c Меню ·
  7d Баннер+Подвал.** Области рейла: 🎨 Тема · 🖼 Баннер · 🧱 Секции · ☰ Меню · 🔻 Подвал ·
  📚 Шаблоны · 🗂 Медиа — одна за раз, без перегруза.

- **2026-06-28 — SE-8a + SE-8b (редактор «для ребёнка», начало).** (a) **SE-8a:** вернул ГЛОБАЛЬНЫЙ
  Простой/Эксперт — тумблер был спрятан в попапе блока, CSS прятал `[data-expert]` лишь внутри него,
  в рейле/панелях режим не работал. Теперь `data-mode` на `#bld-root` (дефолт basic), тумблер в
  топ-баре, `#bld-root[data-mode=basic] [data-expert]{display:none}` → Простой прячет технику ВЕЗДЕ.
  Помечено `data-expert`: типографика, «стиль карточек весь сайт», пер-девайс колонки, лимит,
  источник, скрытие-на-устройстве, точный radius/тень/отступы, drag/order. localStorage (`3f01610`).
  (b) **SE-8b:** починен live-preview — Меню (nav_style/sticky) и Баннер (hero_title/text) теперь в
  `collect()` payload + применяются в `site_preview_draft` → правки видны вживую (раньше только после
  Save). Тест draft применяет nav/hero. Без миграций. SE-8c (готовые виды)/8d (канва) — далее; владелец
  предложил перестройку IA «динамический рейл из включённых блоков, медиа внутри блоков» (SE-9, на согл.).
- **2026-06-29 — SE-9a + SE-9f (мобильная версия первым классом + компактный рейл).**
  (a) **SE-9a:** иконки рейла мельче — nav `w-16→w-14`, кнопки `w-14 py-2→w-12 py-1.5`, эмодзи
  `text-xl→text-lg`, подпись `text-[10px]→text-[9px]` (фидбэк «уменьшить миниатюры»).
  (b) **SE-9f:** переключатель версии сайта Desktop/Tablet/Mobile в канве (был, но незаметен и
  моб-превью читалось узкой колонкой) сделан первоклассным: подпись «Версия:» + `data-dev`;
  Tablet/Mobile → превью в рамке-бизеле (`#home-prev-shell.device-frame`, border 10px/rounded-2.2rem)
  + фикс-высота (mobile 760, tablet 1112) → читается как телефон/планшет; габариты в `#home-dev-dim`;
  выбор запоминается (localStorage `sf_preview_device`). Превью — реальная адаптивная витрина. Тест
  `test_home_builder_get_renders_device_version_toggle`. Без миграций (`266e3cd`).
- **2026-06-29 — SE-9g (правка мобильной раскладки в Простом режиме).** Пер-девайс контролы
  (колонки на устройстве, скрыть на устройстве) были видны лишь в Эксперте (`data-expert`). Теперь
  при выбранной версии 📱/▭ в Простом режиме они раскрываются прямо в области «Секции» —
  крутить телефонную/планшетную версию без ухода в Эксперт. `applyDevice` ставит `data-device` на
  `#bld-root`; CSS `[data-mode=basic][data-device=mobile] [data-device-ctl]{display:flex!important}`
  (специфичность выше правила-пряталки) + подсказка `.bld-device-hint`. Маркер `data-device-ctl` на
  двух группах. Тест `test_home_builder_mobile_layout_unlocks_in_simple_mode`. Без миграций.
- **2026-06-29 — SE-9b (медиа внутрь блоков; убрать общую «Медиа»).** Глобальная область/иконка
  «Медиа» убрана; медиа и быстрые действия открываются С БЛОКА. Ограничение: попап/секции — внутри
  `#home-form`, мультипарт-формы туда вкладывать нельзя → две области ВНЕ формы: `gallery-media`
  (загрузка/удаление фото) и `catalog-add` (добавить категорию). На блоке «Галерея» кнопка «🖼 Фото (N)»,
  на блоке «Категории» — «＋ категория», открывают свою область через `window.__sfShowArea(area)` (карта
  подписей в JS, не в onclick → апостроф перевода не ломает кавычки атрибута). `showArea(area, title)`
  принимает заголовок для областей без кнопки рейла. Подсказка баннера — без «Media». Бэкенд/хендлеры
  (`upload_gallery`/`delete_gallery_image`) не тронуты. Рейл стал 6 иконок. Тест
  `test_home_builder_media_moved_into_blocks`. Без миграций.
- **2026-06-29 — SE-9d (явный режим «Править на сайте»).** Инфраструктура прямой правки на канве уже
  была и всегда активна (текст `[data-edit]`/`[data-cat-edit]` → contenteditable + сохранение на blur;
  drag-ручки `[data-sf-drag]`; вставки `[data-sf-ins]`). Добавлен явный тумблер в топ-баре
  `#bld-edit-toggle` «✍️ Edit on site» (по умолчанию ВКЛ — без регресса): `applyEditMode(on)` через
  `styleEditable` вкл/выкл редактируемость+подсветку текста и видимость ручек/«+»; выкл → чистое
  превью (как у посетителя). Запоминается (`localStorage sf_edit_on`), переключается на лету без
  перезагрузки (`lastEditDoc`). Подсказка `#bld-edit-hint`. Тест
  `test_home_builder_get_renders_edit_on_site_toggle`. Без миграций. Трек SE-9 закрыт, кроме большого
  SE-9c (динамический рейл) — отдельным планом + согласование.
- **2026-06-29 — SE-9c-1 (динамический рейл: иконки включённых блоков).** Первый шаг большого SE-9c:
  под глобальными иконками рейла — разделитель + динамические иконки ВКЛЮЧЁННЫХ контент-блоков
  (`{% for s in sections %}{% if s.enabled and key != hero %}` → `.bld-blk-btn[data-blk]`). Клик зовёт
  `openBlockPopup(key)` (реюз — сам открывает область sections и позиционирует попап настроек блока).
  Эмодзи-карта `_SECTION_ICONS` (views.py) → поле `icon` в `sections`. Репитабл-блоки (text/image/…) не
  попадают (они в `cblocks`, не в `sections`); баннер пропущен (правится глобальной 🖼). «Секции» 🧱 пока
  остаётся (очистится в SE-9c-2). Тест `test_home_builder_dynamic_block_rail`. Без миграций.
- **2026-06-29 — FIX prod 500 на `/dashboard/site/`.** `site_view` («Site») строил список секций как
  `labels[s["key"]]` БЕЗ защиты, а `config["sections"]` может содержать repeatable-блоки (text/image/
  button/spacer, добавленные инсертером «+» в конструкторе главной) и неизвестные ключи — их нет в
  `SECTIONS` → `KeyError` → 500. `home_builder_view` это уже обходил (`if key not in labels: continue`),
  `site_view` — нет. Добавлен тот же фильтр `if s["key"] in labels`. Регрессия
  `test_site_view_survives_repeatable_block_in_config` (config с блоком text → раньше 500, теперь 200).
  `nav_items` безопасен (normalize отбрасывает неизвестные nav-ключи). Без миграций (`d079273`).
- **2026-06-29 — SE-9c-3 (подсветка активной иконки блока в рейле).** При открытом попапе настроек блока
  его иконка `.bld-blk-btn` подсвечивается (`highlightBlkBtn(key)` из `openBlockPopup` — любой источник:
  рейл или клик по секции на канве; снятие в `closeBlockPopup`). **SE-9c-2 отложен** (конфликт с SE-9g +
  Простой режим уже де-загромождает мастер). **Трек SE-9 «редактор для ребёнка» закрыт:**
  9a/9f/9g/9b/9d/9c-1/9c-3. Без миграций (`bf7d182`).
- **2026-06-29 — FIX редактора по фидбэку pranasy (попап + «Edit on site») + обкатка.**
  (a) Попап настроек блока копил строки нескольких блоков («куча настроек других блоков», превью «не
  менялось»): `openBlockPopup` ставил `popupAnchor`, но НЕ `popupRow` → `closeBlockPopup` не возвращал
  строку. Фикс `popupRow = row;` → попап показывает только выбранный блок (`fa45e46`). (b) «Edit on site»
  был ВКЛ по умолчанию → клик ВЫКЛЮЧАЛ правку; дефолт → ВЫКЛ, клик включает режим правки (`fa45e46`).
  (c) Обкатка (B): регресс-сетка — все 5 страниц редактора + витрина держат «свободно собранный» конфиг
  (контент-блоки/секции/галерея/hero) → 200 (`40b7b71`).
- **2026-06-29 — Inline-content Фаза 1, P1-1 (бэкенд правки текста товара на витрине).** Оценка сложности
  «править контент прямо на витрине» → план `docs/storefront-inline-content-plan.md` (фазами: текст→цена→
  фото; структура — в форме). P1-1: `product_inline_edit` (catalog) клонирует паттерн `category_inline_edit`
  — JSON {pk, field, value}, вайтлист `{"name","description"}` → `Product.<field>['de']` живого товара;
  имя пустым не сохраняем; не-вайтлист-поле (цена) → 400. URL `catalog:product-inline-edit`. 5 тестов
  (вкл. защиту цены). Без миграций.
- **2026-06-29 — Inline-content Фаза 1, P1-2 (фронт: имя товара правится на канве витрины).** В
  редакторе-iframe (`site_home.html`) добавлен обработчик `[data-edit-model]` (реюз `styleEditable`/
  `markSaved`; карта `MODEL_EDIT_URLS={product: catalog:product-inline-edit}`; на blur POST
  {pk,field,value}; уважает режим правки `editOn` SE-9d). Имя товара в `_product_card.html` размечено
  `data-edit-model="product" data-edit-pk data-edit-field="name"`; т.к. имя внутри ссылки-карточки —
  в режиме правки клик гасит навигацию (`preventDefault`). `applyEditMode` теперь переключает и
  `[data-edit-model]`. Тесты: карточка с хуками (витрина), редактор навешивает обработчик. Без миграций.
- **2026-06-29 — FIX скролл меню кабинета + диагностика баг D (раскладка).** (1) `#dash-nav`
  (`flex-1 overflow-y-auto`) не скроллился — не хватало `min-h-0` (флекс-ребёнок растёт под контент
  вместо скролла); группировка AB1 сделала меню выше viewport и пробел вылез. Добавлен `min-h-0`;
  сайдбар на десктопе `md:sticky md:top-0 md:h-screen` (меню остаётся в зоне видимости, скроллится
  внутри). (2) Баг D «вид отображения не применяется»: тест доказал — бэкенд применяет раскладку
  (черновик cols4 → витрина `lg:grid-cols-4`); причина визуального «не меняется» — узкое превью
  (`lg:` ≥1024 не срабатывает, `sm:`-шаг совпадает для 2/3). Фикс десктоп-ширины превью — в UX-пассе.
- **2026-06-29 — FIX баг D (корень) + браузер-проверка.** Уточнённый диагноз (предыдущая запись про
  «узкое превью» — лишь вторичный симптом, не корень): настоящая причина — у секции оставался явный
  пер-девайс `cols` (напр. 3), а `normalize_layout` ставит явный `cols` ВЫШЕ пресета (`eff` из пресета,
  затем `cols = _clamp(raw.get("cols", eff["cols"]))`), поэтому выбор «2 в ряд» (пресет `cols2`) всё
  равно рисовал 3 колонки. Фикс (`site_home.html`): клик по миниатюре-пресете (`layout_preset_*`)
  сбрасывает `cols/mobile/tablet` секции → `collect()` не шлёт явный `cols` → пресет реально применяется.
  Тесты: `test_storefront_preview_explicit_cols_overrides_preset` (бэкенд: `{preset:cols2}`→`lg:grid-cols-2`,
  `{preset:cols2,cols:3}`→`lg:grid-cols-3`) + маркер фикса в попап-рендере. **Проверено в браузере**
  (Chromium/Playwright, тенант `baeckerei-test`): продукты с залипшим `cols=3` → `lg:grid-cols-3`; клик
  «2 в ряд» → `lg:grid-cols-2`, инпуты `cols/mobile/tablet` очищены, JS-ошибок нет (скрины до/после).
  CI зелёный (`5ba716e`/`5f214be`). FF-merge в `main`. Без миграций. («Узкое превью ≥1024px» — отдельный
  пункт UX-пасса, не блокер.)
- **2026-06-29 — Редактор/кабинет UX-батч (ТЗ владельца #2–#6), всё проверено в браузере.**
  **#2 одна фокус-панель блока** (вместо 2-го плавающего попапа): `#bld-block-popup` перенесён ВНУТРЬ
  левой панели (первый элемент секции-области); клик по блоку (иконка рейла / секция в превью) даёт
  секции `.focus-on` → CSS прячет список блоков и прочие fieldset'ы, виден только этот блок + «← Ко всем
  блокам» (бывшая ✕); реюз relocate (popupRow/popupAnchor); SE-1f тумблер сохранён. Переключение области
  рейла / свёртка панели — выход из фокуса с возвратом строки в список. **#3 крупнее рейл:** nav `w-14→w-20`,
  кнопки `w-12 py-1.5→w-16 py-2`, эмодзи `text-lg→text-2xl`, подписи `text-[9px]→text-[11px]`. **#4 десктоп-
  превью ≥1024px:** «Desktop» всегда рендерится логически на 1280px, узкую канву масштабируем (transform
  scale на iframe + layout-box shell) → `lg:grid-cols-N` витрины реально срабатывают (раньше на узком
  превью «2/3/4 в ряд» неразличимы, т.к. `sm`-шаг для 2/3 совпадал); пересчёт на resize. **#6 аккордеон-
  группы меню кабинета** (`_base_dashboard.html`): заголовки `nav_groups` — кнопки-аккордеоны (шеврон ▾/►),
  состояние в `localStorage` (`dash_nav_collapsed`), активная группа всегда развёрнута, поиск временно
  раскрывает (`#dash-nav.searching`). Браузер-проверки (Chromium, baeckerei-test): #2 вход в фокус через
  иконку и клик секции → список скрыт/popup не fixed/возврат восстанавливает; #3 рейл 79px/эмодзи 24px/
  подпись 11px; #4 iframe.innerWidth=1280, matchMedia(min-width:1024)=true, «4 в ряд»→4 колонки на узкой
  канве; #6 сворачивание/persist/active-развёрнута/поиск. Поймана и исправлена многострочная `{# #}`
  (рендерилась как текст в меню) → `{% comment %}`. CSS пересобран (`npm run build:css`). #5 (явная кнопка
  свёртки) уже покрыт (✕ панели + клик активной иконки рейла). #7 (inline Фаза 2/3) — на согласовании, не
  трогал. Без миграций. Локально: ruff ✓, 191 тест ✓.
- **2026-06-29 — Медиа-трек M1+M2 + inline-content #7 A+B + фикс сворачивания (всё проверено в браузере).**
  Контекст: владелец попросил редактировать лого/слайдер/фото «через попапы»; разведка (2 Explore-агента)
  показала, что лого не выводится, а слайдер `heroes[]` в билдере не редактируется. Порядок M1→#7AB→M2.
  **FIX сворётки панели:** `#bld-editor-pane` позиционирован внутри канвы (смещена на рейл w-20=5rem) →
  `-translate-x-full` оставлял полоску панели поверх рейла; класс `.bld-collapsed` =
  `translateX(calc(-100% - 5rem))` уводит полностью (миниатюры видны). **M1 — лого:** шапка витрины
  (`_base.html`) показывает `<img>` из `Tenant.logo_url` (модель, минует draft; агрегатор уже его юзает),
  иначе текстовое имя; в билдере Theme→Logo → область `logo-media` (multipart upload_logo/delete_logo,
  `save_product_image folder=logo`). **#7-A — ✎ к форме:** на карточке `.sf-edit-link` (hidden) → форма
  `catalog:product-edit` target=_blank; JS билдера раскрывает только в превью. **#7-B — инлайн-цена:**
  `product_inline_edit` принял `base_price` (Decimal, запятая→точка, 0..1e6, ТОЛЬКО без вариантов →
  иначе 400; `bump_storefront_cache`); фронт: клик по цене (editOn) → инпут-поповер → POST → перерисовка.
  **M2 — слайды баннера:** область `banner-media` (multipart, как logo/gallery), кнопка «Manage slides» в
  🖼 Banner; на слайд фото(файл)+заголовок+текст+кнопка; save/delete/move_hero_slide на `site_config["heroes"]`
  (≤6); витрина-слайдер (`_hero.html`) уже умел рендерить. Браузер: лого 220×60 в шапке; ✎ на 6 карточках;
  цена 3.50→7.77 (DB+превью); слайд «Sommer-Aktion» с фото на витрине; JS-ошибок нет. CI зелёный, FF-merge
  `dddc632..6bb53a2`. Без миграций. (Локальный стенд: `SERVE_MEDIA=True` в dev-override для /media/;
  on-canvas клик по баннеру НЕ делали — `heroes` обёрнут в `[data-sf-section=hero]`, секция-хендлер
  перебивал; «как Лого» = кнопкой. Осталось медиа: **M3** обложки/галерея на канве, **M4** инлайн-фото товара.)
- **2026-06-29 — Медиа-трек завершён: M4 (фото товара) + M3 (обложки разделов), проверено в браузере.**
  **M4 — инлайн-замена главного фото товара:** на карточке кнопка 📷 (рядом с ✎), hidden, раскрывается в
  режиме правки (editOn); клик → файл-диалог → multipart POST `catalog:product-photo-edit` → новое фото
  primary (прежние не-primary), `bump_storefront_cache`, перерисовка. Завершает inline-трио #7 (текст/цена/
  фото). **M3 — обложки разделов:** фото-баннер лендинга архетипа (`archetypes[key].hero_image`) теперь
  грузится из билдера — область `covers-media` (кнопка «Cover photos» в 🖼 Banner), цикл по `cover_specs`,
  реюз `_upload_cover_hero` (folder=cover), экшен подключён в `home_builder_view`; интро/галереи разделов
  остались на странице Sections (ссылка). Браузер (baeckerei-test, SERVE_MEDIA): 📷 → DB images[0] primary
  /media/products/…png, карточка показывает фото; обложка «catalog» → archetypes.catalog.hero_image
  /media/cover/…png, миниатюра в редакторе. JS-ошибок нет. CI зелёный, FF-merge. Без миграций. **Весь
  медиа-трек (M1 лого / M2 слайдер / M3 обложки / M4 фото товара) + #7 A+B — готовы.**
- **2026-06-29 — Редактор: фикс слайд-менеджера + ширина контейнера секции (фидбэк владельца, 3 пункта).**
  По скрину менеджера баннер-слайдов (Pranasy): (1) **контент слайда не помещался в панель** — карточка
  перестроена в стопку (фото+контролы ▲▼✕ верхним рядом, форма во всю ширину панели полями `w-full min-w-0`
  вместо двух `w-1/2`; то же для covers-media); проверено в браузере: панель 360px, гориз. скролла нет
  (`scrollWidth−clientWidth=1px`), все поля в пределах. (2) **возврат к области после сохранения** — `showArea`
  пишет `localStorage['sf_cur_area']`, `closePanel` чистит; init на широком экране восстанавливает область из
  localStorage (если она есть в панели), иначе `sections`; проверено: правка слайда → Save → редактор снова
  открыл `banner-media` (правка сохранилась). (3) **SE-3e ширина контейнера секции (contained/full)** — пер-
  секционная (для ЛЮБОЙ секции, не только сеток; общий размер задан в шаблоне `_base.html` max-w-7xl).
  Хранится на уровне секции `width` (нормализуется в `_normalize_section` и `_clean_cblock`, кламп к
  `("contained","full")`); UI — селект «Width» в визуальном ряду билдера (basic, для всех секций);
  `collect()`/`site_preview_draft` прокидывают в live-preview; рендер — `storefront/home.html` ставит full-bleed
  обёртку (`relative left-1/2 -translate-x-1/2 w-screen px-4 lg:px-8`, как hero) при `b.width=='full'`, иначе
  `display:contents`. Браузер: products→full = `w-screen`, ширина обёртки = вьюпорт, гориз. скролла НЕТ;
  contained-дефолт без регрессии. Тесты: нормализация ширины (+C-блок), POST-сохранение, GET-рендер контрола.
  Без миграций.
- **2026-06-29 — H1.1: фикс «клик по ссылке в редакторе → ошибка» (X-Frame-Options).** Корень (воспроизведён
  в браузере на Pranasy): прод ставит `X-Frame-Options: DENY` глобально; `storefront_home` декорирована
  `@xframe_options_sameorigin` и грузится в iframe редактора, а остальные storefront-страницы (`/sortiment/`,
  `/termin/`, `/veranstaltung/`, деталь товара…) — нет → при клике по ссылке внутри превью-iframe браузер их
  блокирует («refused to connect»). Поэтому ошибка ТОЛЬКО при запущенном редактировании (там витрина в iframe),
  на публичном сайте переход верхнеуровневый — всё работает. Фикс: `StorefrontFrameOptionsMiddleware`
  (`apps/core/middleware.py`, ВЫШЕ `XFrameOptionsMiddleware` → перебивает DENY) выставляет `SAMEORIGIN` для
  storefront-страниц; `/dashboard/`,`/accounts/`,`/admin/` остаются `DENY` (клик-джекинг); ответы с
  `xframe_options_exempt` (G10 embed-виджет для чужих сайтов) не трогаем. Проверено в браузере: клики по
  ссылкам в превью открывают `/sortiment/`,`/termin/…` (editOn off/on). Тесты `test_frame_options.py` (4). Без
  миграций. Часть этапа «архетипы как сущности» — план `docs/archetype-entities-plan.md`.
- **2026-06-29 — H0 (срез 1): гейтинг секций редактора по архетипу.** Матрица «секция главной → архетип-модуль»
  (`apps/core/archetypes.py::SECTION_ARCHETYPE_MODULE` + `section_visible_for(tenant, key)`): секции без записи —
  generic (видны всегда), секция-архетип — только если её модуль активен. `home_builder_view`: GET скрывает из
  списка секций нерелевантные архетипу (пекарня без stays/events/booking/jobs не видит Stay/Search/Rooms/Services/
  Events/Before-after); POST — carry-forward конфига скрытых секций (их полей в форме нет → не затираем enabled/
  layout/visual). ⚠️ catalog = core → products/categories видны у всех (over-inclusion безопасен; «только под
  primary-архетип» — отложенное решение, см. план). Браузер (baeckerei, disabled stays/events/booking/jobs):
  список секций = generic+catalog, чужих архетипов нет. Тесты `test_archetype_gating.py` (5). Без миграций.
  Дальше H0: гейтинг storefront-меню по архетипу, реестр 3 сущностей, матрица настроек/полей.
- **2026-06-29 — H1.3: «Section = чистый список»; настройки секции → в фокус-панель блока.** Строка секции в
  редакторе (`templates/tenant/site_home.html`) разнесена на `.home-block-head` (идентичность: ▲▼ перемещение,
  чекбокс вкл/выкл, имя-кнопка, ⚙ — ВСЕГДА в списке) и `.home-block-settings` (раскладка/width/визуал radius-
  shadow-bg-padding/лимит/заголовок/источник/View-all/hidden_on/quick-styles/медиа). CSS
  `#home-blocks .home-block-settings{display:none}` прячет настройки в списке; клик по имени/⚙ (`.blk-edit` →
  `openBlockPopup`) переносит строку в фокус-панель (вне `#home-blocks` → правило не действует, настройки видны).
  Save сохраняет (инпуты остаются в `#home-form` и в списке через display:none, и в попапе). Заголовок попапа
  теперь из `.blk-edit` (label из шапки убран). Браузер (baeckerei): список = только шапки (width БОЛЬШЕ НЕ в
  списке), клик→панель с настройками, save round-trip (products width=contained persisted), JS-ошибок нет.
  Без миграций. Owner-приоритет «убрать настройки ширины из Section в блоки» закрыт. Часть этапа «архетипы как
  сущности» (`docs/archetype-entities-plan.md`).
- **2026-06-29 — H1.5: пер-секционный шрифт (оверрайд глобального).** Секция несёт `font` (ключ FONTS:
  system/serif/rounded или "" = наследовать) — нормализуется в `_normalize_section`/`_clean_cblock` (валид по
  FONTS). UI: селект «Font» в панели настроек секции (рядом с Width, опции из `font_options` + «Standard»).
  `collect()`/`site_preview_draft` прокидывают в live-preview. Рендер: тег `section_font_vars(b.font)` (siteui)
  выдаёт `--font-body/--font-head` на обёртку секции в `storefront/home.html` (каскадит на тексты секции даже
  через display:contents). **Баг и фикс:** стеки FONTS содержат двойные кавычки (`"Segoe UI"`), которые ломали
  inline-`style="…"` HTML-атрибут (преждевременное закрытие) → браузер игнорил; в теге заменили `"`→`'` (в CSS
  эквивалентны). Браузер (baeckerei): products→serif = заголовок `Georgia,…serif`, и в сохранённом рендере, и в
  live-preview; JS-ошибок нет. Тесты (нормализация +C-блок, тег) в `test_layout.py`. Без миграций.
- **2026-06-29 — H1.2 (срез 1): инлайн-правка ТОВАРА на детальной странице.** «Редактирование не только главной»:
  на `storefront/product_detail.html` имя (`<h1>`) и описание получили `data-edit-model="product"`/`data-edit-pk`/
  `data-edit-field` (name/description) — те же маркеры, что на карточке товара. После H1.1 (переход по ссылкам в
  превью работает) редактор открывает детальную в iframe, его `frame.load`-JS делает эти элементы contenteditable
  (режим «Edit on site»), blur → POST `catalog:product-inline-edit` (вайтлист уже включал name/description) →
  `Product.<field>['de']`. На публичной витрине маркеры инертны (редакторный JS не грузится). Браузер (baeckerei):
  переход на `/sortiment/<pk>/` в превью, имя contenteditable, правка → в БД `name.de` обновлён, JS-ошибок нет.
  Тест `test_product_detail_inline_edit_markers`. Без миграций. Осталось H1.2: страница категории (часть уже есть
  через data-cat-edit), текстовые страницы, контент-настройки секций. Часть этапа «архетипы как сущности».
- **2026-06-29 — H1.2 (срез 2): инлайн-правка СОБЫТИЯ на детальной странице.** Параллельно товару: на
  `storefront/event_detail.html` заголовок (`<h1>`) и описание получили `data-edit-model="event"`/`data-edit-pk`/
  `data-edit-field` (title/description). Новый endpoint `event_inline_edit` (`apps/events/views.py`, login_required
  + require_POST, JSON {pk,field,value}, поля плоские title/description — фолбэк title_text/description_text, кламп
  title 200, пустой title → 400, bump кэша), URL `events:event-inline-edit` (`dashboard/events/inline-edit/`),
  `event` добавлен в `MODEL_EDIT_URLS` редактора. Описание теперь рендерится всегда (с маркером) — правится даже
  пустое. Браузер (pranasy): переход на `/veranstaltung/<pk>/` в превью, заголовок contenteditable, правка →
  в БД `Event.title` обновлён, JS-ошибок нет. Тесты `test_event_detail_inline_edit_markers` +
  `test_event_inline_edit_updates_and_validates`. Без миграций. Multi-page editing: товар + событие закрыты.
- **2026-06-29 — H1.2 (срез 3): инлайн-правка НОМЕРА (stays) на детальной.** Завершает паттерн детальных по
  3 основным архетипам (товар/событие/номер). На `storefront/stay_detail.html` название (`<h1>`) и описание —
  `data-edit-model="stay"`/`data-edit-pk`/`data-edit-field` (name/description). Endpoint `stay_inline_edit`
  (`apps/stays/views.py`, login_required+require_POST, плоские name/description, кламп name 120, пустое имя → 400,
  bump кэша), URL `stays:stay-inline-edit` (`dashboard/stays/inline-edit/`), `stay` в `MODEL_EDIT_URLS`. Описание
  рендерится всегда (с маркером). JS-путь идентичен product/event (generic frame.load-handler, проверен в браузере
  дважды — не менялся). Тесты: markers + endpoint (update/validate). Home_builder рендерит editor с новым URL (89).
  Без миграций. Multi-page editing деталей: товар + событие + номер закрыты.
- **2026-06-29 — H1.2 (срез 4): редактируемые заголовок/интро страницы КАТАЛОГА (сущность «список»).** «Настройка
  не только главной» для страницы категории: `catalog_title` + `catalog_intro` добавлены в `siteconfig.TEXT_FIELDS`
  (нормализуются генерически, принимаются существующим `site_inline_edit`). `products.html`: заголовок — кастомный
  `catalog_title` (фолбэк «Our products») c `data-edit`, суффикс категории вне маркера; интро `data-edit="catalog_intro"`
  (пустое скрыто на публичной, видно/правится под `?preview=1`). `product_list` прокидывает поля из конфига (черновик-
  aware). Тот же generic `[data-edit]`-механизм, что на главной (hero/about). Браузер (baeckerei): на `/sortiment/`
  в превью заголовок contenteditable, правка → `catalog_title` в БД, JS-ошибок нет. Тесты: `site_inline_edit`
  принимает catalog_title/intro + рендер маркеров/override. Без миграций. (Пер-категорийные описания — отдельный
  больший срез: поле на Category + миграция.) Multi-page editing: главная/товар/событие/номер/каталог.
- **2026-06-29 — H1.2 (срез 5): редактируемый тэглайн ПОДВАЛА (ask «настройки подвала»).** `footer_text` добавлен
  в `siteconfig.TEXT_FIELDS`; контекст-процессор (`apps/core/context.py`, draft-aware) отдаёт `storefront_footer_text`;
  `_base.html` рендерит тэглайн в подвале с `data-edit="footer_text"` (пустой скрыт на публичной, виден/правится под
  `?preview=1`) — на ВСЕХ страницах. В области «Подвал» редактора — подсказка про правку на сайте. Тот же generic
  `[data-edit]`/`site_inline_edit`-путь, что у `catalog_title` (проверен в браузере этой сессии — идентичен). Тесты:
  `site_inline_edit` принимает footer_text + рендер маркера/значения в подвале. Без миграций.
- **2026-06-30 — H1.1 FIX: кабинет вне `/dashboard/` остаётся `X-Frame-Options: DENY` (clickjacking).**
  Adversarial-review (workflow на диффе 9 инкрементов) нашёл: `StorefrontFrameOptionsMiddleware` перебивал DENY→
  SAMEORIGIN для ВСЕХ путей вне (`/dashboard/`,`/accounts/`,`/admin/`), но часть кабинета владельца смонтирована на
  корне субдомена (`config/urls_tenant.py`): `/catalog/`,`/imports/`,`/promotions/` (выдача/погашение ваучеров),
  `/crm/` (данные клиентов),`/willkommen/`. Все `@login_required`, ни одна не в `preview_pages` → их защита незаметно
  слабла. Фикс: расширил `_BLOCK_PREFIXES` этими корнями. Клиентский ЛК `/konto/` оставлен SAMEORIGIN (витрина, ссылка
  «Mein Konto» в шапке кликается в превью). Тесты: cabinet-roots не трогаются; уже выставленный DENY на них выживает;
  `/konto/` остаётся SAMEORIGIN. Без миграций. `a4df91e`.
- **2026-06-30 — H0/H1: страницы-ДЕТАЛИ архетипов в переключателе превью редактора.** Раньше `preview_pages` показывал
  главную + лендинги + ОДНУ деталь события (ad-hoc); деталь товара/номера была недостижима из редактора (хотя инлайн-
  эндпоинты H1.2 есть). Формализовал «3-ю сущность» в реестре: `archetypes.DETAIL_ENTITIES` (catalog→товар, stays→
  номер, events→событие) + `example_detail_pages(tenant)` — по активным архетипам отдаёт пункт «деталь» с URL реального
  примера (фильтр как в публичной вьюхе; модели lazy через `apps.get_model` — без цикла core↔apps). `home_builder_view`
  строит `preview_pages` из реестра (заменил ad-hoc event-блок; поведение события сохранено). Select и его JS-обработчик
  не менялись (generic по value → навигация к деталям без правок шаблона). Тесты: товар/номер/событие резолвятся,
  draft-событие исключено (гейт `status=published`), выключенный архетип не даёт детали, интеграция (89 home_builder
  зелёные). Без миграций. `1fde9bf`.
- **2026-06-30 — H1: описание секции главной (контент-настройка секции, Q4).** Каждая секция-грид главной
  (products/categories/events/promotions/services/stay_rooms) получила опциональное ОПИСАНИЕ под заголовком (вводный
  текст над гридом). Тот же generic-механизм, что у заголовка секции/`catalog_intro`/`footer_text`: контент в
  `site_config["section_intros"][key]`, маркер `data-edit="section_intros.<key>"` на витрине, инлайн-правка через
  `site_inline_edit` (БЕЗ правок редактор-JS — реюз contenteditable-обработчика). siteconfig: `SECTION_INTRO_KEYS`
  (= ключи заголовков) + `section_intro()` + блок нормализации (известные ключи, обрезка 300, пустое → ключ убирается);
  тег `{% section_intro %}`; ветка `section_intros.<key>` в site_inline_edit + carry в site_preview_draft; 6 партиалов
  секций (рендер только при непустом описании ИЛИ `?preview=1`). Реюз существующих CSS-классов — build:css не нужен.
  Тесты: save/reject-unknown/empty-dropped/render-marker; 915 (core+catalog+events+stays+promotions) зелёные. `d267f3f`.
- **2026-06-30 — H1: inline-добавление блоков (Templates) реально появляется в live-preview (фидбэк «кнопки
  неактивны»).** Кнопки «+ Text/Image/…» работали (блок сохранялся), но добавленный блок НЕ появлялся на канве →
  выглядел как «ничего не произошло». Браузерная диагностика (стенд baeckerei) вскрыла цепочку из 3 причин:
  **(1)** `site_preview_draft` принимал ТОЛЬКО фикс-секции (`key in SECTIONS`) и дедупил по ключу → ВСЕ C-блоки
  (key=text/image/…) выпадали из черновика live-preview (гл. причина) — добавил ветку `REPEATABLE_BLOCKS` (берём
  C-блок по id, не дедуп по ключу). **(2)** `collect()` не сериализовал C-блоки (строка несёт `order_cb_<id>`, ключ
  "cb_<id>" уходил как фикс-секция без типа/данных) — добавил ветку cb_ → `{key:тип,id,enabled,data}`, `delete_cb_`
  отбрасывает. **(3)** Пустой C-блок рендерился как НИЧЕГО → даже попав в превью был невидим — общий партиал
  `_block_placeholder.html` (пунктирный кликабельный плейсхолдер под `?preview=1`; на публичной пусто) в
  text/image/image_text/button; `is_preview` вынесен в контекст-процессор (был только в product_list) → доступен на
  главной и всех витринных страницах. Проверено в браузере: «+ Text» → блок на канве с плейсхолдером (секций 4→5),
  правка title/body → контент вживую, public чисто. Тесты: draft принимает C-блок + не дедупит по типу; плейсхолдер
  только в превью; непустой рендерит контент. 919 (core+catalog+events+stays+promotions). Реюз CSS-классов. `d53a6d0`.
- **2026-06-30 — H1: простые/правовые страницы в переключателе превью редактора.** Закрывает «настройка ... простых
  страниц»: универсальные инфо/правовые страницы (Über uns/Impressum/Datenschutz/Widerruf) добавлены в `preview_pages`
  редактора главной — владелец открывает их вид прямо в редакторе («О нас» правит about-тексты инлайн). Резолв reverse
  + guard NoReverseMatch; select/JS не менялись. Тест: редактор рендерит 4 URL. Без миграций/шаблонов. `9e7cb5e`.
- **2026-06-30 — H2-1/H2-2: агрегация primary-блоков на главной мультиархетипа.** H2-1:
  `archetypes.aggregate_primary_sections(tenant)` — «главный» блок каждого активного архетипа в порядке реестра
  `_PRIORITY` (`[{key,module,order}]`, без запросов к БД). H2-2: дефолт главной (`storefront_home`) обобщён с одной
  primary на ВСЕ — при отсутствии `sections` в сыром конфиге включаем блок каждого активного архетипа (магазин+
  ретриты+услуги → products+events+services …); гард сохранён (заданные `sections` не трогаем); паритет M20U-2
  (products/promotions default-on → enable идемпотентен). Тесты: порядок/одиночный/полный/пустой + интеграция
  storefront_home. 927 зелёных. Без миграций/шаблонов. План — `docs/h2-multiarchetype-plan.md`. `e515d3b`/`10c23f1`.
- **2026-06-30 — H2-6: слайдер обложки архетипа (лендинг = описание+слайдер+товары).** Обложка `_archetype_cover.html`
  уже рендерилась над любым лендингом (`_base.html`) с intro (описание) + hero; галерея выводилась статичным гридом.
  Заменил на свайп-слайдер (CSS scroll-snap `snap-x/snap-mandatory`, без JS-состояния): крупные фото, мобайл ~1 с
  подглядыванием, десктоп — ряд. Источник — существующий обложечный `gallery` (новый schema не нужен → H2-4/H2-5
  отменены). Теперь лендинг каждого архетипа = «описание + слайдер + товары» (D-MENU). `build:css` (детерминирован,
  +snap/basis-классы). **Браузерно проверено** (pranasy /veranstaltung/: hero+интро+слайдер из 3 фото, snap работает).
  Тесты: слайдер из gallery/маркер; без gallery — нет слайдера; пустая обложка — ничего. Без миграций. `91cdb59`.
- **2026-06-30 — H4/AB3: визуальные карточки архетипа на шаге 1 мастера (визуализация при регистрации).** Фидбэк
  «при регистрации визуализировать архетипы»: шаг 1 онбординга был сухим радио-списком типов. Сделал карточную сетку —
  эмодзи-иконка + подпись + «что это даёт» на языке задач. `onboarding.BUSINESS_TYPE_META` + `business_type_cards()`;
  `setup_view` отдаёт карточки; `setup.html` шаг 1 = `grid sm:grid-cols-2` карточек (реюз CSS, build:css без изменений).
  Сервер-рендер (без JS). **Браузерно проверено** (10 карточек с иконками/описаниями, шаг 1/7). Тесты. Без миграций. `df4bba8`.
- **2026-06-30 — Категории с описанием (i18n-описание категории на странице каталога).** Из видения «категории с
  доп. описанием»: `Category.description` (JSONField i18n, как у Product) — **миграция `catalog/0011`, владелец
  деплоит после мержа**. CategoryForm: `description_de/_en` (Textarea) ↔ `category.description`. `product_list` отдаёт
  `category_description` = выбранная `category.get_i18n("description")`; `products.html` рендерит под интро каталога
  (реюз классов). Сервер-рендер. Тесты: рендер при выборе категории/скрыт без; форма сохраняет i18n. 147 catalog. `f5cf742`.
- **2026-06-30 — Фикс редактора на витрине: инлайн-правка АКЦИЙ (название+цена) + ЦЕНА ТОВАРА на детальной.**
  Фидбэк «не работает редактор акций (названий/цен) и цены товара на детальной». Браузерная диагностика (baeckerei):
  **(1)** инлайн-правки акций НЕ существовало (нет маркеров на промо-карточках) → построил `promotion_inline_edit`
  (title→i18n['de']; price_override→Decimal+bump кэша), URL, `promotion` в `MODEL_EDIT_URLS`; маркеры в `_promo_card.html`
  (h3 title) + `_price.html` (data-price-edit promotion/price_override). **(2)** главная цена на `product_detail.html`
  не имела `data-price-edit` (он был лишь на карточках/похожих → клик попадал в чужой товар) → добавил маркер на
  главную цену. **(3)** обработчик `data-price-edit` обобщён (модель/поле из атрибутов; дефолт product/base_price).
  **Браузерно проверено end-to-end** (название акции/цена акции/цена товара → БД; контент товара уже работал). Тесты:
  эндпоинт (title/price/empty/unknown/bad). Реюз CSS, без миграций. `eb7bf24`.
- **2026-06-30 — Каталог: фасет-фильтры (диапазон цены, бейдж, «только в наличии»).**
  Оценка фильтров по архетипам (запрос «размери какие ещё фильтры нужны и добавь»): события/ретриты уже богаты
  (категория/уровень/язык/город/длительность/месяц/ведущий), отель — поиск по датам/гостям + сорт по цене, услуги/
  запись — обычно мало услуг (фильтр = шум, пропущено). Реальный пробел — **каталог** (самый частый архетип): был
  только категория+диета+сортировка. Добавлены три универсальных для ритейла фасета, все нативные поля БД →
  композируются с keyset-пагинацией: **(1)** диапазон цены `preis_von/preis_bis` (base_price), поле видно только при
  разбросе цен; **(2)** фасет-бейдж (Neu/Beliebt/Angebot/Tagesgericht/Empfehlung) — селект только присутствующих;
  **(3)** тумблер «Nur verfügbare» — наличие с учётом вариантов (Exists-подзапрос, зеркало `Product.in_stock`), виден
  только если что-то распродано. Все гейтятся существующим `catalog_show_filters` + наличием данных (само-скрытие).
  Carry-over фасетов между формой сортировки/диет-чипами/«Show more» (выбор не теряется при пагинации/сорте); комбо-
  тизер подавлён при активном фасете. Сервер-рендер (новый JS не добавлялся). 12 тестов (цена/бейдж/наличие+варианты/
  гейт-тумблера/перенос в сорт), 329 catalog+promotions зелёные. Реюз CSS (rebuild), без миграций. `7a766d0`.
- **2026-06-30 — A1/A2: рейтинг ★ на карточке каталога + док внешних интеграций.**
  Карточка товара в каталоге показывает ★ среднее + число отзывов под названием (сигнал
  доверия ритейла, бэклог F-A1/A2); видна только при опубликованных отзывах. Рейтинг —
  bulk-агрегатом ПОСЛЕ keyset-пагинации (1 запрос ProductReview по pk страницы,
  review_avg/review_count на инстансах) → нет N+1 и нет GROUP BY на keyset-запросе.
  Локальный формат среднего (DACH → «4,5»). Без миграции. Тесты: показ/скрытие. `db5f99a`.
  Создан **`docs/external-integrations-backlog.md`** — собраны все пункты бэклога с
  внешними провайдерами (Stripe live/Connect, Resend, SMS, OTA-API/метапоиск, Shopify/Woo
  импорт, Ads, Push/Wallet) с пометкой «что подключить + блокер владельца»: делаем
  «внутреннее» сначала, эти доделываем на этапе внедрения. Ссылки в CLAUDE.md §6.
- **2026-06-30 — A8: полный LocalBusiness JSON-LD (Map Pack/AI).** `localbusiness_ld`
  (apps/core/seo.py) расширен тремя сигналами для Google Map Pack/AI-выдачи, все из
  существующих полей тенанта: **openingHoursSpecification** (из `opening_hours_structured`
  через `openinghours.normalize`, schema.org dayOfWeek Mo–So), **logo** (+ фолбэк `image`,
  если фото не передано) из `logo_url`, **sameAs** из `website_url` (связь сущностей).
  Без новых параметров шаблона (тег `localbusiness_jsonld` уже зовёт функцию), без
  миграции. Ленивый импорт openinghours (core не тянет tenants на уровне модуля). 5 тестов
  (часы/лого+sameAs/приоритет переданного image/без часов). 88 SEO+jobs+stays зелёные.
- **2026-06-30 — A8: богатая карточка бизнеса — live-статус «Jetzt geöffnet» на городской
  странице.** Карточка листинга в выдаче агрегатора (`_cards.html`) получила live-бейдж
  открытости: открыт → зелёный «Geöffnet · until HH:MM», закрыт → серый «Geschlossen · opens
  Mo HH:MM», без заданных часов — без бейджа. Хелпер `_attach_open_status(cards)` (1 запрос
  Tenant по схемам пула, reuse `openinghours.open_status`) навешивает has_hours/open_now/
  open_until/opens_next; вызван в `city_listing` после attach_ratings. Без миграции. Тест
  `test_city_listing_card_shows_open_status_badge`; 160 aggregator зелёные. `_cards.html`
  шарится (портал/поиск/индекс) — бейдж рендерится только где атрибуты навешаны (city).
- **2026-06-30 — A7: PLZ/Einzugsgebiet (зона обслуживания) — полноценно.** Handwerker/
  Werkstatt/мобильные услуги задают зону обслуживания и показывают её клиенту.
  **Tenant** (миграция tenants/0019): `service_area_plz` (PLZ через запятую) +
  `service_area_note` (текст), property `service_area_plz_list` (парс → 5-значные DE-PLZ,
  uniq), `has_service_area`, `serves_plz()` (пустой список = обслуживает везде).
  **Job** (миграция jobs/0009): `site_plz` (PLZ объекта). Кабинет: оба поля в
  `BusinessSettingsForm` с help-текстами. Витрина Anfrage: баннер «📍 Einzugsgebiet …»
  (note + список PLZ) + поле PLZ — показываем только если зона задана; на сабмит мягкий
  чек (заявку принимаем всегда, но при PLZ вне зоны — info-сообщение, не блок). Демо:
  handwerker-кит сеет Kölner PLZ + текст. Тесты: парс/serves_plz/баннер/скрытие/чек
  (23 jobs + 14 tenants). Без нового JS.
- **2026-06-30 — A7: Rückruf-Anfrage (обратный звонок).** Низкопороговая альтернатива
  полной заявке: на странице Anfrage — вторая компактная форма «Prefer a callback?»
  (имя + телефон + опц. удобное время) → POST `/rueckruf/`. Вьюха `rueckruf` (honeypot +
  rate-limit как Anfrage) создаёт лёгкий лид через тот же jobs-пайплайн (create_job
  title=«Rückrufbitte», best_time → в описание) + enqueue_job_email("new"). Гейт модулем
  jobs. Без миграции/JS. Тесты: лид/требование имя+телефон/best_time/гейт/форма (28 jobs).
- **2026-06-30 — A9: Repair-Status трекинг (публичная страница статуса + письмо «fertig»).**
  Клиент видит прогресс заявки: публичная страница `/auftrag/<public_token>/`
  (`auftrag_status`) — read-only тайм-лайн стадий (Anfrage → Angebot → Beauftragt →
  Erledigt → Abgerechnet) с подсветкой текущей; declined/cancelled → терминальная пометка.
  Переиспользует существующий `Job.public_token` (без миграции). При переходе FSM в `done`
  клиенту уходит письмо `job_done` (Auftrag fertig + ссылка на страницу статуса) — расширен
  `enqueue_job_email` (quoted/done → клиенту) + хук в `JobSM.on_transition`. Шаблоны
  `emails/job_done*.txt`. Тесты: тайм-лайн/текущая стадия/терминал/гейт/письмо (63 jobs).
- **2026-06-30 — A9: TÜV/Service-Reminder (ретеншн Werkstatt).** Бизнес ставит на заявке
  дату следующего TÜV/Service; beat за `SERVICE_REMINDER_LEAD_DAYS` (21) дней до неё шлёт
  клиенту письмо-напоминание. **Job** (миграция jobs/0010): `service_due_date` +
  `service_reminder_sent_at` (дедуп). Кабинет: поле «Next TÜV / service» в форме сметы
  (`_save_lines`); смена даты сбрасывает sent_at → новое напоминание. Beat-задача
  `apps/jobs/tasks.py` (`send_due_service_reminders` чистая логика + `send_service_reminders`
  по всем схемам, зеркало booking/stays); расписание в CELERY_BEAT_SCHEDULE (раз в сутки).
  Письмо `job_service_reminder` (расширен `enqueue_job_email`, дедуп включает дату). Тесты:
  окно/идемпотентность/прошедшее/без e-mail/перезарядка + кабинет (70 jobs). Без нового JS.
- **2026-06-30 — A5: extras с фото.** Универсальная доп-услуга (`core.Extra`) получила фото:
  поле `image` (FileRef-конверт, миграция core/0003) + property `image_url`. Кабинет
  `/dashboard/extras/`: загрузка фото при создании + per-row «📷 Change/Photo» (action
  `set_image`, reuse `catalog.images.validate_image`/`save_product_image`, folder=extras);
  миниатюра в списке. Витрина: миниатюра рядом с чекбоксом в общем партиале `_extras.html`
  (booking/events) и в inline-extras `stay_detail.html` (A5 отель). Пусто = без фото (как
  раньше, не зашумляет). Тесты: property/добавление с фото/set_image/без фото/рендер партиала
  (10 core). Без нового JS (file-input авто-сабмит inline).
- **2026-06-30 — A3: визуальный календарь слотов (Termin).** На страницах записи
  (`/termin/<resource>/` и услуга `/t/<service>/`) над дневной навигацией — месяц-сетка
  наличия: день со свободным слотом подсвечен (emerald) и кликабелен (`?tag=`), занятые/
  прошлые/без правила — серые; нав месяца ‹ › через `?cal=YYYY-MM`. Без JS (только ссылки),
  по образцу календаря отеля. Бэк: хелперы `_slot_month`/`_cal_first` в booking/public_views;
  `check_has_slots(day)` зовётся только в окне [today, MAX_DAYS_AHEAD] (прошлое/за горизонтом
  не считаем). Для услуги `cal_qs` несёт выбранного мастера в ссылки дня. Партиал
  `_booking_calendar.html`. Тесты: хелпер (окно/пометки) + рендер кликабельного дня (73 booking).
- **2026-06-30 — A4: iframe-виджет записи (Termin) — embed-режим.** Ресторан/Friseur
  встраивает форму записи на свой сайт через `<iframe>` (бэклог F-A4; email-reminder уже
  есть — beat `send_booking_reminders`). Зеркало stays G10: хелперы `_is_embed`/`_render_embed`/
  `_embed_redirect` в booking/public_views; при `?embed=1` витрина (index/service_index/
  booking_slots/service_slots/confirmation) рендерится минимальным `_embed_base.html` +
  `xframe_options_exempt`. `embed` пробрасывается ВО ВСЕ ссылки (back/день-нав/слоты/пикер
  мастера/календарь A3), скрытое поле формы и редиректы (успех/ошибка/honeypot/Stripe ok+cancel),
  чтобы флоу не вышел из iframe. Кабинет `/dashboard/booking/`: сниппет `<iframe>` (details).
  Тесты: xframe-exempt + embed во всех ссылках/редиректах/успехе (77 booking). Без миграции/JS.
- **2026-06-30 — A7: авто-запрос отзыва в письме «Auftrag fertig».** При переходе заявки в
  `done` письмо клиенту (job_done) теперь содержит запрос отзыва со ссылкой на страницу
  бизнеса в портале агрегатора — по образцу post-stay/post-event (stays/events). Хелпер
  `_review_url(schema)` (jobs/notifications): best-effort активный портал, где бизнес
  присутствует (по business_type или городу) → `https://<host>/unternehmen/<slug>/`; нет
  портала/слага → '' (письмо без ссылки). Развилка a/b решена консистентностью с
  существующим механизмом (портал, без новой поверхности отзыва — переиспользует модерацию
  портала). Без миграции/JS. Тесты: URL портала/пусто-без-портала/рендер строки отзыва (73 jobs).
  **Внутренний бэклог F закрыт полностью.**
- **2026-07-01 — интеграция ветки планирования nifty-einstein в рабочую линию.** Смёржена
  `claude/nifty-einstein-ix6huq` (планы «единого слоя продаваемой сущности»: market-gap A1–A9,
  `unified-sellable-entity` master-track/U-A…U-E/decisions/priority-review, план **Волны L**
  мультиязычности) + код **UA1-1** (страница-деталь услуги `service_detail.html` на каркасе
  detail.html) + fix теста booking slots (`DAY = today+7`). FF был невозможен (main ушёл вперёд
  на 20 коммитов A-серии) → merge-коммит. Конфликт `service_index.html` разрешён: в embed-режиме
  (A4 iframe-виджет) карточка услуги ведёт прямо на слот-пикер (`?embed=1`, т.к. `service_detail`
  не поддерживает embed), в обычном режиме — на новую детальную. Досверка авто-мержа: вернул
  `date` в импорт `test_public.py` (fix теста убрал его, а A3-тест `_slot_month` его использует).
  Проверка: 413 booking+tenants зелёные.
- **2026-07-01 — Волна L / L1: рантайм-биндинг локалей (N-locale, без миграции).** Поля
  `Tenant.enabled_locales`/`default_locale` (были мертвы) теперь читаются в рантайме. Резолвер
  `Tenant.active_locales` (property) — единый источник «какие языки показывает тенант»:
  пересечение `enabled_locales` с реестром `settings.LANGUAGES`, фолбэк `[default_locale]` при
  пустом (легаси — без регресса). Генерик по N локалям: добавить язык = добавить в
  `settings.LANGUAGES` (+`.po/.mo`), без правки кода. `set_language` (promotions/public_views)
  валидирует против `active_locales`, а не всего реестра → нельзя переключиться на невключённый
  язык (неизвестная/выключенная → `default_locale`). Оверлей витрины (`siteconfig`):
  `OVERLAY_LOCALES=("en",)` → функция `overlay_locales()` (реестр минус базовая) — `_clean_i18n`
  хранит оверлеи любой реестр-локали, не только EN; `normalize` остаётся tenant-free (десятки
  вызовов), per-tenant-гейтинг — в `active_locales`. Переключатель шапки (`_base.html`) — цикл по
  контексту `storefront_locales` (N кнопок, скрыт при 1 локали) вместо 2 захардкоженных DE/EN.
  Тесты: `apps/tenants/tests/test_locale.py` (active_locales/фолбэк/дедуп/3-я локаль,
  set_language-валидация, оверлей на FR, контекст `storefront_locales`). Без миграции/JS.
- **2026-07-01 — Волна L / L2: кабинет «Sprachen» (без миграции).** Владелец включает
  подмножество языков реестра `settings.LANGUAGES` (чекбоксы) и выбирает дефолт (радио) →
  пишется `Tenant.enabled_locales`/`default_locale`; витрина/переключатель сразу отражают через
  `active_locales` (L1). Вью `apps/core/views.py::languages_view` (`@login_required`, ручной POST,
  `update_fields`), маршрут `/dashboard/settings/languages/` (`name="languages"`), пункт меню
  `NavItem("languages")` в группе «Einstellungen», шаблон `templates/tenant/languages.html` (по
  образцу `settings.html`). Инварианты: ≥1 язык; дефолт ∈ включённые (авто-коррекция на первый);
  не-реестр отфильтрован; порядок — как в реестре. UI генерик по N локалям (3-я локаль появится
  без правки кода). Решения владельца зафиксированы: S-1(a) кабинет тоже мультиязычный (L4),
  S-2(b) правовое — отдельная модель `LegalDoc` (L5), S-3 реестр DE+EN (языки по запросу). Тесты:
  `apps/core/tests/test_languages_cabinet.py` (GET/сохранение/инвариант дефолта/пустой/фильтр/порядок).
- **2026-07-01 — Волна L / L3-модель: i18n на `Service` и `StayUnit` (миграция).** i18n-фундамент
  для адаптера SellableEntity (U-A / UA1-3): `booking.Service` и `stays.StayUnit` получили поля
  `name_i18n`/`description_i18n` (JSONField) + `I18nMixin`. **Overlay-семантика** (осознанное
  уточнение плана vs «бэкфилл {de:…}»): базовая локаль остаётся в ПЛОСКИХ `name`/`description`
  (source of truth, БЕЗ дрейфа и без риска RunPython по схемам тенантов), а `*_i18n` хранит только
  переводы НЕОСНОВНЫХ локалей — как оверлей site_config. Аксессоры на `I18nMixin` (переиспользуемо):
  `get_overlay(base, overlay, locale)` (база из плоского поля для `LANGUAGE_CODE`, иначе оверлей→фолбэк
  на базу) и `i18n_full(base, overlay)` (полный словарь база+оверлей — единый вид для адаптера всех 5
  kind). Модели отдают `name_localized()`/`description_localized()` + свойства `*_i18n_full`. Миграции
  `booking/0011`, `stays/0020` — чистый AddField (default=dict), без RunPython/потерь. Витрину/формы
  НЕ трогали (рендер и per-locale-редактирование — L3c/UA1-3, чтобы избежать рассинхрона базы). Тесты:
  `apps/booking/tests/test_service_i18n.py` + `apps/stays/tests/test_stayunit_i18n.py` (overlay/фолбэк/
  база-всегда-плоская/full-словарь/safety). Гейт: 331 core+i18n на свежей БД зелёные.
- **2026-07-01 — hotfix(prod): CSRF 403 на логине субдомена (`<slug>.siteadaptor.de/accounts/login/`).**
  `CSRF_TRUSTED_ORIGINS` теперь ЖЁСТКО содержит `https://siteadaptor.de` + `https://*.siteadaptor.de`
  всегда (env лишь ДОБАВЛЯЕТ, не заменяет) — узкий env-override больше не роняет CSRF на субдоменах.
  `CsrfViewMiddleware` кэширует список на init (в отличие от ALLOWED_HOSTS, динамически не дополнить),
  поэтому базовые origin'ы фиксируем в коде. Диагностика: точную причину CSRF Django пишет в лог
  `django.security.csrf` (WARNING, виден в stdout контейнера) — «Origin checking failed…» / «CSRF
  cookie not set» и т.п. Только `config/settings/production.py` (CI гоняет test.py — не затрагивается).
- **2026-07-01 — UA1-2 (U-A): регистрация детали услуги в превью редактора (без миграции).** Добавлен
  кортеж `("booking","booking.Service","storefront-service-detail",…,("-created_at",))` в
  `archetypes.DETAIL_ENTITIES` → `example_detail_pages` (генерик-цикл с гардами `is_module_active`+
  `NoReverseMatch`) отдаёт деталь услуги (`group="booking_detail"`) в переключателе превью
  `#home-prev-page` при активном booking + ≥1 активной услуге. `SCOPE_PAGE_KEY` НЕ трогали — группа
  `booking_detail` падает в «правь на канве» (как `stays_detail`; пер-страничный инспектор — UA4-1).
  Тесты: `test_preview_pages.py` (услуга в превью + group + исключение неактивной). Гейт: 321 core.
- **2026-07-01 — diag(prod): самодиагностирующая 403-страница CSRF (`CSRF_FAILURE_VIEW`).** Штатный
  403 CSRF непрозрачен без DEBUG → добавлена прод-безопасная страница `apps/core/csrf.py::csrf_failure`
  (подключена `settings.CSRF_FAILURE_VIEW`): показывает ТОЧНУЮ причину Django (`reason`) + сигналы
  запроса, по которым решает `CsrfViewMiddleware` — пришла ли кука `csrftoken`, Origin/Referer,
  `is_secure` за прокси (`X-Forwarded-Proto`), host. За один заход отличает «Origin не в trusted
  origins» от «кука не пришла»/«токен не совпал» без DEBUG и доступа к логам; причина также в лог
  `django.security.csrf`. Для расследования оставшегося 403 на логине субдомена. reason экранируется
  (XSS-safe). Тесты: `apps/core/tests/test_csrf_failure.py`. Гейт: 324 core.
- **2026-07-01 — UA1-3 (U-A): контракт `SellableEntity` + 5 адаптеров (без миграции).** Новый
  `apps/core/sellable.py`: `sellable_for(kind, obj, locale=None)` → `SellableEntity` (dataclass:
  kind/pk/name/description/price_display/image_url/gallery/purchase_mode/purchase_label/detail_url +
  швы `buybox_context`/`attributes`/`info_sections` под U-A3/U-A4). Адаптеры 5 kind (product/service/
  stay/event/combo) ДЕЛЕГИРУЮТ существующим методам: i18n — `get_i18n`/`name_localized` (L3 снял
  асимметрию — service/stay читаются единообразно), цена — `base_price`/`price_from`/`price_eur`/
  `from_price_eur`/грундпрайс, фото — `primary_image`/`image_url`/`images`. kind→mode/label — из
  `archetypes.purchase_mode`/`purchase_label` (без дублей). `combo` — реальный (catalog.Combo, cart,
  без фото). `jobs` ЯВНО не sellable (индивид. смета → U-D). Импорт-изоляция: без top-level импортов
  catalog/stays/events/booking (методы инстанса + ленивый archetypes). Разведка 5 kind —
  адверсариальным воркфлоу (5 Explore-агентов, всё верифицировано против кода). Шаблоны НЕ трогали —
  чистый Python+юниты (шов под UA2-1). Тесты: `apps/core/tests/test_sellable.py` (i18n-оверлей/цена
  free/ab/from/валюта/gallery/mode-label/detail_url/unknown-kind). Гейт: 333 core.
- **2026-07-01 — UA2-1 (U-A): контракт `SellableEntity` в контексте всех 4 деталей (без миграции).**
  Разведка показала: **структурная унификация детали УЖЕ сделана M20U** — `product_detail.html`
  (и stay/event) уже `extends storefront/detail.html` (6 блоков), общий buy-bar `_detail_buybar.html`
  + тег `{% purchase_label %}` уже разделяют хром. Поэтому «вписать standalone product_detail» —
  неактуально (сделано). Остаток UA2-1: сделать контракт живым в запросе — `sellable_for(kind,obj)`
  инъектирован в контекст `product_detail`/`service_detail`/`unterkunft_unit`/`veranstaltung_detail`
  (promotions/booking/stays/events public_views) как `sellable` — шов, который потребляют UA3-1
  (buy-box по `purchase_mode`), UA4 (секции) и UA4-4b (JSON-LD). Функция-локальные импорты (без
  цикла). Гейт: 154 (booking/stays/events/promotions/catalog detail-render) — инъекция не ломает
  рендер; корректность контракта — `test_sellable.py`. Потребление `sellable` в шаблоне — UA3-1.
- **2026-07-01 — UA3-1 слайс 1 (U-A, реш.2): override primary-CTA на детали услуги (без миграции).**
  Резолвер `archetypes.primary_service_action(service, tenant)` → `booking` (бронь слота) | `request`
  (Anfrage/смета, A7/A9). Приоритет: поле `Service.primary_action` (per-service, добавит UA4-3) →
  `tenant.site_config['primary_service_cta']` (per-tenant, без миграции) → дефолт `booking`. `request`
  валиден только при активном `jobs` (иначе нет `/anfrage/` → `booking`). `service_detail` view отдаёт
  `primary_action`; `service_detail.html` меняет местами primary/secondary кнопки (accent) и подпись
  мобильного buybar (`module` jobs/booking) по резолверу. Без риска для checkout — только порядок двух
  ссылок. Тесты: `apps/core/tests/test_primary_action.py` (дефолт/config/jobs-фолбэк/поле>config/
  инвалид/не-dict) + `test_public.py` (порядок кнопок default vs override). Гейт: resolver+booking public.
  Дальше UA3-1 слайс 2: extraction `_buybox.html` (диспатч по `purchase_mode`) с паритет-тестами.
- **2026-07-01 — UA4-3 (U-A): богатая карточка услуги — attributes + FAQ + primary_action (миграция).**
  Закрывает **E-1/D1/D2** (деталь услуги A3/A7/A9). `booking.Service` += `attributes` (JSONField
  list[str] — свободные спецификации/фичи), `faq` (JSONField list[{q,a}]), `primary_action`
  (choices booking|request — per-service override реш.2, теперь реальное поле, читает резолвер UA3-1).
  Нормализаторы `normalize_service_attributes`/`normalize_service_faq` (garbage-safe: не-список→[],
  дропает пустое/мусор, обрезает длину, ≤12) + свойства `attributes_list`/`faq_list` (нормализация на
  чтении, по образцу `events.tier_list`). Рендер на `service_detail.html` (`detail_body`): секции
  атрибутов (список ✓) + FAQ (аккордеон `<details>`) с `data-sf-section`-хуками (под реестр UA4-1),
  скрыты при пустом. Демо: A7 handwerker — первая услуга «Vor-Ort-Beratung» с attributes+FAQ+
  primary_action='request' (спек услуги расширен опц. 6-м dict, обратно совместимо). Миграция
  `booking/0012` (AddField, default list/'') — без потерь. Тесты: `test_service_rich.py`
  (нормализаторы/свойства/поле→резолвер) + `test_public.py` (рендер секций / скрыты при пустом).
  Гейт: 42 на свежей БД. Дальше: UA4-4a (generic Review) / UA4-1 (реестр секций).
- **2026-07-01 — L3c-рендер (Волна L): активация i18n на витрине Service/StayUnit (без миграции).**
  Витрина теперь показывает ЛОКАЛИЗОВАННЫЕ имя/описание услуги и номера через L3-аксессоры
  `name_localized`/`description_localized` (оверлей неосновных локалей, фолбэк на базу): `service_detail`
  (title/h1/описание/alt) + `service_index` карточки; `stay_detail` (title/h1/описание) + `stay_index`
  карточки. i18n-фундамент L1–L3 стал ВИДИМЫМ: EN-посетитель видит EN-контент, где он задан. Без
  регресса (для базовой локали аксессор возвращает плоское поле = то, что редактирует инлайн-редактор
  `data-edit-field`). Per-locale ВВОД (формы/редактор) + засев переводов в демо — остаток L3c (позже).
  Тест: `test_public.py::test_service_detail_renders_localized_name_en` (EN-оверлей под `override('en')`,
  база под дефолтом). Гейт: 30 booking public + 154 stays (без регресса).
- **2026-07-01 — UA4-4a (U-A): generic-модель отзыва `reviews.Review` + data-migration из
  `catalog.ProductReview`.** Новое TENANT-приложение `apps.reviews` (в `base.py` TENANT_APPS →
  test.py как SHARED). Модель `Review(entity_kind∈{product,service,stay,event}, entity_id=UUID, rating,
  author_name, email, comment, verified, is_published)` — адресуется по (kind,id) вместо FK на конкретную
  модель (носитель протокола `SellableEntity` для отзывов/агрегатов/JSON-LD всех архетипов). Уник
  (kind,id,email), индекс (kind,id,is_published), `stars`-проперти. `services.py`:
  `published_for`/`summary`/`bulk_summary` (агрегаты одним запросом для списков) + `is_verified_buyer`
  (per-kind верификатор, **fail-closed**: неизвестный/непривязанный kind → False; product→`catalog.reviews.
  has_purchased`/OrderItem). Data-migration `reviews/0002` (логика в `apps.reviews.backfill.copy_product_
  reviews`, параметризована классами моделей → та же функция вызывается из миграции с историческими
  моделями И из теста с боевыми): переносит все `ProductReview` в `Review(entity_kind='product')`,
  сохраняя опубликованность/таймстемпы (created_at/updated_at), помечая `verified=True`, идемпотентно
  (пропуск уже перенесённых). `ProductReview` НЕ удалён (не деструктивно). Переключены на generic-модель:
  `catalog.reviews.published_for/summary` (тонкие product-обёртки), `product_detail` (список+summary),
  `product_review_submit` (запись в `Review`, верификация через адаптер), список каталога (bulk-агрегат
  рейтинга ★ на карточке через `bulk_summary`), демо-засев `_seed_product_reviews`. Миграции: `reviews/0001`
  (схема) + `reviews/0002` (data). Тесты: новый `apps/reviews/tests/test_reviews.py` (11: перенос без
  потерь/поля/verified/таймстемпы/идемпотентность, агрегаты, fail-closed) + обновлены
  `test_product_reviews`/`test_storefront`/`test_demo_kits` на generic-модель. Гейт (`--create-db`):
  99 passed (reviews + catalog product-reviews/storefront + demo_kits), `manage.py check` чист.
- **2026-07-01 — UA4-4b (U-A): верифицированные отзывы на Service/Stay/Event через generic-модель +
  per-entity JSON-LD.** Расширил generic-отзывы (UA4-4a) на услугу/номер/событие + богатый rich-snippet.
  **Верификация покупателя (per-kind, fail-closed):** `booking.reviews.has_booked` (неотменённая
  `Booking` услуги по e-mail), `stays.reviews.has_stayed` (`StayBooking` юнита), `events.reviews.has_ticket`
  (`Ticket` события) — учитывают fulfilled/attended (был клиентом), исключают cancelled/no_show; любая
  ошибка → False. Диспетчер `reviews.services._verifier_for` теперь связывает product/service/stay/event
  → верификатор (неизвестный kind → None → отзыв запрещён). **Единый приём формы** —
  `reviews.submit.handle_review_submit` (rate-limit по IP → парсинг/валидация → per-kind верификация →
  `update_or_create` в `Review`), общий для 3 сущностей. Детальные вьюхи (`service_detail`,
  `unterkunft_unit`, `veranstaltung_detail`) инжектят `reviews`/`review_summary`/`review_form_token`/
  `review_action`; +3 submit-вьюхи и маршрута (`{leistung|unterkunft|veranstaltung}/<pk>/bewerten/`).
  **Витрина:** новый партиал `templates/storefront/_entity_reviews.html` (сводка рейтинга + список +
  форма отзыва, зеркалит секцию товара; под UA4-1 сведутся) включён в service/stay/event detail.
  **JSON-LD (T6):** `core.seo.entity_ld` строит schema.org из КОНТРАКТА `SellableEntity`
  (@type Product/Service/Event/LodgingBusiness по kind) + `AggregateRating` из generic-summary; тег
  `entity_jsonld` + `{% entity_jsonld sellable review_summary %}` в `detail.html` → per-entity JSON-LD
  со звёздами на ВСЕХ детальных страницах разом (в т.ч. товар, у которого раньше per-entity JSON-LD не
  было). Без миграций. Тесты: `test_service_reviews`/`test_stay_reviews`/`test_event_reviews` (верификаторы
  +submit+рендер), `test_entity_jsonld` (@type per-kind + AggregateRating + тег), `test_reviews`
  (диспетчер 4 kind). Гейт (`--reuse-db`): 56 passed (reviews+3 kind+jsonld+product-reviews) + 168 passed
  регрессия (booking/stays/events public + seo + catalog storefront), ruff+`manage.py check` чисты.
  **Багфикс по адверсариальному ревью (тот же инкремент):** (1) HIGH — stored XSS: JSON-LD встраивается в
  `<script>` через `mark_safe`, а `json.dumps(ensure_ascii=False)` не экранирует `</script>` → имя/описание
  тенанта с `</script><script>…` вырывалось из блока. Фикс централизован в `core.seo._dumps`
  (`translate` `< > &` + U+2028/9 → `\uXXXX`, валидный JSON, декодируется обратно; по образцу Django
  `json_script`) → защищает И существующие `localbusiness_ld`/`offer_ld`. (2) LOW — `stay_review_submit`
  не вызывал `_require_stays_active` (в отличие от service/event submit) → добавлен гейт модуля.
  Тесты: XSS-breakout + Http404 при выключенном stays. 95 passed (entity_jsonld + все seo-сьюты + stay).
- **2026-07-01 — UA4-1 (U-A): единый реестр секций детали — Slice A/B/C.** **Slice A:** новый
  `apps/core/detail_sections.py` — единый источник дескрипторов секций детали (`DetailSection`:
  key+i18n-label+hideable/orderable) для product/event; подписи переехали из `views.py`
  (`_EVENT_SECTION_LABELS`/`_PRODUCT_SECTION_LABELS` удалены) → инспектор читает `section_labels(module)`.
  Zero behavior change. **Slice B:** обобщённый нормализатор в `siteconfig.py`
  (`normalize_detail_sections`/`detail_section_order`/`detail_section_hidden` по module, читают реестр);
  прежние `normalize_event_detail`/`event_detail_order`/`normalize_product_detail`/`product_detail_hidden`
  → тонкие обёртки; `EVENT/PRODUCT_DETAIL_SECTION_KEYS` выводятся из реестра (единый источник). Паритет
  байт-в-байт (параметрический тест). Без цикла импорта (`apps.core.__init__` пуст, `detail_sections`
  тянет только django). **Slice C (рабочий сквозной срез):** реестр расширен на `booking`
  (description/attributes/faq/team/reviews) и `stays` (description/amenities/reviews/similar), hide-only;
  config-ключи `service_detail`/`stay_detail`; `home_builder` рисует инспектор + сохраняет (presence-guard
  `sd_present`/`std_present`) + live-preview проносит черновик; `site_home.html` SCOPE_PAGE_KEY +2, две
  page-block, JS-payload; `service_detail`/`unterkunft_unit` инжектят `detail_hidden`, а
  `service_detail.html`/`stay_detail.html` обёртывают секции `{% if '<key>' not in detail_hidden %}` (у
  stay amenities — вложенные if: у Django нет скобок) → **тумблер билдера реально скрывает секцию на
  витрине end-to-end**. Гейты: Slice A/B — 217+318 passed; Slice C — 276 таргетных + 715 широких
  (`apps/core`+`apps/tenants`) + адверсариальный ревью чист (4 измерения). Хотфикс UA4-4b по пути:
  многострочный `{# #}` в `detail.html` → `{% comment %}` (CI `test_template_comments`). Миграции нет.
  Планы — `docs/unified-sellable-entity-ua4-1-plan-2026-07-01.md` (Slice A-D). Дальше UA4-2 (data-driven
  цикл рендера вместо per-template if/elif).
- **2026-07-01 — UA4-4b: демо-отзывы на услуги/номера/события.** Generic `_seed_entity_reviews(kit, refs)`
  засевает `reviews.Review` для service/stay/event по индексам в `refs[services|stay_units|events]` (как
  `_seed_product_reviews`); `DemoKit` +`service_reviews`/`stay_reviews`/`event_reviews`. Засеяно: friseur
  (услуги), hotel (номера), retreat (события) — по 3 опубликованных отзыва → секция отзывов UA4-4b на
  детали видна в демо. Python-only, без миграций. Гейт: 21 `test_demo_kits` + 6 таргетных passed.
- **2026-07-01 — UA4-2 (U-A): data-driven цикл рендера секций детали — service + stay (серия закрыта).**
  Тела `service_detail`/`stay_detail` переведены с per-template `if/elif` на цикл
  `{% for s in body_sections %}{% if s.visible %}{% include s.template %}{% endif %}{% endfor %}`; вьюхи
  собирают `body_sections` (порядок из `detail_sections.section_keys(module)`, видимость = контент+не
  скрыто); секции вынесены в партиалы `templates/storefront/sections/detail/_service_*`/`_stay_*.html`.
  У stay `similar` остаётся в `detail_wide` отдельным блоком (партиал `_stay_similar.html`+`show_similar`) —
  раскладка сохранена. **event** уже был loop-based (`event_detail_order`+`_event_thematic.html`) — UA4-2
  ему не требуется. **product остаётся per-block**: секции реестра распределены по `detail_aside`
  (description/info в sticky buy-box), `detail_body` (reviews), `detail_wide` (related) — перенос в
  body-цикл сломал бы колонку; уже управляются `product_detail_hidden`. Замки — характеристические
  паритет-тесты порядка секций (service/stay/product). Каждая миграция шаблона — под адверсариальным
  ревью (Workflow, confirmed:[]). Без миграций. Гейт: service 42+275, stay 182+164, product 13 passed;
  ruff+`manage.py check`+`test_template_comments` чисты. Побочно: перешёл на `git commit -F -` (heredoc)
  вместо `-m` с бэктиками (бэктики в двойных кавычках → command substitution). **Волна U-A (UA1–UA4)
  закрыта в `main`.**
- **2026-07-01 — аудит U-/L план↔факт + рынок A1–A9 + security → `docs/audit-2026-07-01.md`** (только
  анализ, код не менялся). Fan-out воркфлоу (finder против кода + адверсариальные скептики). Итоги:
  Волна L L1/L2/L3-модель/L3c ✅ (осознанные отклонения); U-A UA1/UA2/UA4 ✅, но **«U-A закрыта» неточна** —
  из UA3 сделан только override primary-CTA, `_buybox`-диспатч и UA3-2 не сделаны; U-B..U-E не начаты.
  Рынок (метод `(full+0.5·partial)/total`): A5 79.6%, A6 72.4%, A8 61.1%, A1/A2 57.7%, A3 57.4%, A4 54%,
  A9 ~47.8% (скептик-правка: repair-статус K6 + HU/AU-reminder K7 уже реализованы, финдер занизил до 41.3%),
  A7 43.8%. Security: критических нет; **2× HIGH XSS в карте агрегатора** (`templates/aggregator/_map.html`
  — `map_points_json` вне фикса `seo._dumps` + Leaflet `bindPopup` innerHTML), 2× medium (newsletter без
  rate-limit/honeypot; фолбэк Fernet-ключа секретов без гейта DEBUG), несколько low. **Пробелы вплетены в
  ТЗ (docs до кода):** master-track §7 (по очереди волн 0→4), ua-plan §7 (остаток U-A), L-plan §10, pointer'ы
  в ub/uc/ud-планах. Приоритет №1 — E-7 платёжный микс DACH (сквозной, вне волн).
- **2026-07-01 — багфикс(security): 2× HIGH XSS в карте агрегатора (`_map.html`).** (1) JSON точек
  карты шёл в `<script>` через `{{ map_points_json|safe }}` мимо экранирования (обе вьюхи-источника
  `aggregator/views.py::city_listing` и `portal_views.py` делали `json.dumps` без `_dumps`-escape) →
  `Promotion.title` тенанта с `</script>…` вырывался из блока. Фикс: канонический Django
  `{{ map_points|json_script:"agg-map-data" }}` (экранирует `< > &`, `|safe` убран); вьюхи отдают
  raw-list `map_points` вместо пред-сериализованной строки (локальные `import json` удалены). (2) Leaflet
  `bindPopup('<a href="'+p.url+'">'+p.title+'</a>')` вставлял tenant-поля как innerHTML → `<img onerror>`/
  `javascript:` исполнялись при открытии маркера. Фикс: попап через DOM (`document.createElement`,
  `a.textContent=title`, `href` только `https?://` или `/`, иначе `#`). Тесты:
  `apps/aggregator/tests/test_map_xss.py` (breakout-экранирование + DOM-построение попапа). Гейт:
  162 aggregator passed, ruff+`manage.py check` чисты. Без миграций. (medium/low из аудита — отдельно.)
- **2026-07-01 — багфикс(security, medium): newsletter-форма без rate-limit/honeypot.**
  `newsletter_signup` (`promotions/public_views.py`) — единственная публичная POST-форма без общих
  защит: (1) добавлен honeypot `website` (тихий нейтральный «sent» для ботов) + скрытое поле в
  `templates/storefront/newsletter.html`; (2) `ratelimit.hit("news", client_ip, limit=5, window=600)`
  до создания `Customer`/отправки — против email-бомбинга чужих адресов и неогранич. роста `Customer`;
  (3) убран оракул статуса подписки — ответ всегда нейтральный `sent` независимо от того, подписан ли
  e-mail (уже подтверждённому подписчику письмо повторно не шлём). UX-дельта: экран «Sie sind bereits
  angemeldet» больше не показывается (нейтральный «prüfen Sie Ihr Postfach»); ветку `already` в шаблоне
  оставили неиспользуемой. Тесты: `test_newsletter.py` (honeypot→нет Customer/письма; already→нейтрально,
  без повторного письма). Гейт: 164 promotions passed, ruff+check чисты. Без миграций.
- **2026-07-01 — security-батч (Fernet-check + Telegram + XFF + Stripe featured).** Закрыты low/medium
  из аудита. (S1, вариант а) `apps/secrets/checks.py` — Django deploy-check `secrets.W001`: в проде
  предупреждает, если `SECRETS_ENCRYPTION_KEY` не задан (ключ падает на фолбэк из `SECRET_KEY`); `deploy=True`
  → молчит в dev/CI, не ломает старт. Тест `test_checks.py`. (S2) Telegram-вебхуки (`apps/telegram/public_views.py`
  + `apps/aggregator/telegram_bot.py`): заголовок `X-Telegram-Bot-Api-Secret-Token` теперь **обязателен** и
  сверяется `hmac.compare_digest` (пустой/чужой → 404) — закрыт обход пустым заголовком; `set_webhook` всегда
  шлёт `secret_token`, поэтому легитимные апдейты проходят; тесты обновлены (передают заголовок) + новый
  `test_webhook_missing_secret_header_404`. (S3) `caddy/Caddyfile`: оба `reverse_proxy` перезаписывают
  `X-Forwarded-For` реальным peer-IP (`header_up X-Forwarded-For {http.request.remote.host}`) → клиент не может
  подделать XFF (rate-limit/Meldeschein-IP берут первый адрес). ⚠️ применяется при перезагрузке Caddy (деплой).
  (S4) `apply_featured_purchase` (`billing/services.py`) — персистентная идемпотентность featured-платежа:
  новое поле `AggregatorListing.featured_payment_ref` (миграция `aggregator/0013`) + сверка `payment_intent`
  (реплей вебхука при потере Redis-дедупа не продлевает срок повторно); вебхук пробрасывает `payment_ref`.
  Тесты `test_featured.py` (тот же ref → no-op; другой → продлевает). Гейт: 26 таргетных (`--create-db`) +
  регрессия telegram/aggregator/billing; ruff+`manage.py check` чисты. **Миграция `aggregator/0013` → деплой.**
- **2026-07-02 — UB1-1 (U-B): каркас listing.html + листинг услуг на нём + раскладка услуг на канве.**
  Старт Волны U-B (единый листинг). Новый `templates/storefront/listing.html` (блоки
  `listing_header/facets/grid/pagination/empty/after`, по образцу `detail.html`);
  `service_index.html` → extends: грид в `listing_grid` с `data-sf-section="services"`, karten-CTA в
  `listing_after`, карточка/embed/edit-хуки без изменений. Новый per-page ключ `service_index_layout`
  (дефолт cols2): в отличие от соседей НЕ материализуется normalize'ом — отсутствие ключа = легаси-грид
  шаблона (`grid sm:grid-cols-2 gap-4 max-w-3xl`, пиксельная неизменность ненастроенных витрин, решение
  владельца); `termin_index` читает конфиг+черновик (`?preview=1`) и передаёт `services_grid` только при
  заданном ключе. Канва: page-block `data-page-key="services"` (гейт `has_booking`) с опцией «Standard»
  (пустой выбор = ключ удаляется, откат к легаси), `collect()`/draft-эндпоинт/POST/GET-контекст/
  `SCOPE_PAGE_KEY` (`booking:"services"`)/apply-all — вся вертикаль как у каталога/номеров/событий.
  Известный прецедент сохранён: клик по гриду на канве /termin/ открывает секцию ГЛАВНОЙ `services`
  (как events/stay_rooms); настройка листинга — через переключатель страницы + панель «Landing pages».
  Без миграций. Гейт: 837 passed (booking+tenants+core, --reuse-db), CI run 1081 зелёный, FF-мерж
  `384cc83` → main. План — `docs/unified-sellable-entity-ub-plan-2026-06-30.md` (UB1-1).
- **2026-07-02 — UB1-2 (U-B): единая карточка sellable-сущности (услуги+номера, листинги+home).**
  Тег `apps/core/templatetags/sellable_ui.py::sellable_card` (строит `SellableEntity` через
  `sellable_for`+`get_language`) + партиал `templates/storefront/_sellable_card.html` (вертикаль/
  горизонталь; идентичность/медиа/ссылка/CTA — из контракта, мета/сырые цены для data-price-edit —
  per-kind из obj; blocktrans-паритет). Контракт НЕ расширяли (решение владельца): опции вызова —
  variant/href/query/edit/cta/badge/price_total/show_area/show_min_nights/show_description/h2.
  Переведены 5 контекстов: листинг услуг + home-секция услуг (горизонталь, Festpreis, слот-пикер),
  browse-грид номеров + ДОСТУПНЫЙ результат date-search (query с датами, цена за диапазон, Select,
  без едит-хуков/описания) + home-секция номеров; недоступный search-результат остался инлайн.
  `sf-card` теперь и на листингах (глобальный стиль карточек SE-2d действует там — решение владельца).
  Бонус: home-секции услуг/номеров стали локализуемыми (*_localized из контракта, L3c-выравнивание).
  `unterkunft_index` +`search_qs`. Тесты: 7 новых (test_sellable_card) + фикстуры test_services_section
  дополнены интерфейсом контракта (ассерты-замки без изменений). Без миграций. Гейт: 231+72+28 passed
  локально, CI run 1085 зелёный (полный прогон), FF-мерж `92758b6` → main. Попутно в roadmap §Отложено —
  «SEO-модуль v2» (заготовки мета с подстановками + AI-SEO, идея владельца 2026-07-02).
- **2026-07-02 — UB1-3 (U-B): свод трёх листингов на каркас listing.html (UB1 закрыт).**
  Крупнейшая регрессия волны — прошла через характеризационные замки, написанные ДО свода:
  `apps/events/tests/test_index_parity.py` (структура list/grid, фильтры выше грида, порядок по
  дате, оба empty-state) и `apps/catalog/tests/test_listing_parity.py` (порядок header→чипы→
  фасет-форма→сорт→грид→Show more, подкатегории-первыми между фасетами и гридом, empty ×2).
  Каркас +слот `listing_width` (events живёт в max-w-3xl mx-auto). `event_index.html` (оба режима
  list/грид RV3 в listing_grid, details-панель 7 фасетов в listing_facets), `products.html`
  (combos_teaser в хвосте header; чипы/диеты/форма/подкаты/сорт в facets; cursor-«Show more» в
  pagination), `stay_index.html` (date-search в facets; searched/browse в grid) — разметка
  перенесена БЕЗ изменений. Все 4 листинга витрины на одном каркасе. Гейты: 93/68/164 таргетных
  + широкий локальный 1553 passed (1 флейк admin-dashboard — артефакт reuse-db, на свежей БД
  зелёный) + CI run 1088 зелёный. FF-мерж `6f4b567` → main. Без миграций.
- **2026-07-02 — UB2-1 (U-B): протокол FacetProvider + провайдеры фасетов 4 листингов.**
  `apps/core/facets.py`: `FacetProvider` (selected/apply/present) + `NullFacets` + ленивый
  `provider_for(kind)`. Провайдеры-делегаты без изменения выдачи: events (обёртка
  `_event_facets`/`_event_matches`), catalog (категория slug + диета; chips по встречающимся),
  stays (разбор date-search von/bis/erw/kinder; движок наличия не тронут), booking (NullFacets).
  Все 4 вьюхи листингов вызывают провайдер вместо хардкода; product_list: facet_base =
  provider.apply(категория-без-диеты) — прежний снимок для границ цены/бейджей. Новый
  `apps/core/tests/test_facets.py` (6). Гейт: 190 таргетных passed, CI run 1090 зелёный,
  FF-мерж `fe3ba48` → main. Без миграций. Дальше UB2-2 (поиск ?q= + user-facing sort).
- **2026-07-02 — UB2-2 (U-B): поиск `?q=` + user-facing сортировка на всех 4 листингах.**
  Протокол += `search` (icontains v1, решение C-3; хелпер `i18n_icontains_q` — плоские поля +
  KeyTransform ВСЕХ локалей settings.LANGUAGES для JSON-i18n, keyset-safe) и `sort`/`sort_keys`/
  `sort_options` (паттерн `_LISTING_SORTS` агрегатора; ""/мусор = порядок вьюхи). Провайдеры:
  catalog (JSON name/description {de,en}; прежний реестр `_CATALOG_SORTS` переехал в провайдер),
  НОВЫЙ booking.ServiceFacets, stays, events (in-memory, эффективная цена: min-тир при has_tiers).
  Каркас: блок `listing_toolbar` (форма q + select sort с carry активных параметров) между
  facets и grid. Вьюхи: termin (ветка услуг решается ДО поиска; «Nothing found» вместо ухода в
  booking_index), unterkunft (редирект «один юнит» не срабатывает при ?q=; сорт скрыт в searched;
  формы несут q/sort взаимно), veranstaltung (q как активный фильтр: empty-state/раскрытие панели),
  product_list (q — полноправный фасет carry: cursor/«Show more»/формы/диет-чипы; собственный
  сорт-блок каталога заменён тулбаром каркаса; q-empty-state). Тесты: +5 провайдерных, +4 вью
  (в т.ч. EN-локаль поиска). Локальный флейк-урок: fixed form_token двух reserve-тестов дедупится
  в Redis (TTL) — повторный прогон в окне TTL красный, на свежем Redis (CI) зелёный. Гейты:
  11+215+80 таргетных, широкий 1204 passed (+2 Redis-флейка), CI run 1094 зелёный. FF-мерж
  `2d9b04d` → main. Без миграций.
- **2026-07-02 — UB2-3 + UB3-1 (U-B): фасеты цена/наличие/происхождение/рейтинг; подкатегории в каркасе.**
  `CatalogFacets` — полный владелец фасетов каталога: перенос цены («12,50»-ввод, границы из
  present) и «только в наличии» (Exists-зеркало `Product.in_stock` с вариантами) из вьюхи бит-в-бит
  + НОВЫЕ Bio/Regional-Herkunft (`Product.origin`, чипы только указанных значений) и рейтинг
  (`reviews.services.bulk_summary` — один агрегат, `pk__in`, keyset-safe; пороги 3/4/5 как в
  агрегаторе; фасет виден лишь при отзывах). `product_list` делегирует всё провайдеру (бейдж
  остался во вьюхе — вне набора); herkunft/bewertung в carry (cursor/формы) и any_facet_active;
  селекты Herkunft/«from N ★» в фасет-форме. **UB3-1 закрыт констатацией:** подкатегории-первыми
  перенесены в каркас ещё в UB1-3 (замок `test_catalog_subcats_first_between_facets_and_grid`).
  Тесты: +3 провайдерных, +1 e2e. Гейт: 84 passed, CI run 1098 зелёный, FF-мерж `6d15877` → main.
  Без миграций. Остаток волны: UB3-2 (M2M Collection) — мини-разведка
  `docs/ub3-2-collection-recon-2026-07-02.md` НА СОГЛАСОВАНИИ владельца (миграция только после).
- **2026-07-02 — UB3-2 (U-B): M2M-подборки Collection — ВОЛНА U-B ЗАКРЫТА ЦЕЛИКОМ.**
  По согласованной разведке `docs/ub3-2-collection-recon-2026-07-02.md` (решения владельца:
  модель ок, имя `apps.collections`, CRUD в составе, демо-названия ок). Новое TENANT-приложение
  `apps.collections`: модель `Collection` (плоская, без scope; name/description + `*_i18n`
  L3-оверлей; slug unique — параметр фасета; sort_order/is_active) + M2M-поля
  `Service.collections`/`StayUnit.collections`. **Миграции: `collections/0001_initial`,
  `booking/0013`, `stays/0021`** (чистые AddField/таблицы). Фасет `?kollektion=<slug>`:
  хелпер `core.facets.collection_chips` (чипы только активных коллекций с сущностями снимка,
  label на локали) + selected/apply/present в ServiceFacets/StayDateFacets (M2M-JOIN+distinct);
  чипы на /termin/ и /unterkunft/ (паттерн категорий каталога), carry в тулбаре/форме дат;
  ветка услуг в termin_index решается ДО фасета; редирект «один юнит» не срабатывает при фасете.
  Кабинет `/dashboard/collections/` (стиль services_view): создание (slug авто, стабилен при
  переименовании), состав чекбоксами услуг/номеров с presence-guard, вкл/выкл/удаление; ссылки
  с кабинетных страниц услуг/номеров; гейт booking-или-stays. Демо: `DemoKit.collections` +
  сидер по индексам refs; friseur («Damen»/«Herren»/«Färben & Pflege»), hotel («Mit Seeblick»/
  «Familienzimmer»). Тесты: 13 новых (модель/фасет/витрина/CRUD/демо). Гейты: 86+329 passed на
  `--create-db`, CI run 1102 зелёный, FF-мерж `1dd3b6e` → main. **Деплой миграций — владелец:**
  `git pull origin main && ./scripts/deploy.sh single` (+опц. `seed_demo_tenants --kit friseur|hotel
  --recreate` для демо-чипов). Итог волны U-B: единый каркас листинга, единая карточка, свод
  4 листингов, FacetProvider, поиск+сорт, фасеты каталога, коллекции услуг/номеров.
- **2026-07-02 — Остаток U-A (1/3): демо-A9 — богатая карточка услуги + service-отзывы werkstatt.**
  По аудиту 2026-07-01 (`…-ua-plan §7`): у werkstatt-кита UA4-3-карточка была только у handwerker.
  «Inspektion» получает attributes (4) / FAQ (2) / `primary_action='request'` (A9-семантика: цена
  зависит от модели → Kostenvoranschlag mit Fahrzeugangabe) + `image_kw`; `service_reviews` —
  3 отзыва (Inspektion ×2, HU/AU ×1) по образцу friseur, `_seed_entity_reviews` подхватывает без
  правок кода. Тест-замок: модельные проверки + рендер витринной детали услуги (секции
  attributes/FAQ/отзывы видны). Гейт: test_demo_kits 23 passed. Без миграций.
- **2026-07-02 — Остаток U-A (2/3): combo i18n — 5-й kind адаптера SellableEntity локализован.**
  `catalog.Combo` += `I18nMixin` + `name_i18n`/`description_i18n` (overlay-семантика как у
  Service/StayUnit: база в плоском поле, переводы в JSONField) + `*_localized`. Миграция
  **`catalog/0012`** — чистые AddField default=dict. Адаптер `_combo` отдаёт локализованные
  name/description → i18n для 5/5 kind. Гейт: test_sellable+catalog 189 passed на `--create-db`.
- **2026-07-02 — Остаток U-A (3/3): reviews-email wiring — post-visit письма → generic-форма отзыва.**
  events post-event → `/veranstaltung/<pk>/bewerten/` (было — корень витрины); stays post-stay →
  `/unterkunft/<pk>/bewerten/` (было — hotel-портал, хелпер `_review_url` удалён; jobs-портальный
  не тронут — jobs не sellable); booking post-visit НОВОЕ — письмо «Wie war Ihr Termin?» (beat раз
  в сутки, окно N+7 как у stays, только confirmed/fulfilled записи С услугой, ровно одно —
  `post_visit_sent_at` + БД-дедуп) → `/leistung/<pk>/bewerten/`. Миграция **`booking/0014`**
  (AddField). Ссылки абсолютные (домен из `_base_url`; нет домена → письмо без ссылки, без
  падения); `/…/bewerten/` на GET редиректит на деталь с формой. Гейт: 39 таргетных + полные
  сьюты booking/stays/events/reviews 510 passed.
- **2026-07-02 — Остаток U-A (4/5): UA3-1 слайс 2 — единый buy-box `_buybox.html`.**
  По согласованному плану `docs/ua3-1-buybox-plan-2026-07-02.md` (разведка: 5 картографов +
  адверсариальная сверка). C1 — характеризационные паритет-замки ДО правки (7 тестов: точные
  наборы полей cart/reserve/waitlist-форм, якоря, sold-out, orders-off, точные href CTA услуги).
  C2 — партиал `templates/storefront/_buybox.html`: диспатч `cart`/`reserve`/`request`/`booking`
  по `purchase_mode` контракта (или явный `buybox_mode`: promotion — вне реестра sellable,
  service — override primary_action); разметка перенесена 1:1, вьюхи/формы/`_add_to_cart_form`
  не тронуты; детали product/promotion/service — только include. Грабля: `default:`-фильтр в
  `{% with %}` жёстко резолвит аргумент (у promotion нет `sellable`) → `{% firstof %}` (ленивый).
  Гейты: замки байт-в-байт зелёные, полные сьюты catalog/promotions/booking/orders 562 passed.
  Без миграций. Остаток U-A: только UA3-2 (двухшаговый buy-box) — план-док на согласовании.
- **2026-07-02 — Остаток U-A (4/5): UA3-1 слайс 2 — единый buy-box `_buybox.html` (C1+C2+фикс).**
  По согласованному плану `docs/ua3-1-buybox-plan-2026-07-02.md`. C1 — 7 характеризационных
  паритет-замков ДО правки (точные поля cart/reserve/waitlist-форм, якоря, sold-out, orders-off,
  href CTA услуги). C2 — партиал с диспатчем `cart`/`reserve`/`request`/`booking` по
  `purchase_mode` (или явный `buybox_mode`; promotion вне реестра sellable); детали
  product/promotion/service — только include; вьюхи/формы/`_add_to_cart_form` не тронуты.
  Грабли: (1) `default:`-фильтр в `{% with %}` жёстко резолвит аргумент → `{% firstof %}`;
  (2) многострочный `{# #}` в promotion_detail уронил CI-замок test_template_comments
  (урок: core-замки — в локальный гейт шаблонных правок). Гейты: замки байт-в-байт,
  сьюты catalog/promotions/booking/orders 562 passed. Без миграций.
- **2026-07-02 — Остаток U-A (5/5): UA3-2 — двухшаговый buy-box через контракт (вариант A+). ВОЛНА U-A ЗАКРЫТА.**
  Решение владельца: A+ (stay — селектор+форма партиалами за `_buybox.html`, полный «B» для
  stay; селектор услуги остаётся страницей слот-пикера). C1 — паритет-замки ДО правок (точные
  поля POST-форм stay базовая/с rate_plan+extra+embed и service базовая/с resource+embed;
  недоступность/без выбора — фолбэки без формы). C2 — контракт: `SellableEntity` +=
  `select_url`/`submit_url`/`buybox_ready` (реверс per kind, `_reverse_or_empty` pk→без-арга→"").
  C3 — stay: `_buybox_stay_select/form/unavailable.html` (1:1), ветка booking|request в
  `_buybox` — двухшаговый гейт (форма ТОЛЬКО при `buybox_ready`), вьюха отдаёт
  `quote.available`; C4 — service_slots: `_buybox_service_form/pick.html`, вьюха отдаёт
  `bool(selected)`; POST-приёмники и `book_stay`/`booking.services.book` НЕ тронуты. CTA
  детали услуги → `sellable.select_url`. План — `docs/ua3-2-two-step-buybox-plan-2026-07-02.md`.
  Гейты: stays 170, booking+core 510, широкий 606 passed (локальный rl-флейк повторных
  прогонов — точечная чистка `rl:*`). Без миграций.
- **2026-07-02 — E-7 (платёжный микс DACH), внутренняя часть E7-1..3 — по плану `docs/e7-payments-plan-2026-07-02.md`.**
  **E7-1**: `Order.payment_method` (on_site/stripe/vorkasse, ""=легаси; миграция **`orders/0012`**),
  оба checkout-флоу фиксируют способ; `Tenant` += `vorkasse_enabled`+`bank_holder/iban/bic`+
  `stripe_payment_methods` (SHARED-миграция **`tenants/0020`**); кабинет заказов: форма Vorkasse
  (IBAN/BIC нормализуются, guard без IBAN) + бейдж способа в списке. **E7-2**: паритет-замок формы
  ДО правок (один способ = байт-в-байт прежняя); `payments.available_methods` (первый = дефолт,
  сохраняет старое поведение); radio `payment` при >1 способа; способ передаётся в `create_order`
  ДО создания (письмо created его видит); Vorkasse → без Stripe, реквизиты + Verwendungszweck=код
  заказа в письме и на подтверждении; подделка/мусор POST → дефолт. **E7-3**: `connect.
  connected_checkout_session` += `payment_method_types` (пусто → не передаём) из
  `Tenant.stripe_payment_methods` — прокинуто во все 7 продажных вызовов (orders/stays/gift/
  booking/passes/events/jobs), installment сознательно без; кабинет: чекбоксы Zahlarten на
  `/dashboard/billing/payments/`. Гейты: orders 101, billing+депозитные флоу 278, gift 11 passed.
  Урок среды: `billing/tests/test_tasks.py` виснет ЛОКАЛЬНО и на чистом дереве (на CI зелёный) —
  гейтить с `--ignore` до починки. Нативные PayPal/Klarna/SEPA-мандаты — external-integrations-
  backlog; Vorkasse вне orders (stays G7 и пр.) — отложено (E7-4, roadmap §Отложено).
- **2026-07-02 — E-7: два красных CI на хвосте батча (1121/1122) — быстрые ранние замки, уроки в §5.**
  (1) Новые Tailwind-классы (sky-палитра бейджа способа/Vorkasse-блока) без пересборки
  `static/css/app.css` → замок «Build CSS & check freshness». (2) `ruff format --check` гонялся
  точечно и пропустил `apps/stays/public_views.py` (sed-правка gift-вызова) → формат-чек CI по
  всему дереву. Оба фикса — по коммиту; run 1123 зелёный, FF-мерж `86bbd33` → main. Конвенция
  §5 дополнена финальным гейтом батча (format целиком, build:css, шаблонные замки).
- **2026-07-02 — Стек ТЗ одобрен владельцем + СТАРТ ВОЛНЫ U-C: UC1-1 (единый реестр секций).**
  Владелец одобрил целиком: идеи A1–D3 (`feature-ideas-2026-07-02.md`), втяжку U-E-пакетов
  UE2/UE3 в U-C (`uc-plan §11`), контент-анализ CM-1..9 (`market-content-analysis-2026-07-02.md`);
  сводная очередь — roadmap §«Одобренный стек ТЗ». **UC1-1 ✅:** шаг 0 — golden-замки
  `siteconfig.normalize` (4 репрезентативных конфига → эталоны `golden/*.json`, байт-в-байт +
  идемпотентность; постоянный гейт волны); затем фасад `page_types`/`page_section_keys`/
  `page_section_labels`/`page_sections(config, page_type)` над SECTIONS (home) и
  `detail_sections` (детали) — осознанное отклонение от буквы плана (реестры первичны, фасад
  над ними; normalize не тронут). Грабля фикстуры: config-ключи деталей `service_detail`/
  `stay_detail` (не `booking_/stays_`) — normalize молча игнорирует неизвестные. Гейт: 527
  passed (tenants+builder+preview+sections). Без миграций. Дальше — UC1-2′ (listing/info/legal).
- **2026-07-02 — UC1-2 (U-C): реестр page_type += listing/info/legal.** Слоты каркаса
  `listing.html` + about + Impressum/Datenschutz/Widerruf как first-class page_type фасада
  (fixed-order мета, конфиг пока не управляет — тест фиксирует; управление — UC2-3/UC3-2,
  AGB — с E-2/L5). 26 passed (registry+golden+siteconfig), normalize не тронут. Без миграций.
- **2026-07-02 — UC1-3 (U-C): иконки в реестр + generic page_inspector.** `SECTION_ICONS` →
  siteconfig (KEYS+LABELS+ICONS вместе) + `page_section_icons`; `page_inspector(config,
  page_type)` из единого реестра (event — orderable с 1-based order, прочие hide-only) —
  4 ручные сборки в `home_builder_view` заменены; контекст-ключи шаблона неизменны. Гейт: 165
  passed. Фаза U-C1 (реестр) ЗАКРЫТА; дальше UC2-1 (page-scoped draft, ⚠️ горячее). Без миграций.
- **2026-07-02 — UE2-1 (U-E→U-C): единый компонент вывода скидки `_discount_display.html`.**
  Шаг 0 — замки `test_discount_display_parity` (бейдж %/−€ оба размера, strikethrough+красная,
  scarcity-пороги, countdown `data-countdown` в локальной TZ, valid-until, surprise) ДО правок;
  затем 8 дублей `_promo_card.html`/`promotion_detail.html` сведены на include с part=badge|
  surprise|price|scarcity|countdown, size=sm|lg. Замок поймал дрейф порядка CSS-классов бейджа —
  компонент переписан на точные исходные строки. Локальная грабля: `resv_token:*`/`rl:*` в Redis
  переживают прогоны (cache-префикс! чистить `scan_iter('*rl:*')`) — флейк test_public. 172 passed.
- **2026-07-02 — UE2-2 (U-E→U-C): `Promotion.discount_style` — селектор вида скидки.**
  Поле (7 стилей + default ""=легаси) + миграция `promotions/0019` (⚠️ деплой); ветвление в
  `_discount_display.html`: percent/badge — тип бейджа, strikethrough/festpreis/ab — цена
  (ab — по конвенции from-price карточек товара), countdown — таймер без флага, surprise —
  пилюля вместо бейджа. Селектор в PromotionForm (кабинет — цикл полей, UI автоматом). Свойства
  цены/has_discount/анти-оверселл не тронуты (тест-гейт). 181 passed (полный promotions-гейт),
  DE-локаль в тестах: числа с запятой («7,50»).
- **2026-07-02 — UE3-1 (U-E→U-C): инлайн-правка промо на канве — % / старая цена / срок.**
  Вайтлист `promotion_inline_edit` += `compare_at_price` (Decimal ≥0, общая ветка с
  price_override), `discount_percent` (целое 0..100, 0 = очистить), `ends_at` (ISO, naive →
  текущая TZ); после правки — сброс кэша витрины. Поля движка (status/available_quantity)
  закрыты тест-гейтом (анти-оверселл). Канва: старая цена → data-price-edit
  (compare_at_price), %-бейдж редактируем, countdown/«Valid until» → новый generic
  data-dt-edit (datetime-local попап в site_home.html). Замок бейджа перепинен на
  class+текст (editor-атрибуты не ломают визуальный паритет). 951 passed. Без миграций.
- **2026-07-02 — UE3-2 (U-E→U-C): фото акции на канве — promotion-photo-edit.** Новый view
  (реюз `apply_gallery_op`, folder="promotions", select_for_update) + маршрут +
  `MODEL_PHOTO_URLS['promotion']`; 📷 на карточке (replace главного; пустая галерея →
  добавление, фолбэк на фото товара цел), 📷+🗑 на детали (🗑 только при собственной
  галерее). Закрыт пробел «единственная модель канвы без фото-эдита». CSS пересобран.
  Пакет U-E3 закрыт целиком. Без миграций.
- **2026-07-02 — UE2-3 (U-E→U-C): mystery-акция (hidden-until-reveal).**
  `discount_style='mystery'`: цена скрыта (`data-mystery-price hidden` + кнопка-reveal,
  a11y `<button>`), фото в blur-lg; раскрытие — делегированный JS в `_base.html` в пределах
  `data-mystery-root`. Бронь/остаток от стиля не зависят. Миграция `promotions/0020` —
  AlterField choices БЕЗ изменения БД (грабля: ModelForm.full_clean валидирует по
  model-choices — форменного расширения недостаточно). Пакет U-E2 закрыт целиком.
- **2026-07-02 — E-2 слайс 1: §312j-кнопка checkout.** «Place order» →
  `{% trans "Zahlungspflichtig bestellen" %}` (cart.html; DE-msgid — немецкий по
  умолчанию при пустых .po). Тест-замок в test_orders. Остаток E-2 (PAngV-ноты, AGB через
  LegalDoc, засев права в киты, UWG «Anzeige», 404 /entdecken) — следующими слайсами.
- **2026-07-02 — E-2 слайс 2: UWG «Anzeige» + страница бизнеса на главном /entdecken.**
  Бейдж платного продвижения «★ Empfohlen» → «★ Anzeige» (UWG §5a; карточки + копия
  страницы Empfehlung; замки обновлены). A8-асимметрия закрыта: `business_page`
  портал-опциональна (главный домен: база `_base.html`, отзывы read-only, сабмит —
  портал-only с хинтом), маршрут `/entdecken/unternehmen/<slug>/` в urls_public под
  ТЕМ ЖЕ name `portal-business`, `business_link=True` в city_listing. Без миграций.
- **2026-07-02 — UC2-1 (U-C): page-scoped draft-модуль (слайсы A+B).** План-док
  `docs/uc2-1-page-draft-plan-2026-07-02.md` (разведка агентом + решение «виртуальный
  фасад»: хранение ПЛОСКОЕ, `pages` — срез; риски literal-переноса №1-4). Слайс A:
  `PAGE_CONFIG_KEYS` (единая декларация page_type→ключи, вкл. служебный `cart`) +
  `apply_page_payload` (семантика прежних веток 1:1) + `page_config`-срез + замок
  консистентности реестр↔apply. Слайс B: шесть per-page блоков `site_preview_draft` →
  один вызов. Слайс C (save): после анализа НЕ сводим — блоки form-field-driven с
  presence-guard'ами, свод = переписывание → место UC2-4 (зафиксировано в план-доке).
  Замки: 164 draft/save/preview + 160 fan-out + golden. Без миграций.
- **2026-07-02 — UC4-2-доводка (U-C): JSON-LD Offer + BreadcrumbList + Event-поля.**
  Контракт `SellableEntity` += `price_value`/`price_currency`/`ld_extra`; адаптеры заполняют
  (product: availability по in_stock; event: startDate/location; from-price при тарифах/
  вариантах). `entity_ld` эмитит `offers` + мержит `ld_extra`; `breadcrumb_ld` + вторая
  `<script>` в `entity_jsonld` (Start → листинг → имя). XSS-замок перепинен на все блоки.
  1077 passed. Без миграций.
- **2026-07-02 — UC2-2 слайс 1 (U-C): клик→инспектор на всех детальных.** Разведка
  агентом (гейты previewPath==='/', drag связан с order_* главной, C-блоки — home-only) →
  план-док `docs/uc2-2-oncanvas-plan-2026-07-02.md`. Обёртки `data-sf-section=<page-key>`
  на service/stay/product (event уже был) → per-page попап инспектора открывается кликом
  на канве на всех 4 деталях. Слайс 2 — drag ed_order_* (next); слайс 3 (инсертер C-блоков
  вне home) — заблокирован архитектурой, требует решения владельца. Без миграций.
- **2026-07-02 — UC2-2 слайс 2 (U-C): drag тематических секций детали события на канве.**
  `data-ed-section`-обёртки в цикле + `moveEdSection` (мутация `ed_order_*`, приём home
  moveBlock, общий drop-line) → schedule → драфт `event_detail.order` (generic после
  UC2-1). UC2-2 закрыт в реализуемом объёме (слайс 3 — C-блоки вне home — заблокирован
  архитектурой sections=home-only, требует решения владельца; план-док §2). Без миграций.
- **2026-07-02 — UC4-3 (U-C): галерея услуги — шим dict→[dict] (D4a, БЕЗ миграции).**
  `Service.images`-шим над тем же JSONField (легаси dict → [dict]; запись photo-edit —
  всегда список), `image_url` primary-aware; `service_photo_edit` → полный
  replace/add/remove (apply_gallery_op); деталь услуги — единая `_media_gallery`
  (лайтбокс, пер-слайд контролы) → галерея на 5/5 kind. Адаптер gallery из шима.
- **2026-07-02 — UC5-1 (U-C): граница buy-box — `configurable="form"` + замок.**
  Пометка в `detail_sections` (buy-box вне реестров секций — не канва; UA3-1/3-2 держат
  границу функционально) + `test_buybox_boundary_not_canvas_configurable`. Без миграций.
- **2026-07-02 — UC3-1 (U-C): тема каскадом — sf-card на пропущенных карточках.**
  Каскад site_defaults→`--sf-*`→`.sf-card` глобален; пропуски закрыты классами: листинг
  событий (обе раскладки) + «похожие номера» детали. UC3-1 закрыт; UC3-2 — в пакете
  normalize-решений с UC2-3(b) (план-док uc2-3). Без миграций.
- **2026-07-03 — UC2-4 (U-C): единый диспетчер инлайн-правки канвы.** Разведка агентом
  (карта 6+2 эндпоинтов, три JS-канала → MODEL_EDIT_URLS) → план-док
  `docs/uc2-4-inline-dispatcher-plan-2026-07-03.md`. `apps/core/inline_edit.py`:
  декларативный `INLINE_REGISTRY` + `dispatch` (семантика полей 1:1, вкл. асимметрии
  bump как декларации + замок); вьюхи product/event/stay/service/promotion — тонкие
  алиасы (URL/протокол прежние). category/site — вне (другие контракты). Свод
  save-блоков home_builder_view — НЕ сюда (form-driven, отдельное решение).
  1279 passed. Без миграций. **ВОЛНА U-C: автономно выполнимое ЗАКРЫТО ЦЕЛИКОМ** —
  остался только пакет за решением владельца (per-page секции: UC2-3(b)+UC3-2+C-блоки).
- **2026-07-03 — CM-1 (контент-хаб): блог first-class — модуль «blog».** План-док
  `docs/cm1-blog-first-class-plan-2026-07-03.md` (разведка: BlogPost самостоятелен,
  публичные вьюхи не гейтились). ModuleSpec blog (recommended у всех типов, гейт
  /dashboard/blog/ + /blog/), кабинет на /dashboard/blog/ + пункт меню, сидер friseur
  («Neuigkeiten» без модуля событий), sitemap + BlogPosting JSON-LD. Без миграций.
  Грабля: два pytest на одной тест-БД параллельно (фоновый гейт + форграунд) дают
  фантомные ERRORs — не гонять одновременно.
- **2026-07-03 — Решение владельца: per-page хост C-блоков ПОКА НЕ ДЕЛАЕМ.**
  Пакет UC2-3(b)+UC3-2+слайс 3 UC2-2 → roadmap §Отложено (анализ сохранён в план-доках).
- **2026-07-03 — CM-2 (контент-хаб): контент-календарь + отложенная публикация.**
  План-док `docs/cm2-content-calendar-plan-2026-07-03.md`. `SocialPost` (текст/фото/
  ссылка/scheduled_at, SocialPostSM; шов source_kind под CM-3) поверх прежней доставки
  `Publication` (promotion nullable + post FK, XOR-констрейнт; миграция `publishing/0005`
  — ⚠️ деплой). Адаптеры → единый `content_for` (промо 1:1, замки каналов). Beat
  `send_due_content` (300с): посты → Publications; отложенный блог через `published_at`
  БЕЗ новых полей. Кабинет «Beiträge» (/dashboard/posts/, NavItem в publishing),
  блог-формы += «Veröffentlichen am». 311 passed (свежая БД).
- **2026-07-03 — CM-3 (контент-хаб, MVP): авто-посты из блога + префилл «Beiträge».**
  `draft_from_source` (идемпотентно по source_kind+source_id) + `blog_share_draft`;
  авто-черновик при публикации записи (кабинет + beat), кнопка «Teilen» на правке,
  префилл формы постов из GET. Остаток CM-3 (авто-черновики из событий/товаров,
  авто-правила) — следующим слайсом. Без миграций.
- **2026-07-03 — CM-3/2: авто-черновики из событий.** `event_share_draft` (первая
  публикация из кабинета: create published / edit-переход). Товары — осознанно без
  автомата (шум при импорте; префилл-кнопка при спросе — roadmap §Отложено). CM-3 закрыт
  в целевом объёме: блог+события авто, промо публикуется автоматом изначально.
- **2026-07-03 — CM-4 (контент-хаб): медиа-библиотека — реестр MediaAsset + «Medien».**
  План-док `docs/cm4-media-library-plan-2026-07-03.md`. MediaAsset-индекс ПОВЕРХ
  FileRef-копий (миграция `core/0004` — ⚠️ деплой + опц. `backfill_media_registry`):
  fail-safe хук в save_product_image/delete_stored_image, единая карта мест
  `apps/core/media_registry.py` (backfill/write_back_alt/delete_unused/used_paths),
  кабинет `/dashboard/medien/` (фильтр по папкам, alt-редактор с write-back — закрыт
  «мёртвый alt», удаление только незанятых). Слайс C (пикер в билдере, dedup) — план §3.
- **2026-07-03 — B3 (быстрая победа): кросс-селл товаров на детали услуги.** Секция
  `upsell` в реестре booking (скрываемо в билдере) + `_service_upsell.html`
  (featured-first ×4, реюз _product_card) при активном catalog. Без миграций.
- **2026-07-03 — A3 (быстрая победа): именованные версии сайта.** label в записях
  истории (normalize_history, кламп 60), действия save_version (снимок ТЕКУЩЕЙ версии
  с именем, публикация не меняется) и label_version:<idx>; UI истории с именами и ✎.
  CI 1163 (B3-замки реестра) починен обновлением ожиданий. Без миграций.
- **2026-07-03 — C2 (быстрая победа): QR-печатка — цели + фирменный цвет.** `?ziel=`
  (termin/sortiment/unterkunft/veranstaltung, гейт по модулям, фолбэк home) с per-цель
  текстами; постер в primary_color тенанта; дропдаун целей в кабинете акций. Без миграций.
- **2026-07-03 — UE1+UE4-1 (порядок владельца): промо-БЛОК на канве главной + шаблоны.**
  План-док `docs/ue1-promo-block-plan-2026-07-03.md`. Тип `promo` в REPEATABLE_BLOCKS
  (санитизация: promo_pk-строка без DB в normalize, пресеты align/badge_pos, кнопка;
  discount_style НЕ дублируется — источник Promotion/UE2-2); `_block_promo.html` —
  D2=LIVE с fail-safe скрытием, всё через единый `_discount_display` (позиция бейджа —
  новый параметр с прежним дефолтом, паритеты целы), UE3-инлайн работает внутри;
  селектор промо + пресеты в форме блока, промо-поля в collect(), «Aktion» в библиотеке;
  UE4-1 шаблоны — автоматом за REPEATABLE_BLOCKS (замок). golden-замки легаси байт-в-байт.
  Тесты test_promo_block (6). Без миграций. **Волна U-E закрыта в объёме главной**
  (остаток UE4-2 — за отложенным решением per-page).
- **2026-07-03 — Правовой-языковой пакет L4+L5+E-2 (порядок владельца, 4 слайса).**
  План-док `docs/legal-lang-package-plan-2026-07-03.md`. **С1 PAngV:** ноты
  «inkl. MwSt.» на детали товара (+«zzgl. Versand» при delivery_enabled) и у Total
  корзины — немецкие msgid (паттерн §312j-кнопки). **С2 Zusatzstoffe:** реестр
  ADDITIVES (13 классов LMZDV, паттерн ALLERGENS) + `Product.additives`
  (миграция catalog/0013) + чекбоксы формы + строка в LMIV-блоке детали.
  **С3 LegalDoc (S-2b):** модель core.LegalDoc (kind×locale, unique; core/0005),
  резолвер legal.py (LegalDoc[локаль]→LegalDoc[дефолт]→плоское поле→генерённый
  фолбэк), `/agb/` (404 без текста) + AGB в футере по тегу agb_present,
  LEGAL_SECTIONS+=agb, кабинет `/dashboard/recht/` (4 вида × активные локали,
  превью автотекста, presence-guard), демо-засев: право из генераторов без
  placeholder-хинта + AGB-заготовка по модулям кита. **С4 L4-письма:**
  `_render(..., locale)` c translation.override (дефолт-локаль тенанта, fail-safe
  de) — единая точка всех нотификаций; клиентские шаблоны 5 флоу (reservation+
  HTML+waitlist/booking/stays/tickets/orders) на trans с DE=msgid (DE байт-в-байт);
  `locale/en/.../django.po` только-письма (109 строк, все переведены); .mo не в
  git — msgfmt-шаг в CI, compilemessages в deploy.sh, gettext в Dockerfile.
  Остаток DE-only: owner-письма + gift_voucher/inbox/installment/job_* (по мере
  надобности). Урок: Mock-тенант в тестах → `_email_locale` принимает только str.
- **2026-07-03 — A4 (быстрая победа): share-ссылка на черновик витрины.** Кнопка
  «Share preview» в топ-баре билдера → POST выпуск токена (снапшот черновика:
  сессия → БД-_draft → normalize(published); cache 7 дней, token_urlsafe) →
  анонимный GET /vorschau/<token>/ кладёт снапшот в сессию посетителя и уводит
  на /?preview=1 (штатный draft-путь витрины; page-кэш обходится сам). Снапшот
  фиксирован в момент выпуска; нет/истёк → 410. Без миграций.
- **2026-07-03 — C1 (быстрая победа): утренний дайджест владельцу (email).**
  digest.py (метрики по активным модулям, fail-safe, пустой день → молчим) +
  beat send_owner_digests раз в час (гейт «локальный час тенанта == 7», дедуп
  digest:{schema}:{date}) + письмо DE + opt-out Tenant.owner_digest_enabled
  (SHARED миграция tenants/0021) + чекбокс в настройках. Telegram владельцу —
  отдельный трек (chat_id владельца не хранится). Уроки CI 1170/1171: не забыт
  build:css после новых классов; замок page_registry legal+=agb обновлён осознанно.
- **2026-07-03 — Идея B1 (Geschenkgutscheine на все архетипы): B1.1–B1.4.**
  Каталогизация: docs/task-catalog.md (единая карта ID, правило «расширяется →
  углубляется») по фидбэку владельца. B1.1 — gift-вьюхи из stays →
  apps/loyalty/public_views (1:1), новый универсальный модуль `gift` (реестр,
  recommended_for=все типы; гейт страницы = модуль + payments+Connect), футер-
  ссылка «🎁» на всех архетипах (gift_link_active). B1.2 — booking принимает
  voucher_code: поля-снимки (миграция booking/0015), _apply_voucher-зеркало в
  book() (redeem под транзакцией), инпут в буй-боксе услуги (price>0);
  паритет-замки UA3-2 перепинены осознанно. B1.3 — кабинет: блок «Sold gift
  vouchers» на /promotions/vouchers/ (оплата/код/погашение). B1.4 —
  unredeem_voucher (условный декремент >0) + хук «cancelled → вернуть
  использование» в 4 FSM (orders/booking/stays/tickets); однократность — FSM.
  B1.5 (остаток/balance_cents вместо сгорания) — вопрос владельцу; B1.6 (jobs)
  — опц. Уроки: default_disabled_for гасит нерекомендованное → новый
  универсальный модуль обязан перечислить ВСЕ типы в recommended_for.
- **2026-07-03 — B1.5 (решение владельца «а»): Wertgutschein с остатком.**
  `Voucher.balance_cents` (loyalty/0003; null = прежние промокоды) + единая
  точка чекаутов `spend_voucher` (расчёт+списание под одной блокировкой; 4
  копии _apply_voucher orders/booking/stays/events сведены) +
  `unredeem_voucher(amount)` возвращает остаток при отмене (FSM-хуки передают
  снимок). Выпуск gift: balance=номинал, max_uses=0. Кабинет: «Rest X €».
- **2026-07-03 — B1.6 (запрос владельца): Gutschein в сметах Handwerker.**
  Job += voucher_code/discount_cents (jobs/0011); accept Angebot с кодом →
  spend_voucher (Wertgutschein = Zahlungsmittel: gross/счёт полный, скидка
  уменьшает «zu zahlen»/payable_gross); инпут только в простом accept-пути
  (депозит-Checkout без кода); JobSM-отмена возвращает остаток. **Идея B1
  закрыта ЦЕЛИКОМ (B1.1–B1.6).**
- **2026-07-03 — B1.7 (решение владельца «в»): потолок промокода % от чека.**
  `Tenant.voucher_max_percent` (tenants/0022; 0=без лимита, клэмп 0..100 в
  настройках) — кап в единой точке spend_voucher + preview_discount (превью
  корзины orders/quote events = списанию). Только промокоды; проданные
  Wertgutschein не капаются (Zahlungsmittel, §307 BGB).
- **2026-07-03 — CM-8 (карточка клиента 360°): слайсы 8.1–8.4.** Сборщик
  `apps/crm/customer360.py` (owner-URL, fail-soft, гейт is_module_active,
  устойчив к RequestFactory без tenant): KPI-шапка LTV из RevenueEntry +
  счётчики доменов; разделы Termine/Passes/Stays/Tickets/Aufträge(→кабинет)/
  Rechnungen(→кабинет)/inbox-переписка(→тред)/отзывы по email-матчу.
  Generic-рендер карточек в customer_detail. Без миграций. 8.5 timeline — опц.
- **2026-07-03 — CM-6 (репутационный модуль): 6.1–6.4 целиком.** Новый модуль
  reviews (⭐ «Bewertungen», актив из коробки): кабинет /dashboard/reviews/ —
  список отзывов (фильтры, подписи сущностей fail-soft) + скрыть/показать
  (первая модерация вообще) + сводка owner_overview. Ответы владельца
  (reply_text/replied_at, reviews/0003) — форма в кабинете + «Reply from the
  business» в обоих витринных рендерах. Post-purchase просьба об отзыве для
  заказов (orders/0013, beat, DE=msgid+en.po) — круг просьб замкнут по всем
  4 kind. Уроки: msgmerge при перегенерации en.po ТЕРЯЕТ часть переводов и
  fuzzy-подставляет чужие — после makemessages прогонять fill-скрипт и
  проверять `msgfmt --statistics` (112/112).
- **2026-07-03 — Идея B2 (напоминание о незавершённой оплате): B2.1–B2.3.**
  Разведка: настоящий cart-abandonment не ловится (email только на финальном
  POST) — сигнал «создано, ждёт оплаты» есть во всех Stripe-доменах. Orders
  (orders/0014, stripe+unpaid+new, 24ч) + Booking (booking/0016, депозит, 6ч)
  + Stays (stays/0022) + Tickets (events/0022): beat раз в час, письма
  DE=msgid (en.po 125/125), pay-again вьюхи /bezahlen/ (Checkout на лету) +
  кнопки «Jetzt bezahlen» на подтверждениях. Transactional-гейт
  (Vertragsanbahnung), без opt-in. B2.4 (CartLead+DOI) — отложен (UWG-серо).

- **2026-07-03 — B4/CM-9: купон-кампании по сегментам + авто-win-back (v1+v2
  целиком).** План `docs/b4-cm9-campaigns-plan-2026-07-03.md`. `CouponCampaign`
  (promotions/0021: сегмент tag/inactive_days/top_ltv + параметры кода + письмо
  + kind manual|auto_winback) + `Voucher.campaign` FK (loyalty/0004) +
  `segment_customers()` ПОВЕРХ consented_customers (UWG §7 по построению;
  inactive_days отсекает не-покупателей осознанно) + `send_coupon_campaign`
  (персональный одноразовый код каждому + письмо с List-Unsubscribe;
  идемпотентно: реюз кода у manual, дедуп писем по коду) + страница
  `/promotions/kampagnen/` (создание/отправка/live-размер сегмента/аналитика
  выдано-погашено + карточка Auto Win-back) + NavItem «Campaigns» в модуле crm
  + вход из CRM-списка (prefill ?tag=) + beat `send_winback_coupons` (86400,
  дедуп-окно = inactive_days, настройки на кампании — БЕЗ Tenant-миграции).
  Тесты `test_coupon_campaigns.py` (19: сегменты/гейт/идемпотентность/вью/beat).

- **2026-07-03 — идея D2 (self-serve featured): слайсы D2.1–D2.3.** Ядро было
  готово (P2.4b). Доделано: **D2.1** «★ Anzeige» на КАРТЕ (featured-флаг в
  `geo.map_points`, DOM-бейдж в попапе `_map.html` — UWG §5a теперь на всех
  поверхностях; перепин замка test_expired_featured: литерал в статичном JS);
  **D2.2** вход из списка акций («★ Feature»/«★ bis dd.mm.» на active,
  один public-запрос листингов); **D2.3** owner-аналитика —
  `featured_impressions`/`featured_clicks` (aggregator/0014, F-инкременты:
  показы в `split_featured` первой страницы, клики через редирект-счётчик
  `/entdecken/klick/<pk>/`, имя роута продублировано в urls_portal до
  catch-all; featured-карточки + маркеры карты ведут через счётчик,
  rel="sponsored"), блок «Bisher: X Aufrufe · Y Klicks» на странице
  продвижения. D2.4 (stays/events) — следующий слайс; D2.5 (цены в кабинете)
  — ⏸ env достаточно.

- **2026-07-03 — D2.4: self-serve featured для stays/events (идея D2 закрыта в
  рабочем объёме).** Generic-адресация листинга в billing:
  `create_featured_checkout_session`/`apply_featured_purchase` принимают
  `(listing_kind, source_ref)` (легаси promo_uuid работает — незакрытые сессии),
  вебхук прокидывает; хелперы `apps/aggregator/featuring.py`
  (render_feature_page/start_feature_checkout) + generic-шаблон
  `tenant/listing_feature.html` — зеркало promotion_feature; вьюхи
  `stays:unit-feature(+checkout)` и `events:feature(+checkout)` + входы
  «★ Feature» на units-странице и детали события. Без миграций. Тесты:
  billing generic-адресация (4) + stays/events страницы и гейт оплаты (6).
  D2.5 (цены в кабинете) — ⏸ env; полный E-11 (claim-your-business) — позже.

- **2026-07-03 — идея D3: партнёрка веб-студий, v1 целиком (D3.1–D3.4).**
  Решения владельца: делаем; вознаграждение — «несколько вариантов»
  (per-partner); v1 — read-only; этап 2 — вход в кабинеты клиентов (D3.5,
  отдельный план). Новый SHARED-апп `apps.partners`: `Partner` (user
  OneToOne public-auth, `code` unique, reward_kind ""|client_discount|
  revshare + coupon/percent; `partners/0001`) + `Tenant.partner` FK
  (`tenants/0023`, зависимость на partners/0001 сгенерена) + атрибуция
  `?ref=<code>` (session → kwarg `partner_code` в оба создателя →
  `_resolve_partner` fail-safe в `_new_tenant`) + кабинет `/partner/`
  (urls_public, login_required: реф-ссылка, счётчики, список клиентов
  из public-полей, revshare-сводка `BILLING_PLAN_PRICE_EUR`) + шов
  `_partner_discounts` в подписочный Checkout (`discounts=[{coupon}]`
  только при client_discount+coupon; паритет-замок «без партнёра —
  запрос прежний») + unfold-админка и пункт UNFOLD nav «Partners».
  План `docs/d3-partner-plan-2026-07-03.md`. Тесты `apps/partners/tests/`
  (8: атрибуция/мусорный код/кабинет-изоляция/403/ревшара/купон/паритет).

- **2026-07-03 — D3 пост-ревью: 4 находки адверсариального воркфлоу
  исправлены** (детали — план D3 §пост-ревью): savepoint в
  `_resolve_partner` (MEDIUM: except внутри atomic отравлял транзакцию
  онбординга при DB-ошибке), одноразовый `partner_ref` (pop), best-effort
  скидка (протухший купон → ретрай Checkout без discounts), N+1 админ-
  списка (annotate). Реф-коды-слаги — принятый риск. Всё в main (2fc3ddd).

- **2026-07-03 — L3d.1–L3d.4: per-locale ввод форм + мультиязычный демо-засев
  (остаток Волны L; без миграций).** План `docs/l3d-input-plan-2026-07-03.md`.
  **L3d.1**: helper `apps/core/i18n_input.py` (extra_locales/apply_i18n_overlay/
  i18n_inputs_for; presence-guard, базовая локаль НИКОГДА не пишется в оверлей)
  + Service/StayUnit/Combo create+update пишут `*_i18n` из полей
  `<field>_<locale>`, шаблоны services/units/combo_form рендерят доп. инпуты
  только при N>1 локалях (1 локаль — паритет); update Service/StayUnit теперь
  правит и name (только при явно присланном поле). `request.tenant` — через
  getattr (RequestFactory-тесты без миддлвари). **L3d.2**: `_i18n_text`
  генерализован (любые локали), `_split_i18n` → сидеры Service/StayUnit пишут
  оверлеи; EN-примеры: friseur (2 услуги), hotel (2 номера). **L3d.3**: поле
  `DemoKit.combos` + сидер (лукап товаров по `name__de__in` — Product.name
  JSONField) + 2 демо-комбо ресторана с EN. **L3d.4**: инлайн-диспетчер пишет
  в `settings.LANGUAGE_CODE` вместо хардкода "de". Тесты: test_i18n_input (8)
  + demo-kit i18n (3) + смежные замки 75+33 зелёные. L3d.5 (ModelForm
  Category/Product/Promotion → N-locale) — следующим батчем.

- **2026-07-03 — L3d.5: Category/Product/Promotion ModelForm → N-locale
  (ВОЛНА L ЗАКРЫТА в объёме L3d).** `DynamicI18nFormMixin` + `form_locales`
  в `apps/core/i18n_input.py`: статические поля пар de/en убраны, база
  (`*_de`) остаётся классовой (обязательность прежняя), поля прочих локалей
  создаются в __init__ по `active_locales` тенанта (без tenant-kwarg — весь
  реестр: паритет старых вызовов/тестов); save() собирает словарь
  `collect_i18n`. Шесть вьюх-вызовов передают tenant. Шаблоны без правок —
  рендерят `{% for field in form %}`. Тесты: de-only тенант прячет `name_en`,
  3-я локаль (fr) появляется и сохраняется, initial из instance; 237 замков
  catalog/promotions/demo зелёные.

- **2026-07-03 — T-4 (bottom-nav ТЗ): нижнее меню витрины закрыто доводкой
  S7-билдера** (решение владельца: не плодить второй механизм — ТЗ писалось
  до появления S7 `menus.bottom`). Доведено: узел-корзина кастомного нижнего
  меню получает акцент+бейдж (`context.py` S7-ветка: kind=primary +
  `_cart_count` при `url == reverse("storefront-cart")`), подсказка о лимите
  5 и семантике корзины в билдере. Кап 5 и гейтинг целей были. Замки:
  test_action_bar += 2 (custom-меню акцент/бейдж; без корзины — default);
  golden/normalize не тронуты (ключей не добавляли).

- **2026-07-06 — HOTFIX T-5: verify_domain — строгий allowlist (инцидент
  «refused to connect»).** Сканеры (Alibaba-IP) запрашивали TLS на мусорные
  хосты вида `www.1www.whm…baeckerei-test.siteadaptor.de`; blanket-allow
  `endswith(".siteadaptor.de")` в `apps/core/health.verify_domain` пропускал
  их к Caddy on-demand → квота Let's Encrypt (50 серт/168ч) выжжена ботами →
  новые легитимные поддомены (restaurant-demo) не получали сертификат до
  2026-07-06 08:21 UTC. Фикс: разрешены корень (+www) и ТОЛЬКО строки таблицы
  Domain (субдомены/порталы/custom-домены её и так заводят). Тесты
  `test_verify_domain.py` (5: корень/www, Domain-строка, мусор 404, замок
  инцидента). Опс: после деплоя перезапустить caddy (очистить очередь ретраев
  мусорных имён); долгосрочно — wildcard через Cloudflare DNS (пометка в
  Caddyfile).

- **2026-07-06 — T-6: «Edit design» внутри канвы убивал превью редактора
  (X-Frame-Options).** Репродукция жалобы владельца (restaurant-demo, «refused
  to connect» / серая канва): внутренние переходы канвы идут БЕЗ `?preview=1`
  → на этих страницах виден витринный FAB «✏️ Edit design» (`_base.html`,
  гейт только по `request.GET.preview`) → клик грузит `/dashboard/site/home/`
  В КАДР → `X-Frame-Options: DENY` → Chrome коммитит chrome-error («refused
  to connect»; в консоли цитируется ORIGIN — голый `/`, что и путало), а F5
  восстанавливает историю сабфрейма (initiator «Other», blocked:other) —
  канва мертва навсегда. Подтверждено Playwright headful (xvfb): дословное
  сообщение консоли + `chrome-error://chromewebdata/` + «refused to connect».
  Сервер здоров — инцидент T-5 ни при чём. Фикс: FAB → `target="_top"`
  (выпрыгивает из кадра; с обычной витрины поведение прежнее), ✎ правки
  категории в `products.html` → `target="_blank" rel="noopener"` (паттерн
  `_product_card`). Замок на весь класс: `test_frame_escape_links.py` —
  скан витринных шаблонов: `<a>` в DENY-зону обязан нести `_top`/`_blank`.

- **2026-07-06 — T-6.1: deep-link «Edit design» + скрытие FAB в канве + «Страница
  акции» в превью.** Продолжение T-6 по жалобе владельца («редактор открывается
  на главной, где канва — непонятно»): (1) FAB «✏️ Edit design» теперь несёт
  `?page=<текущий path>` → `home_builder_view` через `_safe_preview_page`
  (только внутренний path; DENY-зона/внешние URL → «/») стартует канву прямо
  на той странице, где нажали; селектор страниц синхронизируется, если путь в
  списке. (2) Внутри канвы (iframe) FAB прячется (`window.top !== window.self`)
  — дубль редактора путал владельца; `target="_top"` остаётся страховкой.
  (3) `DETAIL_ENTITIES` += Promotion → пункт «Promotion page» в селекторе
  превью (канва-правка промо UE2/UE3 стала находимой). Замки:
  test_preview_pages (+promotion, +санитайзер deep-link), test_frame_escape_links
  (+`?page=`, +скрытие в кадре). Проверено Playwright e2e: канва стартует на
  `/p/<uuid>/?preview=1`, FAB в канве отсутствует.

- **2026-07-06 — UC6-1: одна кнопка «✏️ Править» + режим «⚙️ Шаблон» (Editor
  UX v2, старт).** Решения владельца зафиксированы (`editor-ux-v2-plan §5`:
  палитра темы / «Шаблон» в редакторе / вкладки Просто-Эксперт в попапе +
  идея «ленты» настроек сверху а-ля Word → UC6-6). Сделано: (1) «Edit panel»
  + «Edit on site» слиты в одну кнопку «✏️ Edit» (правка ВКЛ по умолчанию;
  "0" в sf_edit_on = сам выключил); (2) «⚙️ Template» — рейл областей +
  «Тема» (глобальные настройки), повторный клик/✕ сворачивает; (3) канва-
  first: рейл и панель скрыты на старте (и на широком экране), клик по
  блоку на канве открывает его настройки (openBlockPopup сам зовёт
  showArea), restore-область после save-перезагрузки сохранена; (4) хинт
  подвала обновлён под новое имя кнопки. Замки test_home_builder (id обеих
  кнопок) живы; e2e Playwright: старт/шаблон/клик-по-блоку — зелёные.

- **2026-07-06 — UC6-2: стиль текста C-блока — выравнивание/размер/цвет (палитра
  темы).** text/image_text получили `align` (center/right), `size` (sm/lg/xl),
  `color` (accent/muted): `_text_style` в `_clean_cblock_data` (только валидные
  НЕ-дефолтные значения → старые конфиги байт-в-байт, golden живы), рендер
  `_block_text`/`_block_image_text` (Tailwind-классы уже в app.css, accent —
  `var(--accent)`),три селекта в строке блока билдера («Просто»-уровень),
  collect() += size/color, `_read_cblock_data` += style. Цвет — ТОЛЬКО палитра
  темы (решение владельца). Замки: test_cblocks (+3: валидация/паритет/рендер),
  test_cblocks_builder (+1: save-путь).

- **2026-07-06 — UC6-3: ширина C-блока full/wide/2-3/1-2 + положение (канва).**
  «Текст на 2/3 экрана с выравниванием по правому краю» (запрос владельца):
  `CBLOCK_WIDTHS` += w23/w12 (секции остаются contained/full), новый ключ `pos`
  (left/right; центр = без ключа — старые конфиги байт-в-байт), обёртка блока
  в `home.html` → `md:w-2/3|md:w-1/2` + `md:mr-auto|mx-auto|ml-auto` (мобайл —
  100 %); селекты ширины/положения в строке КАЖДОГО C-блока билдера; collect()
  и site_preview_draft несут width/pos в черновик; save-путь починен — width
  C-блока РАНЬШЕ ТЕРЯЛСЯ при Save (жил только в черновике), теперь
  персистится + `width`/`pos` в контексте cblocks (селекты помнят значение).
  `npm run build:css` (md:w-2/3 и др. — новые классы). Замки: test_cblocks +2
  (валидация w23/w12/pos, секции НЕ расширены), test_cblocks_builder +1
  (save-путь). Попутно: мусорный `</content>` в конце home.html удалён.

- **2026-07-06 — UC6-5: библиотека блоков — карточки с иконкой/подсказкой +
  демо-данные при вставке.** `siteconfig.CBLOCK_DEMO_DATA` (DE-рыба: text/
  image/image_text/button; изображения — генератор `/medien/demo.svg`;
  spacer/promo осознанно пустые) → `add_block` создаёт живой пример вместо
  пустоты («ничего не произошло»). `block_types` → словари value/label/icon/
  hint; обе поверхности (форма «Add block» в Библиотеке + плавающий инсертер
  «+» на канве) показывают иконку и подсказку. Замки: test_cblocks_builder +2
  (демо при вставке; демо-данные проходят normalize без потерь).

- **2026-07-06 — UC6-4: фото C-блока — 📷 замена прямо на канве + скругление.**
  Новый эндпоинт `site-cblock-photo-edit` (реюз `save_product_image`,
  folder="cblock"): пишет url в data блока ПУБЛИКУЕМОГО конфига + зеркалит в
  сессионный черновик и БД-`_draft`; JS синхронизирует поле `cb_<id>_url`
  формы по ответу {url} ДО пере-рендера черновика (иначе push() откатывал бы
  фото). 📷-кнопка в `_block_image`/`_block_image_text` (is_preview+block_id;
  `render_block` прокидывает id блока), MODEL_PHOTO_URLS += cblock. Скругление:
  data-ключ `rounded` (""=rounded-2xl | none | 3xl) — валидация в
  `_clean_cblock_data`, селект в билдере, collect()/`_read_cblock_data` несут.
  build:css (rounded-3xl/none). Замки: test_cblock_photo_edit (публикуемый+
  _draft+сессия; 404/400 без порчи), test_cblocks +2 (rounded-валидация/рендер;
  📷 только в превью).

- **2026-07-06 — UC6-3a/3b + UC6-1b: блоки в ряд, ширины до 1/6, чистка тулбара
  (фидбэк владельца после прода).** (a) `group_block_rows` (siteconfig):
  последовательные УЗКИЕ C-блоки → `{"key":"_row"}` → `md:flex` в home.html;
  обёртка блока вынесена в `_section_block.html` (data-sf-section жив у каждого);
  чекбокс «Start new row» (`newline` на блоке: normalize/collect/save/draft/
  контекст). (b) `CBLOCK_WIDTHS` += w13/w14/w15/w16 (+опции селекта) —
  1/3..1/6 контейнера. (c) селектор страниц УБРАН из тулбара («уже всё
  редактируется»): скоуп панели авто-следует за фактическим путём кадра —
  `PAGE_GROUPS` (server-side JSON: escapejs кодировал дефисы и ломал literal-
  сравнение) + синк в load-обработчике; deep-link ?page= работает. Перепин
  замков селектора на PAGE_GROUPS (2 шт., осознанно). build:css (md:w-1/3..1/6).
  Замки: test_cblocks +3 (группировка/newline/валидация ширин),
  test_cblocks_builder +1 (save newline). Остальной фидбэк (тень, пресеты
  с демо 5-10/тип, FAQ 5 вариантов, Просто/Эксперт per-блок) — по решению
  владельца целиком в UC6-6 (план §4/§5 обновлён).

- **2026-07-06 — UC6-6a: ЛЕНТА настроек блока над канвой (Word-style) + вкладки
  Просто/Эксперт + мобильный bottom-sheet.** Клик по блоку больше НЕ открывает
  левую панель: #bld-block-popup всплывает fixed-лентой по центру над канвой
  (шапка: имя блока · вкладки Simple/Expert · свёртка ▾ до шапки · ✕), канва
  остаётся во весь экран; на <lg лента - bottom-sheet снизу. Ключевой трюк:
  контролы блока НЕ покидают <form id="home-form"> (collect()/Save живы) —
  панель-хозяин прячется через visibility (не display) классом
  `bld-ribbon-open`, который снимает и transform (иначе fixed-потомок
  позиционировался бы от транслированной панели). Контролы C-блоков в ленте
  текут горизонтально. Закрытие восстанавливает состояние панели (curArea).
  Проверено Playwright e2e: лента y=54/960px, правка чекбокса в ленте доезжает
  до live-preview (форма цела), свёртка/закрытие, JS без ошибок. Остаток UC6-6:
  (b) тень/фон/отступ на C-блоки, (c) пресеты отображения с демо (5-10/тип,
  FAQ 5 вариантов).

- **2026-07-06 — UC6-6b: visual C-блоков — тень/радиус/отступ/фон из ленты.**
  `_clean_cblock` += `visual` (реюз `_clean_visual`; ключ ТОЛЬКО при ненулевых
  значениях — golden живы); обёртка `_section_block` уже отдаёт `--sf-*` — новые
  CSS-правила в `_base.html` применяют их к контейнеру `.cb-box`
  (text/image/image_text/button; legacy без переменных не меняется). Лента:
  тень — «Просто», радиус/отступ/фон — «Эксперт» (data-expert); collect() и
  save-путь несут visual, черновик — passthrough; live-update через form-wide
  input/change → schedule(). Замки: test_cblocks (+presence-minimal и
  переменные обёртки), test_cblocks_builder (+save). Остаток UC6-6:
  (c) пресеты отображения с демо (5-10/тип; FAQ 5 вариантов).

- **2026-07-06 — UC6-6c: пресеты отображения при вставке блока (двухшаговый
  инсертер) — UC6 ЗАКРЫТ в объёме C-блоков.** Реестр `CBLOCK_VARIANTS`
  (text: Intro/Zitat/Akzent-Banner/Notiz-2/3 · image: Vollbreite/Schatten/
  Eckig/Halbbreit · image_text: Foto-rechts/Karte/Akzent/Kompakt · button:
  Schatten/Rechts-1/3; + «Standard» = демо) + `cblock_insert_preset(btype,
  variant)` — демо-данные + оверрайды пресета (data/width/pos/visual);
  `add_block` принимает `variant`; инсертер «+» на канве стал двухшаговым
  (тип → варианты, ← Back). Замки: пресет-merge; АДВЕРСАРИАЛЬНЫЙ замок «каждый
  пресет реестра проходит normalize без потерь» (иначе вариант молча давал бы
  стандарт); builder-save. E2E: варианты в инсертере, «Akzent-Banner» даёт
  центрированный акцент-блок на канве. FAQ-варианты отображения — отложены
  отдельным инкрементом (fixed-секция, другой механизм) — roadmap §Отложено.

- **2026-07-06 — UC6-6d: FAQ — 5 вариантов отображения (реестр стилей фикс-
  секций) — пакет UC6-6 ЗАКРЫТ ЦЕЛИКОМ.** Реестр `SECTION_STYLES` (+ DE-лейблы)
  — расширяемый механизм «вариант отображения» для фикс-секций; `_section_entry`
  держит `style` только из реестра (дефолт — без ключа, golden живы);
  `render_block` прокидывает строку секции в контекст (`section_row`). FAQ:
  аккордеон (дефолт) / открытый список / 2 колонки / карточки / нумерация с
  акцент-кружками. Селект «Display style» в настройках блока FAQ (лента);
  collect()/save/draft несут style. Замки: реестр-валидация (чужая секция/
  мусор → без ключа) + рендер всех 5 видов. build:css. FAQ-механизм готов
  к расширению на другие секции (testimonials/process) — по мере надобности.

- **2026-07-06 — UC6-6c2/6d2: донаполнение пресетов (курс на 10/тип) + стили
  «подобных FAQ» секций.** CBLOCK_VARIANTS: text 8 видов (+Nur Überschrift/
  Weiße Karte/Band auf Vollbreite), image 8 (+Halbbreit rechts/Drittel/
  Polaroid), image_text 8 (+Band/Gedämpft/Foto rechts+Karte), button 5
  (+Linksbündig/Band) — адверсариальный normalize-замок покрывает новые
  автоматически. SECTION_STYLES += testimonials (Große Zitate/Offene Liste/
  Akzent-Rand/Einzeln zentriert) и process (Zeitstrahl/In einer Reihe/
  Minimal/Zwei Spalten) — по 5 видов с дефолтом; селект «Display style»,
  collect/save/draft — generic из UC6-6d, ноль новых прокидок. Замки:
  рендер всех видов testimonials/process + реестр-валидация.

- **2026-07-06 — UC6-6e: лента во всю ширину + «Шаблоны = только шаблоны» +
  миниатюры пресетов (фидбэк владельца).** (1) Лента настроек блока — full-width
  полоса в стиле верхнего тулбара (белая, компактная, нижняя граница; мобайл —
  bottom-sheet как был). (2) Форма «Add block» удалена из области «Шаблоны» —
  блоки добавляются ТОЛЬКО инсертером «+» на канве (с выбором пресета);
  в Библиотеке остались блок-/страничные шаблоны и история. (3) Варианты
  пресетов в инсертере показываются КАРТИНКОЙ: JS-миниатюра варианта из props
  (ширина/положение/выравнивание/фото-сторона/тень/фон/цвет — сервер отдаёт их
  в cblock_variants_json); инсертер расширен w-44→w-64. E2E: лента x=0 w=1440,
  Add block из Библиотеки исчез, 26 миниатюр рендерятся; 130 тестов зелёные.
  **E2E-СВИП всего редактора (запрос владельца): 0 ошибок** — 16 секций главной
  открывают ленту с контролами, 6 типов блоков вставляются, 18 страниц превью
  живые (без FAB-протечек/JS-ошибок/5xx); termin/gutschein/konto без inline-
  правок — кандидат на разработку (inline-контракт услуг в листинге).

- **2026-07-06 — UC6-6f: пресеты до 10/тип + промо-пресеты из стилей скидки +
  варианты галереи/команды/trust (заказ владельца).** (1) CBLOCK_VARIANTS:
  text/image/image_text по 9+Standard=10 (Intro links groß, Zitat rechts 2/3,
  Weich gerundet, Schmal 2/3, Kompakt rechts, Akzent-Karte…). (2) Промо-блок:
  8 вариантов вставки = стили вывода скидки (style_hint в data; санитайз по
  PROMO_STYLE_HINTS) + селект в ленте блока; КАСКАД: явный
  Promotion.discount_style ГЛАВНЕЕ hint'а блока (расширение UE2-2 без второго
  источника) — `eff_style` в _discount_display (+style_override из
  _block_promo), паритет-замки живы; миниатюры промо-вариантов рисуются по
  стилю (бейдж/зачёркнутый/countdown/mystery…). (3) SECTION_STYLES += gallery
  (Filmstreifen/Große Kacheln/Polaroid/Stark gerundet), team (Runde Fotos/
  Liste/Kompakt), trust (Linksbündig/Abzeichen/Ohne Karte). (4) Наблюдение
  свипа про «нет inline-правки услуг в листингах» — FALSE POSITIVE: sellable_card
  несёт полный inline-контракт (edit=True дефолт), нули были из-за пустых
  данных ресторана. Замки: каскад hint (promotions), рендеры всех новых видов,
  style_hint-санитайз; адверсариальный замок реестра покрыл новые пресеты
  автоматически. build:css.

- **2026-07-06 — UC6-6g: UX-полировка ленты по живому фидбэку владельца.**
  (1) Клик по блоку БЕЗ «бокового выезда» панели: closeBlockPopup(restorePanel)
  + transition:none на переключении. (2) Лента НЕ перекрывает сайт: канва
  отодвигается на высоту ленты (syncRibbonPad → paddingTop #bld-preview-pane;
  пересчёт на свёртке/смене вкладки, сброс на закрытии). (3) Компактно в ~2
  строки: шапка блока и настройки текут инлайн (flex-wrap; div.w-full →
  display:contents; рамки-разделители погашены; вертикальная черта между
  группами). (4) Дубль Simple/Expert убран из топ-бара (вкладки — в ленте).
  (5) Кнопка «✏️ Edit» убрана — правка ВСЕГДА включена (contenteditable сразу).
  (6) Инсертер «+» не обрезается у нижнего края: внутренний скролл (72vh) +
  кламп позиции после рендера вариантов. (7) «Шаблон» = ТОЛЬКО глобальные:
  кнопка Sections и иконки блоков убраны из рейла (область живёт для фолбэка).
  (8) Переключатель Desktop/Tablet/Mobile переехал в верхний тулбар.
  (9) Заголовок ленты C-блока — тип блока (не «Position»). Перепины замков:
  test_home_builder ×4 (осознанно). E2E: все 8 пунктов зелёные, канва
  отодвинута (paddingTop=высота ленты), 41 contenteditable сразу.

- **2026-07-06 — UC6-7a: page_blocks — хост C-блоков на ЛЮБОЙ странице (рендер).**
  Отмашка владельца («весь функционал главной — на всех страницах») снимает
  блокировку пакета per-page. Архитектура: НОВЫЙ ключ `page_blocks`
  {host: [cblock,…]} — `sections` не тронут; `normalize_page_blocks` (whitelist
  PAGE_BLOCK_HOSTS — 11 страниц, legal сознательно исключён; чистка через
  `_clean_cblock`, кап); ключ в normalize — presence-minimal (golden живы).
  Тег `{% page_blocks "<host>" %}` (siteui): sess-черновик при ?preview=1,
  ряды узких блоков + `_section_block` (клик→лента/📷/инлайн бесплатно), пустой
  хост в превью — пунктирная якорная зона. Хосты: 4 листинга (listing_after) +
  blog + 4 детали + cart + about. План — `uc6-7-page-blocks-plan-2026-07-06.md`.
  Замки: whitelist/чистка/golden-absence + тег (publish/preview/empty).
  Остаток: 7b (редактор: строки в форме + draft/save + инсертер с page_key),
  7c (drag + вставка без перезагрузки), 7d (меню в ленту).

- **2026-07-06 — UC6-7b: РЕДАКТОР page_blocks — весь функционал главной на любой
  странице.** Строка настроек C-блока вынесена в общий партиал `tenant/_cb_row.html`
  (переключатель `pb_page`: `pb_id`+`pb_page_<id>`+`data-pb-page` vs `cb_id`); имена
  полей уникальны по id → collect/save/save-as-template без переименований. GET:
  `page_cblocks` по PAGE_BLOCK_HOSTS в наборе «Landing pages», скрытие существующим
  `applyPageScope`. Save: общий `_cblock_entry_from_post` (главная+страницы),
  page-ветка под presence-guard `pb_present` пересобирает `page_blocks` из
  `pb_id`-строк (host из `pb_page_<id>`, whitelist, сортировка, удаление; пустой хост
  исчезает; без guard конфиг страниц не трётся). Draft: `buildCbEntry` общий,
  home-ветка пропускает pb-строки, отдельный свип `.cb-row[data-pb-page]` →
  `payload.page_blocks` (все хосты, вкл. опустевшие → удаление видно в превью),
  server passthrough + `normalize_page_blocks`. Инсертер «+»: гейт снят на страницах
  с `curPbHost` (из `data-pb-host` кадра; drag home-only до 7c); `add_block`/
  `use_block_template` несут `page_key`+`page_path` → `page_blocks[host]`
  (`insert_after` по id, `pbhost:<key>` → append), `_redirect_builder` возвращает
  канву на ту же страницу (`?page=` через `_safe_preview_page` — no-open-redirect).
  Скрытое `page_path` в `#home-form`, JS синкает при навигации кадра. БЕЗ миграций.
  Замки: `test_cblocks_builder` +7 (page_key/unknown-фолбэк/insert_after/template/
  save-rebuild/presence-guard/GET-рендер), `test_live_preview` +1 (draft passthrough),
  e2e verify_7b (вставка на /ueber-uns/ → канва → лента → Save → публикация, 0 ошибок).
  **Адверсариальный ревью-воркфлоу (5 измерений × verify)** нашёл 2 реальных дефекта
  скоупа (остальные — golden/collect-draft-save/удаление/порядок/безопасность —
  верифицированы safe): (1) `applyPageScope`: `isHome` считал главной ЛЮБУЮ страницу
  вне PAGE_GROUPS (2-я+ деталь, любая деталь услуги, blog: group="") → фолбэк на
  `curPbHost` был недостижим, блоки страницы неуправляемы из панели, показывались
  контролы главной → фикс `isHome = (!group||group==="home") && !curPbHost`; (2) блок
  «Content blocks» главной без `data-scope` был виден на подстраницах (правки уходили
  бы в sections не той страницы) → `data-scope="home"`. Оба проверены на стенде
  (verify_scope: blog vs home) + замок `test_home_content_blocks_details_is_home_scoped`.
  Остаток UC6-7: 7c (drag в регионе + вставка без перезагрузки), 7d (меню в ленту).
