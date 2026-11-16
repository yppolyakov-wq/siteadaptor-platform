# FB-31 P3 «Aktionen» — три страницы акций из блоков

Дата: 2026-11-16. Основание — стратегия `fb31-block-strategy-2026-11-15.md` (§3, §4, §6 P3), образец —
каталог FB-30.16 (`fb30-16-catalog-parts-plan-2026-11-15.md`, `apps/catalog/catalog_parts.py`).
Разведка: агент `planner` (ECC). Срезы R0–R4 вида не меняют (вывод при чтении, сайт байт-в-байт);
R5–R6 — экран, после макетов (стратегия §8.4).

## 0. Что показала разведка
- `/aktionen/` и страница группы (`?gruppe=`) — одна вьюха `promotion_list` и один шаблон
  `promotions_list.html`; шаблон всегда зовёт `{% page_blocks "promos" %}` — группы сегодня показывают
  блоки обзора. Новый хост группы до сохранения обязан брать блоки `promos` (как `page_rows(category)`).
- У детали акции отдельного баннера нет: plakat/prospekt/kompakt/magazin — CSS по
  `data-promo-detail`. «Banner (Plakat/Magazin)» стратегии = **Darstellung закреплённой строки
  «Angebot»**.
- На обзоре от кода зависит только CSS `[data-promo-page="navigator"]`; прочее — ветки шаблона.
  Шаблон читает оси напрямую, `data-promo-page`/`data-promo-detail` — по `legacy_code`.
- Пишут старые ключи: `page_settings.apply_override`, POST Студии (`views.py`), кабинет типов
  акций (`promotions/views.py` `page_style`, `promo_groups[key].style`), демо-киты (не трогаем).
- Поправки объектов: группа `promo_groups[key].style` → `site_defaults.promo_group_style`;
  акция `Promotion.page_style` → `site_defaults.promo_detail_style`.

## 1. Код → оси
**promos** (`promo_page_style`)

| Код | Banner `page_head` | Gruppen `groups` | ★ Darstellung | flach |
|---|---|---|---|---|
| "" | aus | auto | raster | – |
| kopfbild | titelbild | auto | raster | – |
| preisliste | aus | auto | preisliste | – |
| regale | aus | regale | raster | – |
| tabs | aus | tabs | raster | – |
| schaufenster | aus | auto | schaufenster | – |
| navigator | aus | side | raster | да |
| magazin | aus | auto | magazin | да |
| kompakt | aus | index | prospekt | да |

★ › Seite: `promo_grouping` (Thema · Zeit · ohne — «ohne» = флаг flach), `promo_index_layout`.

**promo_group** (`site_defaults.promo_group_style`, поправка `promo_groups[key].style`)

| Код | Banner | ★ Darstellung |
|---|---|---|
| "" | standard | raster |
| schaufenster | standard | schaufenster |
| prospekt | prospekt | prospekt |
| magazin | standard | magazin |
| countdown | countdown (сортировка по окончанию, если нет `?sort`) | raster |
| vergleich | standard | vergleich |

**promo** (`promo_detail_style`, поправка `Promotion.page_style`): строка «Angebot» (закреплена,
первая) с видом standard · plakat · prospekt · kompakt · magazin; свои блоки — `promo_detail` и
`promo:<hex>`; ★ нет.

## 2. Срезы (каждый: замки → ревьюеры ECC → зелёный CI → FF)
- **R0 Золотые** — `apps/promotions/tests/test_fb31p3_promo_golden.py` + `golden_fb31p3/`
  (`FB31P3_GOLDEN=update`): 9 кодов обзора × группы есть/нет × группировка × блок «Liste»;
  6 кодов группы × своя поправка/умолчание × `?sort`; 5 кодов детали × `Promotion.page_style`.
- **R1 Чистые модули** — общее ядро `apps/core/page_parts.py` (описание поверхности: строки → оси,
  таблица код↔части; `from_code`, `legacy_code`, `rows_for`, `from_rows`, `has_parts`,
  `effective`) + `apps/promotions/promo_parts.py` (поверхности PROMOS, PROMO_GROUP, PROMO_DETAIL).
  `catalog_parts` не трогаем до R7.
- **R2 Хранение** (`siteconfig`): встроенные строки хостов promos (`page_head`, `groups`),
  `promo_group`/`promo_group:<hex>` (`page_head`), `promo_detail`/`promo:<hex>` (`offer`); поля ★ по
  хосту; `main_list_sequence` (шапка первой, группы над ★, «Angebot» первой); хост `promo_group`
  с откатом на блоки `promos`; `drop_page_views(cfg, host)`.
- **R3 Витрина читает части** — `promotion_list` и деталь через `promo_parts.effective`; шаблон
  `{% page_blocks promo_blocks_host %}` (своя группа → `promo_group` → `promos`).
- **R4 Писатели** — старые ключи снимают виды (`apply_override`, Студия, кабинет типа акций);
  Студия (`merge_structure`/`protect_owned`/`structure_hash`) знает новые строки.
- **R5 Панели и операции** (после макетов) — `_part_view_panel(surface)`, плитки с причиной
  недоступности (нет групп), `REPLACED_BY_BLOCKS` для трёх кодов, ★ › Seite.
- **R6 Выбор страниц** — группа «Aktionen»: «Aktionen», «Alle Angebotsgruppen», живые группы
  (один запрос, до 40), «Angebot»; `SETTINGS_FOLLOWERS = {}`; adopt — общий для категорий и групп.
- **R7 Уборка** — плитки «Vorlage» трёх кодов, кабинет типа акций → ссылка, ассистент, перевод
  `catalog_parts` на ядро, документы.

## 3. Риски
Байт-в-байт (ветки flat/regale/preisliste/countdown выводятся из частей без смены умолчаний —
R0 закрывает каждую); старые писатели без `drop_page_views` молча проигрывали бы строкам;
Студия без `merge_structure` стирала бы строки; хост группы без отката убрал бы блоки обзора;
ключи групп — свободный текст (переименование осиротит `promo_group:<hex>`, как уже `promo_groups`);
i18n (5 `.po`), Tailwind (`build:css`), однострочные `{# #}`.

## 4. Решения (рекомендации планировщика, по правилу владельца «по рекомендации» стратегии)
1. Вид детали (Plakat/Magazin/…) — Darstellung строки «Angebot», не отдельный баннер. [Да]
2. «Alle Angebotsgruppen» при первом сохранении — копия блоков «Aktionen». [Да]
3. Свой шаблон группы/акции сильнее общих строк (объект → блок → Design), пока у объекта нет своей
   схемы. [Да]
4. Countdown сортирует по окончанию неявно; явная сортировка ★ — в P4. [Да]
5. «Flach» — значение группировки «ohne». [Да]
6. В выборе — только группы с действующими акциями, до 40. [Да]

## 5. ECC-прогоны
- До кода: `django-patterns`, `django-tdd`, `accessibility` (R5).
- `django-reviewer` — каждый срез; `silent-failure-hunter` — R2–R4; `security-reviewer` — R4, R6;
  `database-reviewer` — R6 (запрос групп); `a11y-architect` + Playwright 1440/390 — R5, R6;
  `doc-updater` — R7.

## 6. Ход работ
- R0–R4 сделаны (2026-11-16): снимки 49, ядро `page_parts` + `promo_parts`, хранение строк,
  витрина читает оси (байт-в-байт), писатели снимают виды. У ★ явное «как обычно»: вид
  `raster`, абзацы `auto` (сильнее кода шаблона, как «Raster» каталога).
- Ревью `django-reviewer` R1–R4: сырые строки осей в схеме (закрывает R5); битый
  `page_blocks` в сыром конфиге детали → защита; шаблон акции в её форме снимает вид строки
  «Angebot» её своих блоков (последнее решение владельца); `apply_override` снимает виды только
  при смене шаблона (повтор черновика/ассистент их не стирает).
- R5: строки «Banner · Fotos der Seite», «Angebotsgruppen» (над ★) и «Angebot» (деталь, первой)
  закреплены, панели с плитками и причиной недоступности (нет групп); ★ «Aktionen» — вид и
  «Abschnitte» (по группам / без абзацев); `promo_page_style`/`promo_detail_style` убраны из
  панели настроек (`REPLACED_BY_BLOCKS`).
