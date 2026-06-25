# Архетип A1/A2 — Retail (Laden) + Online-Shop / Versand · рыночный анализ и gap-analysis

> Назначение: оценить готовность платформы для розничных магазинов DACH (Bäckerei,
> Metzgerei, Hofladen, Boutique, Asia-Markt, Teeladen, Kaffeerösterei, Unverpackt,
> Kiosk/Späti) **и** чистых интернет-магазинов/Versand (Direktvermarkter, Honig/Imkerei,
> Handmade/Etsy-Typ, kleine Manufaktur). Сравнить с тем, что владельцы иначе берут у
> Jimdo / Wix / IONOS / Shopify / Gambio / Shopware / Etsy, и дать конкретный бэклог
> с упором на **«Anti-Bitrix»** — сайт собирается за ≤10 шагов, блочно, «как ребёнок».
>
> Составлено: 2026-06-25. Source of truth по коду — `apps/catalog`, `apps/orders`,
> `apps/promotions`; по плану билдера — `docs/m20-site-builder-plan.md`; по вертикалям —
> `docs/micro-business-verticals.md` (§A1/A2). Стиль — проза RU, домен-термины DE.

---

## Current coverage (что движок уже делает)

Срез сделан чтением кода (не догадки): `apps/catalog/models.py`, `apps/orders/{models,services,views}.py`,
`apps/promotions/models.py`, `templates/storefront/*`, demo-kit `SHOP` («Hofladen Sonnenfeld»)
в `apps/tenants/demo_kits.py`.

### Каталог и товар — **сильная сторона, почти полный**
- **Варианты** (`ProductVariant`): label, price, content_amount, stock_quantity, gtin, sku — каждый вариант со своим остатком/Grundpreis/EAN (R1). FULL.
- **Grundpreis / PAngV** (`Product.unit`, `content_amount`, метод `grundpreis()`): €/kg, €/l, €/100 g — обязательная по закону цена за единицу для весового/жидкого товара (R2). FULL.
- **Остаток + anti-oversell** (`stock_quantity`, `in_stock`, атомарный `select_for_update` + `OutOfStock` в `orders/services.py`): резерв атомарный, `None` = без учёта (R3). FULL.
- **GTIN/EAN**, **SKU**, **Kategorie** (с подкатегориями), **ModifierGroup/Option**, **Combo**-наборы. FULL.
- **Bilder**: FileRef-конверт (url/alt/is_primary/sort_order), `primary_image`. FULL.
- **LMIV**: `allergens` (+ `allergen_labels`), `origin` (Herkunft), `ingredients` (Zutaten) — для еды это закон, не UX (G7). FULL.
- **Badge** (Bio/Neu/Beliebt), `is_featured`, `price_from` («ab X €»), `has_variants`. FULL.

### Заказ / fulfillment — **сильная сторона**
- **Click & Collect** (`FULFILLMENT_PICKUP`, `pickup_slot`, несколько `pickup_points`) + **Versand/Lieferung** (`FULFILLMENT_DELIVERY`, `shipping_address`, `shipping_cents`, `shipped_at`). FULL.
- **PLZ-зоны** (`delivery_zones`, `_zone_for_plz()` — самый длинный префикс выигрывает; fee/free-from/min на зону), **Mindestbestellwert** для Lieferung и Abholung. FULL.
- **FSM статусов** (`OrderSM`: new→confirmed→ready→picked_up/shipped, +cancelled/returned), **Tracking-Nummer** (`tracking_code`) в письме, **Lieferschein-PDF** (`delivery_note_pdf()`) с адрес-лейблом. FULL/частично (лейбл = PDF-самоклейка, не API перевозчика).
- **Онлайн-оплата** (`stripe_payment_intent` через Stripe Connect, `payment_state` unpaid/paid/refunded), **возврат денег** (`_refund_order()` на cancelled/returned). FULL (механика), но см. gaps по способам оплаты.
- **Возврат/Retoure** (`STATUS_RETURNED`) — статус есть, авто-рефанд есть. PARTIAL: нет 14-дневного Widerruf-флоу/кнопки и текстов.

### Акции / удержание
- DISCOUNT (% или price_override + `compare_at_price` durchgestrichen), RESERVATION (anti-oversell, `available_quantity`), **Überraschungstüte** (`is_surprise`, Anti-Food-Waste), **Voucher** (код/max_uses/min_order), **Loyalty** (штампы), `recurrence` (daily/weekly). FULL.

### SEO / каналы
- **Product-Feed** (Google Merchant / Meta RSS, варианты как отдельные item'ы), **sitemap.xml**, **LocalBusiness JSON-LD** на всех страницах. FULL.
- **Product JSON-LD** (schema.org Product+Offer) — есть только для `Promotion`, не для товара каталога. PARTIAL.

### Демо-наполнение
- Кит `SHOP` («Hofladen Sonnenfeld», business_type=retail) демонстрирует R1+R2+R3+A1+PLZ-зоны: товары с вариантами/Grundpreis/остатком/EAN, доставка по PLZ-префиксам (402/40/41), Mindestbestellwert. Это «showcase» уже готового кода (был главный пробел до 2026-06-22, см. `docs/kit-archetype-coverage.md`).

**Грубая оценка готовности движка:** A1 (Laden + C&C) ~85 %, A2 (чистый Versand) ~75 %.
Витрина визуально функциональна, но «средне-добротная»: единый каркас детальной
(`storefront/detail.html`), карточка товара (`_product_card.html`), 2-колоночная корзина
с переключателем Abholung/Lieferung. До уровня современного DACH-шопа не хватает ряда
визуальных и правовых деталей (ниже).

---

## Market benchmark (что предлагают конкуренты и ждут покупатели DACH)

**Чем владелец иначе пользуется:**
- **Jimdo** — макс. 100 товаров, сильный **Rechtstexte-Manager** (авто-Impressum/Widerruf/AGB), KI-ассистент «Dolphin», от ~15 €/мес ([digiads44][1], [freiepresse][6]).
- **Wix** — неогранич. товары, физ./цифровые/абонементы/dropshipping, мощный визуальный редактор, от ~27 €/мес ([wix][2]).
- **IONOS MyWebsite** — лидер по фичам в тесте (91 %), домен+хостинг+SSL+E-Mail в комплекте, «Momentum AI» для быстрого старта ([digiads44][1]).
- **Gambio / Shopware** — немецкие shop-системы: **DSGVO-конформ и Rechtstexte ab Werk**, данные на серверах в DE, профессиональный e-commerce ([fuer-gruender][4]).
- **Etsy** — для Handmade: маркетплейс-трафик, но комиссии и «не свой бренд» (наш anti-marketplace = аргумент).

**Что покупатель DACH ждёт (рынок):**
- **Mobile-first**: >65 % покупок инициируются со смартфона; медленная загрузка и мелкие кнопки = conversion-killer ([spocket][3], [smart-web][5]).
- **Способы оплаты**: PayPal — №1 по доверию; **Kauf auf Rechnung** (BNPL/постоплата) — самый популярный способ (~30 % транзакций); Klarna у молодых. **Минимум один бесплатный способ оплаты обязателен по закону** ([cross-border][7], [frisbii][8]).
- **Trust-Signale**: **Trusted Shops / TÜV-Siegel**, Käuferschutz, логотипы платёжных провайдеров, отзывы — быстрый сигнал «здесь безопасно» ([landmark][9], [eology][10]).
- **Возврат**: **85 % немцев** считают понятную и бесплатную политику возврата решающей при покупке ([kvk][11]).
- **Доставка**: 67 % предпочитают доставку домой, 58 % смотрят на цену доставки, 55 % ждут круглосуточной доступности ([kvk][11]).
- **Фото/контент**: несколько ракурсов, макро, сцены применения, короткие видео; тренд — «естественные», не стерильные кадры ([smart-web][5], [needdesign][12]).

**Правовое (драйверы фич, не опция):**
- **Widerrufsbutton — обязателен с 19.06.2026** (то есть уже в силе на дату этого документа). Двухступенчатый онлайн-флоу отзыва договора + e-mail-подтверждение получения на «dauerhafter Datenträger». Нарушение → Abmahnung и продление срока отзыва до **12 мес + 14 дней**, штрафы до 50 000 € ([e-recht24][13], [verbraucherzentrale][14], [fuer-gruender][15]).
- **Pflichtangaben**: Impressum, Widerrufsbelehrung + Muster-Formular, AGB/Datenschutz, **Versandkosten klar vor Kauf**, **Grundpreis (PAngV)**, итоговая цена с НДС. Ошибки = частые Abmahnungen.

---

## Visual / UX gaps (A) — как витрина выглядит против ожиданий

Каждый пункт: почему важно (рынок), эффорт (S/M/L), частично ли есть.

1. **Галерея товара = мульти-фото + zoom/lightbox** — *S/M, PARTIAL.* Сейчас детальная показывает изображения, но рынок ждёт нескольких ракурсов, макро и лайтбокса; лайтбокс уже есть для номеров отеля (M20U) — переиспользовать на товар. Фото «продают лучше текста» ([smart-web][5]).
2. **Trust-полоса под hero / в футере (платёжные иконки, «Käuferschutz», «Kostenloser Versand ab X €», «Widerruf 14 Tage»)** — *S, ABSENT.* Trust-Siegel и логотипы оплаты — топ-сигнал доверия в DE ([landmark][9]). Сейчас доверие живёт только в `trust`-секции (since/marks), без e-commerce-специфики.
3. **Отзывы о товаре (звёзды на карточке + блок на детальной)** — *M, ABSENT.* Отзывы есть только на уровне бизнеса в агрегаторе (`BusinessReview`), не на товаре. Bewertungen — ключевой trust-фактор ([eology][10]).
4. **Sticky-Warenkorb / счётчик корзины + мини-превью** — *S, PARTIAL.* Есть мобильный buybar на детальной и quick-add на карточке, но нет постоянного видимого индикатора «N im Korb» и быстрого открытия корзины; критично для mobile-first конверсии ([spocket][3]).
5. **Плотность сетки и «состояния»** — *S, PARTIAL.* Сетка 2/3/4 адаптивна, есть empty-state корзины, но нет: empty-state пустой категории/поиска, скелетонов при загрузке, видимого «Nur noch N verfügbar» как осознанного urgency-бейджа на карточке (есть только «sold out» и low-stock-текст на детальной).
6. **Микро-интеракции добавления в корзину** — *S, PARTIAL.* Quick-add есть; не хватает явного тоста/«Flieg-zum-Korb»-анимации и подтверждения, что снижает неуверенность на мобильном.
7. **Hero под Versand-магазин** — *S, PARTIAL.* Hero/слайдер есть (M20U-2), но дефолты заточены под «локальный/гастро»; для чистого Versand нужен hero-пресет с акцентом «Versand deutschlandweit», USP-бар (Versand/Bezahlung/Retoure) сразу под ним.

---

## Technical / functional gaps (B)

1. **Widerrufsbutton + актуальные Rechtstexte (Widerrufsbelehrung + Muster-Formular)** — *M, PARTIAL — 🔴 правовой блокер.* Обязателен с 19.06.2026 ([e-recht24][13], [verbraucherzentrale][14]). Нужен двухступенчатый онлайн-флоу отзыва (старт → подтверждение отдельной кнопкой; поля: имя/идентификация договора/контакт) + e-mail-подтверждение получения + обновлённый текст Widerrufsbelehrung. Сейчас есть только `STATUS_RETURNED` и авто-рефанд — флоу для потребителя и тексты отсутствуют.
2. **Способы оплаты: PayPal + Kauf auf Rechnung/BNPL** — *M/L, PARTIAL.* Stripe Connect готов (карты/SEPA), но рынок требует **PayPal** (№1 доверие) и **Rechnung/Klarna** (~30 % транзакций), плюс **минимум 1 бесплатный способ оплаты обязателен** ([cross-border][7], [frisbii][8]). Реализуемо через Stripe (PayPal/Klarna как payment methods) — приоритетная настройка чек-аута.
3. **Rechtstexte-Generator (Impressum/Datenschutz/AGB/Widerruf авто-заполнение)** — *M, PARTIAL.* Юр-страницы есть как маршруты (`/impressum /datenschutz /widerruf`), но рынок-эталон — Jimdo/Gambio с авто-генератором из данных бизнеса ([digiads44][1], [fuer-gruender][4]). Нужен мастер, заполняющий тексты из полей Tenant (форма права + Versandkosten/Zahlungsarten/Widerrufsfrist).
4. **Versandkosten klar vor Kauf + Versandkostenseite** — *S, PARTIAL.* PLZ-зоны/fee/free-from есть, но нет отдельной страницы «Versand & Zahlung» и явного указания стоимости/срока на детальной товара (Pflichtangabe; частая причина Abmahnung).
5. **Поиск по товарам на витрине + фильтры (Preis/Allergen/Bio/Verfügbarkeit)** — *M, PARTIAL/ABSENT.* Живой поиск есть только в кабинете; на витрине — фильтр по категории + пагинация, но нет строки поиска для покупателя и фасетных фильтров. Для каталога >50 SKU это ожидаемо.
6. **Product JSON-LD + Breadcrumbs на товаре** — *S, PARTIAL.* schema.org Product+Offer есть только для Promotion; на товаре нет (важно для Google Rich Results/Free Listings). BreadcrumbList отсутствует.
7. **Versandlabel через API перевозчика (DHL/Hermes/DPD)** — *L, ABSENT.* Сейчас `tracking_code` вводится вручную + PDF-Lieferschein. Полноценный лейбл/трекинг через API — тяжело, для микробизнеса можно отложить (как в roadmap), но это разрыв против «настоящего» Versand-шопа.
8. **Wishlist/Merkliste на товаре** — *S, ABSENT.* Есть избранное только на listing'и агрегатора, не на товар. Минор, но привычно покупателю.
9. **Low-stock-/Wieder-verfügbar-уведомления** — *S, ABSENT.* Остаток отображается, но нет алерта владельцу «осталось мало» и «benachrichtigen, wenn wieder da» покупателю.
10. **Kündigungsbutton для подписочных товаров** — *S, N/A сейчас.* Если появятся Abo-Produkte (кофе по подписке у Rösterei) — потребуется и Kündigungsbutton. Пока товары разовые → вне периметра, отметить на будущее.

---

## Anti-Bitrix block editor — рекомендации

Принцип (северная звезда): магазин собирается **за ≤10 шагов**, блоками, с
live-preview; владелец **никогда не застревает** — всё, что можно, авто-заполнено
и шаблонизировано. Фундамент уже есть: `Tenant.site_config` (JSON, без новых моделей),
билдер `/dashboard/site/builder/` с drag-drop, inline-правкой, палитрой секций, темой
вживую (`docs/m20-site-builder-plan.md`). Ниже — что добавить именно под retail/Versand.

### Блоки витрины, которых не хватает архетипу (приоритет ↓)
1. **`usp_bar` / Trust-Leiste** *(S, P1)* — горизонтальная полоса под hero: «🚚 Versand ab X €», «↩ 14 Tage Widerruf», «🔒 Sichere Zahlung» + платёжные иконки. Закрывает visual-gap #2 + правовую видимость Versandkosten. Авто-заполняется из `delivery`-конфига и включённых способов оплаты.
2. **`bestseller` / `featured_products`** *(S, P1)* — секция «Beliebt» из `is_featured`/топ-продаж; уже есть `products`-секция, нужен пресет-вариант «избранное, 4 в ряд» с per-page layout (механика layout-движка из M20U уже есть).
3. **`reviews_products`** *(M, P2)* — блок отзывов о товарах (требует фичи B-#3); звёзды на карточке + блок на детальной.
4. **`shipping_payment` (страница «Versand & Zahlung»)** *(S, P1)* — авто-генерируемая из `delivery_zones`/Zahlungsarten страница + пункт меню. Закрывает technical-gap #4.
5. **`legal_wizard` хост** *(M, P1)* — не «секция», а шаг онбординга: мастер Rechtstexte (Impressum/Datenschutz/AGB/Widerruf) с авто-заполнением из полей Tenant. Закрывает B-#1/#3.
6. **`category_tiles`** *(S, P2)* — крупные плитки категорий с фото (Hofladen: Obst&Gemüse / Käse&Wurst / Spezialitäten). Частично есть (подкатегории-карточки) — нужен hero-пресет на главной.
7. **`product_search`-виджет** *(M, P2)* — строка поиска + фасеты в шапке каталога (technical-gap #5).

### Онбординг ≤10 шагов до рабочего шопа (предложение)
1. Выбор архетипа → **«Laden»** или **«Online-Shop / Versand»** (определяет дефолтную раскладку и набор блоков).
2. Базовые данные бизнеса (имя, адрес, логотип, акцент-цвет) — **из этого авто-генерятся Impressum + LocalBusiness JSON-LD**.
3. Импорт товаров: CSV/Excel-мастер (`apps/imports` уже есть) **или** старт с 3–6 товаров-плейсхолдеров из demo-kit `SHOP`, которые владелец правит inline.
4. Способ продажи: Abholung (C&C) и/или Versand → если Versand, мастер PLZ-зон с **разумными дефолтами** (плоский тариф + free-ab + Mindestbestellwert предзаполнены).
5. Оплата: подключить Stripe (Connect OAuth, готов) + чекбоксы PayPal/Rechnung; гарантировать ≥1 бесплатный способ (правовое).
6. **Rechtstexte-Wizard**: один экран, тексты сгенерированы, владелец только подтверждает/правит срок Widerruf и Versandkosten; включается Widerrufsbutton.
7. Hero + USP-bar: пресет под архетип, фото и заголовок правятся на месте (inline уже есть).
8. Trust: вкл. отзывы/Trust-Leiste, при желании — Trusted-Shops-бейдж (вставка ID).
9. Доставка/самовывоз и часы — авто-страница «Versand & Zahlung».
10. **Veröffentlichen**: live-preview → один клик публикации.

### Что шаблонизировать/авто-заполнять (чтобы владелец не застревал)
- **Все Rechtstexte** — из полей Tenant (как Jimdo «Rechtstexte-Manager»): главный конкурентный паритет ([digiads44][1]).
- **PLZ-зоны и Versandkosten** — дефолтный пресет (1 зона, плоский тариф, free-ab 39 €) с подсказками.
- **Grundpreis** — автоматически считается из `unit`+`content_amount` (уже так); в мастере товара только спросить «Gewicht/Inhalt».
- **Alt-тексты/SEO товара** — дефолт из названия; Product JSON-LD — авто (фича B-#6).
- **Демо-данные стираемы** (`metadata={"demo": True}`) — владелец стартует с примеров и заменяет, никогда с пустого экрана.

---

## Prioritized backlog table

| # | Gap (тип) | Почему важно (рынок) | Эффорт | Статус | Приоритет |
|---|---|---|---|---|---|
| 1 | **Widerrufsbutton + Rechtstexte** (B1) | Обязателен с 19.06.2026, Abmahnung + срок до 12 мес ([e-recht24][13]) | M | PARTIAL | 🔴 P0 |
| 2 | **Rechtstexte-Wizard** (B3) авто-Impressum/AGB/Widerruf | Паритет с Jimdo/Gambio, снимает страх старта ([digiads44][1]) | M | PARTIAL | P0 |
| 3 | **PayPal + Kauf auf Rechnung** + ≥1 бесплатный способ (B2) | PayPal №1, Rechnung ~30 %, бесплатный способ обязателен ([cross-border][7]) | M/L | PARTIAL | P1 |
| 4 | **Trust-Leiste / USP-bar** блок + платёжные иконки (A2, блок #1) | Топ-сигнал доверия DE ([landmark][9]) | S | ABSENT | P1 |
| 5 | **Страница «Versand & Zahlung»** + Versandkosten на товаре (B4, блок #4) | Pflichtangabe, частая Abmahnung | S | PARTIAL | P1 |
| 6 | **Галерея товара: мульти-фото + lightbox** (A1) | Фото продают, лайтбокс уже есть у stays ([smart-web][5]) | S/M | PARTIAL | P1 |
| 7 | **Отзывы о товаре** (звёзды + блок) (B/A3, блок #3) | Bewertungen — ключевой trust ([eology][10]) | M | ABSENT | P2 |
| 8 | **Поиск по витрине + фасетные фильтры** (B5, блок #7) | Ожидаемо для каталога >50 SKU ([apiando]) | M | PARTIAL | P2 |
| 9 | **Sticky-Warenkorb + счётчик/тост** (A4/A6) | Mobile-first конверсия ([spocket][3]) | S | PARTIAL | P2 |
| 10 | **Product JSON-LD + Breadcrumbs** (B6) | Google Rich Results / Free Listings | S | PARTIAL | P2 |
| 11 | **Wishlist/Merkliste** (B8) | Привычно покупателю | S | ABSENT | P3 |
| 12 | **Low-stock-Alert + «wieder verfügbar»** (B9) | Удержание + операционка | S | ABSENT | P3 |
| 13 | **Versandlabel через API перевозчика** (B7) | «Настоящий» Versand, но тяжело для микро | L | ABSENT | P3 (отложено) |

Рекомендуемый старт: **#1–#2 (правовой блок) → #3–#5 (доверие/оплата/Versand-видимость)
→ #6 (галерея) → остальное по левериджу.** Большинство — поверх `site_config`/существующих
моделей, без тяжёлого ERP.

---

### Источники
[1]: https://www.digiads44.de/website/baukasten-vergleich/ "Baukasten-Vergleich 2026 — IONOS/Wix/Jimdo"
[2]: https://de.wix.com/blog/beitrag/bester-onlineshop-website-baukasten "Wix — bester Onlineshop-Baukasten"
[3]: https://www.spocket.co/blogs/mobile-first-ecommerce-why-it-matters-more-than-ever "Mobile-First eCommerce 2025"
[4]: https://www.fuer-gruender.de/wissen/unternehmen-fuehren/e-commerce/shopsysteme/ "Shopsysteme-Vergleich 2026 — Gambio/Shopware DSGVO/Rechtstexte"
[5]: https://www.smart-web-elements.com/wissen-web/smarte-perspektiven/dein-weg-zum-erfolgreichen-online-shop "Online Shop erstellen — Design & Tipps"
[6]: https://www.freiepresse.de/vergleich/jimdo-vs-shopify/ "Jimdo vs Shopify 2026"
[7]: https://cross-border-magazine.com/e-commerce-payment-germany-2025/ "E-Commerce Payment Germany 2025"
[8]: https://frisbii.com/blog/the-most-popular-online-payment-methods-in-germany/ "Beliebteste Zahlungsmethoden Deutschland"
[9]: https://landmarkglobal.com/eu/en/news-insights/top-10-essential-facts-about-german-e-commerce/ "German E-Commerce 2025 — Trust"
[10]: https://www.eology.de/news/e-commerce-trends "E-Commerce-Trends — Zertifikate & Bewertungen"
[11]: https://www.kvk.nl/en/international/e-commerce-in-germany/ "E-commerce in Germany — Returns/Delivery expectations"
[12]: https://www.needdesign.de/blog/18-aufregende-Trends-im-Grafikdesign-2025.html "Design-Trends 2025 — natürliche Produktfotos"
[13]: https://www.e-recht24.de/ecommerce/13472-widerrufsbutton.html "Widerrufsbutton — Pflicht & Anforderungen"
[14]: https://www.verbraucherzentrale.de/wissen/vertraege-reklamation/kundenrechte/widerrufsbutton-ab-juni-2026-onlinevertraege-einfacher-widerrufen-118449 "Widerrufsbutton ab Juni 2026"
[15]: https://www.fuer-gruender.de/blog/widerrufsbutton-wird-pflicht-fuer-online-shops/ "Widerrufsbutton — Strafe bis 50.000 €"
