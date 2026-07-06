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

| Слайс | Что | Размер |
|---|---|---|
| 7a | siteconfig: PAGE_BLOCK_HOSTS + normalize_page_blocks + тег page_blocks + хосты в шаблонах + рендер-замки | M |
| 7b | Редактор: _cb_row партиал + строки page_blocks в форме + draft/save/инсертер с page_key + e2e | L |
| 7c | Drag в регионе + вставка БЕЗ перезагрузки (fetch → row-partial в форму + schedule) — закрывает и «применять без обновления» | M/L |
| 7d = UC6-6h | Настройки/примеры МЕНЮ в ленту (area-ribbon) | M |

## §5. Замки
- golden normalize (page_blocks отсутствует → байт-в-байт);
- normalize_page_blocks (whitelist/кап/чистка через _clean_cblock);
- рендер-замок: page_blocks на листинге/детали (тег);
- e2e: вставка блока на /termin/ → блок на канве → лента → Save → публикация.
