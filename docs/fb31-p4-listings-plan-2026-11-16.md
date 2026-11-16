# FB-31 P4 — девять листингов, «Team» и «Galerie» из блоков

Дата: 2026-11-16. Стратегия `fb31-block-strategy-2026-11-15.md` §6 P4; образец — P3
(`fb31-p3-promotions-plan-2026-11-16.md`, ядро `apps/core/page_parts.py`). Разведка — `planner` (ECC).
Решение владельца: «делай после плана по ECC» — приняты рекомендации §5.

## 0. Разведка
- Один читатель шаблонов девяти листингов — `apps/core/listing_composition.py` (`selected_code`,
  `context`); вызывающие: services, stays, events, tours, blog, combos, wishlist, lookbook, reviews.
- Оформление — один каркас `templates/storefront/listing.html` (`data-sf-page`, `_hero.html`,
  Navigator-колонка, `_tabs`/`_index`/`_shelves`); `comp_owns_entries` прячет чипы коллекций.
- Оси ★ «Darstellung» у листингов нет: реестр даёт только `"" · kopfbild · regale · tabs ·
  navigator · kompakt`; вид ★ = существующая сетка `*_layout` + форма карточки (Design, P2).
- Навигация есть у четырёх (services, stays, events, combos); у прочих — только шапка.
- **`tours_layout` используется** (`events/public_views.py:820`, `tour_index.html`, `list_blocks.py`) —
  предпосылка стратегии «страница не читает» неверна: оставляем, правим комментарий и стратегию.
- Хост `stays` — `stay_rooms` (остальные совпадают с именем).
- `page_styles` пишут только Студия и `page_settings`; демо-киты и `sitetemplates` — нет.
- Team/Galerie без моделей: списки `team`, `gallery` в конфиге, вид — `style` секции главной.

## 1. Код → оси (все девять)
| Код | `page_head` (off `aus`) | `groups` (off `auto`) |
|---|---|---|
| "" | aus | auto |
| kopfbild | titelbild | auto |
| regale | aus | regale |
| tabs | aus | tabs |
| kompakt | aus | index |
| navigator | aus | side |

Листинги без навигации (tours, lookbook, wishlist, blog, reviews): коды `""`, `kopfbild`; прочие
читаются как «Standard» — как сегодня (`compositions.resolve`).

## 2. Срезы
- R0 золотые снимки через настоящие вьюхи (~80).
- R1 `apps/core/listing_parts.py` — девять поверхностей одним циклом из `compositions.LISTING_SURFACES`
  + Team/Galerie (★ — 5 видов).
- R2 хранение: `siteconfig.part_surface` знает хосты листингов, Team/Galerie.
- R3 витрина: `listing_composition.context()` читает оси; гейты `resolve` — после осей.
- R4 писатели: Студия и `apply_override` снимают виды при смене шаблона.
- R5 панели и операции (`_code_of_host`, подпись строки навигации: Kollektionen · Themen ·
  Bereiche), `REPLACED_BY_BLOCKS` — девять `<surface>_page_style`.
- R6 сортировка: `tours_sort`, `blog_sort`, `reviews_sort` (умолчание владельца); туры — ★
  «Abschnitte» (Nach Ländern · Ohne Abschnitte).
- R7 `tours_layout` — оставить, комментарий/стратегия.
- R8 Team/Galerie ★ (вид как «nur hier» поверх вида главной).
- R9 документы.

## 3. Риски
Байт-в-байт (`data-sf-page`, гейты фото/подкатегорий после осей, `comp_owns_entries`, embed
услуг); общий каркас с каталогом и акциями — их эталоны на каждом срезе; stays/stay_rooms;
старые писатели без сброса видов; Студия не стирает строки; Team/Galerie — панель меняется.

## 4. Замки
R0 эталоны · R1 `test_fb31p4_parts` · R2 `test_fb31p4_storage` · R3 эталоны + `test_stu18d_compositions`
+ эталоны каталога/акций · R4 `test_fb31p4_writers` · R5 `test_fb31p4_panels` · R6 `test_fb31p4_sort`
· R7 `test_lay3a2_page_layouts` · R8 эталоны Team/Galerie.

## 5. Решения (рекомендации, приняты)
1. `tours_layout` оставить. 2. `*_layout`/`*_sort` — настройки страницы в панели ★. 3. Сортировка
туров/блога/отзывов — умолчание владельца, без выпадающего списка у посетителя. 4. Значения:
туры — Reihenfolge · nächster Termin · Name; блог — neueste · älteste; отзывы — neueste · beste
Bewertung. 5. Туры: «Nach Ländern / Ohne Abschnitte». 6. Подписи строки навигации — Kollektionen
(услуги, номера), Themen (события), Bereiche (сеты). 7. Недоступные плитки — серые с причиной.
8. Team/Galerie ★ — только вид (5), выбор состава — позже.

## 6. ECC-прогоны
Скиллы до кода: `django-patterns`, `django-tdd`, `python-testing`; R5/R8 — `accessibility`.
`django-reviewer` — каждый срез; `silent-failure-hunter` — R2–R4, R6; `security-reviewer` — R4, R6;
`database-reviewer` — R6; `a11y-architect` + Playwright 1440/390 — R5, R8; `doc-updater` — R9.
