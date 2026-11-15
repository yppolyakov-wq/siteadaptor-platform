# FB-31 — одна стратегия блоков для «Seitenaufbau»

Дата: 2026-11-15. Запрос владельца: «Прогони с ECC всю структуру страниц и выработай для блоков
одну стратегию». Основание — решение владельца: «настройки привязаны к блокам… к типам выводимой
информации, а не к шаблону; идея с разбивкой верная» (`fb30-16-catalog-parts-plan-2026-11-15.md` §0).
ECC: обход всех 26 типов страниц (два `Explore`), разведка каталога (`planner`, там же §7),
стратегия (`architect`). Документ на утверждение; кода нет.

## 1. Правила (11)
1. **Тип блока = тип содержимого**: Banner, Kategorien/Gruppen, Liste von X, Sets, Text, Bild,
   Bild+Text, Button, Textseite, Kontakt, ссылочные секции, разделы детали. Вид («Regale»,
   «Magazin», «Plakat») — значение оси «Darstellung» своего типа, не ключ и не шаблон.
2. **Одна панель на тип, одинаковая на всех страницах.** Образец — список главной «Was · Welche ·
   Wie». Страница может скрыть недоступные оси, своих не добавляет.
3. **★ = «Liste von <содержимое страницы>»** с той же панелью + группа «Seite»: сортировка,
   фильтр (an · aus · Seitenspalte), постранично (каталог и акции), группировка (акции, туры).
4. **Настройка живёт на блоке, чьё содержимое меняет.** Строка «Einstellungen der Seite» — только
   раскладка детали (Standard · Tabs · Breit); у прочих страниц её нет.
5. **Шаблон страницы = готовый набор блоков**: выводится при чтении (сайт байт-в-байт), при первой
   правке записывается строками. Выбор набора — «Vorlage anwenden» в «+ Block»; плиток шаблона в
   панелях нет.
6. **Значения по умолчанию — в «Design», блок может поставить своё** («wie Design: Kompakt» /
   «nur hier»): форма карточки, ширина текста, правила цен меню. Порядок: объект → блок → Design.
7. **Навигационные виды «Kategorien»** (Seitenspalte, Regale, Reiter, Index) прикреплены к ★ —
   прямо над ним; прочие блоки двигаются свободно.
8. **Детальная страница — тоже схема блоков**: разделы — системные блоки (показ, порядок),
   покупка закреплена, свои блоки между разделами, «Ähnliche / Passt dazu» — Liste.
9. **Своя схема объекта** (товар, категория, акция) — та же схема с отличиями «nur hier».
10. **«Ведомых» страниц нет**: категория, группа акций, акция — пункты выбора «Alle … / nur diese»;
    `SETTINGS_FOLLOWERS`/`SETTINGS_CARRIERS` пустеют.
11. **Одна модель хранения**: строки `page_blocks[host]` (на главной `sections`); встроенные
    строки без id разрешены на любом хосте с активным модулем (расширить белый список
    `normalize_page_blocks` — сейчас молча выкидывает их вне главной).

## 2. Каталог типов блоков
| Тип | Оси панели | Данные сегодня | Новое |
|---|---|---|---|
| Banner | источник (библиотека · фото страницы), выбор, Darstellung (Streifen · Titelbild · Plakat · Prospekt), слайдер | C-блок `banner`, `hero_style`/`hero_banners`, «Kopfbild» = первый баннер | источник «фото страницы», виды Plakat/Prospekt |
| Kategorien / Gruppen | Welche (все · верхние · вручную, подкатегории сначала), Wie (фотоплитки · чипы · Regale · Reiter · Index · Seitenspalte · Wegweiser), колонки | builtin `categories` главной, коды `*_page_style`, `catalog_subcats_first` | навигационные виды |
| Liste von X | Welche (правило · категория · вручную, сортировка, не больше), Wie (Raster · Slider · Schaufenster · Magazin · Mosaik · Preisliste · Vergleich · Countdown, колонки, ряды, Kartenform) | блок `list`, встроенные строки, `*_layout`, `*_sort`, `card_style`/`promo_card` | Team/Galerie как источники |
| ★ Hauptliste | как Liste + «Seite» | маркер `main` (только позиция) + ключи страницы | поля маркера |
| Sets & Menüs | как Liste, источник `combos` | позиция по коду `sets` | `combos` в `BUILTIN_LIST_SOURCES` |
| Text, Bild, Bild+Text, Button, Spacer | поля | C-блоки | – |
| Textseite | текст, ширина (wie Design / nur hier) | `textpage`, `text_width` | поправка |
| Kontakt | карточка контактов | `contact_card`, `CONTACT_REF` | – |
| Ссылочные (FAQ, USP, Stats, Newsletter, Finder, Stay-Suche) | только структура | секции | – |
| Раздел детали | показ, порядок; у related/upsell — Wie | `<kind>_detail.hidden/layout`, `page_override` | строки схемы (сейчас скрыты `is_studio_only`) |

## 3. Целевая структура страниц
| Страница | Блоки |
|---|---|
| home | Banner · встроенные Listen · свои блоки (★ нет) |
| catalog | Banner · Kategorien · Sets · **★ Produkte** · свои блоки |
| category (alle / nur diese) | Banner (фото страницы) · Kategorien (подкатегории) · Sets · **★ Produkte** |
| product, service, stay, event, tour | Kaufbereich · разделы · свои блоки; Seite: раскладка |
| combos · lookbook · wishlist | Banner? · **★ Sets / Looks / Merkzettel** |
| cart | корзина (закреплена) · Liste «Passt dazu» (вместо `cart_upsell`) |
| finder | Finder (закреплён) · **★ Ergebnis** |
| promos | Banner · Gruppen · **★ Aktionen** |
| promo_group (alle / nur diese) | Banner (Prospekt/Countdown) · **★ Aktionen** |
| promo | Banner (Plakat/Magazin) · предложение (закреплено) · свои блоки |
| services · stays · events | Banner · Kategorien (если есть) · **★** |
| tours | Banner · **★ Reisen** (группировка по странам) |
| blog · reviews | Banner · **★** |
| text | Kontakt (если включён) · Textseite · блоки |
| team · gallery | Textseite · **★ Team / Fotos** (новое) |
| contact | форма (закреплена) · Kontakt · блоки |

## 4. Куда переезжает каждая настройка
| Сейчас | Новое место |
|---|---|
| `home_hero` | Banner › Wie |
| `home_sections` | строки схемы |
| `*_page_style` (каталог, категория, 9 листингов, акции, группа, деталь акции) | набор блоков: kopfbild/prospekt/plakat → Banner; regale/tabs/navigator/kompakt/wegweiser → Kategorien; schaufenster/magazin/mosaik/preisliste/vergleich/countdown → ★ Darstellung; sets → позиция Sets |
| `*_layout` листингов | ★ › Wie |
| `tours_layout` | убрать (страница не читает) |
| `*_sort` | ★ › Seite › сортировка (+ туры, блог, отзывы, акции) |
| `catalog_filters` | ★ › Seite › фильтр |
| `catalog_subcats` | Kategorien › Welche |
| `promo_grouping` | ★ Aktionen › Seite › группировка |
| `product_card_form`, `promo_card_form` | Design + «nur hier» на Liste/★ |
| `catalog_menu_prices/labels` | Design › Karten |
| `text_width` | Design › Layout + поправка у Textseite |
| `product_related` | раздел «Ähnliche» › Wie |
| `cart_upsell` | блок «Passt dazu» вкл/выкл |
| `*_detail_sections` | строки разделов детали |
| `*_detail_layout` | строка «Seite» детали |

## 5. Совместимость
Миграций нет: вывод при чтении (`apps/core/page_parts.py` — общее ядро `effective_rows`,
`legacy_code`, `materialize`; поверхностные модули `catalog_parts`, `promo_parts`, `listing_parts`).
Старые ключи — запасное значение до уборки. Студия (`merge_structure`, `protect_owned`,
`structure_hash`) знает новые поля; POST Студии с `*_page_style` идёт в `materialize`.
`sitetemplates`/бандлы пишут прежние ключи — вывод их понимает. Демо-киты не трогаем; после деплоя
`seed --changed` без изменений HTML. Золотые снимки — как `test_fb3016_catalog_golden.py`, до кода
каждой фазы.

## 6. Фазы (каждая: замки → ревьюеры ECC → зелёный CI → FF)
- **P0 Каркас**: ядро `page_parts`, белый список строк, панель ★ = `list_panel` + «Seite».
  `planner`, `database-reviewer`, `silent-failure-hunter`.
- **P1 Каталог + категория (пилот)**: FB-30.16 R0–R6 + «Alle Kategorien». `security-reviewer`
  (R3), `a11y-architect` + стенд (R4).
- **P2 Design**: Kartenform, ширина текста, цены меню → «Design»; на блоках «wie Design / nur hier».
- **P3 Акции**: promos, promo_group, promo — отдельные пункты выбора.
- **P4 Девять листингов + team, gallery**: сортировка везде, снять `tours_layout`.
- **P5 Детали**: разделы — строки схемы, тур в `LAYOUT_KINDS`.
- **P6 Уборка**: плитки «Vorlage», сводки Студии, ассистент, формы объектов → ссылки. `doc-updater`.

## 7. Вопросы владельцу (рекомендация)
1. Kartenform, ширина текста, цены меню — по умолчанию в «Design», на блоке «nur hier»? [Да]
2. Категория, группа акций, акция — пункты «Alle … / nur diese», ведомые строки убрать? [Да]
3. Строка «Seite» — только у деталей (раскладка)? [Да]
4. Шаблоны страниц — только «Vorlage anwenden» в «+ Block», без плиток в панели? [Да]
5. Разделы детали двигать в любом порядке (покупка закреплена)? [Да]
6. Сортировку/группировку — турам, блогу, отзывам, акциям? [Да; постранично — каталог и акции]
7. Team и Galerie получают ★? [Да, в P4]
8. Ширина текста «nur hier» только у Textseite? [Да]
Плюс вопросы каталога из `fb30-16…` §7: копия блоков для «Alle Kategorien»; шапка категории —
Banner «фото страницы»; навигационные виды прикреплены к ★; `Category.page_style` — поправка до
правки в «Seitenaufbau»; «6 колонок» у Index — на ★.

## 8. Макеты на утверждение (до кода)
1. Панель ★ Produkte (Welche · Wie · Seite, Kartenform плитками «wie Design»).
2. Панель Kategorien (7 видов плитками, «прикреплено к ★»).
3. Banner: источник «фото страницы», виды Plakat/Prospekt.
4. Выбор страниц: «Alle Kategorien / nur diese», то же для акций.
5. Схема детали: покупка, разделы, свои блоки, строка «Seite».
6. Design: вкладки «Karten» и «Layout».
7. «+ Block › Vorlage anwenden» с предупреждением.
8. Корзина «Passt dazu»; Finder ★ Ergebnis.
9. Телефон (390) для 1–3.
