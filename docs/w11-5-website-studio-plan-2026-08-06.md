# W11-5 — Website-свод в Studio (план-док, ДО кода)

Дата: 2026-08-06. Родитель: `w11-marketing-plan-2026-08-05.md §2` (пункт W11-5)
+ разведка там же §3. Решение владельца **2а** (2026-08-06): полный свод —
site.html умирает, все его функции живут в Studio (site_home.html), «Website»
ведёт в одно место. Всё БЕЗ миграций БД. Ветка `claude/w11-5-website-studio-7qyojs`.

## §1. Цель и рамка

Один вход «Website» = Studio. Страница `/dashboard/site/` (site.html, 216 строк:
навигационные карточки + quick-start + галерея + контент-форма) перестаёт
существовать; её функции переносятся в рейку/области Studio, сам URL — 302 на
`site-home` (прецедент W10-6 `legacy_redirect`). Медиа в Studio-рейке уже есть
(ST-3a) — НЕ дублируем.

## §2. Разведка: что уже есть, что переносить (верифицировано по коду)

### 2a. Дубли — в Studio УЖЕ есть (перенос = НОЛЬ работы, ветки site_view умрут)

| Функция site.html | Где в Studio |
|---|---|
| Галерея upload/delete (multipart) | `site_home.html:1012-1037` (область `gallery-media`) → `home_builder_view` :1240-1245, ТЕ ЖЕ хелперы `_upload_gallery_images`/`_delete_gallery_image` |
| hero_title / hero_text | форма области `banner` :341/345 + inline на канве (`_hero.html` data-edit) |
| Контент-секции (CTA/FAQ/отзывы/team/trust/process/usp) | ТОТ ЖЕ партиал `_section_fields.html`, include в `site_home.html:785` (область `sections`, details «home»), парсится безусловным `parse_content_sections` в main-save :1769 |
| about_title / about_text | inline-edit на канве (`_about.html` data-edit + `TEXT_FIELDS`) — форменного поля НЕТ и НЕ добавляем (канва — единственный редактор; дублирующий write-путь = класс W6-граблей) |
| Навигационные карточки (Preview/Builder/Menu/…) | Studio сам = билдер; menu-builder залинкован из области `menu` (:876) и мастера; SEO — из `domains.html` (таб W9-4) |

### 2b. Честный гэп — переносим

1. **Quick-start**: галерея шаблонов `sitetemplates.template_cards` +
   `apply_template` (views.py:995) + `load_demo`/`clear_demo` (:1002-1013) +
   контекст `has_demo`. В `home_builder_view` их НЕТ (есть только Look ST-1b,
   который осознанно не трогает sections).
2. **hero_image** (URL фона баннера, `_hero.html:59-63`) — пишется только site_view :1032.
3. **quick_add** (тумблер «+» на карточках, normalize-дефолт True :2389) — только site.html:169.
4. **gallery_video** — только site.html:148; в Studio-области Medien нет.
5. **Достижимость сирот**: после смерти site.html без входа остаются
   `site-sections` и `site-pages` (site-preview достижим из них и из site-menu).

### 2c. Консумеры «Website» → ретаргет на `site-home`

- `_base_dashboard.html:92` — карандаш «✏️ Website» в шапке (самый горячий вход);
- `nav_registry.py:82` — `Anchor("site", …, url_name="site")` → сайдбар + палитра Ctrl+K;
- `onboarding.py:498` — чек-лист готовности, item "banner";
- `modules.py:505` — `NavItem("site")` (рантайм-консумеров нет, только тесты);
- back-link Studio `site_home.html:13` «← Website» → БЕЗ ретаргета станет петлёй
  (site → 302 → site-home) — ведём на `dashboard`;
- back-links соседей: `site_menu.html:11`, `site_preview.html:9`, `site_seo.html:10`,
  `site_sections.html:11` → на `site-home`.
- hub_tiles Website УЖЕ → site-home (`dashboard.py:315-321`) — не трогаем.
- `_EXTRA_NAV_ANCHORS["site"]` — nav_key-карта (не URL), остаётся: `nav="site"`
  эмитят 6 живых вьюх (menu/seo/sections/pages/preview/domains).

### 2d. Архитектурные инварианты site_home.html (НЕ нарушать)

- `#home-form` (:140-912) — единственная большая форма; multipart и standalone
  action-формы живут ТОЛЬКО в полосе 913-1140 (`library`/`catalog-add`/
  `gallery-media`/`logo-media`/`banner-media`/`covers-media`).
- **Fall-through hazard**: POST на site-home без известного `action` падает в
  main-save (:1478), который ПЕРЕСОБИРАЕТ `config["sections"]` из `order_*` →
  форма без этих полей стёрла бы секции. Каждая новая standalone-форма ОБЯЗАНА
  иметь early-return-ветку ДО :1478 (паттерн `use_page_preset` :1391).
- **Коллизии имён**: не заводить поля с префиксами `order_/title_/enabled_/
  arch_/cb_/pb_/hide_/width_/style_/font_/limit_/cols_/visual_*` (их сканируют
  collect() и main-save). Наши имена: `template`, `gallery_video`, `quick_add`
  (+сентинел `quick_add_present`), `hero_image` — чисты (проверено: page-шаблоны
  используют `page_tpl_label`, не `template`).
- **Draft-канал**: поле в `#home-form` получает Undo/Redo и debounce-POST
  бесплатно, но НЕ попадёт в live-превью, пока не добавлено в `collect()`
  (JS) И в whitelist `site_preview_draft` (:2269-2433). Иначе — «сохранится,
  но канва не отреагирует» (молчаливый дроп).
- **Двойная буферизация** (`swapPreview`/`hardReloadPreview`) — форм-агностична,
  не трогаем. Действия quick-start — обычный form-POST → redirect → полная
  перезагрузка билдера (тот же путь, что use_page_preset) — с буферизацией не
  взаимодействует.
- Main-save скалярные поля — ТОЛЬКО через presence-guard (`if "x" in POST`,
  паттерн :1738/:1754/:1763); для чекбокса — сентинел (unchecked не шлётся).

## §3. Инкременты (батч: каждый — коммит, локальный гейт; пуш стопкой)

### И-1. Область «Schnellstart» в Studio (шаблоны + демо)

- Новая область `data-bld-area="quickstart"` в полосе standalone-форм (после
  `library` :983): карточки шаблонов (порт разметки site.html:80-108, тот же
  контекст `site_templates`) с `confirm()` + hidden `action=apply_template`
  + `template=<key>`; блок «Demo content» c кнопкой load/clear по `has_demo`
  (порт site.html:62-75).
- Рейка `#st-rail` += кнопка «Quick start» (`data-st-level="quickstart"` →
  `__sfShowArea('quickstart')`; msgid «Quick start» уже переведён в 5 .po);
  title-карта :1601 += quickstart.
- `home_builder_view`: 3 early-return-ветки ДО main-save (:1478) — те же
  библиотеки `sitetemplates.apply_template` / `demo.load_demo` / `demo.clear_demo`,
  redirect на `site-home`; контекст += `site_templates`, `has_demo`.
- Замки (характеризационные — ДО правок вьюхи, на новую ветку — сразу):
  builder-`apply_template` 302 + секции сменились + **builder-only ключи целы**
  (ui_mode/board/seo — перенос ассертов из `test_sitetemplates.py:241` и
  класс W6/ST-1a `_apply`-базы); `load_demo`/`clear_demo` из билдера работают
  и **не трогают sections** (анти-fall-through); неизвестный template → error-msg.

### И-2. Поля-гэпы

- **hero_image**: input в области `banner` (рядом с hero_title/hero_text, внутри
  `#home-form`) + presence-guard в main-save + `collect()` + whitelist
  `site_preview_draft` (live-превью фона баннера).
- **quick_add**: чекбокс в области `theme` (рядом с настройками карточек
  `sd_card_*`) + сентинел `quick_add_present` в main-save + `collect()` +
  whitelist драфта (live-тумблер «+» на карточках канвы).
- **gallery_video**: мини-форма в области `gallery-media` (standalone, идиома
  области) с `action=save_gallery_video` — early-return, targeted-write
  (normalize(current) → set key → normalize → save), редирект site-home.
- Замки: main-save БЕЗ новых полей не меняет их значения (presence/сентинел);
  с полями — пишет; `save_gallery_video` не трогает sections/gallery; драфт
  прокидывает hero_image/quick_add (тест site_preview_draft).

### И-3. Достижимость соседей + SEO в рейку

- Рейка += ссылка «SEO» (`<a href="{% url 'site-seo' %}">`, стиль st-level).
- Область `library` += компактный блок «Weitere Werkzeuge»: `site-sections`
  (Bereichs-Cover), `site-pages` (Seitenlayouts), `site-preview` (Vorschau) —
  сироты получают вход, W7b-принцип «без сирот».
- Back-links: `site_home:13` → `dashboard`; `site_menu:11`/`site_preview:9`/
  `site_seo:10`/`site_sections:11` → `site-home`.
- Замок: инвариант рейки (test_studio_shell) обновить осознанно.

### И-4. Редирект + смерть site.html

- `site_view` → шим-редирект по W10-6 (`HttpResponseRedirect(reverse("site-home")
  + qs)`, GET-carry `?page=` и пр.); POST тоже 302 (форм больше нет; потеря тела
  из протухшей вкладки — принятый компромисс, как в W10-6).
- Удалить `templates/tenant/site.html`.
- Ретаргет консумеров §2c: `_base_dashboard:92`, `nav_registry:82` (Anchor →
  `site-home`), `onboarding:498`, `modules.py:505`.
- Замки — новый файл `apps/core/tests/test_w11_5_redirect.py` (по образцу
  `test_w10_redirects.py`): 302 + GET-carry + `test_redirect_target_renders_
  end_to_end` (следуем Location, рендерим Studio, 200). Осознанные переписывания
  (карта — build-log):
  - `test_w6_theme.py` (3 теста на save site_view) — умирают вместе с веткой;
    их семантика уже закрыта: main-save билдера стартует с полной копии
    normalize(current), apply_template идёт через `_apply`-базу ST-1a
    (замок test_looks) + новый замок И-1 на builder-apply_template;
  - `test_sitetemplates.py:241/254/264/284` — переносятся на builder-ветку (И-1);
  - `test_siteconfig.py:150` (ссылка на билдер в HTML) — умирает; `:158`
    (save текстов не гасит секции) — семантика main-save, уже под замками
    test_home_builder; удаляем осознанно;
  - `test_home_builder.py:1215` — убрать site_view из цикла entrypoint'ов
    (редирект ≠ 200), `:1195`/`:1252` — переписать на redirect-ассерт/удалить;
  - `test_menu_builder.py:95`, `test_onboarding_wizard.py:868` — умирают с
    веткой save (билдерные аналоги: nav не трогается main-save'ом — уже
    замок test_menu_builder; onboarding переживает main-save — полная копия);
  - `test_sidebar_st4b.py:42` — список url_name якорей: "site" → "site-home";
  - `test_gallery.py` — зовёт хелперы напрямую, выживает без правок.

### И-5. i18n + доки + гигиена

- Новые msgid: максимум реюза строк site.html (перевод переезжает бесплатно:
  "Quick start", "Demo content", "Load/Delete demo content", "Templates",
  "Apply", "Apply this template? …", "Gallery video", "Quick order on cards …",
  "Banner background image (URL)"); честно новые («Weitere Werkzeuge» и т.п.)
  — в 5 .po; гейт `scripts/i18n_gap.py`. 31 msgid-эксклюзив site.html устареет
  в .po — допустимо (гейт смотрит код→po).
- `npm run build:css` при новых Tailwind-классах (порт карточек может принести
  классы, которых в site_home ещё нет — проверить CI-замок свежести).
- build-log + CLAUDE.md (§3 статус + §«Дальше») + task-catalog в том же батче.

## §4. Риски (сводно)

| Риск | Митигция |
|---|---|
| Fall-through: новая форма без action стирает sections | только early-return-ветки; замок «demo/video не трогают sections» |
| Молчаливый дроп в драфте | hero_image/quick_add — в collect() И whitelist; gallery_video — осознанно save-only (витринное видео click-to-load, превью-ценности нет) |
| Петля site↔site-home | back-link Studio → dashboard (И-3 ДО И-4) |
| POST в мёртвый URL из протухшей вкладки | 302 без тела — принятый компромисс W10-6 |
| Двойной write-путь about_* | НЕ добавляем форму (канва — единственный редактор) |
| Регресс 3400-строчного шаблона | Playwright-стенд после каждого инкремента (§5) + инкременты не трогают collect()/swapPreview кроме точечных добавок |
| Anchor-ретаргет ломает W8-замки | осознанное обновление test_sidebar_st4b + прогон test_w8_nav_registry |

## §5. Playwright-стенд (обязателен, по прецеденту UC2-4/W10-6)

Стенд: runserver + сид-тенант, `uv run --with playwright` (Chromium в /opt/pw-browsers).

1. **После И-1/И-2:** рейка показывает Quick start; клик открывает область с
   карточками и демо-кнопкой; apply шаблона → редирект, канва перезагружена,
   секции сменились; load demo → кнопка сменилась на delete; hero_image URL →
   live-фон в канве (debounce+swap) → Save → персист; quick_add off → Save →
   карточки без «+»; gallery_video round-trip.
2. **После И-3/И-4:** карандаш «✏️ Website» из кабинета → Studio;
   `/dashboard/site/` → 302 → Studio; сайдбар Website → Studio; «←» из Studio →
   dashboard; back-links соседей ведут в Studio.
3. **Регресс-инварианты:** Undo/Redo живы; live-драфт hero_title работает;
   инсертер «+» вставляет блок; Save round-trip не теряет ui_mode/board/seo
   (проверка site_config в БД).

## §5b. Статус (2026-08-06) — ВЫПОЛНЕНО ЦЕЛИКОМ

- **И-1 ✅** область `quickstart` (рейка «⚡ Start»): шаблоны + демо; 3 ветки
  early-return ДО main-save. Замки: apply/unknown/demo/рендер области.
- **И-2 ✅** `hero_image` + `quick_add` (форма билдера, presence-guard/сентинел,
  `collect()` + whitelist драфта) · `gallery_video` (форма области «Медиа»,
  targeted-write). Замки: save, no-wipe без полей, драфт, видео-без-секций.
- **И-3 ✅** входы к соседним экранам из области «Шаблоны»; back-links соседей →
  Studio; выход из Studio → кабинет.
- **И-4 ✅** `site_view` = 302 с GET-carry; `site.html` удалён; консумеры
  (карандаш шапки / Anchor W8 / чек-лист онбординга / NavItem спеки) → Studio.
  Замки умершей ветки переписаны осознанно (карта — build-log), новый файл
  `test_w11_5_redirect.py`.
- **И-5 ✅** 2 новых msgid × 5 .po; `app.css` пересобран; доки.
- **Стенд Playwright 28/28.** Найден и исправлен дефект: `quick_add` оказался в
  expert-блоке → в Простом режиме был недоступен (на «Site» был всегда); вынесен,
  замок `test_quick_add_toggle_is_not_expert_only`.
- Уточнение к §2d: инвариант «save не роняет чужие ключи» относится именно к
  ЧУЖИМ ключам; typography/site_defaults/font/hero_style билдер ВЛАДЕЕТ (его
  форма всегда их несёт, W0) — замок W6 переформулирован соответственно.

## §6. Порядок исполнения

Строго §3 И-1 → И-5; замки на трогаемое поведение — ДО правок; каждый инкремент
— отдельный коммит; локальный гейт (`ruff check` + `ruff format --check .` +
pytest затронутых модулей `--reuse-db`) → пуш стопкой → зелёный CI → FF-мерж в
main. Финальный гейт батча: `apps/core/tests/test_template_comments.py` (правки
шаблонов), i18n coverage, css freshness.
