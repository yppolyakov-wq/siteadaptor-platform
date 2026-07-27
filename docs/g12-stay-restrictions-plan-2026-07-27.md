# G12 — Тарифные ограничения v2 («Verkaufsregeln», revenue management отеля)

**Дата:** 2026-07-27 · **Статус:** одобрено владельцем («делай», из gap-анализа
Booking-Engine TravelLine §3.5) · **Каталог:** семейство G (рост отеля), G12.

## 1. Проблема

Сейчас ограничения продаж — только `StayUnit.min_nights` (константа на номер) и
блокировки `UnitBlock`. Нет инструментов управления спросом: сезонный min-stay
(«праздники — от 3 ночей»), max-stay, запрет заезда/выезда по дням недели
(CTA/CTD), глубина бронирования, минимальный срок до заезда. Это главный
функциональный гэп против зрелых booking-движков.

## 2. Решение (v1)

### 2.1 Хранение — паттерн G4 (без новой модели)

`StaySettings` (синглтон тенанта) — три аддитивных поля, миграция `stays/0024`:

- `restriction_rules: JSONField(list)` — список правил (кап 50), правило:
  `{"start": "YYYY-MM-DD"|"", "end": "…"|"", "unit": "<pk>"|"", "min_nights": int,
  "max_nights": int, "no_checkin": [0..6], "no_checkout": [0..6]}`
  (weekday: 0=Mo … 6=So; пустые start/end = всегда; пустой unit = все номера).
- `max_advance_days: PositiveSmallIntegerField(default=0)` — глубина бронирования
  (0 = выключено; жёсткий кап горизонта `MAX_DAYS_AHEAD=365` остаётся).
- `min_advance_days: PositiveSmallIntegerField(default=0)` — минимум дней до
  заезда (0 = можно на сегодня).

### 2.2 Семантика (стандарт PMS)

- min_nights / max_nights / no_checkin матчатся по **дате заезда** в периоде
  правила; no_checkout — по **дате выезда** в периоде.
- Несколько подходящих правил → строжайшее: max(min_nights), min(max_nights>0),
  объединение запрещённых дней.
- Правила поверх `StayUnit.min_nights` (берётся максимум).

### 2.3 Резолвер — `apps/stays/restrictions.py`

`violation(unit, arrival, departure, *, today) -> (code, n) | None`; коды:
`window` / `lead` / `rule_min_nights` / `rule_max_nights` / `no_checkin` /
`no_checkout` (n — число для текста: дни/ночи; для weekday-кодов n=None).
Плюс `clean_rules()` (валидация/капы — как `clean_auto_rules` G4).

### 2.4 Гейт — ТОЛЬКО витрина (решение)

Владелец в кабинете НЕ ограничивается (walk-in/телефон главнее правил онлайн-
продаж — стандарт PMS): `stay_create`, `move_stay`, демо-сиды не трогаем.

- `public_views._quote` — первая проверка → `(nights, 0, False, code)`;
  автоматически кроет деталь номера И поиск `/unterkunft/`.
- `services.book_stay(..., enforce_restrictions=False)` — новый параметр;
  `unterkunft_book` передаёт `True` (server re-validation); новый exception
  `RestrictionViolated(code, n)` → message-текст причины.
- `_buybox_stay_unavailable.html` — тексты причин (с N).
- Селектор дат: `max_date` учитывает окно, `min` date-инпута — lead.
  Календарь: дни за окном кликабельны, сервер честно отказывает с причиной
  (подсветка в календаре — v2 по спросу).

### 2.5 Кабинет — страница `stays:units` (там уже тарифы/Kurtaxe/G4)

Секция «Verkaufsregeln»: (a) форма окна бронирования (2 поля, action
`booking_window`); (b) список правил + форма добавления (Zeitraum von/bis опц.,
Zimmer-селект опц., Min./Max. Nächte, чекбоксы дней «keine Anreise» / «keine
Abreise») + удаление — actions `restriction_add` / `restriction_delete`
байт-в-байт по образцу `autodiscount_*`.

## 3. Вне объёма v1 (отметки)

- Подсветка CTA/CTD/окна прямо в календаре витрины — v2.
- G8-фид метапоиска min-stay не знает — как сейчас (отказ на этапе брони).
- Ограничения per-тариф (RatePlan-скоуп) — v2 при спросе; v1 скоуп = номер/все.
- Часы вместо дней в lead — не нужно малым отелям.

## 4. Замки

`apps/stays/tests/test_restrictions.py`: резолвер (окно/lead/min/max/CTA/CTD/
юнит-скоуп/строжайшее из двух/вне периода), `_quote`-коды, гейт
`unterkunft_book`, кабинет `stay_create` НЕ гейтится, units-actions add/delete +
booking_window, тексты фолбэка. i18n: новые msgid → en/tr/ru/uk `.po`.
