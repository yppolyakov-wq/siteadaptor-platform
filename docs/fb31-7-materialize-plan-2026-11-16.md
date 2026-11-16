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
