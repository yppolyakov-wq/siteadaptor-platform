# STU-12 — Студия без рейки: одна колонка, плашка действий, быстрые поповеры

**Дата:** 2026-09-09 · **Статус:** план-док до кода (решения владельца зафиксированы) ·
**Канвас:** «Studio heute» → страница «Final» (артборды F1–F3), «Panels» (P0–P10 — карта функций
и состояния), «Entscheidungen» (E0–E4B). **Предыстория:** `stu-studio-rework-plan-2026-09-03.md §9/§9a`.

## 0. Решения владельца (2026-09-08/09) — не пересматриваются

| Код | Решение |
|---|---|
| 1B | Глобальный дизайн (Look · Startpaket · Farbe & Schrift · Typografie · Karten & Fotos) — экран кабинета «Design des Shops», НЕ в Студии |
| 2B → снято | Уровень «Menü» отпал вместе с рейкой: шапка/подвал кликабельны на любой странице → колонка «Kopf- & Fußzeile» |
| 3A | «Seite: … ▾» в верхней строке для страниц, недостижимых кликом (Warenkorb, Kasse) + группы акций |
| 4A | Область «Start» (Layout-Vorlagen, Demo-Inhalte) → секция «Vorlagen» на экране кабинета |
| 1 | Левая рейка убрана целиком |
| 2 | Колонка настроек — справа, одна, без вкладок |
| F5A | Быстрые поповеры из плашки действий у блока: Stil · Raster · Breite (≤ 7 плиток) |
| F6A | Пункты меню (порядок/скрыть/переименовать) — в колонке Студии; подменю/цели — Menü-Generator |
| F7A | Телефон: настройки доступны (bottom-sheet + «⚙» в верхней строке) |
| F8A | Панель блока = Inhalt · Darstellung · Erweitert; тексты секции — при секции |
| F9 | Форма карточки для одной категории — открыто (рекомендация B: не расширять модель) |

## 1. Целевой хром (что видит владелец)

- **Верхняя строка:** ← Übersicht · Studio · «Seite: ‹имя› ▾» · ↶ ↷ · статус · 🖥 ▭ 📱 ·
  «Design des Shops →» · 🔗 Vorschau teilen · Speichern. Уходят: ⚙️ Vorlage · ☰ Menü · 🧱 Blöcke ·
  🔍 Kompakt · контекст блока `.bld-ctx` (переезжает в шапку колонки).
- **Канва:** живой сайт во всю ширину; клик по секции/блоку/шапке/подвалу/сетке/детали → колонка
  в нужном охвате + **плашка действий** над выбранным (имя · ▲ ▼ · 👁 · 🗑 для C-блоков ·
  Raster ▾ · Stil ▾ · Breite ▾ · ⚙); «+» между секциями (как сегодня); inline-редакторы
  текста/цены/даты/фото — без изменений.
- **Колонка (справа, 380 px, сворачивается шевроном):** ничего не выбрано → «Diese Seite: ‹тип›»
  (строки реестра; на главной — список секций + Banner + Startseite-Auswahl + аккордеон
  «Vorlagen & Versionen»); выбран блок → крошка «‹страница› › Abschnitt», имя, Einfach|Experte,
  группы Inhalt · Darstellung · Erweitert; клик по шапке → «Kopf- & Fußzeile» (Kopfzeile-пресет ·
  fest · CTA · Logo · Menüpunkte · Fußzeile); клик по галерее/логотипу/баннеру/обложке → «Medien».
- **Телефон:** верхняя строка + «⚙ Seite»; колонка и поповеры = bottom-sheet; плашка у блока видна
  всегда; ▲▼ в листах всегда; точка «не сохранено» у Speichern.

Карта «каждая функция: сегодня → новое место» — артборд «Funktionskarte» (`_generate.py::FMAP`);
после решения 1 все строки с меткой Rail читаются как «клик по канве / «+» / «Seite ▾»».

## 2. Инкременты (каждый мержится отдельно, БЕЗ миграций; замки — ДО кода)

| # | Инкремент | Суть | Замки (красные до правки) |
|---|---|---|---|
| 12a | Верхняя строка + снос рейки/ленты/вкладок | удалить `#st-rail`, `#st-pages`, `#bld-area-tabs`, кнопки ⚙️/☰/🧱/🔍; добавить «Seite ▾» (`preview_pages` + Kasse + `?gruppe=` по STU-7) и «Design des Shops →»; колонка по умолчанию ОТКРЫТА на настройках страницы (`stuPageArea()`), шеврон сворачивает | нет `#st-rail`/`#st-pages`/`#bld-area-tabs`; «Seite ▾» содержит Warenkorb и Kasse; вход = панель страницы; `test_studio_shell` переписан осознанно |
| 12b | Одна колонка вместо «область + лента» | `openBlockPopup` рендерит блок В ТОЙ ЖЕ колонке: крошка + имя (C-блоки — переведённые имена) + Einfach|Experte + «‹» назад; `.bld-ctx` из верхней строки удалён; Esc: блок → страница | крошка и имя в колонке; `.bld-ctx` отсутствует; строка формы по-прежнему ПЕРЕНОСИТСЯ (число `name=` в `#home-form` неизменно — W0) |
| 12c | Шапка/подвал кликабельны | `data-sf-section="header"/"footer"` на витрине → колонка «Kopf- & Fußzeile»: `nav_style`/sticky/пресеты (область menu), Logo, Fußzeile; **новое** поле `nav_cta` + `nav_cta_present`; Menüpunkte-лист (F6A): `menus_json` в `#home-form`, свежая загрузка при открытии, presence-guard, подменю/цели — только Menü-Generator | клик по шапке открывает колонку Kopf; сохранение без `menus_json` не трогает `menus` (W6); CTA presence-safe |
| 12d | Плашка действий + быстрые поповеры (F5A) | плавающий контейнер у выбранного элемента (масштаб канвы учтён: `applyDevice` scale; перепозиционирование после load/hard-reload); поповеры Stil/Raster/Breite = DOM-перенос существующих контролов (`style_*`, `layout_preset_*`, `width_cb_*`), закрытие Esc/клик мимо/выбор; открываются НАД плашкой при нехватке места | контролы не дублируются (счётчик `name=`); поповер закрыт → контрол вернулся в строку; позиция учитывает scale (юнит на `placePopover`) |
| 12e | Группы Inhalt · Darstellung · Erweitert (F8A) | тексты секций из `_section_fields.html` (faq/team/testimonials/process/trust/usp/cta), hero_title/text/image из области Banner, карточки архетипов — в строку СВОЕЙ секции (те же `name=`); Erweitert = `[data-expert]`; высота Abstand редактируема; после вставки блока сразу открывать его колонку | golden normalize цел; `collect()` payload байт-в-байт до/после переноса; Abstand height round-trip |
| 12f | Medien + Kategorie-Popover | 4 out-of-form медиа-области аккордеоном в колонке «Medien» (вход: клик по галерее/логотипу/баннеру/обложке); каждая форма несёт `page_path`; `catalog-add` — поповер из плашки секции Kategorien | после upload канва возвращается на ту же страницу; поповер add_category создаёт категорию |
| 12g | 1B/4A на сервере и в кабинете | экран `/dashboard/design/`: + Farbe & Schrift · Typografie · Karten & Fotos · Vorlagen (Layout) · Demo-Inhalte (с сентинелами `sd_page_bg_present`/`quick_add_present`/`wishlist_present`); **`apply_look` — только оптика** (сегодня сбрасывает порядок секций); `collect()` черновика НЕ шлёт ключи темы; области theme/quickstart/library-links удалены из Студии; «Vorlagen & Versionen» — аккордеон панели главной | apply_look не меняет `sections`; draft-payload без `accent/font/typography/sd_*/theme`; Save Студии не роняет ключи темы (W6-класс) |
| 12h | Телефон (F7A) | «⚙ Seite» в верхней строке; bottom-sheet для колонки и поповеров; плашка видна на тач; ▲▼ всегда; точка статуса; `isNarrow` пересчитывается при resize | стенд 390 px: T2/T1-эквиваленты |
| 12i | Стенд + доки | Playwright по 19 типам страниц × 3 ширины (главная/категория/группа акций/деталь/Warenkorb через «Seite ▾»), build-log, CLAUDE.md, task-catalog | 0 проблем стенда |

Порядок: 12a → 12b → 12c → 12d → 12e → 12f → 12g → 12h → 12i. 12g можно вести параллельно с 12c–12f
(другие файлы: `design.html`/`design_view`/`sitetemplates.apply_look`).

## 3. Инварианты и грабли (из инвентаризации и адверсариальной проверки)

- **W0:** все поля остаются в `#home-form`; поповеры/колонка ПЕРЕНОСЯТ строки (паттерн `openBlockPopup`
  с комментарием-якорем), никогда не клонируют; presence-сентинелы (`cl_present`, `cf_present`,
  `pb_present`, `pd_present`, `sd_present`, `std_present`, `cart_present`, `tw_present`, …) — вне строк.
- **W6:** Save не роняет чужие ключи; `menus` пишется только при валидном `menus_json`; тема после
  1B — ключи не в черновике и не в Save Студии.
- **Масштаб канвы:** desktop = 1280 логических × `scale`; «+» уже имеет латентное расхождение —
  общий `placePopover(rect)` с учётом scale, перепозиционирование после load/hard-reload (Nur hier).
- **Коллизия ключей на подстраницах:** `openBlockPopup` ищет `.home-block` раньше `.page-block`
  (services/events/stay_rooms/reviews) — искать `.page-block[data-page-key]` первым.
- **Esc:** внутри-первым (поповер → блок → страница); клик внутри iframe = «клик мимо» для поповера.
- **Locks к переписке (осознанно):** `test_studio_shell` (rail/pages/tabs), панельные ассерты
  `test_home_builder` (~41 ссылки на ids — ids колонки сохранить), `test_studio_pages` (67 — реестр↔
  разметка остаётся, меняется только контейнер), `test_registry_and_panel_agree` — зелёный.
- **Локализация:** новые msgid (крошки, имена C-блоков, «Design des Shops», «Kopf- & Fußzeile»,
  плашка) × 5 каталогов; `i18n_quickcheck` перед пушем.

## 4. Открытое

- **F9** — форма карточки для одной категории (нужно поле `Category.card_style` + резолвер
  товар → категория → сайт). Рекомендация: B (не делать), пока нет спроса.
- «Vorlagen & Versionen»: аккордеон панели главной (план) vs «⋯» в верхней строке — решается в 12g.
