# UA3-1 слайс 2 — единый `templates/storefront/_buybox.html` (план, 2026-07-02)

> Остаток волны U-A (`unified-sellable-entity-ua-plan §7`). Регрессионно-опасный инкремент:
> СНАЧАЛА характеризационные снапшот-паритет-тесты (шаг 0), правка шаблонов — только после.
> Разведка: 5 параллельных картографов + адверсариальная сверка по каждому kind
> (2026-07-02, все поверхности проверены построчно против кода).

## 1. Цель и рамки

**Цель:** buy-box деталей диспатчится ЕДИНЫМ партиалом `_buybox.html` по `purchase_mode`
контракта (`cart`/`reserve`/`request`/`booking`), а не «каждый шаблон рисует сам».
POST-поля, action, anchor-id, honeypot — **байт-в-байт прежние** (паритет-замки).

**В рамках слайса — 3 поверхности:**
| Поверхность | mode | Сейчас |
|---|---|---|
| `product_detail.html` | `cart` | `#kaufen` + include `_add_to_cart_form.html`; sold-out → `<p>Sold out</p>`, buybar скрыт |
| `promotion_detail.html` | `reserve` | reserve-форма ↔ при `is_sold_out` вместо неё waitlist-форма |
| `service_detail.html` | `booking`\|`request` | `#buchen`, 2 GET-CTA, порядок по `primary_service_action` (UA3-1 слайс 1) |

**Вне рамок (осознанно):** `stay_detail`/`event_detail` — их buy-box'ы двухшаговые/составные
(тарифы, regs, календарь); stay+service идут через контракт в **UA3-2** (`select_url`/`submit_url`),
event — после. Мини-формы карточек (`_product_card`, quick-add), корзина/checkout, комбо-
конфигуратор (`combo_detail`), gift-voucher — НЕ трогаем (это не buy-box детали).

## 2. Карта текущих поверхностей (сверено адверсариально)

### 2.1 product (cart)
- Форма: `templates/storefront/_add_to_cart_form.html` (include в `product_detail.html:55`,
  внутри `div id="kaufen"` строка 21, block `detail_aside`).
- `POST {% url 'storefront-cart-add' %}` (`/warenkorb/add/`), вью `apps/orders/public_views.py:317`.
- Поля: `csrfmiddlewaretoken`, `product` (hidden pk), `variant` (select, ТОЛЬКО при
  `has_variants`, required), `mod` (повторяющееся, ТОЛЬКО при `has_modifiers`; checkbox
  multi-групп / select single-групп), `qty` (number 1..50). **Honeypot НЕТ** (он на checkout).
- Гейты: `{% if orders_enabled %}` (иначе блока нет) → `{% if product.in_stock %}` форма
  `{% else %}` `Sold out` (строки 49–58). Buybar не рендерится без `in_stock` (:144).
- AJAX: `X-Requested-With: fetch` → JSON; иначе 302 `/warenkorb/`.

### 2.2 promotion (reserve + sold-out→waitlist)
- `promotion_detail.html`: ветка `{% if promotion.is_sold_out %}` (:70) → waitlist-бокс
  (форма :74–86), иначе reserve-бокс (:88–110, форма :91–108). Якорных id НЕТ.
- Reserve: `POST {% url 'storefront-reserve' promotion.pk %}` (`/p/<uuid>/reserve/`,
  вью `reservation_create:677`). Поля: `csrfmiddlewaretoken`, `website` (honeypot,
  offscreen-див), `form_token` (hidden, идемпотентность cache.add TTL 600с), `channel`
  (hidden, ?ch=), `name` (req), `email`, `phone`, `quantity` (min 1). Видимые поля —
  циклом `{% for field in form %}` с исключением трёх hidden (PublicReservationForm).
- Waitlist: `POST {% url 'storefront-waitlist' promotion.pk %}`. Поля: `csrfmiddlewaretoken`,
  `website` (honeypot), `name` (opt), `email` (req).
- `is_sold_out` = `available_quantity is not None and <= 0` (None = безлимит).
- Error-пути POST (не трогаем, вьюхи как были): OutOfStock, дубль form_token,
  ReservationLimitReached (:719–723), ratelimit 5/600с.

### 2.3 service (booking|request)
- `service_detail.html`: aside `div id="buchen"` (:30, block detail_aside) — ФОРМЫ НЕТ,
  два GET-CTA; порядок по `primary_action` (резолвер `apps/core/archetypes.py:65`:
  поле `Service.primary_action` → `site_config['primary_service_cta']` → `'booking'`;
  `'request'` валиден только при активном jobs):
  `'request'` → primary `/anfrage/`, secondary `/termin/leistung/<pk>/`; иначе наоборот
  (secondary `/anfrage/` только при jobs_active). Депозит-плашка. Buybar: anchor `#buchen`,
  `module=jobs|booking` по primary_action, `sold_out=False`.
- Реальная POST-форма букинга — на слот-пикере `service_slots.html` (НЕ деталь) — в UA3-2.

### 2.4 Контракт (факт)
- `detail.html` — чистые block-слоты, per-kind if/elif НЕТ; общий рендер только `entity_jsonld`.
- `SellableEntity.buybox_context` (`sellable.py:37`) — мёртвая заглушка (никто не заполняет).
- У promotion НЕТ адаптера (kind'ы: product/service/stay/event/combo) → mode передаём явно.

## 3. Дизайн

**Новый партиал `templates/storefront/_buybox.html`.** Вход: `sellable` (опц.) и/или
`buybox_mode` (явный override — для promotion). Резолв:
`mode = buybox_mode|default:sellable.purchase_mode`. Диспатч `{% if mode == ... %}` по
4 значениям — ЕДИНСТВЕННОЕ место ветвления, шаблоны деталей веток больше не имеют:

- `cart` → текущий блок `#kaufen`: гейт `orders_enabled` → `in_stock` →
  `{% include "storefront/_add_to_cart_form.html" %}` / `Sold out`. Партиал формы НЕ
  редактируем (байты полей сохраняются include'ом).
- `reserve` → перенос обоих боксов из `promotion_detail.html` (sold-out→waitlist ветка
  ВНУТРИ партиала, разметка 1:1). Контекст: `promotion`, `form`, `waitlist_form` — уже в
  `_detail_ctx`.
- `booking`/`request` → перенос содержимого `#buchen` из `service_detail.html`
  (одна разметка, порядок CTA по mode; `request` = primary «Anfrage»).

**Правки шаблонов деталей (3 шт.):** заменить перенесённые блоки на
`{% include "storefront/_buybox.html" ... %}` (promotion — `with buybox_mode="reserve"`;
service — mode из `primary_action`: `request`→`request`, иначе `booking`). Aside-обвязка
(цена/PAngV/депозит-плашка) и buybar остаются в шаблонах — это не buy-box.

**Вьюхи/формы/контракт НЕ трогаем** (slice 2 — чисто шаблонный). `buybox_context`,
`select_url`/`submit_url` — UA3-2.

## 4. Паритет-замки (шаг 0 — ДО правки шаблонов, коммитятся отдельно, зелёные на текущем коде)

Подход как UB1-3 (характеризационные до свода). Парсим из отрендеренного HTML блок
`<form action=X>…</form>` и ассертим ТОЧНЫЙ список `name=` полей + action + анкоры:

- `apps/catalog/tests/test_buybox_parity.py` (product):
  1. in-stock без вариантов: action `/warenkorb/add/`, поля ровно `{csrfmiddlewaretoken,
     product, qty}`, `id="kaufen"` есть, значение `product`=pk;
  2. с вариантами и модификаторами: + `variant` (select) и `mod`;
  3. sold-out: «Sold out» есть, `/warenkorb/add/` НЕТ, `data-buybar` НЕТ;
  4. orders выключен: блока `#kaufen`-формы нет.
- `apps/promotions/tests/test_buybox_parity.py` (promotion):
  5. active: action `/p/<pk>/reserve/`, поля ровно `{csrfmiddlewaretoken, website,
     form_token, channel, name, email, phone, quantity}`;
  6. sold-out: action `/p/<pk>/waitlist/`, поля ровно `{csrfmiddlewaretoken, website,
     name, email}`, reserve-action НЕТ;
- service — замки уже есть (`test_service_detail_default_primary_is_booking_slots`,
  `…_primary_action_request_override`, `…_shows_anfrage_only_when_jobs_active`,
  снапшот порядка секций). Добавить 1 замок: `id="buchen"` + обе ссылки как точные href.

Хелпер парсинга формы — маленький, в тест-файле (regex по `<form…</form>` + `name="…"`),
без новых зависимостей.

## 5. Шаги/коммиты (батч, один прогон CI на верхушке)

1. **C1** — паритет-тесты (шаг 0), зелёные на ТЕКУЩЕМ коде.
2. **C2** — `_buybox.html` + свод product/promotion/service деталей на include;
   локальный гейт: паритет-тесты + `catalog`/`promotions`/`booking` storefront+public
   сьюты + `orders` (cart_add/checkout не трогаем, но прогнать).
3. Push → CI зелёный → FF-мерж. Без миграций.

## 6. Риски и страховки

- **Промо-формы рендерятся Django-form'ой** (`{{ form.website }}`, цикл по полям) —
  переносим разметку 1:1, паритет-замок №5/6 ловит любой дрейф.
- **AJAX-класс/атрибуты формы товара** — не трогаем сам партиал `_add_to_cart_form.html`.
- **Buybar продукта** гейтится `in_stock` в шаблоне детали — остаётся там, замок №3.
- **`{% include with %}` scoping**: партиал использует только переменные контекста детали
  (promotion/form/product/orders_enabled/service/…) — все уже в контексте; smoke-рендер
  в паритет-тестах ловит NameError-подобные пустоты (Django молча пустит "" — поэтому
  замки ассертят ТОЧНЫЕ поля, а не «что-то отрендерилось»).
- Ошибочные POST-пути (OutOfStock/limit/token) не зависят от шаблона — вьюхи не трогаем.

## 7. Превью UA3-2 (отдельное согласование после слайса 2)

`SellableEntity` += `select_url` (GET-шаг выбора) / `submit_url` (POST) + признак
готовности выбора; `_buybox.html` в mode `booking` рендерит селектор, а POST-форму — только
при валидном выборе (`quote.available` у stay / выбранный `?slot=` у service);
`stay_detail` + `service_slots` проводятся через контракт; поля форм
`storefront-unterkunft-book`/`storefront-service-book` НЕ меняются (карта полей — §2 разведки,
у stay: rate_plan/von/bis/erw/kinder/rooms/embed/extra/voucher_code/website/name/email/phone/note;
у service: embed/start/resource/website/name/email/phone/note/pass_code/extra);
сервер ре-валидирует наличие (`book_stay`/`booking.services.book` не трогаем).
