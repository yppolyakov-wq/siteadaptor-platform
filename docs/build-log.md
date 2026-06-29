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
