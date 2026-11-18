# FB-31.7 — перенос старых кодов шаблонов в строки-оси (план, 2026-11-16)

Решение владельца (P6): перенос и снос — отдельной задачей после P6. Разведка — `planner`.
Кода нет.

## Главное
`page_parts.legacy_code` НЕ сносится: CSS и разметка витрины ключуются кодом
(`data-cat-layout`, `data-sf-page`); он переводит оси в код для рендера. Сносится чтение
СТАРЫХ КЛЮЧЕЙ как источника осей (аргумент `code=` в `effective`/`effective_rows`/
`detail_parts`/`group_parts`). До переноса — перевести писателей на оси, иначе после переноса
строки перекроют код и правка владельца молча пропадёт.

## Инвентарь старых ключей
`page_styles[surface]` (листинги), `catalog_page_style`, `site_defaults.category_page_style`,
`Category.page_style`, `promo_page_style`, `site_defaults.promo_group_style`,
`promo_groups[key].style`, `site_defaults.promo_detail_style`, `Promotion.page_style`.
Писатели: `page_settings.apply_override`, `promotions/views.py` (~498, 524, 1156), формы
Category/Promotion, `setup_assistant.py` (440, 494), демо-киты (≈12 мест). `materialize` в
`page_parts` нет (стратегия §5 на него ссылалась).

## Команда `materialize_page_axes`
Каркас как `import_banners` (`--schema`, сбой схемы не останавливает остальные). Режимы:
`--dry-run`; `--apply --backup <file.jsonl>` (снимок `site_config` до записи); `--undo --from
<file>` (вернуть снимок, если с тех пор не менялся). Пишет строки-оси слиянием (id/порядок
сохраняются, поле — только где не задано, presence-minimal; обычный набор — ничего).
Хосты: листинги (`HOST_OF`), `catalog`/`category`, `catalog:<slug>` (категория со своим
кодом — полный набор с учётом `category`), `promos`/`promo_detail`/`promo_group`/группы,
`promo:<uuid>`. Проверка байт-в-байт: переключатель `page_parts.legacy_reading(False)`
(contextvar, только команда и тесты) — рендер ключевых страниц «старый конфиг + старое
чтение» против «новый конфиг + без старого чтения» (RequestFactory, нормализация HTML) + сверка
`Parts`; расхождение — тенант не пишется, дифф в файл, `MISMATCH` в отчёте. Запись —
транзакция на тенанта, `select_for_update`, повтор — 0 изменений. Отчёт по схемам.

## Срезы
- B1: `legacy_reading`, команда, замки (все демо-киты «до = после»; скрытая строка, мусорный
  код, свои строки поверх кода, категория со своим кодом + `category`, повтор, `--undo`);
  `deploy.sh` — только `--dry-run` с WARN.
- B2 (до прогона на сервере): писатели на оси — формы Category/Promotion, `promotions/views`,
  `apply_override`, `setup_assistant`, демо-киты; досверить `sitetemplates` (~2039–2145);
  замок «новый код не пишет старые ключи»; `seed --changed`, HTML без изменений.
- Прогон у владельца (ниже).
- B3 (после подтверждённого прогона): снять чтение старых ключей (`code=`, `from_code` у
  читателей), `drop_*_views`, поля форм; данные старых ключей — через релиз.

## Владельцу
1. `./scripts/backup.sh single`.
2. Копия БД в том же Postgres: `createdb siteadaptor_copy`, `gunzip -c db-<дата>.sql.gz | psql
   … siteadaptor_copy` (проверить, что `production.py` берёт `DB_NAME` из env).
3. На копии: `… run --rm -e DB_NAME=siteadaptor_copy web python manage.py
   materialize_page_axes --dry-run`, затем `--apply --backup /tmp/fb317.jsonl`, затем снова
   `--dry-run` (0 изменений); прислать отчёт.
4. На проде после свежего бэкапа — `--apply --backup …`; откат `--undo --from …`.

## Риски
Тихие писатели (B2 до прогона); скрытая строка (`enabled: False`) сейчас отдаёт ось коду;
открытые черновики «Seitenaufbau» получат конфликт (прогон в тихие часы); миграций нет.

## ECC-прогоны
Скиллы: database-migrations, django-patterns, django-tdd, python-testing; B2 — django-security.
`django-reviewer` — план и каждый срез; `database-reviewer` — B1, B3; `silent-failure-hunter`
— B1, B2; `security-reviewer` — B2; `code-reviewer` — ветка перед мержем; `doc-updater` —
после B3. Гейт: `ruff format --check .`, `test_template_comments`, `i18n_quickcheck`,
`apps/tenants` и все `test_fb31*_golden`.

## Решения владельца (2026-11-16)
1. Запуск — сразу шагом `deploy.sh` (не вручную на копии). Следствия: B1 (команда) и B2
   (писатели на оси) попадают в `main` ОДНИМ батчем; шаг `deploy.sh` всегда пишет снимок
   `site_config` для отката (`--backup` в каталог бэкапов сервера) и не роняет деплой при
   сбое отдельной схемы (WARN + отчёт); повторный деплой — 0 изменений.
2. Сайт с расхождением «до/после» (или со скрытой строкой, которую сейчас заменяет старый
   код) — пропустить и показать в отчёте; допуск расхождений — ноль.
3. Поле «Vorlage der Seite» в формах категории и акции — убрать, вместо него ссылка
   «Im Seitenaufbau bearbeiten».
4. Данные старых ключей — удалить через релиз после B3, отдельным шагом с бэкапом.

## Ход работ
- B1a (2026-11-17): ядро `page_parts.materialize_rows` (строки, дающие без кода тот же вид;
  скрытая строка, которую заменяет код, — None), модуль `apps/core/page_axes_migration.py`
  (поверхности переносятся по одной, вид сверяется после нормализации, расхождение — SKIP/
  MISMATCH, старые ключи остаются), команда `materialize_page_axes` (`--schema`, `--dry-run`,
  `--undo`), снимки — таблица `SiteConfigSnapshot` (миграция `tenants/0043`, public): откат,
  если настройки не менялись; откаченный сайт следующий деплой не трогает. Шаг `deploy.sh`
  после `import_banners` (сбой — WARN). Поверхности: девять листингов (`page_styles`) —
  писатель в интерфейсе уже недоступен (P6), поэтому B2 для них не нужен.
- Дальше: B1b каталог (`catalog_page_style`, `site_defaults.category_page_style`) и обзор
  акций (`promo_page_style`) — с переводом их писателей (демо-киты, `promotions/views`);
  затем объектные коды (`Category/Promotion.page_style`, группы) — с учётом лимита 120 хостов.
- Ревью B1a (`database-reviewer`, `silent-failure-hunter`): хэш отката — после записи и чтения
  из JSONB; перенос считается без блокировки, под блокировкой — сверка «не менялось» (иначе
  заново, до 3 раз) и `lock_timeout` 2 с; снимок — только меняемые ключи (`page_blocks`,
  `i18n`); индекс (tenant, reason, -created_at); переводы блоков выравниваются
  (`realign_block_overlays`); сверка — оси, свои блоки над/под ★, композиция при всех гейтах
  данных, переводы каждого языка; сайт записывается целиком или не трогается; откаченный сайт —
  тихо; итог пропущенных сайтов — одной строкой.
- **К B3 (до сноса чтения кода):** `_draft` и `history` в `site_config` хранят полные старые
  конфиги с кодами — публикация черновика Студии / откат версии после сноса вернут код без
  строк. Перед B3: перенести и их (или очистить), замок.


## План B1b + B2 (planner, 2026-11-18) — одна ветка, в `main` одним батчем
- **Замки до кода:** писатели не пишут старые ключи (демо-конфиг, сырой `site_config`,
  `Category/Promotion.page_style`); текстовый замок по `apps/` (закрытый список исключений:
  читатели, `page_axes_migration`, `promotions/tasks.py:163` до B3); «до = после» на всех
  демо-китах для catalog/category/catalog:<slug>/promos/promo_group/групп/promo_detail/promo:<hex>
  (скрытая строка, мусорный код `demo_kits.py:3909`, потолок хостов, повтор, `--undo`).
- **B1b:** `page_parts.rows_with(s, rows, target, explicit=…)` (`materialize_rows` — обёртка;
  `explicit` — свой код объекта перекрывает общий вид целиком); такой же у `catalog_parts`;
  чистые правила вида `catalog_parts.page_parts` и `promo_parts.overview_parts` (из
  `public_views`/`site_schema`); новый хост начинается с `siteconfig.page_rows` (иначе
  `category_blocks`/`promo_blocks` молча теряют блоки каталога/обзора); объекты читаются в
  `schema_context`; потолки хостов (`_MAX_OBJECT_HOSTS = 120`, категорий 40, групп 40) —
  сначала чистка хостов удалённых объектов, иначе SKIP `hosts_full`.
- **B2:** один помощник `siteconfig.set_page_template(cfg, host, code)`; `apply_override`
  (закрывает ассистента, `page_settings.write`, превью `?tpl=`, старые черновики); формы
  категории и акции — поле убрать, ссылка «Im Seitenaufbau bearbeiten»; `promotions/views.py`
  скрытые ветки `page_style`/`group_style:` снять (**HIGH**: `views.py:519` заменяет словарь
  группы строкой — тихая потеря карточки/раскладки); плитка вида у типа акции → ссылка на
  схему группы; демо-киты — `kit_page_template(host, code)`, `seed --changed` байт-в-байт;
  `tasks.py:163` (повтор акции) копирует и строку `offer` хоста `promo:<old>`.
- **До B3:** откат версии и `_draft` Студии возвращают коды без строк — перед B3 переносить и их.
- **Вопросы владельцу:** каталоги с > 40 категориями со своим видом — поднять потолок или
  SKIP; плитка вида у типа акции → ссылка (как решение 3).
