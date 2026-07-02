# UA3-2 — двухшаговый buy-box через контракт (план, 2026-07-02)

> Последний пункт остатка волны U-A (`…-ua-plan §7`). Базируется на UA3-1 слайс 2
> (единый `_buybox.html`, merged) и разведке `docs/ua3-1-buybox-plan-2026-07-02.md §2`.
> Регрессионно-опасный: паритет-замки ДО правок, вьюхи-приёмники POST не трогаем.

## 1. Цель

Разделить «выбор» и «submit» как ЕДИНЫЙ путь контракта: `SellableEntity` знает, ГДЕ
выбирают (`select_url`, GET) и КУДА бронируют (`submit_url`, POST), а `_buybox.html`
рендерит POST-форму ТОЛЬКО при валидном выборе (признак готовности). Сервер
по-прежнему ре-валидирует наличие (`services.book_stay` / `booking.services.book`
НЕ трогаем — anti-oversell остаётся серверным).

## 2. Факт (из разведки, сверено)

Оба флоу УЖЕ двухшаговые по семантике, но каждый — своей разметкой, без контракта:

- **stay** (`stay_detail.html`): шаг 1 — GET-форма дат (self) + календарь C3 (JS сабмитит
  форму) → вьюха считает `quote`; шаг 2 — POST-форма `storefront-unterkunft-book`
  рендерится при `quote.available`, иначе amber-бокс причины (`min_nights`/`guests`/
  unavailable). Поля POST: `csrfmiddlewaretoken, [rate_plan], von, bis, erw, kinder,
  rooms, [embed], [extra*], voucher_code, website(honeypot), name, email, phone, note`.
- **service** (`service_slots.html`): шаг 1 — сетка свободных стартов (GET `?slot=`),
  пикер мастера, календарь; шаг 2 — POST-форма `storefront-service-book` рендерится при
  `selected`, иначе хинт «Pick a time to continue» (только когда `starts` непуст).
  Поля POST: `csrfmiddlewaretoken, [embed], start, [resource], website(honeypot), name,
  email, phone, note, [pass_code], [extra*]`.
- `sellable` уже в контексте `stay_detail` (`stays/public_views.py:324`) и
  `service_detail` (:367); в `service_slots` — НЕТ (добавим).
- Деталь услуги: CTA-пара в `_buybox.html` (mode booking/request) ведёт на слот-пикер
  жёстким `{% url %}` — станет `sellable.select_url` (байты те же).

## 3. Дизайн (РЕШЕНИЕ ВЛАДЕЛЬЦА 2026-07-02: вариант «A+»)

> A+ = A + stay-селектор тоже становится партиалом за `_buybox.html` (весь buy-box
> номера — один include, полный «B» для stay). Для service селектор остаётся
> контентом страницы слот-пикера (страница И ЕСТЬ селектор — отделять не от чего);
> его переезд станет актуален, если слот-пикер поедет на деталь услуги (отдельный
> UX-инкремент, не UA3-2). Ниже базовый дизайн A, дельта A+ — в §3.1.

**Контракт (`apps/core/sellable.py`):**
- dataclass += `select_url: str = ""` (GET-шаг выбора), `submit_url: str = ""`
  (POST-приёмник), `buybox_ready: bool = False` (валидный выбор в ЭТОМ запросе).
- `sellable_for(kind, obj, locale=None, *, buybox_ready=False)` — реверс per kind
  (`NoReverseMatch` → "", как `detail_url`):
  service → slots/service-book; stay → unit/unterkunft-book; product → ""/cart-add;
  event → ""/event-book; combo → деталь-конфигуратор/combo-add. Пустой `select_url` =
  одношаговый kind. `buybox_ready` задаёт вьюха (stay: `quote and quote.available`;
  service_slots: `bool(selected)`; детали без выбора — False).

**`_buybox.html`, ветка `booking|request`, становится двухшаговым гейтом:**
```
{% if buybox_form %}                {# страница С выбором (stay_detail, service_slots) #}
  {% if sellable.buybox_ready %}{% include buybox_form %}
  {% elif buybox_fallback %}{% include buybox_fallback %}{% endif %}
{% else %}                          {# страница БЕЗ выбора (деталь услуги) — CTA на select_url #}
  ...текущая CTA-пара (primary по mode), href={{ sellable.select_url }}...
{% endif %}
```
- **Селекторы НЕ переезжают** (форма дат+календарь stay, сетка слотов+мастер service —
  контент своих страниц; переезд — отдельное решение, вариант B, сейчас выгоды нет).
- Submit-формы становятся партиалами (разметка 1:1, action → `{{ sellable.submit_url }}`):
  `storefront/_buybox_stay_form.html` (POST-форма stay целиком) и
  `storefront/_buybox_service_form.html` (POST-форма service_slots).
- Fallback-партиалы: `_buybox_stay_unavailable.html` (amber-бокс причин; передаётся
  только когда `quote` есть) и хинт слотов (передаётся только когда `starts` непуст) —
  порядок/условия рендера байт-в-байт как сейчас.

**§3.1 Дельта A+ (stay-селектор в партиал):** форма дат + календарь C3 + JS выбора
диапазона переезжают 1:1 в `storefront/_buybox_stay_select.html`; `_buybox.html` в
ветке booking рендерит `buybox_selector` (если передан) ПЕРЕД гейтом формы —
порядок блоков aside (даты → календарь → форма/amber) байт-в-байт прежний;
`stay_detail` в `#buchen` остаётся один include `_buybox.html` c
`buybox_selector`/`buybox_form`/`buybox_fallback`.

**Правки вьюх (минимальные, приёмники POST не трогаем):**
- `stays.unterkunft_unit`: `sellable_for("stay", unit, buybox_ready=bool(quote and quote.available))`.
- `booking.service_slots`: добавить `sellable=sellable_for("service", service,
  buybox_ready=bool(selected))` в контекст.
- `booking.service_detail`: без изменений (ready=False, CTA-ветка).

## 4. Паритет-замки (шаг 0, зелёные ДО правок)

- `apps/stays/tests/test_buybox_parity.py`:
  1. доступный диапазон, без тарифов/extras: точный набор полей POST-формы
     `{csrfmiddlewaretoken, von, bis, erw, kinder, rooms, voucher_code, website, name,
     email, phone, note}` + action `/unterkunft/<pk>/buchen/`;
  2. с RatePlan + Extra + embed: + `{rate_plan, extra, embed}`;
  3. недоступный диапазон: amber-бокс, action `/buchen/` отсутствует;
  4. без дат (`quote` нет): ни формы, ни amber.
- `apps/booking/tests/test_buybox_parity.py`:
  5. `?slot=` выбран: точный набор `{csrfmiddlewaretoken, start, website, name, email,
     phone, note}` + action `/termin/leistung/<pk>/buchen/`; с мастером — + `resource`;
  6. слот не выбран, старты есть: «Pick a time to continue», формы нет;
  7. embed-carry: `name="embed" value="1"` в форме (зеркало test_embed stays).
- Контракт: в `test_sellable.py` — select_url/submit_url всех 5 kind (+ пустые у
  одношаговых), `buybox_ready` дефолт False / проброс True.

## 5. Шаги/коммиты (батч)

1. **C1** — паритет-замки (шаг 0) на текущем коде.
2. **C2** — контракт: поля + реверс в адаптерах + тесты контракта.
3. **C3** — stay: партиалы `_buybox_stay_form/_unavailable`, `stay_detail` → include
  `_buybox.html` (гейт в партиале), вьюха передаёт `buybox_ready`.
4. **C4** — service: партиал `_buybox_service_form`, `service_slots` → include
  `_buybox.html`, вьюха добавляет sellable; CTA детали услуги → `select_url`.
5. Гейт: новые замки + ПОЛНЫЕ `apps/stays/tests/test_public.py`,
  `apps/booking/tests/test_public.py`, test_embed, test_sellable, затем полные сьюты
  stays/booking/core. Push → CI → FF-мерж. Без миграций.

## 6. Риски

- **Самая жирная форма проекта (stay)** переезжает в партиал — замок №1/№2 держит точный
  набор полей; PAngV-разбивка/тарифы/Kurtaxe переносятся как есть (это внутренности формы).
- **`{% include %}` scoping**: партиалы читают quote/rate_options/extras/adults/…
  из контекста вьюхи — include без `only`, всё видно; замки ловят пустоты.
- **JS календаря** (`__stayCalSelectBound`) остаётся в stay_detail (селектор не переезжает).
- Порядок блоков aside (даты → календарь → форма/amber) — не меняется; существующий
  снапшот-замок секций stay + `test_detail_shows_price_and_book_form` дополнительно держат.
