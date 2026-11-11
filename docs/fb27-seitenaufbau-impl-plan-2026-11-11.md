# FB-27 · «Seitenaufbau» — план реализации (2026-11-11)

Автор — агент `planner` (ECC) по решениям владельца из
`docs/fb27-website-pages-ia-plan-2026-11-11.md` (§5, обе таблицы опросников), a11y-отчёту §4 и
макетам `docs/design/website-seiten-2026-11-11/` (Main, L2, L3, L4). Кода нет. Миграции **не нужны
ни в одном инкременте** (всё в `site_config`, ключи presence-minimal). Ссылки file:line — по
состоянию на дату плана, перед каждым инкрементом сверять.

## A. Разведка: что движок уже умеет, а что новое

### A.1 Схема и выбор типа
- **Есть.** Главная — `sections`, остальные — `page_blocks[<хост>]`, маркер «Hauptliste»
  `{"key":"main"}` (`apps/tenants/siteconfig.py:1194-1239`, `normalize_page_blocks` 1256-1290).
  Сервис FB-25 — `apps/core/site_schema.py`: `blocks_for` 165-217, `apply` 234-308 (под
  `select_for_update`, `realign_block_overlays` на все хосты 296-305), `text_pages`/`host_for`
  114-162. Экран — `apps/core/site_schema_views.py:15-65`.
- **Дефект.** `page_rows` (`site_schema.py:70-86`) перебирает все `PAGE_TYPES` без модулей. Фильтр
  есть только в `page_settings.active_types` (475-481), но он требует «есть настройка кабинета» и
  выбросил бы типы с блоками без настроек (`gift`, `loyalty`, `anfrage`…). Нужен
  `structure_types(tenant)` = `type_active(t)` (463-472) **и** (есть настройки **или** `block_host`).
- **Новое.** Порядок «главное для бизнеса первым», optgroup в select; в том же select — категории
  (`category@<slug>`) и текстовые страницы (`text@<хост>` уже есть).

### A.2 Ширины и авто-ряды
- **Уже работает на всех хостах.** Тег `page_blocks` (`apps/tenants/templatetags/siteui.py:303-347`)
  зовёт `group_block_rows`; партиал `templates/storefront/_page_blocks.html:5-16` рисует ряды;
  `CBLOCK_WIDTHS`/`NARROW_WIDTHS` (`siteconfig.py:604-606`) включают ⅕ и ⅙; `newline` хранится
  (`_clean_cblock` 1051-1081). Утверждение IA-плана «только на главной» **неверно для C-блоков** —
  не хватает только UI.
- **Пробелы.** (1) Фикс-секции главной: только `contained/full` — совпадает с «сетки на всю
  ширину». (2) Блок `list` — C-блок, сегодня сужается; решение «списки целиком» требует клампа (Q1).
  (3) `full` (во весь экран) у живых блоков — показывать «Ganz (randlos)», только если уже выбран.

### A.3 Блок «Liste» и ручной отбор
- **Есть.** 10 источников `LIST_SOURCES` (`siteconfig.py:202-281`), фильтры `_clean_list_block`
  334-428, выборки `_FETCHERS` (`apps/core/list_blocks.py:720-731`), `resolve` 741-793,
  `library_presets` 1473.
- **Нет ручного выбора.** `data["pick"] = [uuid, …]` (≤ `LIST_LIMIT_MAX = 24`), ключ только при
  непустом; в normalize — только формат UUID, без БД. Выборка `pk__in=pick` + фильтр активности
  источника, порядок по индексу. Исчезнувшие объекты молча выпадают на витрине, в панели —
  «nicht mehr verfügbar · entfernen». При `pick` правило хранится (возврат на «Regel» его вернёт).

### A.4 Hauptliste пишет `page_settings`
- **Есть.** `schema()` 484-525, `validate` 613-628, `apply_override` 554-610, единственный писатель
  `write` 631-651, `output_payload` 198-216.
- **Новое.** `write_many(tenant, pending)` в том же модуле: одна блокировка, все ключи разом.
- «Главная строка» есть и у деталей («Produktdetails»), текстовых типов («Seiteninhalt»,
  `text_width`) и главной (`home_hero` в строке баннера).

### A.5 Черновик — три варианта

| | Где | Плюсы | Минусы |
|---|---|---|---|
| **V1 (рекомендация)** | сессия `aufbau_draft[code] = {base, items, settings, ts}` | не пишет `site_config`, нет гонки со Студией | теряется при закрытии браузера, не переходит между устройствами |
| V2 | `site_config["_aufbau_drafts"]` | переживает браузер и устройство | автосейв Студии пишет `{**published}` из устаревшего `request.tenant` (`views.py:3986`) и сотрёт ключ — гонка W6 |
| V3 | общий `site_preview_draft` | одно превью | «Verwerfen» одного экрана стирает работу другого |

V1: `base` — sha1 сохранённого состояния на момент первой правки (на «Speichern» при расхождении —
экран конфликта); счётчик — дифф против сохранённого; превью `?preview=1&aufbau=<code>` — новая
ветка `preview_raw` (`page_settings.py:684-714`) под `_may_preview`, игнорирует черновик Студии.

### A.6 Граница со Студией
- **Два писателя одних ключей уже есть.** Save Студии пересобирает `sections` (`views.py:2508-2636`)
  и все хосты `page_blocks` (2642-2680); FB-25 пишет те же ключи. Открытая вкладка Студии откатит
  схему. Автосейв (3758, 3990-3996) делает `{**published}` из данных начала запроса.
- `protect_owned` (`page_settings.py:790-822`) защищает настройки, но не структуру.
- **Цель.** Seitenaufbau владеет структурой (порядок, enabled, width/pos/newline, состав, оси
  списков, настройки типов); Студия — тексты, фото, стили блока. До R8 — предохранитель R0.

### A.7 Другие находки
- Категория сегодня **складывает** блоки `catalog` и `catalog:<slug>` (`products.html:310, 336`) — Q2.
- Общий потолок 40 хостов (`siteconfig.py:1167`) для `catalog:*` и `seite:*` — свои категории могут
  вытеснить блоки страниц.
- Смена слага категории делает её блоки сиротами (для страниц перенос есть —
  `content_pages.move_page_blocks`).
- «Produkte» главной — фикс-секция, «Was zeigen» её не переключит (Q4).
- `_cblock_entry_from_post` (`views.py:838-867`) сбрасывает `visual`/`font`/`hidden_on`, если полей
  нет в POST → панель обязана патчить, а не пересобирать (W0).
- Студия в меню — сам якорь Website (`nav_registry.py:132-139`); убрать = `targets=("design",)`.
- Новые C-блоки: «Kontakt & Öffnungszeiten», «Textseite»; «Häufige Fragen» = `faq_ref`.

## B. Архитектура экрана

- **URL и имя остаются:** `dashboard/site/aufbau/`, `name="site-schema"` — старый Seitenaufbau
  заменяется на месте; 302 получают только Seitenvorlagen.
- **Сервисы.** `site_schema.py` (расширяем: `structure_types`, ряды, сводки строк без запросов,
  «Ausgeblendet», фикс-строки) · новый `apps/core/aufbau_draft.py` (`load/op/settings/diff/commit/
  discard`; `commit` — одна транзакция) · новый `apps/core/block_forms.py` (вынос
  `_read_cblock_data`/`_LIST_BLOCK_FIELDS`/`_save_builtin_list_data` из `views.py:695-835` — один
  разбор для Студии и панели).
- **POST — операции с PRG.** `op` = `select|toggle|hide|remove|up|down|move|add|add_row|update|
  settings|pick_add|pick_up|pick_down|pick_remove|save|discard`; всё, кроме `save`/`discard`, меняет
  только черновик; ответ 303 на `?seite=&block=`.
- **Рендер.** Сервер; панель — `?block=<ref>` (`?fragment=panel` — партиал); `?ansicht=telefon`.
  Без JS всё работает (select с кнопкой, панель под схемой, подтверждение — отдельный шаг).
- **JS** `static/js/aufbau.js`: смена типа с вопросом о несохранённом, fetch-своп по контракту
  шторки (`docs/references/patterns/drawer.md`), нижний лист, поиск «Einzeln», Escape/фокус.

## C. Инкременты

Общее: скиллы `django-patterns`, `django-tdd`, `accessibility` до кода; `django-reviewer` перед
мержем; гейт — ruff, pytest затронутых модулей, `i18n_quickcheck`, `test_template_comments`,
`npm run build:css`.

| № | Цель | Замки до кода | ECC |
|---|---|---|---|
| **R0** Предохранители | автосейв Студии читает свежую строку; Save Студии сверяет `structure_hash` | автосейв не стирает схему; устаревший хэш → отказ без потери; характеризация FB-25 `apply` | `django-reviewer`, `silent-failure-hunter` |
| **R1** Экран, паритет FB-25 | select `structure_types` (порядок, группы, категории, страницы); схема рядами; «Ausgeblendet»; панель read-only; «Ausblenden»/«Entfernen» раздельно; кнопки «Auf der Seite bearbeiten», «Vorschau» | отель не видит «Katalog», магазин — «Zimmer»; ряды = `group_block_rows`; цели ≥ 44 px; лёгкий пакет | `a11y-architect`, Playwright 1440/390 |
| **R2** Черновик | операции в черновик; Speichern/Verwerfen/счётчик; конфликт `base`; вопрос при смене типа; превью `?aufbau=` | до Save витрина не меняется; конфликт без перезаписи; `?aufbau=` у анонима игнорируется; переводы целы | `security-reviewer` |
| **R3** Панель блока | Was · Welche · Wie · Breite; ширины до ⅙ + «Neue Zeile»; текст/фото/кнопка в панели; запись патчем | round-trip полей; `visual` не стирается; живой `full` цел; golden | `a11y-architect`, Playwright |
| **R4** Главная строка + снос Seitenvorlagen | настройки типа в панели «Hauptliste/Produktdetails/Seiteninhalt/Banner»; `write_many`; Seitenvorlagen → 302 | каждая настройка `schema()` достижима; одна транзакция; старые адреса 302; нет NoReverseMatch | `security-reviewer` |
| **R5** «Einzeln» | `data.pick` для 7 источников; поиск `?lookup=`; порядок; пометка исчезнувших | мусорный UUID не роняет; удалённый выпадает; один запрос на блок; lookup без неактивного | `security-reviewer`, `database-reviewer` |
| **R6** Новые блоки и «+ Block» | `textpage` (full/teaser), `contact`; меню в три группы; «Fertige Zeilen» | страница не встраивается в себя; смена слага не ломает; каждый пресет проходит normalize | `a11y-architect`, Playwright |
| **R7** Схема категории | `category@<slug>`; семантика Q2; перенос при смене слага; раздельные потолки хостов | 41-я категория не вытесняет страницы; переименование хранит блоки | `database-reviewer` |
| **R8** Граница со Студией, меню | Save Студии — только содержимое; контролы структуры в Студии → ссылка; `targets=("design",)` | Save Студии не меняет порядок, но хранит текст; инлайн-правка жива; достижимость `site-home` | `silent-failure-hunter`, Playwright (риск высокий) |
| **R9** Стенд и документы | сценарий владельца 1440/390, de/ru, без JS, 5 архетипов; обход всех типов | — | `e2e-runner`, `doc-updater` |

## D. Что сносится и в каком порядке

1. **R4 — сначала точки `reverse`:** `page_templates.cabinet_url` (80-88), `setup_assistant.py:571,
   646, 860`, `assistant_actions.py:200` → `site-schema`.
2. **R4 — вьюха `page_templates_website` → 302**; `setup_plan_for` остаётся.
3. **R4 — удаляются** `_render` (240-329) и `templates/tenant/page_templates.html`; хелперы превью
   переезжают в `site_schema`.
4. **R4 — `nav_registry`:** запись `page-templates-website` удаляется; имена → `EXPECTED_UNLISTED`.
5. **R1/R4 — тесты, переписываемые осознанно:** `test_fb25_site_schema.py`,
   `test_m21_11_schema_pages.py`, `test_m21_11_page_type.py:70`, `test_page_templates.py`,
   `test_stu19f_grid.py`, `test_dl19_studio.py`, `test_dl20_studio.py`, `test_dl21_studio.py`,
   `test_lay3b_ui.py`, `test_stu19e_ownership.py:63,74`, `tenants/tests/test_price_list.py:283`.
6. **R8 — тесты меню:** `test_sidebar_st4b.py:213-231`, `test_x0_x7_locks.py:45,69-70`,
   `test_ka_w2_nav_locks.py:30`, `test_menu_label_equals_h1.py:25`, `test_w11_5_redirect.py:106`.

## E. Вопросы владельцу и риски

- **Q1. Узкие списки.** «Сетки на всю ширину» расходится с макетами («Kategorien ⅔»).
  Рекомендация: списки — Ganz, ⅔ или ½; простые блоки — до ⅙.
- **Q2. Своя схема категории: заменяет или добавляет** блоки каталога? Рекомендация: заменяет,
  с кнопкой «Aufbau vom Katalog übernehmen».
- **Q3. Черновик в сессии** (теряется при закрытии браузера, не переходит с телефона на ПК).
  Рекомендация: сессия в v1.
- **Q4. Встроенные секции главной:** «Was zeigen» только чтение, смена источника — «Als eigenen
  Block kopieren». Рекомендация: да.
- **Q5. Студия = только тексты/фото/стили**; порядок секций детали товара/услуги тоже в
  Seitenaufbau. Рекомендация: да на оба.

Риски: (1) два писателя `sections`/`page_blocks` → R0, R8; (2) сдвиг переводов при перестановке →
`realign_block_overlays` по всем хостам; (3) W0 — панель с частью полей стирает остальные → патч и
сентинелы; (4) общий потолок 40 хостов → R7; (5) сироты при смене слага категории → R7;
(6) волна переписки замков и `reverse` при сносе → порядок §D; (7) цена рендера и превью — сводки
без фетчеров, `?aufbau=` только под `_may_preview`.
