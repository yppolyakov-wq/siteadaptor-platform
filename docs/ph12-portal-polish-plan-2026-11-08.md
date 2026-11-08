# PH-12 — доводка городского портала после редизайна PH-11 (план, 2026-11-08)

План составлен агентом `planner` по итогам PH-11a…e (`docs/ph11-portal-redesign-plan-2026-11-08.md`,
build-log от 2026-11-08), сверен ведущей сессией по коду (CI гоняет `pytest -n auto` —
`ci.yml:138`; кэш тестов — одна база Redis `/1` — `config/settings/base.py:140`; `new_businesses`
не смотрит ни фото, ни наличие предложений). Учтены открытые пункты списка ошибок прода
(`docs/portal-home-variants-analysis-2026-11-07.md` §1) и известные долги после PH-11.

## 0. Рамки

- **Без миграций.** Ни один пункт не требует новой схемы.
- **Правила PH-11 действуют:** кэшируемый HTML без персональных данных (P0-1, у анонима нет
  csrf); платное — только в полосе «★ Anzeige» (UWG § 5a); всё работает без JS; новые строки —
  `gettext` во всех пяти `.po`.
- **Локальный гейт** (CLAUDE.md §5): `uvx ruff@<версия из uv.lock> check/format --check .`
  целиком · pytest затронутых модулей · `test_template_comments` · `scripts/i18n_quickcheck.py` ·
  `npm run build:css` при новых классах.
- **Рабочий цикл:** батч → один прогон CI → FF в `main`.

## 1. Сверка §1 анализа с кодом после PH-11

| № | Ошибка на проде | Статус | Где видно |
|---|---|---|---|
| 1 | Тестовые бизнесы («Про», «Test aktion», «123», пустая «Buchhandlung») в «Neu in Solingen» | **открыт** | `new_businesses` (`portal_home_blocks.py`) берёт любой `KIND_BUSINESS` за 30 дней — не проверяет ни фото, ни наличие предложений |
| 2 | Подпись заглушки «Sg-biergarten» | **открыт** | `svg_for` (`apps/tenants/demo_images.py`) без `cap` берёт подпись из ключа |
| 3 | «200 Angebote» vs «571 neu» | закрыт | цифры первого экрана сняты (PH-11d2) |
| 4 | «Endet heute/bald» — акции закрытых бизнесов | **открыт** | quad «endet» фильтрует только по `ends_at`, часы работы не смотрит |
| 5 | Портретное фото ломает ряд | закрыт в `_cards.html` (`aspect-[4/3]` + `object-cover`) | проверить стендом «Das Beste», «Top-Aktionen», «Geschäfte» |
| 6 | «EUR» вместо «€» | закрыт | фильтр `currency_sign` (PH-11e) |
| 7 | Время события «08:52» = время засева | **открыт** | кортеж `events` кита (`demo_kits.py`); сидер переносит время запуска |
| 8 | «⚑ Melden» под каждой карточкой | **открыт** | `_cards.html`; на странице предложения ссылка тоже есть (`offer.html`) |
| 9 | Первая карточка на телефоне — ~3-й экран | вероятно закрыт (быстрые фильтры и плитки сняты) | замерить стендом 390 px |
| 10 | Категории повторяются 4 раза | закрыт | остались мега-меню и «Das Beste» |
| 11 | Ссылка «Angebote München» | закрыт | ссылки на чужие порталы с главной сняты (PH-11e) |

## 2. Инкременты

### PH-12a — флаки параллельного прогона на общем Redis

**Цель.** Убрать флаки `test_portal_menu::test_feed_menu_is_cached`,
`test_portal_accounts::test_verify_logs_in_and_creates_user`,
`test_konto_reservations::test_result_is_cached`, `test_mcp_tools::test_list_categories_is_cached`.

**Причина.** Все воркеры xdist пишут в одну базу Redis; `cache.clear()` у django-redis — это
`FLUSHDB`, и чужой воркер стирает magic-link токен или прогретый кэш соседа. `isolated_ratelimit`
спасает только счётчики ratelimit, а не `django.core.cache.cache`.

**Подход.** В `config/settings/test.py` — своя база Redis на воркер по `PYTEST_XDIST_WORKER`
(`gw0` → db 3, `gw1` → db 4, …; 0/1/2 заняты брокером/кэшем/result). Воркеров больше, чем
свободных баз, — второй круг отделяется `KEY_PREFIX` по воркеру. Чинится класс, а не точечные
фикстуры; тесты не трогаем; локальный прогон без xdist не меняется. При реализации подтвердить,
что тестам ничего не нужно от общего кэша (`scan_iter('*rl:*')` останется в своей базе).

**Замки до кода** (`apps/core/tests/test_test_cache_isolation.py`): при `PYTEST_XDIST_WORKER=gw1`
`LOCATION` кэша оканчивается на `/4`; без переменной — прежний.

**Приёмка.** Три прогона CI подряд без этих падений (опц. локально `pytest -n 4 apps/aggregator` ×3).

### PH-12b — читаемые чернила на `--portal-color`

**Цель.** Белый текст на кнопках/пилюлях/чипах портала — контраст ≥ 4,5:1 при любом
`AggregatorPortal.primary_color`; ссылки цветом портала на белом — тоже ≥ 4,5:1. Бренд `#C2410C`
проходит (5,2:1); риск — цвета, которые оператор задаёт в админке.

**Где белый на `var(--portal-color)` (~15 мест):** `portal_base.html`, `_portal_tabs.html`,
`_portal_kind_chips.html`, `_portal_filter_bar.html`, `_portal_filter_drawer.html`,
`_portal_header_search.html`, `_portal_slider.html`, `_home_top_actions.html`, `_portal_menu.html`,
`portal_login.html`, `portal_link_invalid.html`, `for_business.html`, `follow*.html`.

**Подход.**
1. Вынести `_rel_luminance`/`_accent_ink` из `apps/core/context.py` в `apps/core/colors.py`
   (в `context.py` — реэкспорт, витрина не меняется).
2. `readable_on_white(hex)`: затемнять (смешением с `#111827` шагами 10 %) до контраста ≥ 4,5 —
   только для цвета ссылок.
3. В `portal_base.html` три переменные: `--portal-color`, `--portal-ink` (= `ink_on(primary)`),
   `--portal-link`; значения — тег в `templatetags/portal_brand.py`.
4. Глобальное правило по прецеденту витрины (`storefront/_base.html`):
   `[style*="background: var(--portal-color)"]{color:var(--portal-ink)!important}` — без
   переписывания `text-white` в 15 шаблонах.
5. Ссылки `style="color: var(--portal-color)"` → `--portal-link`.
6. Битый `primary_color` (не `#rrggbb`) → фолбэк `#111827`; проверка в admin-форме.

**Замки до кода:** `ink_on` для `#C2410C`/`#111827`/`#FDE047`/`#22C55E`/мусора → белый/белый/
тёмный/тёмный/белый; `readable_on_white` для 5 цветов даёт ≥ 4,5; HTML портала с `#FDE047`
содержит `--portal-ink:#111827`; скан шаблонов `templates/aggregator/` — нет `text-white` рядом
с `var(--portal-color)` без правила п. 4 (замок класса).

**Приёмка.** Стенд: жёлтый и бирюзовый тестовые порталы, axe-контраст на главной, выдаче и в
шторке — 0 нарушений.

### PH-12c — порядок заголовков главной

**Цель.** H1 «Was gibt's heute in …» (`_portal_hero.html`) — первый заголовок страницы; сейчас
перед ним в DOM 4–5 `<h2>` слайдера (`_portal_slider.html`).

**Подход.** Заголовки слайдов → `<p>` с теми же классами (вид и макет K1 целы); слайд остаётся
`role="group"` + `aria-roledescription="Folie"` + `aria-label` = заголовок; у ленты —
`aria-label` «Highlights in <город>» (есть). `id="slide-deal-h"` сохранить на `<p>`
(`aria-labelledby` ссылки Deal — проверить grep).

**Замки до кода** (дополнить `test_portal_slider_ph11d.py`): в теле главной первый `<h1` раньше
первого `<h2`; внутри `data-portal-slider` нет `<h2`.

**Приёмка.** Ревью `a11y-architect`; дерево заголовков в Playwright: h1 → h2 секций.

### PH-12d — честность первого экрана (§1 п. 1, 2, 4, 8)

- **d1. «Neu in <город>».** `new_businesses` берёт только бизнесы, у которых в пуле есть фото
  (`.exclude(image={})`) и хотя бы одно предложение (`Exists` листинга того же `tenant_schema`
  не вида `KIND_BUSINESS`).
- **d2. «Endet heute» (quad).** Акция остаётся, только если бизнес открыт сейчас или откроется
  раньше конца акции — по уже переданному снимку часов (0 запросов). Подмножество — инвариант
  «карточка ⊆ ленты» цел. Ленту `sort=endet` в v1 не трогаем (заметка в roadmap). Нет снимка /
  часов — fail-closed (не утверждать «закрыто» для бизнеса без часов: без часов — показываем).
- **d3. «⚑ Melden».** Убрать из `_cards.html`; остаётся на странице предложения и (Р-2) компании.
  Замок `test_catalog_hygiene.py` переписать осознанно.
- **d4. Подпись заглушки.** Пустой `cap` и технический ключ (`^[a-z]{1,3}-`) → без подписи,
  только эмодзи (сверить `apps/tenants/tests/test_demo_images.py`). Ops: реальные тестовые
  тенанты прода пометить `is_internal` в админке (`tenants/0037`).

**Замки до кода:** бизнес без фото/без предложений не в «Neu»; акция бизнеса, закрытого до
завтра и кончающаяся сегодня, не в «Endet heute»; открытый или открывающийся до конца акции —
в карточке; в выдаче нет `data-report-link`; `svg_for("sg-biergarten")` без `cap` не содержит
«Sg-biergarten».

### PH-12e — «Das Beste» без параметра на каждый открытый бизнес

**Цель.** `When(tenant_schema__in=sorted(open_set))` в `best_by_section` и `open_block` передают
по параметру на каждый открытый бизнес: на крупном пуле — сотни параметров и новый текст запроса
при каждом размере `open_set`.

**Подход.** Один массив-параметр (`= ANY(%s)` через `Func`/`RawSQL` с именем таблицы из
`_meta.db_table`) как условие `When(...)` и `.filter(...)`. **Сначала** `database-reviewer` —
EXPLAIN на синтетике из 500 схем; нет выигрыша — оставляем, фиксируем в плане.

**Замки до кода:** SQL «Das Beste» при `open_set` из 50 значений содержит 1 параметр для схем;
порядок строк не меняется (эталон). Кап запросов главной (22) цел.

### PH-12f — время событий демо + сводный стенд

- **f1.** Сидер событий (`DemoKit.events` / `apps/tenants/demo_city/builder.py`; обработчик
  найти grep'ом) ставит начало из спеки (`"8"` → 08:00, иначе 10:00), а не `now`; поднять
  `SEEDER_VERSION`. Замок: засеянное событие кита начинается в `HH:00`.
- **f2. Стенд** (Python/Node-Playwright, Chromium из `/opt/pw-browsers`): портал Solingen,
  1440/390, de/ru — первая карточка предложения на 390 px не ниже 2-го экрана (п. 9), нет рваных
  рядов в «Das Beste»/«Top»/«Geschäfte» (п. 5), axe-контраст, дерево заголовков.
- **ops после деплоя:** `seed_demo_tenants --group solingen-dcc --changed`.

## 3. Порядок

12a (снимает флаки) → 12b → 12c → 12d → 12e → 12f. Батчи CI: **A** = a · **B** = b + c (главная и
a11y) · **C** = d · **D** = e + f.

## 4. Риски

| Риск | Мера |
|---|---|
| База Redis на воркер упрётся в 16 баз | второй круг — `KEY_PREFIX` по воркеру; замок на маппинг |
| `!important`-чернила перебьют намеренно белый текст на тёмном фото слайда | правило только на `style*="background: var(--portal-color)"`; стенд слайдов |
| Фильтр «Endet heute» опустошит карточку | пустая карточка не рендерится (уже в коде) — замок |
| `ANY`-условие привязано к имени таблицы | имя из `_meta.db_table`; замок на SQL |
| Многострочный `{# #}`, новые классы Tailwind | `test_template_comments`, `npm run build:css` в том же коммите |
| `<p>` вместо `<h2>` у слайдов ломает `aria-labelledby` | grep `slide-deal-h` до правки |

## 5. Решения владельца

| Вопрос | Рекомендация |
|---|---|
| **Р-1** Заголовки слайдов | `<p>` вместо `<h2>`; макет K1 не трогаем |
| **Р-2** «Melden» | только на странице предложения и компании |
| **Р-3** Критерий «Neu» | фото + ≥ 1 предложение, без требования часов |
| **ops** Тестовые тенанты прода | пометить `is_internal` в админке до деплоя PH-12d |

Если владелец молчит — исполняются рекомендации.

## 6. ECC-прогоны

**Скиллы до кода:**

| Инкремент | Скиллы |
|---|---|
| 12a | `python-testing`, `redis-patterns`, `django-tdd` |
| 12b | `accessibility`, `django-patterns`, `django-tdd` |
| 12c | `accessibility`, `seo` (дерево заголовков) |
| 12d | `django-patterns`, `django-tdd`, `postgres-patterns` (`Exists`) |
| 12e | `postgres-patterns` (EXPLAIN; миграций нет) |
| 12f | `e2e-testing` (Python/Node-Playwright стендом, без `playwright install`) |

**Агенты:**

| Агент | Когда |
|---|---|
| `django-reviewer` | после каждого батча, до пуша |
| `a11y-architect` | 12b (контраст/чернила), 12c (заголовки, карусель) |
| `database-reviewer` | 12e — до кода (EXPLAIN-решение) и после; 12d — запрос с `Exists` |
| `silent-failure-hunter` | 12b (фолбэк битого цвета), 12d2 (нет снимка часов — правило явное, без молчаливой лжи) |
| `security-reviewer` | 12b — только если трогаем admin-форму `primary_color` (ввод оператора) |
| стенд Playwright (`e2e-runner`) | 12b, 12c, 12f (1440/390, de/ru, axe) |
| `doc-updater` | после 12f: build-log, task-catalog (семейство PH), §3 `CLAUDE.md` |

**Грабли из `docs/pitfalls.md`:** переменная контекст-процессора в аргументе фильтра;
`cache.clear()` под xdist; свежесть `app.css`; `i18n_gap` строже quickcheck; локальный ruff ≠
uv.lock; `sr-only` в горизонтальной ленте растягивает страницу.
