# FB-29.4b — своя структура страницы у товара и услуги

Дата: 2026-11-14. План агента `planner` (разведка кода), до кода. Решение владельца
(2026-11-14): объект не только показывает/скрывает разделы общей структуры, но и держит СВОИ
блоки, видимые лишь на его странице. Макет — `docs/design/fb29-2026-11-13/Struktur.dc.html`
(D), дополняется зоной «Eigene Blöcke dieses Produkts».

## 1. Что есть в коде (проверено)

- `detail_sections.py`: секции товара (`catalog`) и услуги (`booking`) только скрываются,
  порядка нет. `siteconfig.normalize_detail_sections` / `detail_section_hidden` /
  `detail_layout` читают `site_config["product_detail"|"service_detail"]` = `{hidden, layout}`.
- Витрина товара: `promotions/public_views.py` (`product_detail_hidden`), шаблон
  `storefront/product_detail.html` (`{% page_blocks "product_detail" %}`). Услуга:
  `booking/public_views.py:_service_rich_context`, `service_detail.html`.
- Своя схема категории (FB-27 R7): `site_config["page_blocks"]["catalog:<slug>"]`
  (`_CATEGORY_HOST_RE`, `_MAX_CATEGORY_HOSTS = 40`, `has_own_schema`), в экране — строка
  `category@catalog:<slug>` (`site_schema.host_for`), на витрине — тег `category_blocks`,
  уборка — `content_pages.move_page_blocks(prefix="catalog:")`; переводы — оверлей
  `i18n[loc]["page_blocks"][host]` (`realign_block_overlays`).
- `Product.card_style` есть (`card_forms.card_form`: товар → категория → сайт); у `Service`
  такого поля нет. PK обоих — UUID; `Product` удаляется мягко.
- Не проверено: дублирование товара/услуги, CSV-импорт/экспорт, вкладки `service_page.html`.

## 2. Хранение — у каждой оси один писатель

1. **Показ секций и шаблон страницы** — поле `page_override = JSONField(default=dict)` у
   `Product` и `Service`: `{"hidden": [...], "shown": [...], "layout": ""}`. `site_config`
   не растёт на тысячах товаров, удаление каскадное, текстов нет.
2. **Форма карточки** — `Product.card_style` (есть) и новый `Service.card_style` (тот же реестр).
3. **Свои блоки** — `site_config["page_blocks"]["product:<uuidhex>"|"service:<uuidhex>"]`,
   как у категории: переводы, черновик, `mutate`, панель, `aufbau.js`, тег `page_blocks`
   достаются без второго писателя. Потолок `_MAX_OBJECT_HOSTS = 60` (замок). Уборка: удаление
   объекта → `move_page_blocks(pk, None, prefix=…)`; копия объекта → копия хоста с новыми id.

## 3. Сборка страницы — `apps/core/object_structure.py`

- `effective_hidden(config, module, obj)` = (общее скрытие − `shown`) ∪ `hidden`, только
  ключи реестра; `effective_layout`; `object_host(kind, obj)`; `reset(obj)`.
- Витрины берут значения из этого модуля; новый тег `siteui.object_blocks` сразу после
  `{% page_blocks "<kind>_detail" %}`.
- Гарантия: поле пустое и хоста нет → прежние значения и пустая строка (замок — снапшот HTML).

## 4. Кабинет

Вкладка «Seitenaufbau» в форме товара и на странице услуги: «Standard / Zeigen / Ausblenden»
на секцию, плашка «N Abweichungen», шаблон страницы, форма карточки, сводка своих блоков и
кнопка «Blöcke bearbeiten» → существующий экран `site-schema?seite=product@product:<hex>`
(ветка в `site_schema.host_for` по образцу категории; объект обязан существовать),
«Zurück zum Standard».

## 5. Срезы и замки (до кода)

- **S1 ядро.** Миграции `catalog` 0045 (`page_override`), `booking` 0045 (`page_override`,
  `card_style`); `object_structure.py`; витрины. Замки: объект без правок рендерится как
  прежде; `shown` перекрывает общее скрытие, `hidden` — общий показ; мусор отбрасывается.
- **S2 вкладка.** Форма и POST с сентинелом `page_override_present` (W0: сохранение из
  другого места не трогает поле); сброс; права (`view_perms`).
- **S3 свои блоки.** `_OBJECT_HOST_RE`, потолок, `host_for`, тег, уборка при удалении и
  копировании. Замки: несуществующий pk → нет хоста; блок виден только на своей странице;
  удаление убирает хост с переводами; расширить
  `test_every_declared_block_host_is_actually_rendered`.
- **S4 шлифовка.** Стенд Playwright 1440/390, de/ru, без скриптов.

## 6. Миграции

Обе добавляют поля с `default`, без бэкфилла — быстрое изменение метаданных на каждой схеме.
Дописать в список миграций к деплою (§3 `CLAUDE.md`).

## 7. Риски и вопросы

- Слаг категории и pk объекта — разные пространства хостов при одном писателе.
- Потолок 60 объектов со своими блоками (рост `site_config`); при нехватке — пересмотр.
- Свои блоки стоят под общими блоками страницы (выбор «над/под» — позже).
- `?seite=` объекта не показывает настройки типа страницы.

## 8. ECC-прогоны

- До кода: `django-patterns`, `django-tdd`, `database-migrations` (S1), `django-security`
  (S2, S3), `accessibility` (S2), `e2e-testing` (S4).
- `django-reviewer` — каждый срез; `database-reviewer` — S1; `security-reviewer` — S2 (POST,
  права), S3 (хосты из ввода, доступ по pk); `silent-failure-hunter` — S3 (уборка);
  `a11y-architect` — S2; стенд Playwright — S4.
