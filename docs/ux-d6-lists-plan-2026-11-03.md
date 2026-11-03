# UX-D · D6 — «Остальные списки»: строки без форм, «＋» шторкой, правка после создания (план, 2026-11-03)

Основание: `ux-declutter-analysis-2026-11-03.md` строка D6 (П1 список — обзор, П2 создание — «＋»,
П4 настройки — в Einstellungen). Механики D3/D4/D5: шторка `apps/core/drawer.py` (`drawer_aware`
внутренний, `fragment`, `open_after`), прецеденты `stays/unit_new_views.py`,
`booking/views_resources.py::resource_new`, `booking/booking_new_views.py`; вкладки `_i18n_switch`;
права `core/view_perms.py` + `EXPECTED_UNLISTED`; W0. План — агент ECC `planner`. **Миграций нет.**

**Решения (2026-11-03, по рекомендации; владелец может поменять):** порядок D6.0 → D6.1 Extras →
D6.2 Lager → D6.4 Gutscheine/Treue → D6.5 Finanzen → D6.3 Kollektionen → D6.6 Team/Kanäle → D6.7;
новый счёт — страницей (8 строк + поиск клиента); удаление допа/подборки — только со страницы
объекта (блок «Gefahr»); смена `stamps_required` действует только на новые штампы; «Trennen» канала
— отдельной кнопкой с подтверждением; настройки склада → Einstellungen › «Lager»; хотфикс D6.0 —
первым и отдельным мержем.

## Разведка (file:line, сверено planner'ом)
- **Zusatzleistungen** (`core/views.py:37-154`, `tenant/extras.html`): 4 формы в строке, создание
  (13 полей) раскрыто, **правки после создания нет**. **Деньги:** цена `float(…replace(",", "."))`
  → «1.234,50»/мусор молча = 0 €; `scope` без белого списка.
- **Kollektionen** (`collections/views.py`, `collections/list.html`): каждая подборка — раскрытая
  форма; **потеря данных:** показаны только активные позиции и ≤ 200 товаров, Save делает `.set()`
  из присланного → членство неактивных и 201-го+ товаров стирается; N+1 (3 запроса на подборку).
- **Склад** (`inventory/views.py:324-434`, `inventory/stock.html`): над таблицей настройки и три
  формы «Buchung erfassen» + Produktion/Zählliste/Standorte; `threshold`/`lots_toggle` пишут
  `site_config` целиком без блокировки (класс W6).
- **Gutscheine** (`promotions/views.py:1750-1792`): генерация раскрыта, суммы в центах, **отключить
  код нельзя** (`is_active` есть и проверяется, действия нет).
- **Treueprogramme**: создание раскрыто, **правки нет**.
- **Finanzen** (`finance/views.py`): формы журнала/расходов/счёта раскрыты; **деньги:**
  `Decimal(x.replace(",", "."))` — «1.234» = 1,234 €, `NaN`/`Infinity` → 500, мусорная дата → «сегодня»
  (GoBD); при ошибке теряется ввод. Правильный разбор — `core/money.parse_money`.
- **Team** (`core/team.py`, `tenant/team.html`): роль селектом с автосабмитом onchange (WCAG 3.2.2),
  полная форма прав в `<details>`, приглашение раскрыто.
- **Kanäle** (`publishing/views.py:29-90`): пустое поле не затирает сохранённое — отключить канал,
  удалив ключ, нельзя.

## Инкременты
- **D6.0 — хотфиксы денег и данных (до вёрстки):** цены/суммы → `parse_money` + ≤ 2 знаков +
  конечное; мусорная дата → ошибка; `scope` по белому списку; подборки: состав = (отмеченные ∩
  показанные) ∪ (текущие − показанные); склад — запись под блокировкой; ваучер — «Deaktivieren/
  Aktivieren».
- **D6.1 Zusatzleistungen:** строки, «＋ Zusatzleistung» шторкой, НОВАЯ страница допа (правка всех
  полей, фото, переводы, «Gefahr»).
- **D6.2 Lager:** таблица — рабочая поверхность, действия кнопками в шторку `stock-book?art=`,
  настройки → `stock-settings`.
- **D6.3 Kollektionen:** строки с количествами (annotate), «＋» шторкой, страница с вкладками
  Grundlagen · Inhalt · Fotos.
- **D6.4 Gutscheine & Treue:** генерация шторкой, суммы в €, страница программы лояльности.
- **D6.5 Finanzen:** «＋ Buchung»/«＋ Ausgabe» шторками, «＋ Neue Rechnung» страницей.
- **D6.6 Team & Kanäle:** страница участника (роль кнопкой, права формой E6.7d), «＋ Person einladen»
  шторкой; каналы — статус + «Einrichten» + «Trennen».
- **D6.7 стенд, i18n, доки.**

## Замки — до кода
D6.0: «1.234,50» → 1234,50 €; «abc»/«1,234» → ошибка без записи; `NaN`/`inf` → ошибка, не 500;
мусорная дата → ошибка; подборка с неактивным и 201-м товаром переживает Save; порог склада не
затирает чужой ключ `site_config`; отключённый ваучер не гасится ни у прилавка, ни на чекауте.
D6.1–D6.6: в строке нет полей; round-trip; чужой uuid → 404; фрагменты без `<script>`; без JS → 302;
реестры `view_perms`/X7.

**Переписать осознанно:** `core/tests/test_extras_image.py`, `stays/tests/test_d4_room_page.py:465`,
`collections/tests/test_collections.py:157-209`, `test_lookbook.py:114-147`,
`catalog/tests/test_wr3_form_noise.py:30-31`, `core/tests/test_design_guard.py:80`, team-тесты
(адрес рендера), `publishing/tests/test_merchant_feed_screen.py:259`.

## ECC-прогоны
| Когда | Что |
|---|---|
| до кода | скиллы `django-patterns`, `django-tdd`, `django-security`, `accessibility`, `e2e-testing`, `error-handling`; `docs/pitfalls.md` §1, §3, §5 |
| D6.0 | `django-reviewer`, `silent-failure-hunter`, `security-reviewer` (ваучер), `database-reviewer` (блокировка тенанта) |
| D6.1 | `django-reviewer`, `security-reviewer`, `silent-failure-hunter`, `a11y-architect` |
| D6.2 | `django-reviewer`, `silent-failure-hunter`, `a11y-architect` |
| D6.3 | `django-reviewer`, `database-reviewer`, `a11y-architect` |
| D6.4 / D6.5 | `django-reviewer`, `security-reviewer`, `silent-failure-hunter` |
| D6.6 | `django-reviewer`, `security-reviewer`, `a11y-architect` |
| D6.7 | `e2e-runner`: shop/clothing, friseur/hotel, cafe, finance-кит × 1600/390, без JS |

## Риски
Числа — только `parse_money`; плитка фото со скриптом — не в шторке; multipart в шторке проверить
по контракту; старые POST принимаются до конца волны; `Tenant.select_for_update().save()` пытается
создать схему (pitfalls §6) — писать через `update()`/`update_fields`; «Kontaktdaten sehen» (E6.7g)
маскирует e-mail и на странице участника.
