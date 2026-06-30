# A1/A2 Retail (Online-Shop + Click&Collect/Versand) — рынок ↔ функционал — 2026-06-30

> **Шаг 1** серии «детальная проверка архетипов» (порядок: A1/A2 → по номерам).
> Метод: воркфлоу из 16 агентов — (код-инвентарь + бенчмарк DACH-рынка + сверка
> отчёта 2026-06-25/демо) → синтез → **адверсариальная проверка 12 гэпов**
> (9 CONFIRMED_MISSING, 3 PARTIAL, 0 ложных). Все факты — `файл:строка`.
> Серия/хронология — `docs/market-gap-audit-2026-06-30-index.md`.
> Предыдущий срез — `docs/market-analysis/a1a2-retail-online-shop.md` (2026-06-25, снапшот).

## 0. Вывод одной фразой

Движок ритейла **production-grade и закрывает «оффлайн-first» базу лучше Shopify**
(Click&Collect + точки выдачи, PLZ-зоны, PAngV-Grundpreis, anti-oversell, отзывы
с верификацией покупателя, Google-фид, полный Widerruf-flow с авто-возвратом). Но
**самые болезненные дыры — коммерческо-правовые, а не структурные:** платёжный микс
DACH (нет PayPal и Klarna «Kauf auf Rechnung») + три дешёвых, но обязательных
комплаенс-пункта (кнопка §312j, нота PAngV «inkl. MwSt./Lieferzeit», AGB/Versand&
Zahlung). Плюс отстаём от Shopware/JTL в слое discovery (нет поиска, тонкие фасеты,
одноосевые варианты).

## 1. Структура сайта (карта страниц)

| Страница | Статус | Маршрут / шаблон | Заметка |
|---|:--:|---|---|
| Главная | ✅ | `/` `storefront-home` · `home.html` | секционный билдер, archetype-aware |
| Каталог/листинг | 🟡 | `/sortiment/` `storefront-products` · `products.html` | категории+подкатегории+диет-фасет+пагинация. **Нет:** поиск, фасеты цена/бренд/наличие, контрол сортировки |
| Деталь товара | ✅ | `/sortiment/<pk>/` `storefront-product` · `product_detail.html` | галерея+лайтбокс, варианты, Grundpreis, модификаторы, аллергены, отзывы, related, buybar. **Нет:** Product JSON-LD/Breadcrumb, Lieferzeit |
| Корзина | ✅ | `/warenkorb/` `storefront-cart` · `cart.html` | позиции, pickup/delivery, адрес, точка выдачи, промокод, апселл |
| Checkout | 🟡 | `/warenkorb/bestellen/` (POST, инлайн в корзине) | honeypot+rate-limit, мин.заказ+зоны, опц. Stripe. **Нет:** выбор способа оплаты; кнопка `Place order` вместо `Zahlungspflichtig bestellen` (§312j) |
| Подтверждение заказа | ✅ | `/bestellung/<code>/` `storefront-order` | по коду без входа |
| ЛК клиента | ✅ | `/konto/` `account-home` | magic-link, история заказов + reorder, GDPR экспорт/удаление |
| Impressum | ✅ | `/impressum/` · авто из полей Tenant | |
| Datenschutz | ✅ | `/datenschutz/` · авто-шаблон DSGVO | placeholder, если поле пустое |
| Widerruf + форма | ✅ | `/widerruf/` + `/widerruf-formular/` | Widerrufsbelehrung für Waren при доставке |
| **AGB** | ❌ | — | нет маршрута/поля/шаблона |
| **Versand & Zahlung** | ❌ | — | нет страницы; платёжные/доставочные условия только инлайн в корзине |
| **Merkzettel/Wishlist** | ❌ | — | избранное есть только в агрегаторе (бизнесы), не товары |
| Combos/Menüs | ✅ | `/kombi/` `storefront-combos` | скорее A4, общая корзина (аналог подарочных наборов) |

## 2. Что УЖЕ есть (сильные стороны — паритет/выше рынка)

Варианты (одноосевые) с пер-вариантным остатком/Grundpreis/GTIN · **PAngV-Grundpreis**
(€/кг·л, авто на карточке и детали) · **anti-oversell** (atomic `select_for_update`) ·
галерея+лайтбокс · категории+подкатегории · корзина (session, без аккаунта) ·
**Click&Collect + неск. точек выдачи** · **доставка с PLZ-зонами** (fee/free-from/min) ·
Stripe-Connect предоплата (карты + 3DS) · гостевой checkout · **отзывы о товаре с
верификацией покупателя** · ваучеры/промокоды · лояльность · **Google/Meta product feed**
(пер-вариант `item_group_id`) · **Widerruf-flow + авто-возврат** · ЛК + reorder ·
mobile-first (HTMX/Alpine/Tailwind) · HTTPS (Caddy).

## 3. Матрица «рынок ↔ наш статус»

Важность: **must** обязательно для DACH-шопа · should · nice.
Статус: ✅ have · 🟡 partial · ❌ missing.

| Фича рынка | Важн. | Наш статус | Заметка по гэпу |
|---|:--:|:--:|---|
| Варианты с пер-вар. остатком/ценой/SKU/фото | must | 🟡 | одноосевые (нет color×size), нет пер-вар. фото — дыра для Boutique |
| Фасеты (цена/цвет/размер/бренд/Bio/наличие) | must | 🟡 | только категория + диет-фасет; нет сортировки для юзера |
| Поиск по витрине + autosuggest | should | ❌ | **поиска на витрине нет вообще** (есть только в кабинете/агрегаторе) |
| Галерея с зумом/лайтбокс | must | ✅ | закрыто с 2026-06-25 |
| Wishlist/Merkzettel | should | ❌ | избранное только у бизнесов в агрегаторе |
| Cross-sell/«Passt dazu» | should | ✅ | по категории + апселл в корзине |
| Остаток + **Lieferzeit** на товаре | must | 🟡 | остаток есть; **Lieferzeit-поля нет** (только демо-текст) — abmahnsicher-норма |
| **Grundpreis (PAngV)** | must | ✅ | авто; единств. пробел — не импортируется CSV |
| **PayPal** | must | ❌ | **нет** — #1 способ DACH, жёсткий конверсионный блокер |
| **Klarna Kauf auf Rechnung / Ratenkauf** | must | ❌ | **нет** — самый востребованный способ DACH |
| SEPA-Lastschrift | should | 🟡 | возможно через Stripe, но не выбирается явно |
| Карта (Visa/MC) + 3DS | must | ✅ | Stripe Checkout |
| Vorkasse/Überweisung | should | ❌ | нет ручного банк-перевода |
| Apple/Google Pay | should | 🟡 | вероятно через Stripe, не подтверждено/не настроено |
| Гостевой checkout | must | ✅ | соответствует DSGVO-минимизации |
| Versandkostenrechner (вес/зона) | must | 🟡 | только зоны/флэт; нет веса/тарифа перевозчика; нет отдельной страницы |
| **DHL/Hermes API** (тариф/лейбл/трекинг) | must | 🟡 | `tracking_code` вводится вручную; нет API/лейбла |
| Click&Collect | should | ✅ | сила платформы (неск. точек) |
| Versandkostenfrei ab X € + прогресс | should | 🟡 | порог есть, нет «Noch X € bis…» в корзине |
| **Отзывы о товаре** | must | ✅ | верифиц. покупатель (Omnibus/UWG) |
| Trusted Shops Gütesiegel/Käuferschutz | should | ❌ | только текстовые USP-чипы |
| Платёжные/доставочные бейджи (лого) | should | 🟡 | USP-чипы есть, лого-бейджей нет |
| **Impressum §5 DDG** | must | ✅ | авто |
| **Datenschutz + cookie-consent (TTDSG)** | must | ✅ | без трекинг-куки → баннер не нужен |
| **AGB** | must | ❌ | **нет** |
| **Widerrufsbelehrung + Muster-Formular** | must | ✅ | + авто-возврат |
| **Versand & Zahlung** страница | must | ❌ | **нет** |
| **Кнопка «Zahlungspflichtig bestellen» (§312j)** | must | ❌ | сейчас `Place order` — риск необяз. договора + Abmahnung |
| ЛК (история/адреса/reorder) | should | ✅ | без адресной книги, но достаточно |
| Возвраты/RMA (лейбл, портал статуса) | should | 🟡 | юр. Widerruf+возврат есть; нет self-service RMA |
| Newsletter Double-Opt-In (UWG §7) | must | ✅ | конвенция платформы |
| Gutscheine/Geschenkgutscheine | should | ✅ | промокоды; ритейл-gift-card точечно |
| Google Shopping feed | should | ✅ | есть |
| Mobile-first / CWV | must | ✅ | архитектурно |
| Брутто-цены «inkl. MwSt., zzgl. Versand» (PAngV) | must | 🟡 | **нет ноты на товаре/в корзине** (есть только у отеля) |
| Подтверждение заказа e-mail + статусы | must | ✅ | + трекинг в письме |
| Bundles/Staffelpreise/мультипаки | nice | 🟡 | Combos + pack-варианты; нет тиров кол-ва |
| Altersnachweis (алкоголь, JuSchG) | should | ❌ | нет age-gate (must для Feinkost с алкоголем) |
| Мультиязык/мультивалюта (EN/CHF) | nice | 🟡 | UI переводим, мультивалюты/CHF нет |

## 4. Недостающий функционал — приоритизировано (верифицировано)

Размер S/M/L. Вердикт — из адверсариальной проверки против кода.

### 4a. Правовое/комплаенс (DACH MUST — риск Abmahnung, дёшево закрыть)
| # | Что | Вердикт | Размер |
|---|---|:--:|:--:|
| R1 | **Кнопка «Zahlungspflichtig bestellen» (§312j BGB)** — сейчас `Place order` (`cart.html:161`) | CONFIRMED_MISSING | **S** |
| R2 | **Нота PAngV «inkl. MwSt., zzgl. Versand»** на товаре/в корзине + **Lieferzeit** на товаре | CONFIRMED_MISSING | **S** |
| R3 | **AGB** (поле `Tenant.agb` + `/agb/` + автошаблон + футер/чекаут) + **Versand & Zahlung** страница | CONFIRMED_MISSING | **M** |

### 4b. Платежи (DACH MUST — конверсия)
| # | Что | Вердикт | Размер |
|---|---|:--:|:--:|
| P1 | **Платёжный микс**: PayPal + Klarna «Kauf auf Rechnung» (+ Vorkasse); поле `Order.payment_method` (сейчас только `payment_state`) | CONFIRMED_MISSING | **L** |
| P2 | Явный выбор/настройка SEPA + Apple/Google Pay (через Stripe) + лого-бейджи | PARTIAL | S |

### 4c. Discovery / конверсия
| # | Что | Вердикт | Размер |
|---|---|:--:|:--:|
| D1 | **Поиск по витрине** `?q=` + autosuggest (сейчас нет вообще) | CONFIRMED_MISSING | **M** |
| D2 | **Фасеты**: цена, Bio/Regional/Herkunft, наличие, бренд, рейтинг + контрол сортировки | PARTIAL | M |
| D3 | **Multi-axis варианты** (color×size) + пер-вариантное фото (для Boutique) | CONFIRMED_MISSING | L |
| D4 | Wishlist/Merkzettel (cookie или аккаунт) | CONFIRMED_MISSING | M |
| D5 | Versandkostenfrei-прогресс «Noch X € bis…» в корзине | (из матрицы) | S |

### 4d. Данные / интеграции / SEO
| # | Что | Вердикт | Размер |
|---|---|:--:|:--:|
| I1 | **Полный CSV-импорт родительского товара**: gtin, unit, content_amount (Grundpreis), images, badge, allergens, diets, is_featured + авто-создание категорий | CONFIRMED_MISSING | M |
| I2 | **DHL/Hermes API**: расчёт тарифа + лейбл + авто-Sendungsverfolgung + весовой Versandkostenrechner | PARTIAL | L |
| I3 | **Product JSON-LD (schema.org Product/Offer) + BreadcrumbList** на детали (сейчас только у промо/агрегатора) | CONFIRMED_MISSING | S |

### 4e. Trust / нишевое
| # | Что | Вердикт | Размер |
|---|---|:--:|:--:|
| T1 | Хук **Trusted Shops** Gütesiegel/Käuferschutz + реальные лого-бейджи | (из матрицы) | S |
| T2 | **Altersnachweis** (алкоголь, JuSchG) — вертикаль Feinkost | (из матрицы) | M |
| T3 | Возвраты/RMA self-service: return-label + портал статуса | PARTIAL | M |

## 5. Сравнение с лидерами

Наш ритейл — **достойный «Shopify-Lite для DACH-оффлайна»**: ядро держит немецкую
базу там, где важнее всего для микробизнеса (PAngV-Grundpreis, anti-oversell,
одноосевые варианты, галерея+лайтбокс, **Click&Collect с неск. точками** и
PLZ-зоны — сильнее лёгкого local-pickup у Shopify, верифиц. отзывы, Google-фид,
полный Widerruf+возврат, гостевой checkout). Против **Shopware 6 / JTL** отстаём в
слое discovery/конверсии (нет поиска, тонкие фасеты, только одноосевые варианты, нет
Merkzettel/RMA-портала) — для них это table stakes. Самые опасные гэпы —
**коммерческо-правовые**: платёжный микс (PayPal + Klarna «Kauf auf Rechnung», что
есть у всех лидеров и воспринимается покупателем как обязательное) + три дешёвых
MUST (кнопка §312j, ноты PAngV, AGB/Versand&Zahlung), которые немецкие платформы
делают по умолчанию. Закрыть платежи и эти MUST → платформа переходит из «хороший
движок, рискованно запускать» в защищаемый продукт; мультитенант + Click&Collect +
автогенерация правового — реальный дифференциатор.

## 6. Что устарело в отчёте 2026-06-25 (сверка)

С 2026-06-25 **доехало** (отчёт занижал): отзывы о товаре (`ProductReview`,
верифиц. покупатель), usp_bar/Trust-Leiste, online Widerruf-форма, лайтбокс на
товаре, диет-фасет. **Осталось как было:** платёжный микс (PayPal/Klarna),
Rechtstexte-Wizard/AGB, поиск по витрине, Product JSON-LD/Breadcrumb,
Wishlist, carrier-API. Оценки отчёта (A1 ~85%, A2 ~75%) по этим 5 пунктам — устарели.

## 7. Связанные
`docs/archetype-completeness-audit-2026-06-30.md` (общий аудит) ·
`docs/market-analysis/a1a2-retail-online-shop.md` (снапшот 2026-06-25) ·
`apps/catalog`, `apps/orders`, `apps/promotions`, `apps/imports`, `apps/billing/connect.py`.
