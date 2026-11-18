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
- **Решение владельца (2026-11-18):** потолок своих хостов категорий поднять (`_MAX_CATEGORY_HOSTS`
  40 → 120, как у объектов) — перенос не пропускает сайты с большим каталогом.
- **Решение владельца (2026-11-18):** плитка вида у типа акции → ссылка «Im Seitenaufbau bearbeiten»
  (как решение 3); скрытая ветка `group_style:` в `promotions/views.py` уходит.
- **К B1b (ревью FB-32 S6f, 2026-11-18):** у `promo_detail` строка оси `offer` — ещё и место раздела
  (`detail_parts.AXIS_SECTIONS`). `materialize_rows` вставляет недостающую строку оси в начало:
  при якоре `related` и своих блоках без строки `offer` блоки «над Angebot» уехали бы в середину.
  Перенос: при якорях без строки `offer` — SKIP/MISMATCH, а не вставка.


## B1b — разведка перед кодом (2026-11-18)
- **Объём батча.** Чтобы каждая перенесённая поверхность сразу получила писателя на оси (иначе
  строки перекроют правку владельца), батч делится: **B1b-1** — поверхности уровня сайта
  (`catalog_page_style`, `site_defaults.category_page_style`, `promo_page_style`,
  `site_defaults.promo_group_style`, `site_defaults.promo_detail_style`) + их писатели
  (`apply_override`, демо-киты, `promotions/views.py` 498–505); **B1b-2** — коды объектов
  (`Category/Promotion.page_style`, `promo_groups[key].style`) + формы/типы акций (ссылка).
- **Сверка — по отрисованной странице, не только по осям.** Пример: у корня каталога код
  `sets` шапку не показывает (`public_views.py:2235`: `cat_style != "sets" or _head_explicit`),
  хотя `from_code("sets").head == "titelbild"`. Перенос «в лоб» (строка `page_head: titelbild`)
  включил бы шапку. Верный перенос — `page_head: aus` + `combos: above` (`legacy_code` того же
  набора — снова `sets`). Значит, `_view` каталога/акций = рендер страницы RequestFactory в схеме
  тенанта (без своих блоков и с ними) «старый конфиг» против «новый конфиг» и против «новый
  конфиг без старого ключа» (для B3); расхождение → SKIP/MISMATCH.
- **B1b-1 ✅ (код, 2026-11-18)**: писатель `siteconfig.set_page_template` (строки схемы, старый
  ключ снимается) и чтение `page_template_code`; `apply_override`/`current_value` — через них;
  перенос `page_axes_migration.migrate_templates` (ключ остаётся — решение 4) со сверкой осей и
  отрисованной страницы (`renderer(tenant)`: каталог, категория без своего шаблона, обзор, группа,
  акция; одноразовые токены форм маскируются; замок детерминизма); демо-киты — `templates_to_rows`
  (старых ключей нет); скрытые писатели `promotions/views.py` (`page_style`, `group_style:`) сняты.
  Сверка нашла и исправила читателя старого ключа: табы родительской категории
  (`public_views`, теперь `page_template_code`). Объекты (своя категория/акция/группа) — B1b-2.
- **Ревью B1b-1 (django-reviewer, silent-failure-hunter), исправлено:** «Alle Kategorien»
  (`category_page_style`) вынесен в B1b-2 — строки общего шаблона перекрыли бы
  `Category.page_style` (свой шаблон обязан побеждать; переносить вместе со своими кодами в
  `catalog:<slug>`); писатель выравнивает переводы своих блоков (`_with_host_rows`) и не теряет
  выбор молча (`TemplateNotExpressible` → `PageSettingError`); «тот же шаблон» и сверка переноса —
  по осям (`page_template_parts`/`page_template_is`, с правилом шапки корня у «sets»), а не по
  ближайшему коду; сбой рендера → `render-failed` (сайт не трогается, в отчёте), не-200 — «нечего
  сверять»; образцы сверки — акция/группа без своего шаблона и своих строк.
- **Остаток к B1b-2/B3:** читатели старых ключей в Студии (`core/views.py` ~3620, 3712–3726) —
  через `page_template_code`; маскировать обратные отсчёты в сверке, если на сервере будут
  ложные MISMATCH (безопасная сторона — сайт пропускается).


## B1b-2 план (planner, 2026-11-18)
Одна ветка, три коммита-подсреза, в `main` одним батчем (перенос и писатели вместе). Миграций
Django нет: шаг `materialize_page_axes` в `deploy.sh` уже есть, снимок — `SiteConfigSnapshot`.

**Решение владельца D1 (2026-11-18): «Да, копировать».** Новые хосты `category` и
`promo_group:<md5>` стартуют копией общих блоков и переводов (`siteconfig.page_rows`), как B1b-1
для `promo_group`: вид тот же, будущие правки общих блоков туда не доходят. В отчёт команды —
строка `detached: …`.

**Находки разведки:**
- Категория: витрина (`promotions/public_views.py:1637–1649`) берёт хост `catalog:<slug>`, только
  если в нём есть оси (`catalog_parts.has_parts`), иначе — `category` поверх своего кода. Цель —
  тот же вид явными строками своего хоста по всем осям (`write_rows`, `root=False`). Свои хосты и
  «Alle Kategorien» считаются от ИСХОДНОГО `norm` (иначе вид накладывается дважды).
- Хост категории только с осями (без блоков с `id`) не забирает блоки (`has_own_schema`,
  `siteconfig.py:1794`; `category_blocks`/`place_banners` в `siteui.py:458, 526`).
- Группа: `promo_blocks` (`siteui.py:494`) берёт свой хост при наличии ключа → новый
  `promo_group:<md5>` начинается с `page_rows`. У `group_parts` (`promo_parts.py:113`) две оси —
  свой код писать по всем осям явно (`page_parts.rows_with(..., explicit=True)`, `materialize_rows`
  — обёртка), иначе после B3 `head` придёт из общих строк.
- Акция: свой код сильнее строк `promo_detail`, хост `promo:<hex>` — слой поверх; блоки добавляются,
  копировать нечего. `offer` — ещё и место раздела: якоря без строки `offer` → SKIP.
- Читатель старого ключа: табы родителя (`public_views.py:1827`) — общий помощник
  `catalog_parts.category_parts(cfg, category)` для 1637–1649 и 1827.
- Студия `core/views.py:3620, 3712–3726` → `page_template_code` или удалить по grep с замком.
- Потолок: `normalize` молча режет хосты по алфавиту (`siteconfig.py:1834–1837`) — перед записью
  явная проверка «существующие + новые ≤ потолка».
- Скрытые писатели: `promo_type_save` ветка `style:` (`promotions/views.py:435`),
  `_drop_own_offer_view` (1138–1149), `setup_assistant.py:494`, сид категорий `demo_kits.py:25131`.
- Писатель «Alle Kategorien» (`page_settings.py:672`) после перехода на строки перекрыл бы свой
  шаблон категории без своих осей → перед записью закреплять свои коды категорий.

**B1b-2a — ядро и читатели (вид не меняется):** `_MAX_CATEGORY_HOSTS = 120`;
`PAGE_TEMPLATE_HOSTS["category_page_style"] = ("category", ("site_defaults","category_page_style"))`
+ ветка `category` в `page_template_parts/is/code` и `set_page_template`; `rows_with(explicit=)`;
`category_parts`; переключатель `page_axes_migration.objects_blind()` (contextvar, только команда и
тесты: витрина не видит своих кодов объектов — рендер вида после B3); Студия.

**B1b-2b — перенос объектов:** `ObjectIndex` в `apply_tenant` (категории, акции с `page_style`,
живые группы, id для чистки призраков; `migrate` чистый). Поверхность `categories` одной единицей
(свои коды → `catalog:<slug>`, затем `category_page_style` → `category`; SKIP — целиком);
`promo:<hex>`; `promo_group:<md5>` по живым группам (`orphan` не блокирует). Потолки: сначала
чистка хостов удалённых объектов, нет места — SKIP `hosts_full`. Сверка: оси
(`want == after == bare`, `bare` — без ключа и с `objects_blind`) + рендер три раза (старый / новый /
новый без ключа + `objects_blind`) по страницам `pages(cfg, unit)`. Повтор → SAME; `ROLLED_BACK`
не трогается; `--undo`.

**B1b-2c — писатели, формы, ссылка:** поле «Vorlage der Seite» → ссылка «Im Seitenaufbau
bearbeiten» (категория: `catalog/forms.py`, `category_form.html`, на создании — подсказка; акция:
`promotions/forms.py`, `promotion_form.html`; тип акции: `promo_type_save` игнорирует `style:`,
`promo_type_list.html` → ссылка на схему группы); `page_settings` — `category_page_style` строками с
закреплением своих кодов (`PageSettingError`, без тихой потери); демо-киты без `page_style`,
прогон тех же единиц; `promotions/tasks.py:163` — `object_structure.copy_blocks("promo", old, heir)`
под блокировкой, потолок → чистка, нет места — `logger.warning`, наследник создаётся;
`studio_pages.py:178, 266` — до B3 в исключениях.

**Замки до кода:** `test_fb317_b1b2_migrate.py` (свой код + строки `category`; скрытая «Kategorien»
→ SKIP; 118+5 хостов → чистка → `hosts_full`; группа со своим `view` при общей `head` → `head` явно;
копия блоков группы; акция без `offer` → SKIP; `orphan`; повтор → SAME; `--undo`; хост с одними
осями не забирает блоки); рендер-замок демо-китов «до = после»; текстовый замок писателей
`page_style=`/`["style"]`; наследник акции; ссылка (имя, `<a>`, `?seite=`).

**Риски:** D1; время рендера (≤120 категорий × 3) — замер на крупнейшем ките; ложные MISMATCH от
дат/отсчётов (безопасная сторона — SKIP); открытые черновики — прогон в тихие часы; ключ группы с
пробелами (`siteconfig.py:5076` против `1319`) — хост по точному `Promotion.group`.

**ECC-прогоны:** скиллы до кода — django-patterns, django-tdd, python-testing, database-migrations,
postgres-patterns, django-security, accessibility, error-handling. Агенты: `django-reviewer` — план и
каждый подсрез; `database-reviewer` — 2b и `copy_blocks`; `silent-failure-hunter` — 2b и 2c;
`security-reviewer` — 2c; `a11y-architect` — ссылка; `code-reviewer` — ветка перед мержем. Гейт:
`ruff format --check .`, `test_template_comments`, `i18n_quickcheck`, `apps/tenants`, `test_fb31*_golden`.
