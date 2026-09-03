# Фидбэк владельца 2026-09-03: скидка на фото, артикулы, состав заказа, оплата и доставка

**Запрос владельца (2026-09-03, после DL-21, скриншот `/aktionen/` кита aktionsmarkt, Look «retro»):**

1. «В нижних блоках не отображается на картинке скидка.»
2. «На сайте в товаре выводить основной артикул товара.»
3. «В личном кабинете в заказе выводить артикул рядом с товаром, так же отображать его при
   выставлении счёта и во всех местах, где указывается товар.»
4. «В заказе выводить также после номера и до наименования главное фото товара. Так же при
   добавлении позиции.»
5. «При заказе товара со скидкой просто стоит цена со скидкой, но это же основная цена − скидка;
   должна быть прописана скидка на товар в заказе, и учесть, если их несколько.»
6. «Для каждого типа заказа всех архетипов, по желанию: оплата онлайн, при получении или на месте,
   или выставить счёт как юрлицо. Видимо нужен выбор: юрлицо покупает или физлицо.»
7. «Нужна опция доставки для тех архетипов, где есть доставка: самовывоз или доставка.»
8. (второй скриншот, бакеты предпросмотра по одной карточке) «Разделим блоками и сделаем их рядом.»

Идентификаторы: **DL-22** (п.1) · **DL-23** (п.8) · **SH-19** (п.2) · **SH-20** (п.3) ·
**SH-21** (п.4) · **SH-22** (п.5) · **SH-23** (п.6) · **SH-24** (п.7). Семейство SH = «заказ,
клиент, деньги» (волна 2026-08-20, SH-1…SH-18); строка в каталоге заводится этим планом.

---

## 1. DL-22 — бейдж скидки на фото для всех карточек с вычислимой выгодой

### 1.1 Что показала разведка (файл:строка)

* Бейдж на фото эмитит `templates/storefront/_discount_display.html` `part="badge"`; гейт —
  ТОЛЬКО `discount_style`, не наличие выгоды: `percent` → «−N %», `badge` → «−N €»,
  **любой другой непустой стиль → ничего** (`:24-25`, тело ветки — комментарий), пустой стиль →
  авто «−N %»/«−N €» (`:26-29`).
* На скриншоте: Brötchen и Toilettenpapier — стиль `""` → бейдж есть; Croissant — стиль
  `countdown`, Überraschungskiste — стиль `surprise`, Waschmittel (второй скриншот) —
  `festpreis` → бейджа нет, хотя `Sie sparen …` (part `savings`) печатается: два разных гейта над
  одними данными.
* Вычисленный процент уже есть: `Promotion.discount_percent_display` (`models.py:380-387`) —
  из `compare_at`/`price_override`, когда `discount_percent` пуст; `discount_amount` (`:363`).
  CSS retro-штампа (`app.css:538-548`) лишь перекрашивает `.bg-red-600.rounded-full`, ничего
  не прячет.

### 1.2 Решение

Бейдж по СМЫСЛУ стиля, а не по факту «стиль задан»:

| Стиль | Бейдж на фото |
|---|---|
| `""`, `percent`, `countdown`, `surprise` | «−N %» (`discount_percent_display`; фолбэк «−X €») |
| `badge`, `strikethrough`, `festpreis`, `ab` | «−X €» (`discount_amount`; акцент этих стилей — цена «statt») |
| `mystery` | ничего (SF-1.4: утечка цены запрещена, замок держит) |

Разметка бейджа — байт-в-байт прежняя (`absolute top-3 left-3 bg-red-600 … rounded-full shadow`,
размеры sm/lg) → retro-штамп и замок DL-15 «крупный бейдж» не трогаем. Подсказка стиля от
C-блока (`style_override`) идёт тем же путём: «strikethrough» теперь даёт «−X €», а не тишину —
семантика подсказки = семантика стиля. Деталь акции (`promotion_detail.html:85-91`) имеет свой
гейт (пилюля у цены для countdown/surprise; festpreis/ab — «только новая цена») и в этом
инкременте НЕ трогается: запрос владельца — про картинку карточки.

Замки: `test_discount_style.py` — countdown/surprise/strikethrough/festpreis/ab переписываются
осознанно (ассерт «бейдж есть и какого вида»), `mystery` остаётся «нет»; `test_discount_display_parity
::test_block_style_hint_cascade` — «−30» → ожидаем «−X €»; регресс в `test_dl15_center_wide`
(промо со стилем countdown/surprise в полосе «Endet bald» несёт `rounded-full shadow`).

## 2. DL-23 — бакеты предпросмотра рядом колонками

### 2.1 Что есть

`promotions_list.html:95-108`: `upcoming_groups` (три бакета `start_woche / start_naechste /
start_spaeter`, `public_views._upcoming_buckets:411`) рендерятся тремя `<section class="mb-8"
data-upcoming>` со слайдер-лентой каждая. При одной карточке в бакете — три почти пустых ряда
(скриншот владельца).

### 2.2 Решение

Правило «мало карточек → блоки рядом»: если бакетов ≥ 2 и в КАЖДОМ ≤ 2 карточек, секции
оборачиваются в `grid md:grid-cols-{n}` (n = число бакетов, 2–3), каждая — блок с заголовком и
карточками столбиком (без слайдера); иначе — прежние ленты. Мобайл — стопка, как раньше. Заголовки
и маркеры `data-upcoming` сохраняются (замок `test_dl17_preview` цел), добавляется
`data-upcoming-row` на обёртку. Стенд на ките aktionsmarkt (у него ровно 3 бакета по 1).

## 3. SH-19 / SH-20 — артикул на витрине и везде, где печатается позиция

### 3.1 Что показала разведка

* Снимок `OrderItem.sku` есть и заполняется всеми тремя писателями (`orders/services.py:312,
  361-371`, `editing.py:192,203`); карточка заказа, подтверждение, Lieferschein-PDF, письма
  `order_created`/`order_owner` его печатают.
* **Деталь товара печатает Art.-Nr. уже сейчас** (`product_detail.html:43-49`, следует за
  выбором варианта), но **у ВСЕХ демо-товаров SKU пуст** — `_p(..., sku="")`, ни один кит его не
  задаёт (GTIN задаётся). Плюс в форме товара поле `sku` спрятано в свёрнутом «Mehr anzeigen»
  (`product_form.html:339-343`) — владелец его не находит.
* Пробелы (файл:строка): строка списка продаж `_order_rows.html:27`, KDS `_kitchen_board.html:19`,
  корзина `cart.html:33`, письма anprobe/quote, **счёт** (`finance/services.py:291-300` строки
  `{"text","qty","unit_price","vat_rate"}` без sku → `invoice_detail.html:24`, `finance/pdf.py:112`),
  **смета** (`JobLine` без sku; FK product/variant `SET_NULL` — живое поле нарушило бы контракт
  снимка), **Offer** (`OfferLine` без sku; `offers.py:89` создаёт `**line` → ключ обязан быть полем),
  пикер (`catalog/picker.py:30,43` — подписи без артикула), панель «Details» витрины.

### 3.2 Решение

* **SH-19 (без миграций):** артикулы демо — детерминированно из кода кита (`<KIT>-<NNN>` в сидере при
  пустом `sku`, варианты `<KIT>-<NNN>-<n>`); поле `sku` в форме товара — из свёрнутого блока в рейл
  «Preis & Bestand» рядом с ценой; Art.-Nr. дополнительно в панели «Details» (`_product_info.html`)
  и в корзине.
* **SH-20:** (a) без миграций — `Invoice.lines[*]["sku"]` (JSON; `compute_totals` игнорирует лишние
  ключи, легаси-счета рендерятся как прежде) + печать в `invoice_detail`/PDF; строка списка
  продаж, KDS, письма anprobe/quote, пикер (подпись «Name · Art.-Nr.»); (b) **миграции
  `orders/00xx` `OfferLine.sku` + `jobs/00xx` `JobLine.sku`** (blank AddField, без бэкфилла) —
  заполняются при создании/`set_lines` из product/variant, печатаются в смете (кабинет/PDF/публичная),
  Offer (публичная страница/письма) и уезжают в снимок счёта. Реюз msgid «Art.-Nr.» (есть во всех
  пяти каталогах).
* Замки: расширить `test_merge::test_order_snapshots_sku_and_option_sku`, `test_order_editing::
  test_invoice_from_order_snapshots_net_lines` (+sku), `test_offers`/`test_offer_page`, jobs
  `test_public::test_angebot_renders_with_lines`; инвариант `dl-name` (SKU внутри ячейки имени —
  `test_card_mobile_feedback`).

## 4. SH-21 — главное фото в строке позиции и в пикере

### 4.1 Что показала разведка

* Сетка строк `.dl-row` ОДНА на пять карточек (заказ/смета/номер/запись/билет): `app.css:1000-1005`
  `grid-template-columns: 1.75rem minmax(0,1fr) 3.5rem 6.5rem 5.5rem 6.5rem`; мобайл `app.css:1032-1037`
  (`.dl-name` = `calc(100% - 1.75rem)`). Новая колонка = правка у ВСЕХ пяти (шапка
  `core/_deal_items_head.html:6-13`, `core/_deal_lines.html:11-21`, `jobs/detail.html:58`, обе ветки
  `orders/order_detail.html`), иначе колонки поедут.
* Источник фото: `ProductVariant.image_url` (`catalog/models.py:516`) → `Product.primary_image`
  (dict, `:320`; у Product НЕТ `image_url`) → `Combo.primary_image_url` (`:701`); свободная строка —
  пусто. Миниатюр нет — размер CSS (`w-9 h-9 object-cover`, прецедент `inbox/offer_compose.html:26`).
  N+1: `orders/views.py:238` `order.items.all()` → `select_related("product","variant","combo")`.
* Пикер общий для заказа/сметы/Offer: `catalog/picker.py:13-74` отдаёт `{value,label,price,title}`
  без фото; потребители — `<select name="part">` (`order_detail.html:56-59`, приёмник `views.py:311`),
  `<select data-qt-addpick>` (`jobs/detail.html:114-117`). `<option>` картинку не рисует.

### 4.2 Решение

* `OrderItem.image_url` (свойство, без миграции: вариант → товар → комбо → «»); колонка `dl-photo`
  между `dl-idx` и `dl-name` во всех пяти карточках + CSS (десктоп трек `2.25rem`, мобайл
  `flex: 0 0 2.25rem`, `.dl-name` пересчитан); пустая строка — плейсхолдер-квадрат, сетка не
  схлопывается. `JobLine`: фото из `product/variant` FK (живые; при удалении — плейсхолдер).
* Пикер: `_catalog_parts` += `image` (значения `value/label/price/title` байт-в-байт);
  `<select>` → компактный список радио-строк «фото · имя · остаток · цена» с текстовым фильтром
  внутри прежнего `<details>`, `name="part"` тот же → приёмники не меняются; общий партиал для
  заказа и сметы (JS сметы читает `data-title`/`data-price` — переносятся на строку). Без вложенных
  `<form>` (замок `test_no_nested_forms_on_any_deal_card`).
* Замки: `test_card_mobile_feedback` (+`dl-photo` в наборе классов, мобильные правила),
  `test_deal_card_shell` (колонки макета ×2), `jobs/test_cabinet.py:219-224` (+`image`), новые:
  вариант → фото варианта, комбо → `primary_image_url`, свободная строка → плейсхолдер, пикер
  → `part` резолвится как прежде.

## 5. SH-22 — скидка акции per-строка + сводка «Rabatte»

### 5.1 Что показала разведка (файл:строка)

* Корзина УЖЕ знает листовую цену (`orders/public_views.py:640-651` `base_unit_price`, чип «Aktion»
  в `cart.html:35`), но `create_order` (`services.py:276-337`) пишет в `OrderItem` ТОЛЬКО
  `unit_price = промо-цена + опции` и маркер `{"promo": id, "label": "Aktion"}` в `modifiers`
  (`:300-303`) — референс выброшен. Промо-чекаут `/p/<uuid>/kaufen/` (`promotions/services.py:174`)
  — `custom_lines` с `title = название АКЦИИ` и ценой акции, референса нет. Кабинетное «Position
  hinzufügen» (`editing.py:168-218`) акций не знает вовсе (продаёт по листовой цене, лимит не
  клеймит) — смежная несогласованность.
* `OrderItem` (`orders/models.py:170-238`): product/combo/variant/variant_label/sku/qty/unit_price/
  vat_rate/cost_price/title_snapshot/modifiers — **нет ни листовой цены, ни суммы скидки, ни
  имени акции**; `modifiers_label` печатает буквально «Aktion». Восстанавливать из FK нельзя:
  `old_price`/`new_price`/`title` акции живые, акция soft-delete → нарушение доктрины снимков.
* Итоги (`orders/totals.py:32-78`): одна строка `Rabatt` = ручная/ваучер (`discount_cents`);
  промо-скидки невидимы; `deal_card.py:190-198` `deal_lines_total = items` (уже нетто акции).
  Несколько акций в заказе возможны уже сейчас (`claim_totals` по `promo.pk`), но никак не
  сгруппированы. Счёт `finance/services.py:288-320`: текст строки = `title_snapshot`.

### 5.2 Решение

* **Миграция `orders/00xx` (аддитивная, без бэкфилла):** `OrderItem.list_price` (Decimal, NULL =
  скидки не было/легаси — разницу не выдумываем), `OrderItem.promotion` (FK SET_NULL — снимок
  переживает удаление кампании), `OrderItem.promo_label` (снимок названия акции на момент продажи).
  Хранить листовую цену ЗА ЕДИНИЦУ, не сумму скидки за строку: `set_item_qty` меняет qty на месте,
  а `(list_price − unit_price) × qty` масштабируется сам. Свойства `discount_per_unit`/`discount_total`.
  Маркер `{"promo": id}` в `modifiers` остаётся (его читают `deal_counts`, `_restore_promo_limits`,
  `_item_promo_id`); `label` маркера = название акции (не «Aktion»).
* **Писатели:** `create_order` (ветка `line_promo` знает обе цены: `list_price = база + опции`,
  FK, label) · `custom_lines` += 8-й слот `{list_price, promotion}` (распаковка по арности в двух
  местах синхронно) · промо-чекаут: `list_price = promotion.old_price`, `title_snapshot` = имя
  ТОВАРА, название акции → `promo_label` · кабинетное `add_item`: применять действующую акцию +
  `claim_units` как `create_order` (иначе владелец продаёт по листовой и лимит не двигается).
* **Читатели:** `totals.py` += `list_items` и `promo_rows` (группировка по акции, сумма desc;
  ключи `items/gross/net/vat/rows` НЕ меняются — их читают счёт/карточка) с инвариантом
  `list_items − Σpromo_rows − discount + shipping == gross` (замок); карточка: `Zwischensumme` =
  листовая сумма, затем строки «🏷 Rabatt · Aktion „…“ −X €» ПЕРЕД ручной скидкой DC-9
  (`_deal_totals.html:21-26`, общий партиал — для stay/booking/ticket/job строк нет → no-op); строка
  позиции: зачёркнутая `list_price` над ценой в `dl-unit`, подпись «−X € · Aktion „…“» под именем
  (идиома корзины); подтверждение/письма (`order_created`, `order_owner`, anprobe/quote) — то же
  («показано = списано»). **Счёт — описательно:** текст строки «Saft (statt 2,49 €, Aktion „…“
  −0,50 €)» — суммы `compute_totals` байт-в-байт, без риска центового дрейфа (структурные
  минус-строки — отдельное решение владельца).
* Замки: `test_promo_cart` (паритет ×5 + `list_price`/FK), `test_order_editing::
  test_invoice_from_order_snapshots_net_lines`, `test_deal_card_shell` (порядок итогов, формат денег),
  новые: две акции в заказе → две строки `promo_rows`; qty-правка масштабирует `discount_total`;
  легаси-строка (`list_price=NULL`) рендерится как прежде; переименованная/удалённая акция →
  `promo_label`; `purchase()` пишет `old_price` + FK; `test_mixed_vat_invoice` остаётся зелёным
  без правок (страховка сумм).

