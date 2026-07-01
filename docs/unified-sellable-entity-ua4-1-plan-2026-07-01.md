# UA4-1 — Единый реестр секций детали (KEYS+LABELS) — план — 2026-07-01

> Подзадача U-A4 мастер-трека. Источник правды: `docs/unified-sellable-entity-ua-plan-2026-06-30.md`
> (стр. 60-62, 158-172) и `docs/unified-sellable-entity-master-track-2026-06-30.md` §3 U-A4.
> Конвенция: docs до кода. UA4-1 = ТОЛЬКО реестр+нормализатор+инспекторы (нулевое изменение
> вывода витрины). Data-driven цикл рендера — отдельная подзадача UA4-2.
> Зависит от UA2-1. Без миграций.

## 0. Что делает UA4-1 (и чего НЕ делает)

**Делает:** обобщает три пер-архетипных механизма конфигурации секций детали в ОДИН реестр
дескрипторов `(kind, section) → {label, orderable, hideable, applies_to}` плюс ОДИН
нормализатор `config['<module>_detail'] = {order, hidden}`, совмещённый с LABELS (сейчас
LABELS разбросаны по `apps/core/views.py`). Добавляет ключи для service/stay. Проводит
round-trip через save (`home_builder_view`) И live-preview (`accept_preview_draft`).

**НЕ делает (→ UA4-2):** не меняет шаблоны детали, не вводит цикл `{% for section %}`, не
трогает вывод витрины. UA4-1 — чистый Python-реестр + плюмбинг инспектора билдера. Витрина
после UA4-1 рендерится байт-в-байт как до неё (для event/product — через уже существующие
`event_detail_order`/`product_detail_hidden`, теперь читаемые из обобщённого нормализатора).

## 1. Инвентарь секций по детальным шаблонам (разведка, file:line)

Все четыре наследуют `templates/storefront/detail.html:1-36` (6 блоков: `detail_back`,
`detail_gallery`, `detail_aside`, `detail_body`, `detail_wide`, `detail_buybar`). JSON-LD —
`detail.html:19` (`{% entity_jsonld %}`).

### product (`templates/storefront/product_detail.html`)
| Секция | Блок | Строки | Ключ hide (сейчас) |
|---|---|---|---|
| Галерея | `detail_gallery` | 8-18 | — (ядро) |
| Buy-box: категория/badge/h1/rating-link/цена/Grundpreis | `detail_aside` | 20-37 | — (ядро) |
| Описание (в aside!) | `detail_aside` | 38 | `description` (`product_detail_hidden`) |
| LMIV-инфо (Herkunft/Zutaten/Allergene) | `detail_aside` | 41-47 | `info` |
| Add-to-cart / sold-out / store-hint | `detail_aside` | 49-67 | — (ядро) |
| Отзывы (inline, `#bewertungen`) | `detail_body` | 71-127 | `reviews` |
| Related («More from category») | `detail_wide` | 129-140 | `related` |
| Buybar (мобильный) | `detail_buybar` | 142-148 | — (ядро) |

Ключи: `siteconfig.PRODUCT_DETAIL_SECTION_KEYS = ("description","info","reviews","related")`
(`apps/tenants/siteconfig.py:568`). **hide-only, без order.** Внимание: `description`/`info`
живут ВНУТРИ `detail_aside` (не body) — это осложняет их вынос в body-цикл UA4-2 (см. §7).

### service (`templates/storefront/service_detail.html`)
| Секция | Блок | Строки | Маркер `data-sf-section` |
|---|---|---|---|
| Фото (single) | `detail_gallery` | 14-27 | — |
| Buy-box: h1/длит./цена + primary/secondary CTA + deposit | `detail_aside` | 29-54 | — (ядро) |
| Описание («About this service») | `detail_body` | 57-62 | нет (есть `data-edit`) |
| Атрибуты (UA4-3) | `detail_body` | 64-73 | `service_attributes` |
| FAQ (UA4-3) | `detail_body` | 74-86 | `service_faq` |
| Команда (resources) | `detail_body` | 87-99 | нет |
| Отзывы (include `_entity_reviews.html`) | `detail_body` | 101 | `reviews` (в партиале) |
| Buybar | `detail_buybar` | 104-112 | — |

**Нет пер-страничного конфига секций сегодня** (нет `service_detail` в siteconfig).

### stay (`templates/storefront/stay_detail.html`)
| Секция | Блок | Строки | Маркер |
|---|---|---|---|
| Галерея | `detail_gallery` | 14 | — |
| Buy-box: h1/rating/факты/цена + форма дат + календарь + quote-форма | `detail_aside` | 16-213 | — (ядро, U-A3) |
| Описание | `detail_body` | 218 | нет (есть `data-edit`) |
| Факты + Ausstattung/Amenities | `detail_body` | 221-237 | нет |
| Отзывы (include) | `detail_body` | 239 | `reviews` (в партиале) |
| Similar rooms | `detail_wide` | 244-261 | нет |
| Buybar | `detail_buybar` | 263-267 | — |

**Нет пер-страничного конфига секций сегодня** (`apps/stays/public_views.py:255` не передаёт
никакого `*_detail_order`).

### event (`templates/storefront/event_detail.html`)
| Секция | Блок | Строки | Механизм |
|---|---|---|---|
| Галерея | `detail_gallery` | 7 | — |
| Buy-box: h1/promise/дата/локация/цена/CTA | `detail_aside` | 9-36 | — (ядро) |
| Описание | `detail_body` | 40 | нет |
| **14 тематических секций (цикл)** | `detail_body` | 45-47 | `event_detail_order` → `_event_thematic.html` |
| Плätze / бронь-форма (`#buchen`, RV1 2-step) | `detail_body` | 49-246 | — (ядро, U-A3) |
| Groups & companies (Angebot) | `detail_body` | 249-255 | нет |
| Отзывы (include) | `detail_body` | 257 | `reviews` (в партиале) |
| Buybar | `detail_buybar` | 260-264 | — |

Ключи: `siteconfig.EVENT_DETAIL_SECTION_KEYS` (14 шт., `siteconfig.py:523-538`).
**order+hide.** Уже есть data-driven цикл (`event_detail.html:46` +
`_event_thematic.html` if/elif по `k`). Это единственный шаблон с реализованным циклом —
эталон для UA4-2.

**Вывод для реестра:** секции делятся на (a) НЕ-body спец-секции (галерея, buy-box, buybar —
всегда есть, свой блок, не hideable/orderable через реестр — остаются `{% block %}`); и
(b) body-секции (описание/атрибуты/FAQ/инфо/отзывы/команда/amenities/related/тематические),
которыми управляет реестр.

## 2. Существующая инфраструктура реестра / hide-order (foundation)

Три несогласованных механизма, которые UA4-1 сводит в один:

1. **event** — `EVENT_DETAIL_SECTION_KEYS` + `normalize_event_detail(raw)→{order,hidden}`
   (`siteconfig.py:541-550`) + `event_detail_order(config)→[visible keys]` (`:553-562`).
   Config-ключ `config['event_detail']`. **order+hide.**
2. **product** — `PRODUCT_DETAIL_SECTION_KEYS` + `normalize_product_detail(raw)→{hidden}`
   (`:571-575`) + `product_detail_hidden(config)→set` (`:578-580`). Config-ключ
   `config['product_detail']`. **hide-only.**
3. **LABELS** — живут отдельно в `apps/core/views.py`: `_EVENT_SECTION_LABELS`
   (`views.py:1737-1752`), `_PRODUCT_SECTION_LABELS` (`:1755-1760`). Разрыв KEYS↔LABELS —
   ровно то, что UA4-1 должен устранить.

**Нормализация** вызывается в `siteconfig.normalize()` (`:1289-1291`):
`normalized["event_detail"] = normalize_event_detail(...)`,
`normalized["product_detail"] = normalize_product_detail(...)`.

**Билдер (инспектор), save-путь** — `home_builder_view` (`views.py`):
- Рендер строк инспектора: `event_sections` (`:1257-1265`), `product_sections`
  (`:1268-1271`) → контекст site_home. Presence-guard.
- Сохранение из POST: event `ed_order_*`/`ed_visible_*` c presence-guard `any(ed_order_*)`
  (`:1045-1059`); product `pd_visible_*` c presence-guard `pd_present` (`:1062-1069`).
- Дублирующая копия save-логики event в `pages_view` (`views.py:1780-1791`) и рендер
  `event_sections` там же (`:1808-1819`) — **два места пишут `event_detail`**, оба надо
  провести через обобщённый хелпер.

**Live-preview draft** — `accept_preview_draft` (`views.py:1574-1579`): пропускает
`event_detail`/`product_detail` из POST-JSON в черновик `site_preview_draft` (сессия);
`normalize_*` чистит при чтении. Тест — `test_live_preview.py:297-316`.

**On-canvas плюмбинг (SE-1…SE-5,** `docs/storefront-onsite-editor-plan.md`**):**
- `data-sf-section` обёртки на канве → клик открывает инспектор (SE-2b-2, план стр. 16, 45,
  103-105). `event_detail.html:45` несёт `data-sf-section="event_detail"`.
- Скоуп-мэппинг `group → page-block`: `SCOPE_PAGE_KEY` в `site_home.html:1665` =
  `{catalog:"catalog", events:"events", stays:"stay_rooms", events_detail:"event_detail",
  catalog_detail:"product_detail", cart:"cart"}`. **Нет `booking_detail`/`stays_detail`.**
- `page-block[data-page-key=...]`: `event_detail` (`site_home.html:435`),
  `product_detail` (`:457`). **Нет для service/stay.**
- Превью-переключатель: `example_detail_pages(tenant)` (`archetypes.py:139-172`) отдаёт
  `group="<module>_detail"`. `DETAIL_ENTITIES` (`archetypes.py:124-136`) уже включает
  `booking.Service` (UA1-2) → `booking_detail`, и `stays.StayUnit` → `stays_detail`. Обе
  группы сегодня падают в fallthrough «правь на канве» (`site_home.html:1687-1691`), т.к.
  `SCOPE_PAGE_KEY` их не знает.
- Как view прокидывает конфиг в деталь: product — `product_detail_hidden(_cfg)`
  (`promotions/public_views.py:565`); event — `event_detail_order(_raw)`
  (`events/public_views.py:292`). stay/service — не прокидывают ничего.

## 3. Контракт `SellableEntity` и его связь с реестром

`apps/core/sellable.py`: dataclass `SellableEntity` (`:22-39`) уже несёт `attributes: list`
и `info_sections: list` — «швы под U-A4» (комментарий `:24-25`), сейчас всегда пустые
(`sellable_for` их не заполняет, `:149-160`). `SELLABLE_KINDS = ("product","service","stay",
"event","combo")` (`:130`).

**Решение о разграничении (для плана, не для кода UA4-1):**
- **Контентные секции сущности** (`attributes`, `info_sections`/FAQ) — данные КОНКРЕТНОГО
  объекта. Их наполняет адаптер `sellable.py` (UA4-3 для service: `Service.attributes_list`/
  `faq_list` уже есть в `apps/booking/models.py:129-134`). Реестр UA4-1 описывает секцию
  `attributes`/`faq` как **дескриптор** (label/order/hide), а рендерит её UA4-2, читая данные
  из контракта или объекта.
- **Реестр секций (UA4-1)** — это МЕТА-слой (какие секции существуют для kind, их порядок/
  видимость, подписи в билдере). Он НЕ хранит данные, только дескрипторы. Не путать с
  `attributes`/`info_sections` полями контракта (это данные).
- Итого: реестр `DETAIL_SECTIONS` (новый) ↔ контракт `SellableEntity` пересекаются только
  через UA4-2 (рендер-цикл прочитает дескриптор из реестра и данные из контракта/объекта).
  UA4-1 сам контракт не трогает.

## 4. Дизайн реестра

### 4.1 Новый модуль `apps/core/detail_sections.py`
Единый источник правды: дескрипторы секций для всех 4 kind. Ленивые импорты моделей не
нужны (чистые данные + i18n label). Форма дескриптора:

```
SectionDescriptor:
  key: str            # "description", "reviews", "for_whom", "amenities", ...
  label: lazy str     # i18n подпись для билдера (переносим из views._*_LABELS)
  orderable: bool     # можно ли двигать (event=True; product/stay/service — см. §7)
  hideable: bool      # можно ли скрыть
```

Реестр как `dict[kind, tuple[SectionDescriptor, ...]]` в дефолтном порядке рендера:

- `product`: `description`, `info`, `reviews`, `related` (совпадает с текущими
  `PRODUCT_DETAIL_SECTION_KEYS`; hideable=True, orderable=False — сохраняем текущее hide-only).
- `event`: 14 ключей из `EVENT_DETAIL_SECTION_KEYS` (orderable=True, hideable=True).
- `service` (NEW): `description`, `attributes`, `faq`, `team`, `reviews` (hideable=True;
  orderable=False на старте — order добавим позже, чтобы не расширять риск).
- `stay` (NEW): `description`, `amenities`, `reviews`, `similar` (hideable=True; orderable=False).

Замечание по именованию: план U-A предлагает ключи service `(description/attributes/faq/
related)` и stay `(amenities/facts/related)`. Уточняем по факту шаблонов: у service «related»
нет (есть `team`); у stay есть `similar` (не «related») и `amenities`. Реестр отражает
реальный шаблон — это критично для UA4-2. `facts` у stay встроены в тот же блок, что
`amenities` (`stay_detail.html:221-237`) → одна секция `amenities`.

### 4.2 Обобщённый нормализатор в `apps/tenants/siteconfig.py`
Ввести `DETAIL_SECTION_KEYS: dict[module, tuple]` и один нормализатор:

```
normalize_detail_sections(raw, module) -> {"order": [known], "hidden": [known]}
detail_section_order(config, module) -> [visible keys]   # order minus hidden
detail_section_hidden(config, module) -> set             # для hide-only чтения
```

где `module ∈ {catalog, events, booking, stays}`. Реализация обобщает существующие
`normalize_event_detail`/`event_detail_order`/`normalize_product_detail`/
`product_detail_hidden` (они становятся тонкими обёртками `→ normalize_detail_sections(raw,
"events")` и т.п., чтобы старые импорты не сломать).

**Бэк-компат (ЖЁСТКИЙ ГЕЙТ):** config-ключи остаются `event_detail`/`product_detail`
(module→config-key: `events→event_detail`, `catalog→product_detail`, `booking→booking_detail`,
`stays→stays_detail`). Существующий event/product-конфиг нормализуется идентично прежнему —
байт-в-байт тот же результат (тест-паритет). Для order-only модулей (product/stay/service, где
orderable=False) `order` в конфиге игнорируется/не пишется — только `hidden`.

`normalize()` (`siteconfig.py:1289-1291`) вызывает обобщённый нормализатор для 4 модулей
(добавить `booking_detail`, `stays_detail`; сохранить `event_detail`/`product_detail`).

### 4.3 LABELS ← в реестр
Удалить `_EVENT_SECTION_LABELS`/`_PRODUCT_SECTION_LABELS` из `views.py:1737-1760`; читать
label из `detail_sections.DETAIL_SECTIONS`. `views.py` строит `event_sections`/
`product_sections`/(new)`service_sections`/`stay_sections` из реестра одним хелпером
`inspector_rows(config, module)`.

## 5. Инспектор билдера + превью (плюмбинг)

- `SCOPE_PAGE_KEY` (`site_home.html:1665`): добавить `booking_detail:"service_detail"`,
  `stays_detail:"stay_detail"`. (Ключи слева — `group` из `example_detail_pages`;
  `example_detail_pages` уже отдаёт `booking_detail`/`stays_detail` через `DETAIL_ENTITIES`.)
- `site_home.html`: добавить `page-block[data-page-key="service_detail"]` и
  `[data-page-key="stay_detail"]` по образцу product (`:457-470`) с presence-guard-hidden
  (`sd_present`/`std_present`) — только hide-тоглы (order позже).
- `home_builder_view` save (`views.py:1045-1069`): добавить ветки для booking/stays по образцу
  product presence-guard; обобщить в один цикл по модулям с активным guard.
- `accept_preview_draft` (`views.py:1574-1579`): пропустить `booking_detail`/`stays_detail` из
  draft-JSON (как event/product).
- Пробросить конфиг в детали: `apps/booking/public_views.py` (service_detail view) +
  `apps/stays/public_views.py:255` — добавить в контекст `detail_hidden`/`detail_order`
  (потребляется UA4-2; в UA4-1 можно прокинуть, но не использовать — или отложить проброс
  до UA4-2, чтобы UA4-1 остался чисто builder-side. **Рекомендация: прокинуть в UA4-1** —
  нулевой визуальный эффект, но готовит почву и покрывается тестом round-trip).

## 6. Спец-секции (buy-box / галерея / buybar) остаются особыми

Галерея (`detail_gallery`), buy-box (`detail_aside`), buybar (`detail_buybar`) — НЕ в реестре
UA4-1. Они всегда присутствуют, живут в своих `{% block %}` (наследование, `detail.html:21-35`),
управляются U-A3 (buy-box) отдельно. Реестр покрывает только body-секции (`detail_body`/
`detail_wide`). Это фиксируется как инвариант: `DETAIL_SECTIONS[kind]` перечисляет ТОЛЬКО
body/wide секции. Продуктовая аномалия (`description`/`info` в aside) документируется как долг
для UA4-2 (§7).

## 7. Риски и особые случаи

1. **product `description`/`info` в `detail_aside`, не в body** (`product_detail.html:38,41`).
   Реестр UA4-1 их описывает (hide-only, как сейчас), но UA4-2 при переносе в body-цикл
   изменит РАСКЛАДКУ (описание уедет из sticky-aside в body). → В UA4-1 фиксируем как явный
   долг UA4-2; **UA4-1 не меняет расположение** (hide-флаг работает там же, где сейчас).
2. **`event_detail` пишется в двух местах** (`home_builder_view` + `pages_view`) — оба надо
   провести через общий хелпер, иначе разъедутся. Гейт: `test_pages_view.py:46` +
   `test_home_builder.py:729`.
3. **Бэк-компат нормализации** — общий для save И live-preview. Существующий product/event
   конфиг обязан нормализоваться идентично. Гейт: параметризованный паритет-тест
   (old `normalize_event_detail(x) == new normalize_detail_sections(x,"events")`).
4. **presence-guard** — при частичном POST не должно скрыться всё. Есть тесты
   `test_home_builder.py:838` (product), `:854` (event) — расширить на service/stay.
5. **order-vs-hide-only mismatch** — service/stay/product orderable=False. Реестр должен
   явно нести `orderable`, чтобы UA4-2 не начал их сортировать.

## 8. Инкрементальный, низко-регрессионный путь (слайсы, каждый — своя ветка/CI)

**Слайс A — Реестр + LABELS (zero behavior change).**
Новый `apps/core/detail_sections.py` (дескрипторы product+event, перенос LABELS). `views.py`
читает label из реестра (удалить `_EVENT_SECTION_LABELS`/`_PRODUCT_SECTION_LABELS`). Вывод
билдера и витрины неизменен.
- Файлы: `apps/core/detail_sections.py` (new), `apps/core/views.py` (labels←реестр,
  строки 1257-1271, 1737-1760, 1808-1819).
- Тесты: `apps/core/tests/test_home_builder.py` (инспектор рисует те же подписи),
  `apps/core/tests/test_archetypes.py` (импорт реестра не тянет модели).
- Гейт: инспектор event/product рендерит идентичные подписи; `_EVENT_SECTION_LABELS` больше
  нет.

**Слайс B — Обобщённый нормализатор (paritet event/product).**
`normalize_detail_sections`/`detail_section_order`/`detail_section_hidden` в `siteconfig.py`;
старые 4 функции → тонкие обёртки. `normalize()` вызывает обобщённо. Config-ключи и результат
байт-в-байт как раньше.
- Файлы: `apps/tenants/siteconfig.py` (523-580, 1289-1291).
- Тесты: `apps/core/tests/test_home_builder.py`, `apps/core/tests/test_live_preview.py`,
  `apps/tenants/tests/test_layout.py` (нормализация), новый параметрический паритет-тест.
- Гейт: `normalize({event_detail:...}) == прежний`; product hide-only без order.

**Слайс C — service+stay ключи + инспектор + save + preview round-trip.**
Добавить `service`/`stay` дескрипторы в реестр; `SCOPE_PAGE_KEY` +2; `page-block` service/stay
в site_home; save-ветки booking/stays (presence-guard); `accept_preview_draft` +2 ключа;
проброс `detail_hidden` в service/stay view (без визуального эффекта).
- Файлы: `apps/core/detail_sections.py`, `apps/core/views.py` (save 1045-1069, инспектор
  1257-1271), `templates/tenant/site_home.html` (SCOPE_PAGE_KEY 1665, page-blocks ~457),
  `apps/tenants/siteconfig.py` (normalize +2 модуля), `apps/booking/public_views.py`,
  `apps/stays/public_views.py:255`.
- Тесты: `apps/core/tests/test_home_builder.py` (save/inspector service+stay + presence-guard),
  `apps/core/tests/test_live_preview.py` (draft round-trip booking/stays),
  `apps/core/tests/test_preview_pages.py` (`booking_detail`/`stays_detail` группы).
- Гейт: round-trip POST И live-preview для 4 модулей без потерь; presence-guard для всех 4;
  витрина service/stay неизменна (снапшот).

**Слайс D (опц., граница UA4-1/UA4-2) — паритет-снапшоты как «замок» перед UA4-2.**
До миграции ЛЮБОГО тела в цикл — зафиксировать снапшоты текущего HTML детали для 4 kind
(проверка, что реестр НЕ изменил вывод). Служит гейтом входа в UA4-2.
- Тесты: `apps/catalog/tests/test_storefront.py`, `apps/booking/tests/test_public.py`,
  `apps/stays/tests/test_public.py`, `apps/events/tests/test_storefront.py` — assert на
  наличие/порядок секций (data-sf-section, заголовки) без изменений.

## 9. Критерии готовности UA4-1 (из плана U-A, §UA4-1)
- Один нормализатор `normalize_detail_sections` + `detail_section_order/hidden(config,module)`.
- KEYS совмещены с LABELS в `apps/core/detail_sections.py` (LABELS ушли из `views.py`).
- `SCOPE_PAGE_KEY` получил `booking_detail`/`stays_detail`.
- Round-trip через POST И live-preview без потерь для 4 модулей.
- **Бэк-компат:** существующий event/product-конфиг нормализуется идентично (параметрический
  паритет-тест — жёсткий гейт).
- Вывод витрины детали не изменился (снапшот-паритет) — рендер-цикл переносится в UA4-2.

## 10. Гейтящие тест-файлы (по шаблонам)
- product: `apps/catalog/tests/test_storefront.py`, `apps/promotions/tests/test_public.py`
- service: `apps/booking/tests/test_public.py`, `apps/booking/tests/test_services.py`
- stay: `apps/stays/tests/test_public.py`
- event: `apps/events/tests/test_storefront.py`
- builder/preview: `apps/core/tests/test_home_builder.py`, `test_live_preview.py`,
  `test_preview_pages.py`, `test_pages_view.py`; `apps/tenants/tests/test_layout.py`

## 11. Связанные
`docs/unified-sellable-entity-ua-plan-2026-06-30.md` (UA4-1/UA4-2) ·
`docs/unified-sellable-entity-master-track-2026-06-30.md` §3 U-A4 ·
`docs/storefront-onsite-editor-plan.md` (SE-2b-2, реестр секций) ·
`apps/tenants/siteconfig.py` · `apps/core/views.py` · `apps/core/sellable.py` ·
`templates/storefront/detail.html`.
