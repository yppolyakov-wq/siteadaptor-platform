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
