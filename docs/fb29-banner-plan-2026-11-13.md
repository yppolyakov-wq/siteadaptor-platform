# FB-29.2 «Banner» — библиотека баннеров и выбор из неё

Дата: 2026-11-13. План составлен агентом `planner`. Решения владельца (2026-11-13): баннеры —
отдельный подпункт меню «Website»; в блоке баннеры выбираются так же, как категория — один
или несколько; несколько — слайдер со своими настройками.

## 1. Что есть в коде

- Слайды — `site_config["heroes"]` (`siteconfig.py` `normalize_heroes`, `_MAX_HEROES=6`):
  image (строка URL), title, text, button_label/url, `link` «тип:цель» (`MENU_NODE_TYPES`),
  `align/overlay/tone`, `starts/ends`, `click_all`. Фото без `path` — медиатека считает его
  свободным (можно удалить из-под баннера).
- Блок «banner» хранит свой единственный слайд в `data` (тот же нормализатор).
- Пишут `heroes`: Студия (`views.py` `_save/_delete/_move_hero_slide`), демо-киты
  (`demo_kits.py`), город (`demo_city/builder.py`), импорт CS-Cart (`imports/cscart.py`).
- Читают: `_hero.html` + `siteui.hero_slides` (фильтр дат, `menu._node_url`), `banner_slide`;
  первое фото как запасное — `page_settings.py`, `listing_composition.py`,
  `promotions/public_views.py`; сводка строки — `site_schema.py`.
- Переводы — позиционный оверлей `i18n[loc]["heroes"][i]` (`TRANSLATABLE_KEYS`).
- Настроек слайдера нет: интервал 6 с, точки, без стрелок зашиты в `_hero.html`.
- Готовый механизм выбора: `_PICK_OPS`, `clean_pick`, `list_blocks.live_queryset/is_live/
  pick_entries`, `_schema_pick.html` (ручной состав блока «Liste»).
- Меню Website: 8 пунктов, замок разрешает 9 (`SUBMENU_DEBT["site-home"]`).

## 2. Модель и перенос

`apps/core/models.py` → `Banner(I18nMixin, TimestampedModel)` (TENANT, UUID): `title`, `text`,
`button_label` (+ `*_i18n`), `image` (JSON: url, path, alt), `link`, `button_url`, `align`,
`overlay`, `tone`, `click_all`, `starts`, `ends`, `is_active`, `sort_order`, `legacy_key`
(уникален, когда не пуст: `heroes:<i>` / `block:<id>`). Очистка — одна функция
`banners.clean_fields()` (та же санитизация, что `normalize_heroes`).

Ссылки: главная — `site_config["hero_banners"] = {pick: [uuid…], auto, interval, arrows}`;
блок «banner» — `data.pick` + те же ключи слайдера.

Миграции: `core/0020_banner` (схема) и `core/0021_banner_import` (данные; логика —
`banners.import_legacy(tenant)`, повторяемая командой `import_banners`): слайд/блок →
`Banner` через `update_or_create(legacy_key=…)`, переводы → `*_i18n`, фото с `MEDIA_URL` →
`path`; в конфиг дописывается `pick`. Старые `heroes`/`data` НЕ удаляются (откат на релиз).
⚠ Миграция данных пишет public-строку `Tenant` из схемы бизнеса — проверить на копии;
запасной путь — только команда после деплоя.

## 3. Читатели

Одна функция `banners.resolve(tenant, pick=None, legacy=None)`: по `pick` — активные сегодня
записи в порядке выбора, с переводом и `href`; иначе прежний путь. `hero_slides` и
`banner_slide` — обёртки; запасное фото — `banners.first_image(tenant)`.

## 4. Экраны

- «Banner»: `dashboard/site/banner/` (`site-banners`), `…/neu/`, `…/<uuid>/`,
  `…/<uuid>/loeschen/`; пункт меню после «Seiten»; права `_r(W, WE)`; список плитками (фото,
  заголовок, срок, «показывается на …»), поиск; форма с выбором цели из целей меню;
  удаление выбранного где-то баннера — с подтверждением.
- «Seitenaufbau»: источник `banners` в механизме выбора; операции выбора — для строки
  «Banner» главной и блока «banner»; настройки слайдера (auto, interval, arrows).
- Витрина: общий `_banner_slider.html`; стрелки — кнопки; без скриптов виден первый слайд.
- Студия: менеджер слайдов заменяется ссылкой «Banner verwalten».

## 5. Срезы

- **S1** — модель, 0020, `banners.py` (clean, resolve), медиатека видит фото баннеров.
  Витрина не меняется.
- **S2** — экран «Banner» (вьюхи, шаблоны, меню, права, переводы).
- **S3** — перенос (0021 / команда), переключение читателей.
- **S4** — выбор и настройки слайдера в «Seitenaufbau», общий слайдер, правка Студии.
- **S5** — писатели (киты, город, импорт) пишут в `Banner`; чистка `heroes` — отдельным
  релизом после сверки на сервере.

## 6. Замки (до кода)

После переноса главная и блок дают тот же HTML и порядок; повторный перенос без дублей;
обратный ход возвращает конфиг; баннер вне дат не выдаётся; `pick` с удалённым UUID не роняет
главную; удаление выбранного баннера требует подтверждения; `javascript:` в ссылке → пусто;
сотрудник без права сайта — 403; путь фото баннера входит в `used_paths`; нетронутая панель
ничего не меняет (W0); `interval` вне 4..12 сбрасывается.

Осознанно переписать: `test_sidebar_st4b` (+ `site-banners`), `test_ka_w2_nav_locks`,
`test_hero_slider`, `test_fb22_hero_slides`, `test_home_builder`, `test_i18n_localize`
(heroes); на S5 — `test_cscart`, `test_demo_kits`.

## 7. Вопросы владельцу (идём по рекомендации)

1. Оформление (вуаль, тон, положение текста) — у баннера; высота — у места показа.
2. Ни один выбранный баннер не активен — показывается одиночный заголовок, как сейчас.
3. Потолок слайдов в одном слайдере — 10.
4. Слайдер по умолчанию: автопрокрутка 6 с, без стрелок, на телефоне без автопрокрутки.
5. Привязка баннера к нескольким местам показа (FB-29.2c) — отдельным срезом после S4.

## 8. ECC-прогоны

- До кода: `django-patterns`, `django-tdd`, `database-migrations`, `django-security`,
  `accessibility`, `e2e-testing`.
- `django-reviewer` — каждый срез; `database-reviewer` — S1, S3; `silent-failure-hunter` — S3;
  `security-reviewer` — S2 (загрузка, ссылки), S4 (операции выбора); `a11y-architect` — S2, S4;
  стенд Playwright 1440/390, de/ru, без скриптов — S2, S4.

## 9. FB-29.2c — «Wo zeigen» у баннера (решение владельца 2026-11-14: «да, нужен»)

Один баннер показывается сразу на многих страницах без блока на каждой.

- **Хранение.** `Banner.show_on` — список строк «<вид>:<цель>» в том же пространстве значений,
  что цели ссылок меню (`menu.target_options`): `category:<slug>`, `product:<pk>`,
  `service:<pk>`, `promotion:<pk>`. Миграция `core/0021` (аддитивная, `db_default`).
  Потолок 50 мест у баннера.
- **Писатель.** `banners.set_show_on(banner, keep, add, allowed)` — из формы баннера по
  сентинелу `b_show_present`; новое место — только из списка целей, которые сайт сейчас
  открывает. Смена адреса категории переносит места (`banners.rename_place`).
- **Витрина.** Тег `place_banners kind obj` на странице категории (над списком), товара,
  услуги и акции: баннеры с этим местом, активные сегодня, по порядку библиотеки; несколько —
  тот же слайдер, что у блока «Banner» (общий `_block_banner.html`). Один запрос на страницу.
- **Кабинет.** В форме баннера — «Wo zeigen»: выбранные места флажками (снять = убрать) и
  выбор «Ort hinzufügen» из того же списка целей, что ссылка. Работает без скриптов.
- **Замки до кода:** место вне списка целей не сохраняется; форма без сентинела мест не
  трогает; баннер вне срока на месте не показывается; страница без баннеров — пусто и без
  ошибок при отсутствии таблицы; смена адреса категории сохраняет место.
- **ECC:** `django-reviewer`, `security-reviewer` (ввод мест), `database-reviewer` (0021),
  `a11y-architect` (форма); стенд — форма и страница товара.
