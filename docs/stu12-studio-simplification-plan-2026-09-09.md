# STU-12 — ТЗ: Студия без рейки (одна колонка, плашка действий, быстрые поповеры, глобальный дизайн в кабинете)

**Дата:** 2026-09-09 · **Статус:** ТЗ утверждено владельцем, разработка идёт · **Ветка:** `claude/aktionsmarkt-analysis-45t2vu`
(FF-мерж в `main` по зелёному CI после каждого инкремента — правило владельца) · **Источник правды по
решениям:** этот файл, §0 · **Канвас:** «Studio heute» (страницы «Final» → «Panels» → «Entscheidungen»),
исходники `docs/design/studio-2026-09-07/_generate.py` (артборды F1–F3, P0–P10, E0–E4B; карта функций —
константа `FMAP`) · **Предыстория:** `stu-studio-rework-plan-2026-09-03.md §9/§9a`.

> Этот документ самодостаточен: новая сессия обязана продолжить работу по нему без чата. Перед каждым
> инкрементом — §6 «Как возобновить», затем §2 (инкремент) и §3 (инварианты).

## 0. Решения владельца (2026-09-08/09) — не пересматриваются

| Код | Решение |
|---|---|
| 1B | Глобальный дизайн (Look · Startpaket · Farbe & Schrift · Typografie · Karten & Fotos · Seitenhintergrund) — экран кабинета «Design des Shops» (`/dashboard/design/`), НЕ в Студии. Живого превью там нет — принято осознанно; превью-плитки (iframe) как сегодня |
| 2B → снято | Уровень «Menü» отпал вместе с рейкой: шапка и подвал кликабельны на ЛЮБОЙ странице → колонка «Kopf- & Fußzeile» |
| 3A | «Seite: ‹имя› ▾» в верхней строке — для страниц, недостижимых кликом (Warenkorb, Kasse) + группы акций (`?gruppe=`) |
| 4A | Область «Start» (Layout-Vorlagen, Demo-Inhalte) → секция «Vorlagen» на экране кабинета «Design des Shops» |
| 1 | Левая рейка убрана ЦЕЛИКОМ (все её функции = клик по канве, «+», «Seite ▾») |
| 2 | Колонка настроек — СПРАВА, одна, без вкладок |
| F5A | Быстрые поповеры из плашки действий у выбранного блока: Stil · Raster · Breite (≤ 7 плиток, те же поля формы) |
| F6A | Пункты меню (порядок / скрыть / переименовать) — в колонке Студии при клике по шапке; подменю и цели ссылок — Menü-Generator |
| F7A | Телефон: настройки доступны (bottom-sheet + «⚙ Seite» в верхней строке) |
| F8A | Панель блока = группы Inhalt · Darstellung · Erweitert; тексты секции (FAQ, Team, CTA …) — при самой секции |
| F9 | **Делаем**: форма карточки для одной категории (`Category.card_style`, ⚠️ миграция) с порядком товар → категория → сайт |

Ранее согласованное остаётся: один вход в дизайн · настройки типа страницы — из реестра
`apps/core/studio_pages.py` · канва = живой сайт · пилюля охвата «Für alle / Nur hier» рядом с контролом ·
Einfach|Experte РЕДАКТОРА остаётся (решение владельца при SM-1).

## 1. Целевое поведение (что видит владелец)

**Верхняя строка:** `← Übersicht` · `Studio` · **«Seite: ‹имя› ▾»** · `↶ ↷` · статус · `🖥 ▭ 📱` ·
**«Design des Shops →»** · `🔗 Vorschau teilen` · `Speichern`. Уходят: `⚙️ Vorlage`, `☰ Menü`, `🧱 Blöcke`,
`🔍 Kompakt`, контекст блока `.bld-ctx` (переезжает в шапку колонки).

**Канва:** живой сайт во всю ширину (слева ничего нет). Клик по секции / C-блоку / шапке / подвалу / сетке
листинга / корню детали → колонка переключается в нужный охват И над выбранным появляется **плашка
действий** (тёмная, как макет P3): `имя` · `▲ ▼` · `👁` · `🗑` (только C-блоки) · `Raster ▾` (сетки) ·
`Stil ▾` (секции со стилями) · `Breite ▾` (C-блоки) · `⚙` (= колонка). «+» между секциями и inline-редакторы
текста/цены/даты/фото — без изменений; после вставки блока сразу открывается его колонка.

**Колонка (справа, `--bld-panel-w` 380 px, шеврон сворачивает, ресайз остаётся):**
- ничего не выбрано → **«Diese Seite: ‹тип›»**: строки реестра типа (как сегодня, без вкладок); на главной —
  список секций (⠿ · имя · 👁; клик по имени = выбрать секцию) + `Banner-Stil` + `Was Besucher zuerst sehen`
  (storefront_root) + аккордеон «Vorlagen & Versionen» (шаблоны страниц, Versionsverlauf, «Seite als Vorlage»);
- выбран блок → крошка `‹страница› › Abschnitt`, имя блока (C-блоки — ПЕРЕВЕДЁННЫЕ имена), `Einfach|Experte`,
  `⋯` (плотность = бывший 🔍 Kompakt), `✕`; тело — аккордеоны **Inhalt · Darstellung · Erweitert**
  (Erweitert виден в Experte);
- клик по шапке/подвалу → **«Kopf- & Fußzeile»** с крошкой «Website › gilt auf allen Seiten»: пресет шапки
  (Classic/Zentriert/Minimal) · Feste Kopfzeile · **CTA-Button** (новое поле) · Logo · **Menüpunkte** (список
  ⠿/👁/имя, «＋ Punkt»; подменю → Menü-Generator) · Fußzeile;
- клик по галерее / логотипу / баннеру / обложке раздела → **«Medien»** (Fotogalerie · Banner-Slides ·
  Titelbilder · Logo аккордеоном; формы вне `#home-form`, несут `page_path`).

**Телефон (< 1024 px):** верхняя строка `← · ↶↷ · Seite ▾ · ⚙ · ● · Speichern`; колонка и поповеры —
bottom-sheet (существующие правила 78vh/55vh + backdrop); плашка у блока видна без hover; `▲▼` в листах
всегда; точка `●` «не сохранено» у Speichern; `isNarrow` пересчитывается при resize.

### 1a. Карта функций: сегодня → новое место (из `FMAP`; после решения 1 «Rail» читается как «клик по канве»)

| Функция | Сегодня | Новое место | Где |
|---|---|---|---|
| Rail «Design» | → область Theme | уходит; ссылка «Design des Shops →» в верхней строке → экран кабинета (1B) | Kabinett |
| Rail «Seite ‹тип›» | область sections/page + лента страниц внизу | рейки нет → открывает панель «Diese Seite: ‹тип›»; ленты нет | Canvas |
| Rail «Blöcke» | поповер «+» (в конец страницы) | рейки нет → тот же поповер вставки у кнопки рейки; после вставки сразу открывается панель нового блока (сегодня — ничего); на страницах без хоста блоков кнопка серая | Canvas |
| Rail «Medien» | только Fotogalerie | рейки нет → панель «Medien» — Fotogalerie · Banner-Slides · Titelbilder · Logo | Canvas |
| Rail «Start» | quickstart (демо + Layout-Vorlagen) | уходит → секция «Vorlagen» на экране кабинета (4A) | Kabinett |
| НОВЫЙ rail «Menü» | вкладка Menü / ☰ в верхней строке | уровень рейки: панель «Kopf- & Fußzeile» (2B) | Canvas |
| Лента страниц внизу | чипы, полная перезагрузка | уходит → «Seite: … ▾» в верхней строке (3A); Warenkorb/Kasse оттуда | Topbar |
| Topbar: ← Übersicht · Studio · ↶ ↷ · статус | всегда | остаются | Topbar |
| Topbar: имя блока · Einfach\|Experte · ▾ · ✕ | при выбранном блоке | переезжают в шапку панели (крошка «Startseite › Produkte») | Panel |
| Topbar: 🖥 ▭ 📱 | всегда | остаётся | Topbar |
| Topbar: 🔍 Kompakt | плотность инспектора | в меню «⋯» шапки панели | Panel |
| Topbar: ☰ Menü · 🧱 Blöcke · ⚙️ Vorlage | дубли рейки/областей | уходят: рейка Menü/Blöcke; Vorlage — на экране кабинета | weg |
| Topbar: 🔗 Vorschau teilen · Speichern | всегда | остаются | Topbar |
| Вкладки панели (🎨 🖼 📄 ☰ 📚) | вторая навигация | уходят: панель показывает то, что выбрано (рейка или клик по канве) | weg |
| Theme: Startseite (storefront_root) | область Theme | панель «Diese Seite: Startseite» | Panel |
| Theme: Look · Startpaket · Farbe · Schrift · Typografie · Karten/Fotos/Chrome/Fond | область Theme (живой черновик) | экран кабинета «Design des Shops» (1B); превью-плитки как сегодня, живой канвы нет | Kabinett |
| Theme: Logo · Footer → | кнопки в Theme | панель «Menü» (Logo, Fußzeile) | Panel |
| Banner: Überschrift · Text | область Banner + inline | inline на канве + группа «Inhalt» секции Banner | Canvas |
| Banner: Folien · Titelbilder · Bild-URL | кнопки → медиа-области | панель «Medien» (Slides, Titelbilder); фото — 📷 на канве | Panel |
| Sections: Banner-Stil | select в области sections | группа «Darstellung» секции Banner + «Stil ▾» на плашке действий | Popover |
| Sections: список секций (⠿ № ▲▼ ☑ имя ⚙) | область sections | панель «Diese Seite: Startseite» (⠿ 👁 имя); ▲▼ 👁 — на плашке действий у секции | Panel |
| Sections: «Unser Angebot» (карточки архетипов) | fieldset в sections | группа «Inhalt» секции «Unser Angebot» | Panel |
| Sections: 📦 Inhaltsabschnitte (тексты FAQ/Team/CTA/…) | details в sections | группа «Inhalt» СВОЕЙ секции (F8) | Panel |
| Sections: «Seite als Vorlage speichern» | низ области | аккордеон «Vorlagen & Versionen» панели главной | Panel |
| Page: 27 настроек реестра (Vorlage der Seite · Raster · Sortierung · Filter …) | область page, по типу | панель «Diese Seite: ‹тип›» — те же строки, без вкладок | Panel |
| Page: пилюля Für alle / Nur hier (4 настройки) | рядом с плиткой | рядом с плиткой — в панели и в быстром поповере | Panel |
| Page: C-блоки страницы | строки в page | список «Blöcke auf dieser Seite» в панели; настройки — по клику на блок | Panel |
| Menü: Kopfzeilenstil · Feste Kopfzeile · Beispiele | область menu | панель «Menü»: плитки Classic/Zentriert/Minimal + ☑ fest + ☑ CTA | Panel |
| Menü: пункты меню | экран Menü-Generator | список в панели «Menü» (F6); второй писатель menus → свежая загрузка при открытии + presence-guard; подменю/цели — в Menü-Generator | Panel |
| Library: сохранённые блок-шаблоны | вкладка Vorlagen | только в поповере «+» (там и так есть) | Popover |
| Library: шаблоны страниц · Versionsverlauf | вкладка Vorlagen | аккордеон «Vorlagen & Versionen» панели главной | Panel |
| Library: ссылки SEO · Titelbilder · Menü-Generator | вкладка Vorlagen | уходят (есть в подменю Website кабинета) | weg |
| Медиа-области ×4 | разбросаны | панель «Medien» аккордеоном | Panel |
| «Kategorie hinzufügen» | область catalog-add | поповер «＋ Kategorie» из плашки действий секции Kategorien | Popover |
| Лента блока: настройки секции (4–34) | правая колонка | панель блока: Inhalt · Darstellung · Erweitert (F8); Einfach\|Experte в шапке; имя C-блока переведено (сегодня сырой ключ); высота Abstand редактируема (сегодня только при вставке) | Panel |
| Лента C-блока: Position · Sichtbar · Entfernen | голова строки | плашка действий у блока: ▲ ▼ 👁 🗑 | Leiste |
| Лента C-блока: Breite · Position · Neue Zeile | хвост строки | «Breite ▾» на плашке действий (поповер) + группа Darstellung | Popover |
| Лента: Stil-варианты · Raster | select/плитки в колонке | «Stil ▾» / «Raster ▾» на плашке действий — поповер ≤ 7 плиток (F5) | Popover |
| Kartenform на листингах | строка в page | «Kartenform ▾» на плашке действий сетки — поповер с пилюлей охвата (F5) | Popover |
| Canvas: текст · цена · дата · 📷/🗑 · «+» · ⠿ | уже на канве | остаются без изменений | Canvas |
| Canvas: клик по секции/контенту | открывает колонку | открывает панель в нужном охвате + показывает плашку действий | Canvas |

## 2. Инкременты (каждый мержится отдельно; замки — ДО кода и красные без правки)

### 12a · Верхняя строка + снос рейки, ленты страниц и вкладок
- **Удалить:** `#st-rail` (site_home.html ~100–113, обработчики ~4249–4311), `#st-pages` (~117–121,
  ~4276–4300), `#bld-area-tabs` (~133–148, `clickTab`), кнопки `⚙️ Vorlage` (`#bld-drawer-toggle`),
  `☰ Menü` (`#bld-menu-btn`), `🧱 Blöcke` (`#bld-blocks-btn` — сам инсертер остаётся, вход = «+» на канве
  и «＋ Block» в панели страницы), `🔍 Kompakt` (`#bld-compact-btn` → пункт «⋯» колонки), CSS-офсеты
  `left:4rem` / `bottom:2.75rem`.
- **Добавить:** «Seite: ‹имя› ▾» (`preview_pages` + «Kasse» + группы акций из `promo_groups`/фасета;
  группы «Auf der Website erreichbar» / «Nur von hier»; клик = `reloadBuilderPage(?page=)` — STU-7-санитайзер;
  подпись = тип + объект из `body[data-stu-page]`/`data-stu-ref`); «Design des Shops →» (`design_view` с
  `?next=` обратно в Студию на ту же страницу).
- **Колонка по умолчанию ОТКРЫТА** на `stuPageArea()` (sections на главной / page иначе); шеврон
  `#bld-panel-toggle` сворачивает; `sf_cur_area` больше не нужен.
- **DoD/замки:** в разметке нет `#st-rail`, `#st-pages`, `#bld-area-tabs`, `#bld-drawer-toggle`,
  `#bld-menu-btn`, `#bld-blocks-btn`; «Seite ▾» перечисляет Warenkorb и Kasse и группы акций; вход в
  Студию показывает панель страницы (на главной — sections); `test_studio_shell` переписан осознанно;
  `test_registry_and_panel_agree` зелёный; Playwright: вход → колонка видна; клик по шеврону → канва во всю ширину.

### 12b · Одна колонка вместо «область + лента блока»
- `openBlockPopup(key)` показывает блок В ТОЙ ЖЕ колонке (`#bld-editor-pane`): шапка = крошка
  «‹Seite› › Abschnitt» + имя + `Einfach|Experte` + `⋯` + `✕` («‹ zurück» = `closeBlockPopup` → страница);
  строка формы по-прежнему ПЕРЕНОСИТСЯ (комментарий-якорь), `.bld-ribbon-open`-геометрия становится
  геометрией колонки; `.bld-ctx` из верхней строки удалена. Имена C-блоков — через `CBLOCK_LABELS`
  (переводимые). Esc: блок → страница → свернуть.
- **Грабля:** на подстраницах искать `.page-block[data-page-key]` РАНЬШЕ `.home-block` (коллизия ключей
  services/events/stay_rooms/reviews).
- **Замки:** крошка/имя в колонке; `.bld-ctx` отсутствует; число `name=` в `#home-form` до/после открытия
  блока одинаково (W0); Esc-цепочка.

### 12c · Шапка и подвал кликабельны (2B-снято, F6A)
- Витрина: `data-sf-section="header"` на `<header>` и `"footer"` на `<footer>` (все страницы, в
  `_base.html`) → Студия открывает колонку «Kopf- & Fußzeile» = область `menu` (nav_style-плитки
  `data-menu-preset`, `nav_sticky`) + `Logo` (кнопка → Medien/Logo) + `Fußzeile` (указатели) +
  **`nav_cta`** (новое: чекбокс «CTA-Button in der Kopfzeile» → `site_config["nav"]["cta"]`, presence-сентинел
  `nav_cta_present`; витрина уже читает `nav.cta` — DS-3b) + **Menüpunkte** (список верхнего уровня
  `menus.top.items`: ⠿ порядок, 👁 скрыть, инлайн-переименование; «＋ Punkt»; hidden `menus_json` в
  `#home-form`; Save пишет `menus` ТОЛЬКО при валидном JSON; дерево грузится свежим при открытии колонки
  (второй писатель — Menü-Generator); подменю/цели/i18n — только в Menü-Generator; `site_preview_draft`
  принимает `menus`).
- **Замки:** клик по шапке → колонка Kopf; Save без `menus_json` не трогает `menus`; невалидный JSON →
  `menus` цел; `nav_cta` round-trip и presence; dead-config: `nav.cta` у китов DS-3b рендерится.

### 12d · Плашка действий + быстрые поповеры (F5A) — ✅ сделано 2026-09-09
- Плашка: fixed-контейнер над выбранным элементом (координаты из `getBoundingClientRect` элемента в iframe
  × `scale` из `applyDevice` + смещение кадра; общий `placeAnchored(rect, size)` с clamp/flip; пересчёт
  после `load`/hard-reload и `sf:navigated`); кнопки → существующие обработчики (`blk-up/blk-down`,
  `enabled_*`, `delete_cb_*`), `⚙` = колонка.
- Поповеры Stil/Raster/Breite: контейнер `#bld-quick-pop` ВНУТРИ `#home-form`; в него ПЕРЕНОСИТСЯ
  существующий контрол (`style_<key>`, `layout_preset_<key>` c `.bld-thumbs`, `width_cb_<id>`) на время
  открытия и возвращается на место при закрытии (комментарий-якорь, как `openBlockPopup`); открывается НАД
  плашкой, если снизу нет места; закрытие Esc / клик мимо (в т.ч. внутри iframe) / выбор / другой элемент;
  один поповер за раз; live-draft штатный.
- **Замки:** контролы не клонируются (счётчик `name=`); закрытие возвращает контрол; юнит `placeAnchored`
  учитывает scale; поповер над плашкой при нехватке места.
- **Сделано** (`test_stu12_actionbar.py`, 10 замков; стенды `stu12d_stand.mjs` 27/27 и
  `stu12d_cblock.mjs` 8/8). Сверх плана закрыты четыре дефекта, найденных стендом:
  секции-обёртки `display:contents` (якорь = первый ребёнок с коробкой), `space-y-6`
  формы сдвигал плашку на 24 px (`margin:0 !important`), **пред-существующий провал
  двойной буферизации** (`about:blank`-load буфера считался ошибкой → hard-reload на
  каждую правку, канва теряла оснастку) и односторонняя 👁 (у скрытого блока нет
  коробки → плашка гасла и вернуть блок было нечем). Детали — build-log 2026-09-09.

### 12e · Группы Inhalt · Darstellung · Erweitert (F8A)
- Тексты секций из `_section_fields.html` (faq_text, team_text, testimonials_text, process_text,
  trust_since/trust_marks, usp_text, cta_*) и `hero_title/hero_text/hero_image` (область Banner),
  карточки архетипов («Unser Angebot») — переезжают в СТРОКУ СВОЕЙ СЕКЦИИ с теми же `name=`
  (W0; `collect()` байт-в-байт); группы = `<details>` Inhalt (данные) / Darstellung (стиль, раскладка,
  ширина) / Erweitert (`[data-expert]`, виден в Experte). Высота Abstand редактируема (`spacer_height`
  как control, не только пресет при вставке). После вставки блока — `openBlockPopup(new_id)`.
- **Замки:** golden normalize цел; `collect()`-payload не меняется от переноса; spacer height round-trip;
  after-insert открывает блок.

### 12f · Medien + Kategorie-Popover
- Колонка «Medien»: 4 out-of-form области (`gallery-media`, `banner-media`, `covers-media`, `logo-media`)
  аккордеоном; входы: клик по галерее/логотипу/баннеру/обложке (витрина помечает `data-sf-media="gallery|logo|hero|cover:<key>"`);
  каждая форма несёт hidden `page_path` → `_redirect_builder` возвращает канву на ту же страницу.
  `catalog-add` — поповер «＋ Kategorie» из плашки секции Kategorien.
- **Замки:** upload возвращает на ту же страницу; add_category из поповера создаёт категорию.

### 12g · 1B/4A: глобальный дизайн и «Start» — в кабинет (параллелится с 12c–12f)
- `/dashboard/design/` (`design.html`, `design_view`): + карточки «Farbe & Schrift» (accent, font,
  typography-ranges), «Karten & Fotos» (`sd_card_style`, `media_shape`, `card_chrome`, `page_bg`, `variant_style`,
  `quick_add`, `wishlist`), «Vorlagen» (Layout-Vorlagen `apply_template` + «Demo-Inhalte laden/löschen»);
  сентинелы (`sd_page_bg_present`, `quick_add_present`, `wishlist_present`, `sd_present`) переезжают туда же.
- **`apply_look` — только оптика** (сегодня сбрасывает порядок секций главной; у `apply_bundle` семантика
  обратная и остаётся).
- Студия: `collect()` НЕ шлёт ключи темы (`accent/font/typography/site_defaults.card_*/theme/page_bg`),
  Save Студии их не пишет и не роняет (presence); области `theme`, `quickstart`, ссылки `library`
  удалены; «Vorlagen & Versionen» = аккордеон панели главной; `storefront_root` — в панель главной.
- **Замки:** `apply_look` не меняет `sections`; draft-payload без ключей темы; Save Студии сохраняет
  тему, выставленную в кабинете (W6-класс); экран Design round-trip всех перенесённых полей.

### 12h · Телефон (F7A)
- «⚙ Seite» в верхней строке (< lg) открывает колонку-лист страницы; поповеры → bottom-sheet; плашка
  видна на тач; `▲▼` всегда в листах; `●` статус у Speichern (< md); `isNarrow` через `matchMedia`
  listener. Стенд 390 px: T2 (текст inline) и T1' (шаблон категории «Nur hier»).

### 12i · Стенд + доки
- Playwright (`config.settings.stand`, порт 8021, демо-тенант `aktionsmarkt` из сидера) по 19 типам
  страниц × 1440/1024/390: колонка по умолчанию, клик секции/шапки/сетки, поповеры, «Seite ▾» → Warenkorb/
  Kasse, Undo/Save, 0 JS-ошибок; build-log, CLAUDE.md §3, task-catalog.

### 12j · F9: форма карточки для одной категории (⚠️ миграция `catalog/00NN`, аддитивная)
- Модель: `Category.card_style = CharField(max_length=32, blank=True, default="")` (значения — реестр
  `apps/core/card_forms.py`, валидация в форме/normalize, choices в модели НЕ фиксируем — реестр растёт
  без миграций).
- Резолвер: `card_form`-тег (`apps/core/card_forms.py`) — `product.card_style` → `product.category.card_style`
  (на странице категории — категория страницы, если она предок/сама) → `site_defaults.card_style`; мусор в любом
  слое → следующий слой (не 500).
- Реестр `studio_pages`: настройка `product_card_form` получает объектную привязку ПО ТИПУ страницы
  (`object_by_type = {"product": ("product","card_style"), "category": ("category","card_style")}`;
  `studio_scope._fetch` резолвит по типу канвы) → пилюля «Nur hier» появляется на странице категории.
- Кабинет: плитки «Kartenform» в форме категории (аналог DL-19.5 у товара, `_cardform_picker`).
- Демо: одна категория с собственной формой в ките `clothing` (Accessoires = Deal).
- **Замки:** резолвер 3 слоёв + мусор; пилюля на категории пишет `Category.card_style` и НЕ трогает
  сайт (класс W6/STU-9); `test_registry_and_panel_agree`; демо-инвариант.

**Порядок:** 12a → 12b → 12c → 12d → 12e → 12f → 12g → 12h → 12i → 12j (12g и 12j можно вести
параллельно с 12c–12f — другие файлы). Каждый инкремент: замки → код → `ruff format --check .` →
`i18n_quickcheck` → template_comments → CI зелёный → FF-мерж в main → строка в build-log.

## 3. Инварианты и грабли

- **W0:** все поля живут в `#home-form`; колонка/поповеры ПЕРЕНОСЯТ строки, никогда не клонируют;
  скрытие — только CSS; presence-сентинелы (`cl_present`, `cf_present`, `pb_present`, `pd_present`,
  `sd_present`, `std_present`, `cart_present`, `tw_present`, `quick_add_present`, `wishlist_present`,
  `sd_page_bg_present`, новые `nav_cta_present`) — ВНЕ переносимых строк.
- **W6:** Save Студии не роняет чужие ключи (`ui_mode`… нет, но `board`, `seo`, `page_blocks`, `notify`,
  после 12g — тема); `menus` — только при валидном `menus_json`.
- **Масштаб канвы:** desktop = 1280 логических × `scale` (`applyDevice`); все якорные координаты —
  через общий `placeAnchored`; у «+» латентное расхождение — чинится тем же хелпером.
- **Коллизия ключей на подстраницах** (`services/events/stay_rooms/reviews`): `.page-block` первым.
- **Esc:** внутренний-первым (поповер → блок → страница); клик внутри iframe = «мимо» для поповера
  (слушатель в документе кадра).
- **Golden normalize** не трогать; новые ключи — presence-minimal (`nav.cta`, `spacer_height`).
- **Локализация:** новые msgid (крошки, имена C-блоков, «Design des Shops», «Kopf- & Fußzeile», плашка,
  «Seite», «Nur von hier erreichbar») × 5 каталогов; `scripts/i18n_quickcheck.py` перед пушем;
  многострочные `{# #}` запрещены (`test_template_comments`); новые Tailwind-классы → `npm run build:css`.
- **Замки к осознанной переписке:** `test_studio_shell` (rail/pages/tabs), панельные ассерты
  `test_home_builder` (~41 ссылка на ids — ids колонки СОХРАНИТЬ: `#bld-editor-pane`, `#bld-block-popup`,
  `#bld-panel-toggle`, `#home-prev-frame`, `#bld-root`), `test_studio_pages` (67, реестр↔разметка
  остаётся), `test_registry_and_panel_agree` — зелёный всегда; `test_frame_escape_links` — новые ссылки
  из витрины в кабинет только `target=_top`.

## 4. Что НЕ меняется
Inline-редакторы канвы (текст, цена, дата, 📷/🗑, «+», ⠿), реестр настроек по типам, пилюля охвата
(механика `site-scope-save`), живой черновик (double-buffer, watchdog), Undo/Redo, Einfach|Experte,
Menü-Generator для подменю, экран `design.html` как точка входа 1B (расширяется, не переписывается).

## 5. Открытые вопросы (не блокируют старт)
- «Vorlagen & Versionen» — аккордеон панели главной (план) или «⋯» верхней строки → решается в 12g.
- Плашка на детальных страницах (товар/услуга/номер/событие): нужны ли `Raster/Stil` — у деталей нет
  сеток; v1 — только `⚙` + inline.

## 6. Как возобновить в новой сессии
1. `git fetch origin && git checkout claude/aktionsmarkt-analysis-45t2vu && git log --oneline -5` — найти
   последний коммит `STU-12x`; в `docs/build-log.md` — что уже влито в main.
2. Прочитать §0–§3 этого файла; открыть `templates/tenant/site_home.html` (ids: `#bld-root`, `#bld-editor-pane`,
   `#bld-block-popup`, `#home-form`, `#bld-inserter`, `#home-prev-frame`), `apps/core/studio_pages.py`,
   `apps/core/views.py` (`home_builder_view`, `preview_pages`, `_safe_preview_page`), `apps/tenants/siteconfig.py`.
3. Тесты Студии: `uv run pytest apps/core/tests/test_studio_pages.py apps/core/tests/test_studio_shell.py
   apps/core/tests/test_home_builder.py --reuse-db`; стенд — `config.settings.stand`, порт 8021 (см. §2/12i).
4. Канвас перегенерировать: `cd docs/design/studio-2026-09-07 && python _generate.py` → seed-canvas
   (skill design) → republish той же ссылки.
5. По завершении инкремента: build-log + CLAUDE.md §3 «Самое свежее» + `task-catalog.md` (семейство STU).
