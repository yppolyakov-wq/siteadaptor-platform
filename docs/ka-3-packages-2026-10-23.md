# KA-3 · Пакеты: какие экраны и доступы у каждой ступени (спецификация для T-8.32a–e) — 2026-10-23

> Документ на согласование. Кода нет. Основа: концепция `t8-32-tiers-data-ai-setup-concept-2026-10-22.md`
> (решения §8, §10), программа `ka-cabinet-audit-program-2026-10-22.md`, `ka-0-inventory-2026-10-22.md`,
> `ka-1-standards-2026-10-23.md`, `ka-2-market-2026-10-23.md` §3(c). Сверено с кодом на 2026-10-23
> (`apps/core/modules.py`, `lite_cabinet.py`, `tg_login.py`, `storefront_profile.py`, `nav_registry.py`,
> `middleware.py`, `apps/promotions/limits.py`, `response.py`, `apps/billing/plans.py`,
> `apps/tenants/onboarding.py`, `services.py`, `config/urls_tenant.py`).
> **[доп.]** — допущение, проверяется в плане инкремента. Вопросы владельцу — §9.

## 1. Цель и принятые решения

KA-3 задаёт, что видит и может открыть владелец на каждой ступени: пункты меню, Mini App, палитру
Ctrl+K, страницы витрины, лимиты; и как ОДНА функция доступа заменяет нынешние пять механизмов.

| № | Решение владельца | Что это значит здесь |
|---|---|---|
| Р-1 | Две оси «Paket × Richtung» | реестр `apps/core/packages.py` + направления Waren/Termine/Zimmer/Tickets/Anfragen |
| Р-2 | Промежуточный пакет «Website-Vitrine» | пакет `website`: свой сайт без онлайн-продаж |
| Р-3 | Честный доступ | модули сверх пакета выключены, данные не удаляются; прямой адрес тоже закрыт |
| Р-4 | Жёсткий гейт готовности | пока обязательное не заполнено, корзина/оплата/бронь закрыты |
| Р-7 | AGB — внешний генератор | проверяем только наличие текста AGB (`LegalDoc kind=agb`) |
| — | «Aktionen» = минимум | акции, кабинет, чат, контакты, право; без блога, новостей, каталога-раздела, Studio, финансов, склада |
| §10 | Бесплатно только на время теста | план `test`: 5 активных акций, 50 товаров, ИИ ~20 действий/мес |
| §10 | Склад и финансы — Profi | дополнения `profi_lager`, `profi_finanzen` |
| §10 | Тарифы нигде не видны | `PRICING_PUBLIC=False`: ни цен, ни названий тарифов, ни кнопок покупки; на лимите «Im Testbetrieb begrenzt» |

## 2. Реестр пакетов и планов

### 2.1. Модули и «области»

Core-модули (выключить нельзя): `dashboard`, `board`, `catalog`, `settings`, `billing`. Опциональные:
`promotions`, `crm`, `reviews`, `orders`, `booking`, `stays`, `loyalty`, `gift`, `analytics`, `publishing`,
`jobs`, `events`, `blog`, `inbox`, `finance`, `telegram`, `customer_account`.

Core-модули через `is_module_active` закрыть нельзя (`modules.py:554`), поэтому пакет ограничивает на
двух уровнях: **потолок опциональных модулей** и **области (features)** — виртуальные группы экранов
внутри core-модулей (без миграций и новых записей REGISTRY):

| Область | Экраны (url_name / префикс) |
|---|---|
| `studio` | `site-home`, `site-menu`, `site-sections`, `site-preview*`, `site-inline-edit`, `site-scope-*`, `site-seo`, `design`, `media-library`, `domains*` |
| `catalog_admin` | `sellable-manage` (раздел), `catalog:category-*`, `catalog:combo-*`, `collections:list`, `imports:start/map/preview/status`, `catalog:products-merge` |
| `product_edit` | `catalog:product-create/edit/delete/image-*`, `variant-*`, `modifier-*` |
| `site_import` | `imports:website`, `imports:website-run` |
| `stock` (**Profi Lager**) | `/dashboard/stock/`, `/dashboard/purchasing/`, `purchasing-maengel-pdf` |
| `finance_erp` (**Profi Finanzen**) | `finance:journal`, `expenses`, `expenses-datev`, `ergebnis`, `offene`, `bank`, `export-csv`, `export-datev` |
| `finance_basic` | `finance:invoices`, `invoice-detail`, `invoice-pdf`, `invoice-mahnung`, `deal-invoice` |
| `sales_board` | `verkaeufe*`, `board-*`, `ablaeufe`, `status-*`, `transitions-save`, `deal-*`, `payments-page` |
| `settings_full` | `settings`, `languages`, `notifications-settings`, `payment-settings`, `integrations-home`, `extras`, `modules`, `finder-settings`, `team`, `einstellungen-home`, `support:*` |
| `legal` | `legal-docs` (owner-only) |
| `lite` | `lite-business`, `lite-visibility`, `lite-share` |

`finance_basic` отделён от ERP: счёт фирме выпускается сам на чекауте (SH-23), из сделки (`deal-invoice`),
а GoBD требует хранить и выдавать счета — закрыв весь `finance` вместе с Profi, мы лишили бы владельца
его же счетов.

### 2.2. Пакеты

| Пакет | Ключ | Опциональные модули | Области | Профиль витрины | Онлайн-продажа |
|---|---|---|---|---|---|
| **Aktionen** | `aktionen` | `promotions`, `inbox`, `publishing`, `telegram` | `lite`, `legal`, `product_edit` (только из акции, §2.3) | `aktionen` (есть) | нет |
| **Eintrag** | `eintrag` | как Aktionen | + `site_import` + `catalog_admin` (импортированные позиции, без CSV) | `eintrag` (есть) | нет, позиции ведут на сайт владельца |
| **Website-Vitrine** | `website` | + `reviews`, `crm`, `blog`, `jobs`, `analytics`; `booking`/`stays`/`events` **как контент** | всё, кроме `stock`, `finance_*`; `sales_board` — заявки и резервы | **новый `vitrine`** | никогда (гейт закрыт навсегда, §5) |
| **Laden** | `laden` | все подходящие направлению (`recommended_for` ∪ выбор владельца) | все; `stock`/`finance_erp` — Profi (§2.4) | обычная витрина | да, после гейта |

**Одно правило доступа:** открыто = входит в пакет ∩ не выключено владельцем (`disabled_modules`) ∩
подходит по типу бизнеса (X4) ∩ роль (owner-only, W9-10).

### 2.3. Core-модуль `catalog` в «Aktionen»

Акция с ценой сама создаёт товар (`attach_product`, T-8.23d); форма товара открывается из «Bearbeiten»
акции. Решение:
- **раздела каталога нет**: «Angebot» (`sellable-manage`) уходит из меню; закрыты `catalog_admin`,
  коллекции, наборы, CSV-импорт, склад;
- **карточку товара править можно, но только из акции** (`product_edit` в белом списке);
  `catalog:product-create` закрыт — товар появляется только из формы акции;
- данные не теряются: на ступени выше те же товары сразу видны в «Sortiment».
Расходится с макетом T-8.31 (там «Angebot» есть) → вопрос **В-1**.

### 2.4. Планы и лимиты (цены скрыты, пока `PRICING_PUBLIC=False`)

| План | Кому | Активных акций | Товаров | Импорт с сайта | ИИ-действий/мес | Profi |
|---|---|---|---|---|---|---|
| `test` | все сейчас | 5 | 50 | 50 | ~20 (значение — владелец) | см. В-3 |
| `basis` | после теста; сейчас — `subscription_status="active"` | ∞ | ∞ | ∞ | N (пусто) | нет |
| `profi_lager` | дополнение | — | — | — | — | `stock` |
| `profi_finanzen` | дополнение | — | — | — | — | `finance_erp` |
| `ai_pack` | дополнение | — | — | — | +N | — |

- Пока `PRICING_PUBLIC=False`: нет цен, названий планов, кнопок «Kaufen/Upgrade», checkout подписки;
  «Abo & Rechnung» виден, только если подписка уже есть (`stripe_customer_id`).
- Лимиты читают план; нынешние env (`LITE_FREE_ACTIVE_PROMOS` base.py:687, `IMPORT_FREE_ITEMS` :744,
  `AI_TENANT_DAILY_*` :772) становятся значениями плана `test` по умолчанию.
- Демо (`is_demo`) лимитов не получают (как `limits.active_limit`).
- `plans.ALL_MODULES` с несуществующим `"aggregator"` (`billing/plans.py:10`) заменяется реестром планов.

## 3. Состав экранов по пакетам

Aktionen и Eintrag — плоское своё меню (`lite_cabinet.sidebar_items`; мораторий X7 на якоря полного
кабинета не затрагивается). Website и Laden — 6 якорей W8 с подменю (состав якорей заморожен замком
`test_sidebar_anchor_composition_is_frozen`; пакет только скрывает якоря, новых не добавляет).

### 3.1. Aktionen

Первые четыре пункта — мобильный таб-бар (рынок: Google BP — 3 кнопки, TGTG — 3–4).

| Пункт | url_name | Внутри | Сейчас |
|---|---|---|---|
| 🏠 Start | `dashboard` → `lite_home` | «требует действия» (отложено к выдаче, новые сообщения), цифры недели, «Mehr verkaufen» | есть |
| 📣 Aktionen | `promotions:promotion-list` | quick/create/edit/preview/quick-done/flyer/shop-poster/transition/text-check/quick-ai/today-dismiss/image-* | есть |
| 💬 Kunden & Nachrichten | **`inbox:list`** | `inbox:thread`, poll, typing, reply-draft, unread-count; отклики: `promotions:reservation-list`, `promotions:redeem*`, `reservation-action` | **нет** (дыра KA-0 §5) |
| 👁 Sichtbar | `lite-visibility` | `lite-share`, привязка общего бота и уведомлений, свой бот (T-8.29), каналы + GBP (owner) — карточками | есть |
| 🏪 Geschäft | `lite-business` | **+ часы работы** (сейчас только name/address/phone/whatsapp, `lite_cabinet.py:81`); **Recht** → `legal-docs` | часы и Recht — **нет** |

Из меню уходят «Angebot» (§2.3) и «Teilen» отдельным пунктом (часть «Sichtbar»; адрес остаётся).

**Закрыто по прямому адресу** (страница «nicht enthalten», §4.3): `blog-*`, `publishing-posts`,
`promotions:newsletter`, `coupon-campaigns`, `promo-type-*`, `analytics`, `crm:*`, `reviews:*`,
`loyalty`/`vouchers`/`voucher-redeem`, `orders:*`, `booking:*`, `stays:*`, `events:*`, `jobs:*`,
`verkaeufe*`, `board*`, `ablaeufe`, `status-*`, `deal-*`, `payments-page`, `finance:*`, вся `studio`,
`catalog_admin`, `catalog:product-create`, `imports:*`, склад, закупки, коллекции, полная форма
`settings`, `languages`, `payment-settings`, `integrations-home`, `extras`, `modules`, `finder-settings`,
`team`, `einstellungen-home`, `portal-stats` (блоком на `lite-visibility`), `billing*` без подписки.

**Mini App:** `TG_LITE_VIEWS` ∩ белый список пакета + **новый inbox-набор**. `legal-docs` в Telegram не
открываем (решение T-8.30 Р-2), с «Geschäft» — «im Browser öffnen». `promotions:voucher-redeem`
убирается из набора Aktionen (ваучеры loyalty/gift не входят; купоны T-8.3 гасятся через `redeem`).

**Ctrl+K:** только белый список пакета (сейчас лёгкому бизнесу видно 51 запись, KA-0 §5); поиск по
данным — сообщения и акции.

**Витрина** (`aktionen`): главная-визитка, `/aktionen/`, страница акции (reserve, coupon, waitlist,
confirmation, QR), сообщения, Impressum/Datenschutz/Widerruf, Merkzettel. Каталог/корзина/наборы
скрыты (`redirect_if_aktionen`); `/termin/`, `/unterkunft/`, `/veranstaltung/`, `/blog/`, `/gutschein/`,
`/konto/`, `/anfrage/` — потолком модулей (404).

**Отклик «Anfragen»** сейчас требует `jobs` (`response.py:52`), которого в пакете нет → предлагаем
заявку по акции в `storefront-message` с темой и ссылкой на акцию (тред inbox) — вопрос **В-2**.

### 3.2. Eintrag

Меню = Aktionen + 📥 **Website-Import** (`imports:website`, owner-only; уже в `EINTRAG_NAV`) +
📦 **Einträge** (`sellable-manage` в режиме «позиции из импорта»: видимость в каталоге города,
`external_url`, правка через `product_edit`). Без создания товара с нуля и CSV-импорта.
Mini App: как Aktionen + `sellable-manage`, `sellable-visibility`, `sortiment-view`; импорт — нет.

### 3.3. Website-Vitrine

| Якорь | Подпункты |
|---|---|
| Übersicht | `dashboard` (заявки, сообщения, резервы) |
| Verkäufe | если активен `jobs` или есть резервы: `verkaeufe?tab=job`, `?tab=reservation`, `?tab=kunden`; без `payments-page`, `orders:*`, `finance:*` |
| Sortiment | `sellable-manage`, категории, коллекции, наборы, `imports:start`, `imports:website`; по направлению-контенту `booking:services`, `stays:units`, `events:list`/`tour-list`; без склада/закупок |
| Marketing | `marketing-home`, акции, `inbox:list`, `reviews:list`, `crm:customer-list`, `redeem`, `blog-list`, `newsletter`, `publishing-posts`, `portal-stats` |
| Website | `site-home` (Studio), `design`, `site-seo`, `domains`, `media-library` |
| Einstellungen | `einstellungen-home`, `settings`, `languages`, `legal-docs`, `notifications-settings`, `integrations-home`, `team`, `support:help`, `modules`; без `payment-settings`, `extras`, `billing` (без подписки) |

Витрина `vitrine`: каталог, услуги, номера, события видны; кнопки покупки/брони заменены на
«Anfragen / Nachricht / Anrufen».

### 3.4. Laden — общие якоря и подменю по направлениям

Базово: **Verkäufe** `verkaeufe`, `?tab=kunden`, `payments-page`, `ablaeufe?from=board` · **Sortiment**
`sellable-manage`, категории, коллекции, наборы, `imports:start` · **Marketing** как Website +
`coupon-campaigns`, `promo-type-list`, ваучеры/лояльность (если loyalty), резервы вкладкой (D8) ·
**Website** как Website · **Einstellungen** как Website + `payment-settings`, `extras`, `billing`.

| Направление | Verkäufe + | Sortiment + | Только Profi |
|---|---|---|---|
| **Waren** (`orders`) | `orders:deliveries`, `orders:kitchen` (KITCHEN_TYPES), `orders:table-qr` (TABLE_TYPES) | — | Lager: `stock`, `purchasing` |
| **Termine** (`booking`) | `booking:resources`, `booking:availability` | `booking:services`, `booking:passes` | — |
| **Zimmer** (`stays`) | `stays:checkins`, `stays:reports`, `stays:channels` | `stays:units` | — |
| **Tickets** (`events`) | `verkaeufe?tab=ticket`, `events:checkin` | `events:list`, `tour-list`, `teacher-list` | — |
| **Anfragen** (`jobs`) | `verkaeufe?tab=job`, `jobs:new` | — | — |
| все | `finance:invoices` (basis: есть счета или способ «invoice») | — | Finanzen: `journal`, `expenses`, `ergebnis`, `offene`, `bank` |

Мобильный таб-бар Laden (KA-2): Übersicht · Verkäufe · ＋ · Nachrichten · Mehr — детально в KA-4.
Mini App Laden: нынешний `TG_LITE_VIEWS` + inbox-набор.

## 4. Как устроен доступ в коде (без кода)

### 4.1. `apps/core/packages.py` — единственная точка истины
- `PACKAGES` (`Package(key, label, modules, features, profile, lite, url_allow|None)`; `url_allow` —
  только у лёгких пакетов, по умолчанию закрыто, как `TG_LITE_VIEWS`), `PLANS` (`Plan(key, limits, features, price=None)`).
- `package_of(tenant)`: `site_config["package"]`; без ключа — вывод: профиль `aktionen` → `aktionen`,
  `eintrag` → `eintrag`, иначе `laden`. Без миграции.
- `plan_of(tenant)`: `subscription_status=="active"` → `basis`, иначе `test`; дополнения — `site_config["addons"]`.
- `module_allowed(tenant, key)`, `view_allowed(tenant, url_name, user=None)`, `limit(tenant, name)`,
  `profile_for(tenant)`.

### 4.2. Кто её вызывает

| Место | Изменение |
|---|---|
| `modules.is_module_active` (`modules.py:549`) | `and packages.module_allowed(...)` для не-core → пакет сам доходит до сайдбара, палитры, `storefront_archetypes`, `ModuleGatingMiddleware`, hero-плиток, `can_buy/can_inquire`, уведомлений |
| новый `PackageScopeMiddleware.process_view` (после `TelegramLiteScopeMiddleware`) | кабинетные префиксы → `view_allowed(url_name)`, отказ — §4.3 |
| `modules.sidebar_nav` / `lite_cabinet.sidebar_items` | «лёгкий» решается по `package.lite`, дети через `view_allowed` |
| `templatetags/cabinet.nav_palette` (:75) | + `view_allowed`; `palette-search` — только открытые виды |
| `TelegramLiteScopeMiddleware` | `TG_LITE_VIEWS ∩ view_allowed` |
| плитки главной | `view_allowed` |
| `storefront_profile` | читает `packages.profile_for`; новый профиль `vitrine` (`STOREFRONT_PROFILES` + normalize) |
| `promotions.limits`, `imports/site/apply.py`, `apps/ai/budget.py`, создание товара | `packages.limit(...)` |

`site_config["package"]`/`["addons"]` обязаны пережить `siteconfig.normalize` и все Save'ы (класс W0/W6);
ключи presence-minimal, golden не меняются.

### 4.3. Закрытый адрес

| Случай | Ответ |
|---|---|
| модуль выключен владельцем | 404, как сейчас |
| кабинетный экран вне пакета, GET | **403-страница «In Ihrem Paket nicht enthalten»**: что входит, «Zurück», «Mehr Funktionen» → «Laden eröffnen»; без цен |
| то же, POST/fetch | 403 JSON (как `tg-lite-info`) |
| витринный адрес вне пакета | 404 или 302 на главную; покупатель слов о пакетах не видит |

### 4.4. Совместимость с живыми бизнесами
- Без записи пакета: `aktionen`/`eintrag` по профилю, иначе `laden` с потолком «все модули» — для
  Laden ничего не меняется (замок паритета §8).
- `disabled_modules` при смене пакета не переписываются: пакет — потолок поверх выбора владельца.
- До деплоя T-8.32b — `manage.py package_report`: какие лёгкие бизнесы потеряют доступ к модулям, где у
  них ЕСТЬ данные (Job, Order, BlogPost…); решение по каждому — у владельца.
- [доп.] проверить, не уходят ли сейчас в каталог города товары, созданные из акций у Aktionen.

## 5. Гейт готовности к продаже (жёсткий, Р-4)

### 5.1. `apps/core/readiness.py`
`Check(key, label, directions, test(tenant), fix_url)`, `missing(tenant, direction)`,
`can_sell(tenant, direction)` (у aktionen/eintrag/website — всегда False). Один реестр питает экран
«Laden eröffnen», гейт точек продажи и чек-лист главной.

| Проверка | Направления | Как |
|---|---|---|
| Impressum: имя, адрес, e-mail, телефон | все | `name`, `address`, `public_email`, `public_phone` (§5 DDG) |
| Налоговый статус | все | `vat_id` ∨ `tax_number` ∨ `small_business` |
| Ответственный | все | `legal_responsible`; `register_entry` — подсказка [доп.: поля «Rechtsform» нет] |
| Datenschutz | все | генерируется с фолбэком — ✓ |
| **AGB** | Laden с онлайн-оплатой; у Termine «только на месте» — подсказка | `LegalDoc(kind="agb", text≠"")`; слабая `_has_legal_doc` (`onboarding.py:71`, «любой документ») заменяется проверкой по виду |
| Widerruf | Waren с доставкой | `delivery_enabled` → Widerruf (`LegalDoc` или генерированный); исключения § 312g |
| ≥1 способ оплаты | все | `core/payment_methods.available(...)` |
| ≥1 активный товар с ценой | Waren | `Product.is_active`, `base_price>0` |
| Grundpreis у весовых | Waren | `unit` задан, `content_amount` пуст → ✗ (PAngV) |
| способ получения | Waren | самовывоз или `delivery_enabled` с ценой/зоной |
| аллергены | Waren ∩ FOOD | подсказка, не гейт [доп.] |
| ≥1 услуга + часы | Termine | `Service.is_active`; `opening_hours_structured` или ресурсы |
| ≥1 номер, правила отмены | Zimmer | `StayUnit.is_active`, `price_cents`; `cancellation`/`free_cancel_days` |
| ≥1 событие, правила отмены | Tickets | `Event` с `capacity`, `price_cents`; `cancellation` |
| налоговый статус | Anfragen | для сметы с НДС |

### 5.2. Где гейт действует
`storefront-checkout` (+ кнопка корзины), `storefront-promo-kaufen`, `storefront-termin-book`,
`storefront-service-book`, `storefront-karte-kaufen`, `storefront-unterkunft-book`, `storefront-event-book`,
`storefront-gutschein-buy`, принятие `storefront-offer` и `storefront-angebot`.
**Не действует:** Zurücklegen, Coupon holen, waitlist, сообщение, `/anfrage/`, сделки из кабинета.
Покупатель видит «Online-Bestellung ist bald möglich» + «Nachricht / Anrufen», без названия пункта.
Демо гейт не проходят [предложение: в кабинете демо — полоса «würde geschlossen sein»].

### 5.3. Экран «Laden eröffnen» (T-8.32c)
`/dashboard/laden-eroeffnen/` (owner-only, запись в `nav_registry`, вход из «Mehr verkaufen»):
направления чипами (предвыбор по типу) → чек-лист ✓/✗ с кнопкой в `fix_url` → «Laden eröffnen»
(пакет можно включить и раньше — продажа останется закрытой гейтом).

## 6. Переходы и лимиты

| Переход | Что делаем | Данные |
|---|---|---|
| Aktionen → Eintrag | `package=eintrag`, профиль `eintrag` | сохраняются |
| Aktionen/Eintrag → Website | `package=website`, профиль `vitrine` | товары из акций видны в Sortiment |
| → Laden | `package=laden`, профиль снят, `enable_module` для направлений; продажа — после гейта | сохраняются |
| Laden → Website/Aktionen | только если нет незакрытых сделок (будущие брони/номера/билеты, неоплаченные или неисполненные заказы), иначе список «Erst abschließen» | ничего не удаляется |
| Website → Aktionen | профиль `aktionen`, Studio-настройки остаются в `site_config` | сохраняются |

Одна функция `packages.switch(tenant, to, *, directions=())` — точечная запись под `select_for_update`
(как `enable_module`), событие «package_changed» в аудит. Вход наверх — «Mehr verkaufen» на Start, на
странице лимита и в Telegram вместо письма на `kontakt@` (`limits.limit_message`).

**Лимиты при `PRICING_PUBLIC=False`:** «Im Testbetrieb sind bis zu %(n)s Aktionen gleichzeitig aktiv.»
(так же для товаров и ИИ), без «kostenlos», цен и кнопок покупки; статус в настройках — «Testbetrieb»
без даты. Лимит товаров — только на СОЗДАНИЕ (существующие не скрываются; товары из акций в счёт идут,
но акцию не блокируют). Проверить `/fuer-unternehmen/` (`portal_views.py:633`) на упоминание цен (KA-9).

## 7. Дубли, которые касаются меню пакетов (KA-0 §3)

| # | В KA-3 / T-8.32 | Остальное — KA-4 |
|---|---|---|
| D5 подключения ×5 | Aktionen/Eintrag — одна «Sichtbar»; `integrations-home` с Website | «Verbindungen» для полного кабинета |
| D7 погашение ×2 | Aktionen — только `promotions:redeem` | автоопределение кода |
| D8 резервы | Aktionen — экран; Website/Laden — вкладка | — |
| D10 Geschäft ↔ Mein Geschäft | `lite-business` += часы; одна форма-источник полей | — |
| D11 статистика видимости | Aktionen — блок на `lite-visibility` | свод для Laden |
| D6 исходящий контент | вне Aktionen/Eintrag | «Kommunikation» для Laden |
| D12 хаб `catalog` | Sortiment-подменю по направлению из хаба `sellables` | удаление хаба `catalog` |
| D4 оплата ×3 | `payment-settings` только в Laden | слияние `billing-payments` |

D1, D2, D3, D9 — в KA-4.

## 8. Инкременты реализации

Порядок: planner → замки до кода → django-reviewer + security-reviewer → зелёный CI → FF в main.
**Миграций не ожидается** (`site_config["package"]`, `["addons"]`, профиль `vitrine`).

| ID | Что | Замки ДО кода | Риск |
|---|---|---|---|
| **T-8.32a** | `packages.py` (пакеты, планы, `package_of`, `plan_of`, `limit`), `PRICING_PUBLIC`, лимиты читают план, `plans.py` без `aggregator`, normalize хранит ключи | вывод пакета (3 случая); **паритет Laden**: `sidebar_nav` и палитра 16 типов байт-в-байт; лимиты = env; normalize/Save не роняют `package` | низкий |
| **T-8.32b** | честный доступ Aktionen/Eintrag: потолок в `is_module_active`, `PackageScopeMiddleware`, страница «nicht enthalten», меню (Kunden & Nachrichten, Recht, часы), Mini App + inbox, палитра, Anfragen → inbox (В-2), `package_report` | обход резолвера: вне белого списка → 403-страница, внутри → 200; пункты меню reverse'ятся и открыты; палитра ⊆ списка; TG ⊆ пакета; `/blog/`, `/termin/` → 404; owner-only цел | **средний** → отчёт до деплоя |
| **T-8.32c** | `readiness.py` + «Laden eröffnen» + гейт в 10 точках, проверка документов по виду | каждая точка продажи отказывает при ✗ и пропускает при ✓; Zurücklegen/Coupon/Nachricht/Anfrage не гейтятся; Website `can_sell`=False | **высокий** для живых Laden без AGB → В-5 |
| **T-8.32d** | `packages.switch` вверх/вниз, запрет спуска при открытых сделках, «Mehr verkaufen» (веб + Telegram) | туда-обратно не меняет `disabled_modules` и данные; спуск блокируется будущей бронью | средний |
| **T-8.32e** | пакет Website (профиль `vitrine`), области Profi с разделением `finance_basic`, видимость `billing` | Laden без Profi: `invoice-pdf` и счёт из сделки работают, `finance:journal` → 403; `vitrine`: все кнопки покупки заменены | средний (GoBD) |

Общие риски: `is_module_active` зовут и Celery/beat (для Laden поведение прежнее); демо — потолок
применяется, гейт и лимиты нет; новые экраны (`laden-eroeffnen`, «nicht enthalten») — по чек-листу
`docs/cabinet-screen-dod.md`, якоря не добавляются (мораторий X7).

## 9. Вопросы владельцу

| № | Вопрос | Рекомендация |
|---|---|---|
| **В-1** | В макете T-8.31 у Aktionen есть «Angebot», а решение §8 — «без каталога». Что оставляем? | Убрать «Angebot» из меню Aktionen; товар правится только из акции; «Angebot» появляется с Eintrag |
| **В-2** | Отклик «Anfragen» в Aktionen: через `jobs` (сметы, доска) или через чат `inbox`? | Через **inbox**: тред с темой и ссылкой на акцию; `jobs` — с Website/Laden; до деплоя — отчёт о лёгких бизнесах, у которых уже есть заявки |
| **В-3** | Profi (склад, ERP-финансы) во время теста: открыты для Laden или закрыты? | **Открыты, пока `PRICING_PUBLIC=False`**; закрываются одним переключателем при объявлении тарифов, данные сохраняются |
| **В-4** | Лимиты теста (5 акций, 50 товаров) — на всех без подписки или только на лёгких? | **На всех без подписки, кроме демо**; ограничивается только создание нового |
| **В-5** | Жёсткий гейт для уже продающих: сразу или с переходным периодом? | Отчёт `readiness_report` → 14 дней полосы «Ihr Shop schließt am …, fehlt: AGB» → гейт; для новых — сразу |
| **В-6** | Website-Vitrine: услуги, номера, события с «Anfragen» вместо брони (модули как контент)? | **Да** — подъём на Laden тогда = включение продажи, а не перенос данных |
