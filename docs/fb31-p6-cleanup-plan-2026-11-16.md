# FB-31 P6 «Уборка» — план (2026-11-16)

Стратегия — `docs/fb31-block-strategy-2026-11-15.md` §6; хвосты — планы P3/P4/P5
(`docs/fb31-p5-detail-plan-2026-11-16.md` §9–§13). Разведка — `planner` (ECC). Кода нет.

## Главный вывод
Старые коды шаблонов (`*_page_style`, `page_styles`, `promo_*_style`, `Category.page_style`,
`Promotion.page_style`) — ДАННЫЕ: из них `page_parts.legacy_code`/`effective_rows` выводят оси,
когда своих строк нет; их пишут демо-киты и `sitetemplates`. Поэтому: (A) без переноса данных —
уходят писатели и интерфейс; (B) перенос данных и снос чтения — отдельной задачей FB-31.7.

## Срезы A (только код)
- A0 эталоны до кода: POST Студии до/после по `event_detail`, `service_detail`,
  `product_detail`, `detail_related_layout`, `page_styles`, `catalog_page_style`; замок
  «устаревшая вкладка Студии не откатывает порядок/видимость/раскладку из Seitenaufbau».
- A1 правка разделов уходит из Студии: писатели `ed_order_*`/`ed_visible_*`/`ed_layout`,
  `pd_*`, `sd_*` (`apps/core/views.py` ~2903–2949), `*_detail_sections`/`*_detail_layout` в
  `studio_pages.py`; в инспекторе — ссылка «Im Seitenaufbau bearbeiten». Писатель — один.
- A2 ось «Ähnliche» уходит из Студии (`studio_pages.py` 387, 487; `related_preset`).
- A3 плитки «Vorlage» уходят из Студии (`*_page_style`, `catalog/category_page_style`,
  `promo_*_style`; писатели views 2864–2901); сводки — по блокам (`effective_rows`).
  Проверить: кто ещё зовёт `materialize`/`drop_*_views` (ассистент, мастер).
- A4 ассистент `PAGE_SETTING`: снятые коды и разделы отвергаются ссылкой на «Seitenaufbau»;
  `out_max`/`out_mode` с мусором — ошибка, без `out_max` — прежнее значение.
- A5 формы объектов: переход «Im Seitenaufbau bearbeiten» предупреждает о несохранённых
  правках; вкладка карточки пишет `page_override` под блокировкой (Tenant → объект).
- A6 мелочи: кэш объекта на запрос в схеме объекта; пустые вкладки Tabs у событий/туров не
  рисуются (осознанная смена эталона); `catalog_parts` на ядро `page_parts`; сортировка туров
  по названию с умляутами.
- A7 документы (`doc-updater`).
Порядок: A0 → A1 → A2 → A3 (батч Студии, один CI) → A4 → A5 → A6 → A7.

## Срез B (перенос данных) — FB-31.7
B1 команда `materialize_page_axes` (идемпотентная, `--dry-run`, отчёт по схемам, шаг
`deploy.sh`); B2 после прогона на сервере — снос чтения `legacy_code`, демо-киты и
`sitetemplates` на оси, `seed --changed`. Риски высокие: эталоны на снимке прода, копия БД.

## Вопросы владельцу (рекомендация)
1. Разделы деталей (порядок, видимость, раскладка) — только в «Seitenaufbau»; в инспекторе
   Студии вместо ручек ссылка. [Да]
2. Плитки «Vorlage» уходят из Студии; шаблон — «+ Block › Vorlage anwenden». [Да]
3. Ассистент не меняет снятые коды и разделы — отвечает ссылкой на «Seitenaufbau». [Да]
4. Перенос данных и снос старых ключей — отдельно FB-31.7 после P6, с подсчётом на сервере. [Да]
5. Пустые вкладки в Tabs скрывать (смена HTML). [Да]

## ECC-прогоны
Скиллы: django-patterns, django-tdd, python-testing; A4 — django-security; A5 — accessibility;
B — database-migrations. `django-reviewer` — план и каждый срез; `silent-failure-hunter` — A1,
A3, A4, B1; `security-reviewer` — A1/A3 (POST Студии → конфиг), A4, A5; `database-reviewer` —
A5, A6, B1; `a11y-architect` + Playwright 1440/390 de/ru — A1, A5, A6; `doc-updater` — A7.
Гейт батча: `ruff format --check .`, `test_template_comments.py`, `i18n_quickcheck`,
`npm run build:css`, гейт с `apps/tenants`.
