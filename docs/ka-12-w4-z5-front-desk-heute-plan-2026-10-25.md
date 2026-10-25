# KA-12 · Zimmer Z-5: стойка и «Heute» (§3.1/§3.3), DF-Z3/DF-Z4, check-in/out, `checkout_hour`. План от 2026-10-25

План составил агент `planner` по `main`. Родительский план: `docs/ka-12-w4-zimmer-plan-2026-10-25.md` (§0 строки 13/15/16, §1 строки 30–33, §2 DF-Z3/DF-Z4, §3 `0044`, §4 пп. 4–5, §5 строки 80–81, §8 О-2/О-6/О-7/О-8).

**Миграция.** Последняя миграция — `stays/0043_rateplan_units` (Z-4). Z-5 получает **одну аддитивную `stays/0044`**. Kurtaxe-поля родителя (`kurtaxe_child_cents`, `kurtaxe_exempt_note`) уходят в Z-6 отдельной `0045`: в `0044` их не кладём, иначе Z-5 сделает поля без UI и без тестов.

## 0. Что уже есть в коде (объём сокращён до недостающего)

| Пункт родителя | Состояние | Где |
|---|---|---|
| Тариф на стойке явным выбором | ✅ Z-4 | `apps/stays/views.py:677–688` (`resolve_choice(empty="none")`), `templates/stays/_walkin_form.html:36–67` |
| «Automatische Rabatte anwenden» | ❌ | `book_stay` всегда применяет `pricing.auto_discount` (G4, Lücken-Deal, акция на номер с `claim_units`): `services.py:407–419` |
| Комната на стойке | ❌ | `book_stay` комнату не принимает. `services.assign_room` (152–178) есть: лок, `free_rooms_for`, `RoomConflict` |
| Способ оплаты на стойке | ❌ | `book_stay(payment_method=…)` есть (329/459), стойка его не передаёт. Реестр — `apps/core/payment_methods.py` |
| Блок через сервис | ❌ | `stay_create` mode=block (`views.py:659–670`) делает `UnitBlock.objects.create` в обход сервиса. `services.create_block` (243–281) проверяет ёмкость только у блока комнаты; у блока категории (`room=None`) проверки нет. Тот же пробел в `units()` action `block` (1030–1071), он уже зовёт сервис |
| Предупреждение G12 на стойке (О-2) | ❌ | `restrictions.violation` зовут только витрина, `availability:328` и `book_stay(enforce_restrictions)` |
| DF-Z3 quantity ниже проданного | ❌ | `unit_settings` (`views.py:951–955`) пишет `quantity` без проверки. `room_delete` (1081–1088) удаляет комнату вместе с назначенными бронями (FK уходит молча) и уменьшает ёмкость через `sync_room_quantity` (284–294) |
| DF-Z4 «Heute» | ❌ | `apps/core/sales_page.py:159–301` `heute_columns`. «Anreisen» читает реестр, а «Abreisen» (213) и «Im Haus» (231) — литерал `STATUS_CONFIRMED`. `_safe` (170–174) глотает исключение без лога, и пустая колонка выглядит как «Nichts für heute.». Карточка = title/subtitle/url: без комнаты, оплаты, Meldeschein, кнопок. Шаблон `templates/core/_sales_heute.html` — элемент целиком `<a>`, кнопку внутрь не положить |
| Виджет главной | ❌ тот же литерал | `apps/core/dashboard.py:150–166`: `departures` по `STATUS_CONFIRMED` |
| Check-in/out | ❌ | Полей нет. «Abgereist» = FSM `fulfilled` через `stay_action` → `core_transactions.apply_action` (`views.py:607–634`). Хук выезда в `state_machine.py:58–80`: комната → dirty, `settle_on_delivery`, выручка |
| `checkout_hour` | ❌ | `tasks.py:57` `AUTO_CHECKOUT_HOUR = 14`, используется в строке 72. Тест `test_belegungsplan.py:672` ссылается на константу |
| `next=` | ⚠️ слабо | `stay_action` (349–351) и `stay_create` (651–652) проверяют только `startswith("/") and not "//"`. `/\evil.com` проходит (pitfalls §3) |

## 1. Требования
1. **Стойка (§3.1):**
   - тумблер «Automatische Rabatte anwenden» (по умолчанию вкл. — паритет);
   - селект физической комнаты;
   - способ оплаты (на месте / Vorkasse);
   - блок дат — только через `services.create_block`, включая блок комнаты;
   - после создания брони — предупреждение о нарушенных правилах G12/NightRate (О-2: не запрет).
2. **DF-Z3 (О-8 — запрет).** Нельзя уменьшить `quantity` или удалить комнату ниже проданного на любую ночь от сегодня. Нельзя удалить комнату, назначенную будущей или текущей активной брони. Проверки — под локом категории (тот же лок, что `book_stay`).
3. **DF-Z4.** «Heute» и виджет главной считают статусы через реестр (кастом-статусы видны). Ошибка колонки логируется и показывается как «konnte nicht geladen werden», а не как пустой день.
4. **Heute (§3.3):** в карточке комната(ы), оплата (состояние + способ), Meldeschein ✓/—, отметка «eingecheckt HH:MM», POST-кнопки Check-in / Check-out.
5. **Check-in/out (О-7):** `checked_in_at` / `checked_out_at` — отметки времени, не статус FSM. Check-out = отметка + штатный переход `fulfilled` (одна точка денег).
6. **`checkout_hour`** — настройка `StaySettings` (по умолчанию 14 — байт-в-байт с константой) для авто-выезда. `checkin_hour` (15) — только подсказка в Heute.

## 2. Решения по развилкам

**Р-1. Тумблер авто-скидок.**
- Новый параметр `book_stay(..., apply_auto_discount=True)`. При `False` — `auto_discount_cents=0`, label `""`, `promo_hit` не считается, `claim_units` не зовётся (лимит акции не списывается).
- `night_prices` не меняется (снимок до авто-скидки, Z-1).
- В форме: чекбокс `auto_rabatt` (checked) + hidden `auto_rabatt_present=1` (W0). Без сентинела (легаси-формы, тесты) → `True`; с сентинелом и без чекбокса → `False`.
- Ваучер (`voucher_code`) тумблер НЕ трогает: это явный ввод сотрудника.

**Р-2. Комната на стойке.**
- Селект `room` в walk-in: опции — активные комнаты всех категорий с `data-unit`. Первая опция «— Zimmer später zuweisen —».
- Делегированный JS на `document` (урок Ф1) прячет комнаты чужой категории; без JS решает сервер.
- Вьюха: если `room` непустой, разбирается строго `uuid` (pitfalls §2, `rate_plans.parse_uuid`). `Room.objects.filter(pk, unit=unit, is_active=True)`. Нет комнаты → «Zimmer gehört nicht zur Kategorie», брони нет.
- `rooms > 1` с комнатой → отказ «Mehrere Zimmer — bitte in der Buchung zuweisen» (паритет с drag E4.10b, `views.py:388–395`).
- `book_stay` и `assign_room` — в одном `transaction.atomic()` во вьюхе. `RoomConflict` → откат всей брони (вместе с `claim_units`, письмом-Notification и `commit_options`) и сообщение «Zimmer ist in diesem Zeitraum belegt».
- `book_stay` НЕ расширяем параметром room. Сервис назначения один (`assign_room`), порядок локов «категория → комната» сохраняется: `book_stay` лочит юнит, `assign_room` — комнату.

**Р-3. Способ оплаты на стойке.**
- Белый список стойки: `ON_SITE` (по умолчанию), `VORKASSE`. Мусор и `stripe` → `ON_SITE` (fail-safe, денег не меняет).
- `invoice` на стойке в v1 НЕ предлагается: `book_stay(auto_confirm=True)` сразу зовёт `on_confirmed` (CO-2d) и выпустил бы счёт без реквизитов фирмы. Счёт фирме оформляется в карточке брони, блок «Rechnungsempfänger» (CO-2 v2). Подсказка в форме.
- `payment_due_at` стойка не передаёт (`None`). Иначе beat `expire_payment_holds` снял бы телефонную Vorkasse-бронь через 3 дня — для walk-in это неверно. Тест-замок.

**Р-4. Блок через сервис + ёмкость блока категории.**
- `stay_create` mode=block → `services.create_block(unit, arrival, departure − 1, reason, room=room|None)`. Ловятся `NoCapacity`, `RoomConflict`, `ValueError`; тексты те же, что в `units()` 1054–1071 — вынести в общий `_block_error_msg(exc)`.
- В `create_block(room=None)`: `atomic` + `StayUnit.select_for_update()` + `range_available(unit, start, end+1)`. Если `False` → `NoCapacity`. Блок категории занимает 1 место на ночь (`availability.py:51`), поэтому на распроданных ночах он даёт тот же овербукинг, что E4.10a закрыл для комнат.
- iCal/OTA (`services.py:735/836`) и демо-сидер пишут `UnitBlock` напрямую — НЕ трогаем: это внешние факты, отказ невозможен.

**Р-5. DF-Z3 — запрет (О-8). Новый модуль `apps/stays/capacity.py`.**
- `sold_by_night(unit, from_day) -> dict[date, int]`: активные брони (`status_registry.active_statuses_for("stay")`) × `rooms` на ночи `≥ from_day`. Один запрос `values_list(arrival, departure, rooms)`, развёртка в памяти по образцу `range_available`. **Блоки НЕ считаем:** О-8 говорит о проданном; лишний блок безвреден.
- `class CapacityBelowSold(Exception)` с полями `day`, `sold`.
- `set_quantity(unit, new_qty, today)`: под `select_for_update` юнита; при `max(sold) > new_qty` → исключение с первой такой ночью.
- `delete_room(room, today)`: под локом юнита, затем комнаты (порядок E4.10a).
  - (а) назначена активной брони, у которой `departure > today` (`room` или `extra_rooms`) → `RoomAssigned(booking)`;
  - (б) ёмкость после удаления `< max(sold)` → `CapacityBelowSold`;
  - иначе — прежняя логика `views.py:1086–1088` (удаление её блоков + `sync_room_quantity`).
- `unit_settings` при отказе сохраняет **остальные поля**, `quantity` оставляет прежним и выдаёт `messages.error`: «Am %(day)s sind %(sold)s Zimmer verkauft — weniger geht nicht.»
- Комнаты с `is_active=False` в кабинете никто не выключает (grep: писателей нет) — вне объёма.
- Деактивация категории (`toggle`) с будущими бронями — вне объёма, запись в roadmap §Отложено.

**Р-6. Check-in / Check-out (О-7) — модуль `apps/stays/front_desk.py`.**
- `checkin_allowed_statuses(tenant)` = `active_statuses_for("stay", tenant) − {"pending"}`. Неподтверждённая онлайн-заявка сначала подтверждается, кастом-«Anzahlung erhalten» допустим.
- `check_in(booking, *, actor, today, now)`:
  - статус ∈ allowed, иначе `FrontDeskError("bitte zuerst bestätigen")`;
  - `arrival ≤ today < departure`; ранний заезд на день раньше — отказ;
  - запись — условный `UPDATE … WHERE checked_in_at IS NULL` (двойной тап → «bereits eingecheckt», без второго штампа);
  - `audit_event` в собственном `with transaction.atomic()` (pitfalls §3).
- `undo_check_in`: только при `checked_out_at IS NULL` и статусе ≠ fulfilled.
- `check_out(...)`:
  - требует `arrival ≤ today` и `departure ≤ today`. Ранний выезд → отказ «Abreise vor dem gebuchten Datum — bitte zuerst die Abreise in der Buchung ändern»: ночи и деньги меняются только явной правкой (E4.7a);
  - затем `core_transactions.apply_action("stay", booking, "fulfilled", actor, tenant)` — единственная точка денег/выручки/комнаты→dirty;
  - отметку ставит хук FSM.
- **Отметка выезда — в `StayBookingSM.on_transition` при `dst == "fulfilled"`:** `filter(pk, checked_out_at__isnull=True).update(checked_out_at=now)` + атрибут на инстансе, если `not kw.get("auto")`. Так кнопка «Abgereist», доска и Heute ставят отметку одинаково.
- `auto_fulfil_departed` зовёт `sm.apply(booking, "fulfilled", auto=True)`. `NULL` = «автоматически abgereist» (честно: факт выезда никто не подтвердил).
- Зеркало для кастом done-роли stay — в `apps/core/status_effects.py` (ветка `kind == "stay"`, строка 56): та же отметка.
- **Гард противоречий (одна точка — `core_transactions.apply_action`, kind stay):** `no_show` для брони с `checked_in_at` → отказ `IllegalTransition`-подобной ошибкой с текстом «Gast ist eingecheckt». Отмена эингечеканной брони разрешена (бывает), но с предупреждением.
- **Правка брони** (`stay_action` update/move): если `checked_in_at` и новый `arrival > today` → отказ «Gast ist eingecheckt — zuerst Check-in zurücknehmen».
- Права: check-in/out — любой с доступом к кабинету (стойка, staff). Undo — тоже (ошибочный тап).

**Р-7. Эндпоинты — новые action в существующем `stay_action`** (`@login_required` + `@require_POST` уже стоят): `check_in`, `check_in_undo`, `check_out`.
- Новых URL нет, значит новых сирот в `test_orphan_decorators` / `test_staff_walk` нет.
- Попутно `next` в `stay_action` и `stay_create` → общий `_safe_next(request)` через `url_has_allowed_host_and_scheme(host=request.get_host())` + отказ от `\`.

**Р-8. `checkout_hour` / `checkin_hour`.**
- `StaySettings.checkout_hour = PositiveSmallIntegerField(default=14)`, `checkin_hour = PositiveSmallIntegerField(default=15)`, `CheckConstraint` 0..23 для обоих.
- Классметод `StaySettings.hours()` → `(checkin, checkout)` **только чтением**: `values_list(...).first()` или дефолты. `load()` создаёт строку, а beat не должен писать в каждую схему ежечасно.
- `tasks.auto_fulfil_departed`: `now.hour >= checkout_hour`. `AUTO_CHECKOUT_HOUR` остаётся как имя дефолта (тест 672 цел).
- В кабинете — action `stay_hours` (селекты 0–23, рядом с формой Kurtaxe/Hausordnung в `templates/stays/units.html`, секция настроек). Добавить в `RATE_EDIT_ACTIONS`: час влияет на момент признания выручки, политика owner/admin — AST-замок Z-4 его потребует.
- JSON-LD `checkinTime`/`checkoutTime` НЕ выводим: дефолт был бы заявлением от имени всех отелей. В roadmap §Отложено.

**Р-9. Heute: одна точка списков — `front_desk.today_lists(tenant, today)`.**
- Возвращает `{"arrivals": qs, "departures": qs, "in_house": qs}`. Её используют `sales_page.heute_columns` И виджет `dashboard._stays_today` (счётчики = `.count()` тех же qs; расхождений «виджет 2, список 3» больше не будет).
- **Семантика:**
  - **Anreisen:** `arrival = today`, статус ∈ active (вкл. pending — видна неподтверждённая заявка с бейджем «unbestätigt»). Эингечеканные остаются в списке с ✓ HH:MM: стабильный счёт, стойка видит прогресс.
  - **Abreisen:** `departure = today`, статус ∈ (active − pending) ∪ {fulfilled}. Выехавшие остаются с ✓.
  - **Im Haus:** статус ∈ active − pending, `arrival ≤ today < departure`, и (`arrival < today` или `checked_in_at` задан), `checked_out_at IS NULL`.
- Запросы: `select_related("customer", "unit", "room", "registration")` + `prefetch_related("extra_rooms")`, срез `[:50]`. Бюджет — постоянное число запросов на колонку (замок).
- Оплата — `get_payment_state_display` + `payment_methods.label(payment_method)` без дополнительных запросов. Сумму «offen» через `money_contract.due` в v1 НЕ показываем: фолио generic → N+1. В roadmap.
- Элемент колонки (генерик, совместимо с booking/orders): `title`, `subtitle`, `url` + необязательные `badges: [{text, tone}]`, `actions: [{label, url, action, confirm}]`. Колонки booking/orders не меняются.
- `_safe` → `logger.exception("heute column %s failed", key)` и колонка `{"error": True, "items": []}`. Шаблон показывает «Konnte nicht geladen werden.». То же исправление — в `dashboard._safe` (проверить, логирует ли; если нет — тем же коммитом).
- Шаблон `_sales_heute.html`: элемент = `<div>` с `<a>` (имя/подзаголовок) + бейджи + `<form method=post>` кнопок (csrf, hidden `action`, hidden `next={{ request.get_full_path }}`). Кнопки ≥ 44 px (телефон). Check-out с `<dialog>`-подтверждением по образцу E2.4: выезд переводит деньги в выручку.

## 3. Точки изменения

| # | Файл | Что |
|---|---|---|
| 1 | `apps/stays/models.py:390+` `StayBooking` | `checked_in_at = DateTimeField(null=True, blank=True)`, `checked_out_at` — то же |
| 2 | `apps/stays/models.py:643+` `StaySettings` | `checkin_hour`, `checkout_hour` + `Meta.constraints` (CheckConstraint ≤ 23) + `hours()` |
| 3 | `apps/stays/migrations/0044_ka12_z5_checkin_checkout_hours.py` | 4 `AddField` + 2 `AddConstraint`, без data-шага. Nullable — metadata-only; `default=14/15` — fast default PG11+ |
| 4 | `apps/stays/services.py:243` `create_block` | ветка `room=None` под локом юнита + `range_available` → `NoCapacity` (Р-4) |
| 5 | `apps/stays/services.py:309` `book_stay` | `apply_auto_discount=True` (Р-1), строки 407–419 |
| 6 | `apps/stays/capacity.py` (новый) | `sold_by_night`, `set_quantity`, `delete_room`, `CapacityBelowSold`, `RoomAssigned` (Р-5) |
| 7 | `apps/stays/front_desk.py` (новый) | `checkin_allowed_statuses`, `check_in`, `undo_check_in`, `check_out`, `today_lists`, `FrontDeskError` (Р-6, Р-9) |
| 8 | `apps/stays/state_machine.py:58–80` | отметка `checked_out_at` при `fulfilled`, если не `auto` |
| 9 | `apps/core/status_effects.py:56` | зеркало отметки для кастом done-роли stay |
| 10 | `apps/core/transactions.py` `apply_action` (kind stay) | гард `no_show` при `checked_in_at` (Р-6) |
| 11 | `apps/stays/tasks.py:57–87` | `StaySettings.hours()` вместо константы; `sm.apply(..., auto=True)` |
| 12 | `apps/stays/views.py:640–736` `stay_create` | `_safe_next`; mode=block → `create_block` (Р-4); `auto_rabatt` (Р-1); `room` + atomic (Р-2); `payment_method` (Р-3); после успеха `restrictions.violation(...)` → `messages.warning` «Hinweis: verletzt die Verkaufsregel … (an der Rezeption erlaubt)» (О-2) |
| 13 | `apps/stays/views.py:340+` `stay_action` | `_safe_next`; action `check_in`/`check_in_undo`/`check_out` → `front_desk`; гард «eingecheckt» в update/move (Р-6) |
| 14 | `apps/stays/views.py:951–955` `unit_settings` | `capacity.set_quantity`; отказ не блокирует остальные поля |
| 15 | `apps/stays/views.py:1081–1088` `room_delete` | `capacity.delete_room`, сообщения; `stay_hours` action + `RATE_EDIT_ACTIONS` (Р-8) |
| 16 | `apps/stays/views.py:63` `stay_new`, `:163` `calendar_context` | в контекст `walkin_rooms` (активные комнаты, `select_related("unit")`), `walkin_payment_methods` |
| 17 | `apps/core/sales_page.py:159–236` | колонки stays на `front_desk.today_lists`, бейджи/кнопки, `_safe` с логом и `error` |
| 18 | `apps/core/dashboard.py:150–166` | счётчики из `today_lists` |
| 19 | `templates/stays/_walkin_form.html` | селект комнаты (`data-unit`), способ оплаты, чекбокс авто-скидок + сентинел, делегированный JS (расширить существующий `sync()`) |
| 20 | `templates/core/_sales_heute.html` | разметка элемента (Р-9), состояние `error`, подпись «Check-out bis %(h)s:00» у колонки Abreisen |
| 21 | `templates/stays/booking_detail.html` | блок «Anreise / Abreise»: отметки + те же кнопки (форма → `stay_action`) |
| 22 | `templates/stays/units.html` (секция Kurtaxe/Hausordnung ~714) | форма `stay_hours` (скрыта при `not can_edit_prices`) |
| 23 | `static/css/app.css` | пересборка, если появятся новые классы |

## 4. Тесты-замки — до кода
Файлы: `apps/stays/tests/test_z5_front_desk.py`, `test_z5_capacity.py`, `test_z5_checkin.py`; `apps/core/tests/test_z5_heute.py`.

**Стойка**
1. Без `auto_rabatt_present` → авто-скидка применена, итог = прежний (паритет; LOS-правило в тесте).
2. С сентинелом и без чекбокса → `auto_discount_cents == 0`, label пуст, итог = база × rooms + Kurtaxe. Акция на номер в тесте: лимит НЕ списан, `booking.promotion is None`.
3. Ваучер при выключенном тумблере всё равно применяется.
4. `room` своей категории, свободный → `booking.room == room`.
5. `room` занят на эти даты → сообщение, `StayBooking.count()` не изменился, лимит акции и Customer откатились.
6. `room` чужой категории / мусор / `"1 OR 1"` → сообщение, без 500, броней нет.
7. `rooms=2` + `room` → отказ.
8. `payment_method=vorkasse` → снимок vorkasse, `payment_due_at is None` (замок «beat не снимет walk-in»).
9. `payment_method=stripe` / `invoice` / мусор → `on_site`; счёт не выпущен (`Invoice.count()` неизменен).
10. mode=block без комнаты на распроданных ночах → `NoCapacity`-сообщение, `UnitBlock` не создан.
11. mode=block с комнатой → `UnitBlock.room == room`; комната с гостем → `RoomConflict`-сообщение.
12. Ручной POST mode=block с `departure ≤ arrival` → «Invalid dates.».
13. Бронь на ночь со stop_sell / нарушением G12 → бронь создана + `messages.warning` (О-2).
14. `next=/\evil.com` и `next=//evil.com` → редирект на `stays:calendar`, а не наружу (`stay_create` и `stay_action`).
15. Регресс: `test_front_desk.py` 64/98/117/135 зелёные без правок.

**`create_block` (сервис)**
16. Категория с quantity=1 и бронью → блок категории на эти ночи → `NoCapacity`. Свободная ночь → создан. `test_e410a_room_block.py` зелёный.

**DF-Z3**
17. `sold_by_night`: брони × rooms, cancelled не считается, прошлые ночи не входят.
18. `unit_settings` quantity 3 → 1 при 2 проданных на будущую ночь → quantity = 3. Описание/имя при этом сохранились, сообщение с датой и числом.
19. Уменьшение до проданного ровно → проходит.
20. Прошлая ночь с 3 бронями не мешает уменьшению.
21. `room_delete` назначенной будущей брони → комната жива, сообщение с кодом брони. Назначенной как `extra_rooms` → то же. Брони прошлой → удаляется.
22. `room_delete` неназначенной, но ёмкость после удаления < проданного → отказ, `quantity` не изменился.
23. Конкурентность: `set_quantity` берёт `select_for_update` юнита (проверка по `connection.queries` / мок лока как в Z-3).

**Check-in/out**
24. `check_in` confirmed в день заезда → `checked_in_at` задан. Повтор → тот же timestamp, сообщение «bereits». Pending → отказ. `arrival > today` → отказ. Кастом active-статус (site_config) → разрешено.
25. `undo_check_in` → NULL; после fulfilled → отказ.
26. `check_out` в день выезда → status fulfilled, `checked_out_at` задан, `RevenueEntry` = итог (паритет с «Abgereist»), комната dirty.
27. `check_out` при `departure > today` → отказ, статус неизменен.
28. «Abgereist» (action `fulfilled` старой кнопкой) → `checked_out_at` тоже ставится.
29. `auto_fulfil_departed` → fulfilled, `checked_out_at IS NULL`.
30. `no_show` эингечеканной через `stay_action` и через доску (`apply_action`) → отказ.
31. Правка брони (update) эингечеканной с `arrival > today` → отказ, даты неизменны.
32. `audit_event` упал (monkeypatch) → отметка всё равно сохранилась (savepoint — pitfalls §3).

**`checkout_hour`**
33. `checkout_hour=11`: в 10:59 бронь с выездом сегодня не закрыта, в 11:00 закрыта.
34. Без строки `StaySettings` → поведение 14:00, и строка НЕ создана (`StaySettings.objects.count() == 0` после beat).
35. Ночь перевода часов (25.10) и `now` после 22:00 UTC — ожидание считается тем же `localtime`, что код (pitfalls §6).
36. `stay_hours` от staff → отказ (`RATE_EDIT_ACTIONS`). 24 / «x» / «²» → без 500, значение не изменено. AST-замок Z-4 «каждый писатель политики в константе» зелёный.

**Heute / DF-Z4**
37. Кастом active-статус → бронь видна в Abreisen и Im Haus (раньше нет). Виджет главной считает её же.
38. Pending сегодняшнего заезда → в Anreisen с бейджем «unbestätigt», нет в Im Haus.
39. Эингечеканный в день заезда → в Anreisen с ✓ и в Im Haus. Выехавший сегодня → в Abreisen с ✓, нет в Im Haus.
40. Карточка показывает номер(а) комнат (`room` + `extra_rooms`), состояние оплаты и способ, Meldeschein ✓ при наличии `GuestRegistration`, «—» без неё.
41. Кнопки: форма POST на `stays:stay-action`, `action=check_in` / `check_out`, csrf, `next` с `view=heute`.
42. Бюджет запросов: 10 броней → `django_assert_max_num_queries(N)`, где N фиксирован и не растёт с числом броней (сравнить 3 и 10).
43. Исключение в колонке (monkeypatch `today_lists`) → `caplog` содержит запись, в теле «Konnte nicht geladen werden», нет «Nichts für heute».
44. Регресс: `test_front_desk.py:178/222`, `test_cabinet_review_fixes.py:105/150`, `test_w10_redirects.py:66`, `test_verkaeufe` — зелёные.

**Миграция**
45. `--create-db`; копия шаблонной схемы T-10 (`ensure_template_schema`) сохраняет имена CheckConstraint — прогон теста копии.

**Playwright-стенд** (демо hotel после `--recreate` у себя, 390 и 1440 px):
- Heute: Check-in → ✓ HH:MM без перехода со страницы `view=heute`;
- Check-out → диалог → бронь в Abreisen с ✓, комната «Zu reinigen» в Belegungsplan;
- walk-in: смена категории прячет чужие комнаты, тумблер авто-скидок снят → итог базовый;
- `room_delete` занятой → сообщение;
- кнопки ≥ 44 px, без горизонтального скролла на 390 px.

## 5. i18n
Базовые msgid немецкие, переводы в 5 `.po` (дописыванием в конец — pitfalls §4, без `polib.save()`). Проверки: `scripts/i18n_quickcheck.py`, CI-гейт `i18n_gap`, дуп-чек polib. Без `gettext` в f-строках.

- «Automatische Rabatte anwenden»
- «Zimmer» / «— Zimmer später zuweisen —»
- «Dieses Zimmer gehört nicht zur gewählten Kategorie.»
- «Dieses Zimmer ist in diesem Zeitraum belegt.»
- «Mehrere Zimmer — bitte die Zimmer in der Buchung zuweisen.» — msgid уже есть, переиспользовать
- «Zahlung» / «Rechnung an eine Firma — in der Buchung unter „Rechnungsempfänger“.»
- «Hinweis: Diese Buchung verletzt die Verkaufsregel (%(rule)s) — an der Rezeption erlaubt.»
- «Am %(day)s sind %(sold)s Zimmer verkauft — weniger geht nicht.»
- «Zimmer %(number)s ist der Buchung %(code)s zugewiesen — bitte zuerst umbuchen.»
- «Check-in» / «Check-out» / «Check-in zurücknehmen»
- «Eingecheckt %(time)s» / «Ausgecheckt %(time)s» / «unbestätigt»
- «Bereits eingecheckt.» / «Bitte die Buchung zuerst bestätigen.»
- «Anreise ist erst am %(day)s.»
- «Abreise vor dem gebuchten Datum — bitte zuerst die Abreise in der Buchung ändern.»
- «Gast ist eingecheckt — zuerst Check-in zurücknehmen.»
- «Konnte nicht geladen werden.»
- «Meldeschein»
- «Check-in ab (Uhr)» / «Check-out bis (Uhr)» / «Danach schließt das System die Abreise automatisch ab.»
- «Check-out bis %(h)s:00»
- «Gast auschecken? Die Buchung wird abgeschlossen und als Umsatz gebucht.»

## 6. Инкременты — один батч, коммиты по шагам
- **Z-5a** — `0044`, модели, `StaySettings.hours()`, `tasks` на `checkout_hour` (Р-8) + action `stay_hours`. Тесты 33–36, 45.
- **Z-5b** — `capacity.py`, `create_block` с ёмкостью категории, `unit_settings`/`room_delete` (Р-4/Р-5). Тесты 16–23.
- **Z-5c** — стойка: авто-скидки, комната, оплата, блок через сервис, предупреждение G12, `_safe_next` (Р-1–Р-4). Тесты 1–15.
- **Z-5d** — `front_desk.py` check-in/out, хук FSM, зеркало `status_effects`, гарды `apply_action`/update, кнопки в `booking_detail` (Р-6/Р-7). Тесты 24–32.
- **Z-5e** — Heute + виджет через `today_lists`, DF-Z4 (Р-9). Тесты 37–44.
- **Z-5f** — i18n ×5, `npm run build:css`, Playwright-стенд, ревью, доки: `build-log`, `task-catalog`, §3 `CLAUDE.md`, очередь миграций `stays/0044`.

## 7. Риски
- **Деньги при check-out.** Отметка — в хуке FSM, деньги — в той же `apply_action`; второго пути выручки нет. Ранний выезд запрещён до явной правки дат, иначе «показано ≠ проведено».
- **Блок категории теперь может получить отказ** (`NoCapacity`) там, где раньше молча создавал овербукинг. Это изменение поведения `units()` action `block` — упомянуть владельцу в чекпоинте.
- **Стойка: тумблер по умолчанию вкл. = паритет.** Выключенный не трогает ваучер. Лимит акции не списывается — тест 2.
- **Атомарность walk-in с комнатой.** Внешний `atomic` во вьюхе вокруг `book_stay` (сам `@transaction.atomic`) и `assign_room`. Письмо «created» — Notification в той же транзакции, откат гасит и его. Проверить, что `enqueue_stay_email` не шлёт `on_commit` напрямую в Celery — если шлёт, то по `on_commit` и откатится корректно.
- **DF-Z3 по брони, а не по блокам.** Блоки сверх ёмкости после уменьшения дадут «Überbuchung»-предупреждения `overbooked_nights` (KA-H6). Осознанно: блок — не продажа. Описать в сообщении-подсказке не нужно.
- **Heute меняет семантику Abreisen/Im Haus** (кастом-статусы, выехавшие с ✓). Тесты 178/222 должны остаться зелёными. Если нет — осознанная переписка с комментарием.
- **N+1 в Heute.** `registration` (reverse OneToOne) — `select_related`, `extra_rooms` — prefetch. Сумма «offen» сознательно не выводится (фолио generic), запись в roadmap §Отложено.
- **`checkout_hour` в beat** — только чтение настроек. Иначе `load()` создавал бы строку в каждой схеме ежечасно.
- **Шаблон T-10.** Новые CheckConstraint — проверить копию схемы (грабля `_uniq` → `_key` закрыта, тест копии гнать).
- **Вне объёма (в roadmap §Отложено):**
  - no-show-подсказка по `checked_in_at IS NULL` после выезда;
  - JSON-LD `checkinTime`/`checkoutTime`;
  - счёт фирме прямо со стойки;
  - деактивация категории с будущими бронями;
  - «offen €» в Heute;
  - `checkin_hour` как гейт раннего заезда (сейчас только подсказка).
- **Демо.** `SEEDER_VERSION` не поднимаем: данные кита не меняются. Отметки заселения в демо — Z-7.

## 8. ECC-прогоны

| Шаг | Скиллы до кода | Агенты / проверки |
|---|---|---|
| Сразу после плана | `django-security`, `django-patterns`, `database-migrations` | `security-reviewer` — ревью плана: Р-2 (подделка room/unit), Р-3 (белый список оплаты, отсутствие счёта без реквизитов), Р-7 (`_safe_next`, новые action в `stay_action`), права check-in у staff. `database-reviewer` — `0044` (fast default, CheckConstraint), локи `capacity.py` (порядок юнит → комната), бюджет запросов `today_lists` |
| Z-5a | `django-tdd`, `database-migrations` | тесты 33–36/45 красные до кода; `--create-db`; `django-reviewer` |
| Z-5b | `django-tdd`, `postgres-patterns` | `database-reviewer` (лок, развёртка ночей в памяти, без N+1); `silent-failure-hunter` (отказ `unit_settings` не теряет остальные поля и не молчит) |
| Z-5c | `django-security`, `error-handling` | `security-reviewer` (room/payment/next/mode подделки); `silent-failure-hunter` (откат брони при `RoomConflict`, отсутствие тихого фолбэка способа оплаты на деньги, `claim_units` при выключенном тумблере) |
| Z-5d | `django-tdd`, `error-handling` | `silent-failure-hunter` (деньги check-out через одну точку, `audit_event` в savepoint, гард no_show на всех поверхностях); `django-reviewer` |
| Z-5e | `accessibility`, `e2e-testing` | `django-reviewer` (запросы, логирование `_safe`); `a11y-architect` (кнопки в карточке, `<dialog>`, размеры на 390 px); **Playwright-стенд Heute** 390/1440 (§4) |
| Перед мержем | — | `django-reviewer` по всей ветке (обязательно); `security-reviewer` по итоговому диффу `views.py`; `ruff check .` + `ruff format --check .` целиком; pytest `apps/stays apps/core apps/finance apps/tenants` (`--create-db`); `test_orphan_decorators`; `test_template_comments`; `scripts/i18n_quickcheck.py` + дуп-чек polib; `scripts/i18n_untranslated.py`; `npm run build:css` + коммит `static/css/app.css`; зелёный CI → FF в `main` |

**ops после деплоя:** `./scripts/deploy.sh single` (`stays/0044`). Пересев демо не нужен.

## 9. Ревью плана `security-reviewer` (2026-10-25, до кода) — принять при реализации
1. **Р-2:** `room` — строго `rate_plans.parse_uuid`; сначала `unit`, потом `room` внутри него; в `mode=block`
   комната тоже разбирается строго; тест-замок «письмо/Celery брони — только `on_commit`» (откат при `RoomConflict`).
2. **Р-3:** сервисный тест «`payment_method=invoice` + `auto_confirm` без реквизитов → счёт не выпущен»;
   форма стойки не шлёт buyer/company → дефолты `book_stay` не ведут к счёту фирме; **Vorkasse на стойке
   только при заданных банковских реквизитах** (guard IBAN, как в E7).
3. **`_safe_next`:** переиспользовать общий хелпер (`core/views.py`, `inbox/views.py`), а не третий;
   `url_has_allowed_host_and_scheme(allowed_hosts={host}, require_https=is_secure)` + отказ от `\`, `\t\r\n`;
   пробы `/\evil.com`, `/%09/evil.com`, `///evil.com`, `https://evil.com` в `stay_action` и `stay_create`.
4. **Права check-out:** решение через систему прав сотрудников (запрос владельца 2026-10-25 — настраиваемые
   права, выдаёт администратор; план — отдельным инкрементом ДО кода Z-5). Undo check-in запрещён и при `no_show`.
5. Двойной тап: «bereits» — по `rowcount == 0`; два `check_out` подряд — одна выручка.
6. Гард `no_show` после check-in — и в массовой смене статусов (E2.1), и в кастом-ролях.
7. Гард правки заселённой брони — в `services.move_stay`/update (не только вьюха): перенос `departure`
   раньше сегодня, смена категории/комнаты, drag на шахматке.
8. `stay_hours`: клампить в 0..23 до записи (CheckConstraint не должен давать 500); `"٣"` не должен стать 3.
9. Тест блока категории «ночи свободны, но часть ёмкости уже блокирована».
10. Порядок локов «юнит → комната» одинаков в `delete_room`/`assign_room` — проверить по `connection.queries`.
11. Heute: `logger.exception` без PII; `next` с `"><script>` экранирован; Meldeschein — только ✓/—.

## 10. Ревью плана `database-reviewer` (2026-10-25, до кода) — принять при реализации
1. `delete_room`: проверка «назначена активной брони» — строго ПОСЛЕ `select_for_update` комнаты
   (`assign_room` лочит только комнату); тест: без лока комнаты — красный.
2. DF-Z3 по `quantity` — только категории без комнат; с комнатами ёмкость уменьшает лишь `room_delete`,
   сравнение `max(sold) > active_rooms − 1`; presence-guard `quantity` в `unit_settings` (W0: без поля — не 1).
3. `checked_out_at` — ПЕРВЫМ действием ветки `fulfilled`; `check_out` в `atomic`; тест «падение
   `settle_on_delivery` откатывает статус и отметку».
4. Check-in: `UPDATE … WHERE checked_in_at IS NULL AND status IN (allowed)`, «bereits» vs «статус изменился»
   перечитыванием; undo — условия в UPDATE; даты от `timezone.localdate()`.
5. `create_block`: лок юнита + `range_available` + `NoCapacity` — общая часть выше развилки по `room`;
   два блока на последний номер → `NoCapacity`.
6. `sold_by_night`: SQL `departure > from_day`, `status__in=active`, × `rooms`; наружу обычный dict.
7. Heute: `Exists(GuestRegistration)` → `has_registration` (reverse OneToOne без строки бросает); «Im Haus»
   одним `Q`; бюджет запросов 3 vs 10 броней.
8. `CheckConstraint(condition=…)` (Django 5.1), только `≤ 23`; имена согласованы с `0044`.
9. ops: после деплоя проверить в логе пересборку шаблонной схемы (шаг 6a).
10. Письма walk-in — тест «только on_commit» обязателен.
11–14. `%5c` в пробах `next`; гард `no_show` и исключение `pending` — по РОЛИ статуса, не по коду;
   симметричный тест кастом done-роли (отметка ставится, но не при `auto`).
