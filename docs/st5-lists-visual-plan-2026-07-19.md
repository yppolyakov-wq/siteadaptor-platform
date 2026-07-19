# ST-5 «Списки → визуал» — план (2026-07-19)

ТЗ (`next-gen-master-tz-2026-07-19.md` §3 D1): (a) экран Angebote — грид
КАРТОЧКАМИ с фото; (b) заказы — переключатель Канбан ⇄ Календарь ⇄ Лента с
дефолтом по архетипу (календарь — услуги, лента — магазин); (c) CRM-карточки.
Без миграций. Разведка (2026-07-19, Explore) — факты ниже проверены по коду.

## §1 Факты разведки

- Фото sellable уже унифицировано: `sellable.display_fields` → `image_url`
  (+`gallery`); `ManagedSellable.image_url` уже в контексте
  `sellable_manage.html`; combo без фото (нужен плейсхолдер 🏷️). Фото — инлайн
  JSONField, N+1 нет. Замки sellable_manage к разметке НЕ привязаны.
- Доска: `_board_body.html` с JS-табами KIND'ов (`data-board-tab`) — готовый
  паттерн переключения без перезагрузки; HUB_TABS["board"] уже связывает
  Board/Bestellungen/Termine(booking:calendar)/Übernachtungen(stays:calendar)/
  Tickets/Aufträge как СТРАНИЦЫ хаба «Verkäufe».
- Календари booking/stays — полноэкранные per-domain вьюхи (day-view /
  occupancy_grid) — переиспользуем НАВИГАЦИЕЙ, не встраиванием.
- Персональные UI-ключи: паттерн `set_presence_view` (targeted-write,
  presence-minimal) + `primary_module`/`_PRIORITY` для архетип-дефолта.
- classic_ui: контекст-процессор + вьюха-гейт (эталон ST-4a); замок
  `test_classic_ui` — под classic на главной НЕТ слова «kanban».
- Замки: order_list — reference_code, `qty× title`, `<select name="status">`,
  кастом-лейблы; CRM — имена/теги + `?q`; st4_home — маркеры ic-orders и др.

## §2 ST-5a — Angebote карточками (наименьший риск)

- НОВЫЙ партиал `tenant/_sellable_manage_card.html`: фото 16:10 (image_url,
  фолбэк — крупный эмодзи-плейсхолдер на градиенте), имя, цена, статус/тумблер
  видимости (POST как в строке; event — status-бейдж), «Bearbeiten».
- `sellable_manage.html`: грид `grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4`
  под гейтом `{% if classic_ui %}` — старый divide-y список (партиал строки НЕ
  удаляется).
- Данные не меняются (image_url уже есть). Редирект тумблера сохранён.

## §3 ST-5b — представления заказов: Канбан ⇄ Календарь ⇄ Лента

Решение (v1 — навигационный переключатель, БЕЗ встраивания трёх движков в одну
страницу): сегмент-контрол «🧮 Kanban · 📅 Kalender · 📃 Liste» на трёх
поверхностях хаба «Verkäufe» — board / календарь (booking или stays) /
orders:order-list. Клик = переход на страницу представления + persist выбора.

- Ключ `site_config["orders_view"]` ∈ {"", "kanban", "calendar", "feed"} —
  presence-minimal ("" = ключа нет = архетип-дефолт), в `normalize` рядом с
  `ui_mode` (замок «normalize сохраняет»; урок W0/S5).
- Дефолт по `primary_module`: booking|stays → calendar; catalog → feed;
  иначе (events/jobs/промо-микс) → kanban. Резолвер
  `apps/core/orders_view.py::resolve_view(tenant)` + `calendar_url(tenant)`
  (booking:calendar при активном booking, иначе stays:calendar; нет обоих —
  календарь в контроле скрыт).
- Сеттер `set_orders_view` (паттерн set_presence_view, targeted-write) —
  сегмент-контрол шлёт POST и редиректит на выбранную поверхность.
- Точки входа уважают выбор: хаб-плитка «Bestellungen» (ST-4a hub_tiles) и
  вкладка хаба ведут на предпочтённое представление (`orders_entry_url`).
  Встроенный канбан главной НЕ трогаем (замки st4_home/classic).
- Партиал `core/_orders_view_switch.html` включается на board.html,
  booking/calendar.html, stays/calendar.html, orders/order_list.html (после
  hub_tabs). classic_ui → партиал не рендерится (легаси-вид цел).

## §4 ST-5c — CRM-карточки контактов

- `customer_list.html`: под гейтом classic_ui — card-грид (sm:2/lg:3): аватар-
  инициал на акцентном фоне, имя, email/phone, теги-пилюли; клик → карточка 360°.
  Поиск `?q`, пагинация «Show more» и кнопки (Neu/Export) — как были.
- LTV на карточке — БАТЧЕМ: один `RevenueEntry.objects.filter(customer__in=page)
  .values("customer").annotate(Sum)` на страницу (25 шт.), «\d+ € · N Käufe»
  только при наличии записей; per-row агрегации НЕТ.
- Замок test_list_and_search (имена/теги/`?q`) сохраняется.

## §5 Риски / инварианты

- classic_ui гейтит ВСЕ три инкремента; легаси-разметка не удаляется (Р7).
- Слово «kanban» не появляется в classic-рендере главной (замок).
- `orders_view` — только через normalize (иначе Save билдера сотрёт) +
  presence-minimal (golden целы, ключ пишется только при явном выборе).
- Замки order_list/CRM: фильтр-select, reference_code, `qty× title`, имена,
  теги, `?q` — сохранить в новых разметках.
- i18n: новые строки — по конвенции файла (кабинет-шаблоны: msgid как соседние)
  + переводы en/tr/ru/uk.

## §6 Инкременты (батч-конвенция)

1. **ST-5a** карточки Angebote + classic-гейт + тест (карточка с фото/фолбэк,
   тумблер жив, classic = старый список).
2. **ST-5b** резолвер+ключ+сеттер+сегмент-контрол на 4 поверхностях + entry-url
   хаба + замки (normalize сохраняет ключ; дефолты по архетипу; classic чист).
3. **ST-5c** CRM-карточки + батч-LTV + тесты; докблок (build-log, CLAUDE.md,
   task-catalog, ✅-маркер D1) + i18n.
