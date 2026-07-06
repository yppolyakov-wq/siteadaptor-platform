# UC6-7 — канва/C-блоки/шаблоны НА ВСЕХ страницах (план, 2026-07-06)

Отмашка владельца (2026-07-06): «Редактирование блоков и контента есть только
на главной. Должно быть на всех. Весь функционал главной, канва и т.д. должен
работать на всех страницах». Снимает блокировку пакета UC2-3(b)+UC3-2+слайс 3
UC2-2 (см. `uc2-3-page-scope-plan §3`, `uc2-2-oncanvas-plan §2`).

## §1. Архитектура хранения (ключевое решение)

**НЕ трогаем `config["sections"]`** (home-only, горячее место golden-замков).
Новый top-level ключ:

```
config["page_blocks"] = { "<page_key>": [ <cblock-entry>, … ], … }
```

- `page_key` — группы существующего реестра страниц (catalog, events,
  stay_rooms, services, cart, event_detail, product_detail, service_detail,
  stay_detail, info, blog, …) — whitelist `PAGE_BLOCK_HOSTS` в siteconfig.
  ⚠️ legal-страницы НЕ входят (право должно быть видимым, DACH-риск —
  решение из uc2-3-плана сохраняем).
- Каждый entry — тот же `_clean_cblock` (типы/данные/width/pos/newline/visual/
  style_hint — весь функционал главной автоматически). Кап на страницу —
  `_MAX_CBLOCKS`.
- `normalize_page_blocks(raw)`: dict→whitelist→список через `_clean_cblock`;
  отсутствие ключа = `{}` → старые конфиги байт-в-байт (golden живы).

## §2. Рендер

Тег `{% page_blocks "<page_key>" %}` (siteui):
- сам резолвит site_config (+ сессионный черновик при `?preview=1` — паттерн
  storefront_home), берёт `page_blocks[page_key]`,
- рендерит через `group_block_rows` + `_section_block.html` (обёртки
  `data-sf-section="<id>"` → клик→лента, 📷, инлайн — работают БЕСПЛАТНО).

Хосты v1 (один регион на страницу, после основного контента):
- `listing.html` (4 листинга разом — блок `after`),
- `detail.html`-каркас (service/stay/event) + `product_detail`,
- `cart`, `about` (info), `blog_index`.

## §3. Редактор

- **Форма**: cb-row вынесен в партиал `tenant/_cb_row.html`; рендерится для
  home-cblocks (как сейчас) И для всех `page_blocks` (+ hidden
  `pb_page_<id>=<page_key>`); `applyPageScope` показывает строки только
  текущей группы (имена `cb_<id>_*` глобально уникальны по id).
- **Черновик**: collect() += `page_blocks` (сбор по pb_page_*);
  `site_preview_draft` — ветка page_blocks (реюз cblock-ветки).
- **Save**: POST-парсер собирает `page_blocks` по `pb_page_*` (те же
  `_read_cblock_data`/width/pos/newline/visual).
- **Инсертер «+»**: гейт `previewPath === "/"` снимается; на не-home «+»
  зоны вешаются на блоки хоста (+ пустой хост получает якорную «+»-зону);
  `add_block` несёт `page_key` (из PAGE_GROUPS по previewPath) → сервер
  кладёт в `page_blocks[page_key]` (insert_after по id). Пресеты/демо/
  миниатюры — те же (реюз).
- **Drag** внутри региона — слайс 7c (value-based по индексам).

## §4. Слайсы

| Слайс | Что | Размер | Статус |
|---|---|---|---|
| 7a | siteconfig: PAGE_BLOCK_HOSTS + normalize_page_blocks + тег page_blocks + хосты в шаблонах + рендер-замки | M | ✅ (main 1f110b9) |
| 7b | Редактор: _cb_row партиал + строки page_blocks в форме + draft/save/инсертер с page_key + e2e | L | ✅ |
| 7c | Drag в регионе + вставка БЕЗ перезагрузки (fetch → row-partial в форму + schedule) — закрывает и «применять без обновления» | M/L | — |
| 7d = UC6-6h | Настройки/примеры МЕНЮ в ленту (area-ribbon) | M | — |

### 7b — как сделано (2026-07-06)

- **Партиал `templates/tenant/_cb_row.html`** — разметка строки C-блока вынесена 1:1
  из `site_home.html`; переключатель `pb_page`: при заданном хосте рендерит `pb_id` +
  `pb_page_<id>=<host>` + `data-pb-page` на `.cb-row` (вместо `cb_id`). Имена полей
  (`cb_<id>_*`, `order_cb_<id>`, `width_cb_<id>`, `visual_*_cb_<id>`) глобально
  уникальны по id → collect()/save/save-as-template работают без переименований.
- **GET-контекст** `page_cblocks = [{page_key, blocks:[…]}]` — по `PAGE_BLOCK_HOSTS`
  (стабильный порядок), только хосты с блоками; рендерятся в наборе «Landing pages»
  (`data-scope="landing"`), скрытие — существующим `applyPageScope` по `data-page-key`.
- **Save**: `_cblock_entry_from_post(post, bid, btype)` — общий билдер entry (data +
  width/pos/newline/visual) для главной И страниц; page-ветка под presence-guard
  `pb_present=1` пересобирает `config["page_blocks"]` из `pb_id`-строк (host из
  `pb_page_<id>`, whitelist, сортировка по order, удаление по `delete_cb_`); пустой
  хост исчезает; POST без guard не трогает конфиг страниц.
- **Draft**: `collect()` — `buildCbEntry(id)` (общий), home-ветка пропускает
  pb-строки (`pb_page_<id>` present → null), отдельный свип `.cb-row[data-pb-page]`
  → `payload.page_blocks={host:[…]}` (шлёт все хосты, вкл. опустевшие → удаление
  видно в превью); server passthrough `cfg["page_blocks"]=data["page_blocks"]`,
  чистит `normalize_page_blocks`.
- **Инсертер «+»**: гейт снят на страницах с `curPbHost` (из `data-pb-host` кадра;
  drag остаётся home-only до 7c); `add_block`/`use_block_template` несут `page_key`
  (=curPbHost) + `page_path` → кладут в `page_blocks[host]` (`insert_after` по id;
  якорь `pbhost:<key>` пустой страницы → append), редирект `_redirect_builder`
  возвращает канву на ту же страницу (`?page=` через `_safe_preview_page`).
- **`page_path`** — скрытое поле `#home-form`, JS синкает при навигации кадра →
  Save/действия ленты возвращают канву на текущую страницу.
- **Замки**: `test_cblocks_builder.py` +7 (add с page_key/unknown-key-фолбэк/
  insert_after/template/save-rebuild/presence-guard/GET-рендер), `test_live_preview.py`
  +1 (draft passthrough + чистка), e2e verify_7b.js (вставка на /ueber-uns/ → канва →
  лента → Save → публикация; 0 JS-ошибок).

## §5. Замки
- golden normalize (page_blocks отсутствует → байт-в-байт);
- normalize_page_blocks (whitelist/кап/чистка через _clean_cblock);
- рендер-замок: page_blocks на листинге/детали (тег);
- e2e: вставка блока на /termin/ → блок на канве → лента → Save → публикация.

## §6. Слайс 7c — drag в регионе + вставка БЕЗ перезагрузки (план реализации)

Закрывает и явный пункт владельца «при выборе настроек можно ли не обновлять
страницу, а применять автоматом» + «при добавлении материала он скрывается внизу».

**7c-1 (drag внутри региона страницы).** Сейчас drag-on-canvas гейтится
`previewPath === "/"` (E.4, ~site_home.html:2421) и переставляет `order_<key>`
секций главной. Для страниц: снять гейт при `curPbHost`, но целевой набор — НЕ
секции главной, а `order_cb_<id>` строк ТЕКУЩЕГО хоста. Механизм по образцу
`moveEdSection` (value-based по индексам): собрать `.cb-row[data-pb-page="<host>"]`
input'ы `order_cb_*`, переставить значения, `schedule()` (live-preview
перерисуется из payload.page_blocks). Ручка ⠿ вешается на `[data-sf-section]`
блоки внутри `[data-pb-host]`. Публикация — обычный Save (значения order уже в
форме). Замок: e2e drag 2 блоков на /blog/ → порядок в черновике/после Save.

**7c-2 (вставка без перезагрузки).** Сейчас инсертер делает форм-POST → редирект
(перезагрузка билдера). Заменить на fetch:
- новый JSON-эндпоинт `site_cblock_add` (или расширить существующий add_block
  веткой `X-Requested-With: fetch` → отдаёт `{id, host, row_html}` вместо
  redirect); `row_html` = рендер `_cb_row.html` нового блока (с `pb_page` для
  страниц) + серверный рендер `_section_block.html` для вставки в кадр.
- клиент: вставить `row_html` в форму (в нужный `.page-block[data-page-key]`
  контейнер или home cblocks details), навесить обработчики (openBlockPopup,
  visual-синк), затем `schedule()` — черновик перерисует кадр С новым блоком БЕЗ
  полной перезагрузки билдера. Позицию (`add_after`) сервер уже поддерживает.
- fallback: при сетевой ошибке — старый форм-POST (не потерять вставку).
Риск: дублирование логики рендера строки (форма) и блока (кадр). Митигция:
`row_html` из того же `_cb_row.html`; кадр перерисовывается через `schedule()`
(не ручная вставка в iframe — меньше рассинхрона).
Замок: e2e вставка на /blog/ БЕЗ навигации (URL билдера не меняется) → блок в
кадре + строка в форме + Save публикует.

**7c-3 (авто-применение настроек — уже частично есть).** Правки полей блока в
ленте уже идут в `schedule()` → live-preview без перезагрузки (D2b). Проверить,
что ВСЕ контролы строки (width/pos/visual/style_hint) слушаются `schedule` —
добавить недостающие `change`-листенеры на новые селекты, если где-то только на
Save. Замок: изменение width блока страницы → кадр обновился без Save.

**Порядок:** 7c-2 (вставка без перезагрузки — самый заметный UX) → 7c-1 (drag) →
7c-3 (доводка листенеров). Каждый — свой e2e; батч-гейт как в 7b.
