# KA-12 · Волна 4 · направление «Zimmer» (отель / пансион) — план, 2026-10-25

План — агент `planner` по `main` (`7c26d7eb`), ссылки сверены. Источники: `ka-12-master-plan-2026-10-23.md`
(§E4 E4.6, §E1 E1.15, Волна 4 «Zimmer»), `ka-5d-zimmer-2026-10-23.md`, `pitfalls.md`. Правило мастер-плана:
перед направлением — золотой путь E11.1 (Z-0). Миграции только аддитивные; последняя в stays — `0040`.
Решения О-1…О-10 приняты по рекомендации (владелец: «Делай по рекомендации», 2026-10-25) — см. §8.

## 0. Что значит каждый пункт
| ID | Смысл |
|---|---|
| E4.6 | Календарь «Preise & Verfügbarkeit»: категории × дни (14/31), в ячейке цена ночи и ограничения дня (стоп-продажа, min-stay при заезде, CTA, CTD); массовая правка «категории × период × дни недели → действие» (цена = X €, ±N %, сброс, стоп вкл/выкл, min-stay, CTA/CTD) с предпросмотром «затронуто N ночей»; тарифы по категориям |
| E1.15 | Месячный Kurtaxe-отчёт для общины (ночи взрослых/детей, освобождённые, сумма по снимку `kurtaxe_cents`, CSV + PDF); выгрузка Meldeschein за период; ввод Meldeschein walk-in из кабинета; заработает `kurtaxe_children_free` |
| §3.1 | Пересечение сезонов; явный тариф на стойке (сейчас молча первый); тумблер авто-скидок на стойке; фид G8 по тем же ценам/ограничениям |
| §3.2 | Фолио закрыто волной 3; гарантия картой + no-show fee — external, вне волны |
| §3.3 | Отметки заселён/выехал; `checkout_hour` настройкой вместо константы 14; «Heute» с комнатой, оплатой, Meldeschein, кастом-статусами |
| §3.4 | Оповещение/запрет при уменьшении номеров ниже проданного; блок с walk-in через общий сервис; allotment — вне v1 |

## 1. Что уже есть
- Цена: `stays/pricing.py` `nightly_price_cents` (SeasonRate → weekend → base), `price_breakdown`, `apply_rate_plan`,
  `occupancy_adjust`, `quote_total_cents`, `auto_discount`, `kurtaxe_total_cents` (флаг детей игнорируется).
- Модели: `StayUnit`, `RatePlan` (на весь тенант, без категорий), `SeasonRate` («пересечения не проверяются,
  побеждает первое»), `Room`, `UnitBlock`, `StayBooking` (нет статусов заселения; поночного снимка цен нет),
  `StaySettings` (`restriction_rules` G12, kurtaxe_*), `GuestRegistration`.
- G12 `stays/restrictions.py::violation` — только витрина (`book_stay(enforce_restrictions=True)`, `_quote`).
- Кабинет цен `views.units()` — POST-диспетчер ~25 действий, `rate` без проверки пересечений; вьюха только
  `@login_required`.
- Потребители цены (паритет обязателен): `book_stay`, `move_stay`, `public_views._quote`/варианты тарифов/фид G8,
  `aggregator/hotel_search.py`, `events/services.py` (номера ретрита), `core/deal_discount.py`,
  `views.booking_detail` (breakdown).
- Стойка `views.stay_create`: тариф по умолчанию — первый; `mode=block` пишет `UnitBlock` в обход
  `services.create_block`.
- `sync_room_quantity`: правка `quantity` не проверяет брони. «Heute» (`core/sales_page.py`) фильтрует литералом
  `STATUS_CONFIRMED`, `_safe` глотает ошибки без лога. `tasks.AUTO_CHECKOUT_HOUR = 14` — константа.
- Счёт: `finance/services.invoice_from_stay` (Bruttomethode); легаси `stays/services.stay_to_invoice`
  (net, 7 % на питание) достижим подделанным POST `stay_action action=invoice`.

## 2. Дефекты по ходу (деньги)
- **DF-Z1** `deal_discount._stay_lodging_cents` и breakdown карточки пересчитывают проживание по СЕГОДНЯШНИМ
  ценам → после правки сезона скидка DC-5 меняет итог на разницу цен (pitfalls §1). Breakdown не учитывает
  rooms/occupancy/авто-скидку.
- **DF-Z2** легаси `stay_to_invoice` → перевести ветку на `invoice_from_stay`, легаси удалить.
- **DF-Z3** уменьшение `quantity`/удаление комнаты ниже проданного → овербукинг без оповещения.
- **DF-Z4** «Heute»: кастом-статусы и тихий `except`.

## 3. Модель данных (аддитивно)
| Миграция | Что |
|---|---|
| `stays/0041` | `NightRate(unit, day, price_cents null, stop_sell, min_nights, no_checkin, no_checkout)`, unique (unit, day). Храним только переопределённые дни; пусто = прежняя цепочка байт-в-байт |
| `stays/0042` | `RatePlan.units` M2M (пусто = все категории) |
| `stays/0043` | `StayBooking.night_prices` JSON `[[iso, cents], …]` (после тарифа и occupancy, до авто-скидки) — источник истины breakdown/`deal_discount`; у легаси пусто → прежняя формула |
| `stays/0044` | `checked_in_at`/`checked_out_at`; `StaySettings.checkout_hour`=14, `checkin_hour`=15, `kurtaxe_child_cents`, `kurtaxe_exempt_note` |

Приоритет цены ночи: `NightRate.price_cents` → SeasonRate → weekend → base, затем тариф и occupancy.
Ограничения дня читает `restrictions.violation` (stop_sell / min_nights по заезду / no_checkin / no_checkout).
Стоп-продажа — не блок: в отчётах загрузки и `range_available` занятостью не считается.

## 4. UI
1. `/dashboard/stays/preise/` (`stays:price-calendar`): сетка категория × день (14/31, листание), на телефоне
   карточки без горизонтального скролла; массовая правка над сеткой (Vorschau — GET без побочных эффектов,
   «Übernehmen» — POST одной транзакцией, upsert, кап 2×366 ночей × категории); `<dialog>` одного дня; без JS
   работает (W0). Вход — подпункт реестра в «Sortiment», ссылки с Belegungsplan/страницы номера/`?sec=preise`.
2. Тариф: чекбоксы категорий (сентинел `rateplan_units_present`), подпись «für: … / alle».
3. Сезоны: отказ при пересечении с названием.
4. Стойка: тариф явным выбором («— ohne Tarif —»), «Automatische Rabatte anwenden», комната, способ оплаты,
   блок через `create_block`.
5. Heute: комната, оплата, Meldeschein ✓/—, кнопки Check-in/Check-out (POST), кастом-статусы.
6. `/dashboard/stays/kurtaxe/?month=` (таблица + CSV + PDF) и выгрузка Meldeschein — `@owner_required` +
   `audit_export`; в карточке брони «Meldeschein erfassen / drucken».

## 5. Тесты — до кода
- Z-0 сервер `apps/stays/tests/test_golden_zimmer.py`: паритет «показано = списано» (сезон+выходные+тариф с
  питанием+авто-скидка+2 номера); fulfilled → `RevenueEntry` = итог; `invoice_from_stay(...).gross == итог`
  со ставками 7/19/0; невозвратный тариф; тот же клиент по e-mail.
- Z-0 браузер `gp4_zimmer` в `scripts/golden_paths.py` (`/unterkunft/` → номер → свободные даты → форма →
  `/s/<code>/` → `_db_has`).
- DF-Z1: правка сезона после брони не меняет итог; скидка меняет итог ровно на скидку.
- E4.6: пустой NightRate — все замки цен байт-в-байт; цена дня бьёт сезон; stop_sell на витрине; кабинет
  бронирует; отчёт загрузки не меняется; тариф чужой категории отвергнут; массовая правка идемпотентна,
  −% не в минус, кап; Vorschau без записи; роли.
- §3.x и E1.15 — пересечение сезонов, стойка без тарифа, блок через сервис, quantity ниже проданного, Heute с
  кастом-статусом, `checkout_hour` (стык суток, pitfalls §6), Kurtaxe = Σ снимков, CSV owner-only.

## 6. Инкременты
| # | Что | Миграции |
|---|---|---|
| Z-0 | золотой путь GP-4 + серверный двойник; находки — исправлением | нет |
| Z-1 | DF-Z1 снимок `night_prices` + DF-Z2 | 0043 |
| Z-2 | E4.6a NightRate + резолвер во всех потребителях (вкл. фид G8, hotel_search) | 0041 |
| Z-3 | E4.6b экран календаря + массовая правка + диалог дня | нет |
| Z-4 | E4.6c `RatePlan.units` + пересечения сезонов | 0042 |
| Z-5 | стойка и Heute (§3.1/§3.3), DF-Z3/DF-Z4, check-in/out, `checkout_hour` | 0044 (часть) |
| Z-6 | E1.15 Kurtaxe-отчёт + Meldeschein | 0044 (часть) |
| Z-7 | демо hotel + `SEEDER_VERSION`++ + переводы | нет |

## 7. Риски
Паритет цены (одна функция; grep-замок на прямое чтение season_rates/NightRate вне pricing/restrictions) ·
снимок vs пересчёт («Neu berechnen» — осознанно сегодняшние цены) · массовая правка: блокировки по pk, не
трогать неизменённые строки (pitfalls §2), кап, audit · стоп-продажа не трогает проданные ночи · старые брони
со снимком тарифа · Kurtaxe только из снимков · Meldeschein — персональные данные (owner-only, журнал) ·
i18n ×5 · `npm run build:css`.

## 8. Решения (по рекомендации)
О-1 цена дня бьёт сезон — да · О-2 ограничения дня только витрина, стойка видит предупреждение — да ·
О-3 тарифы v1 производные от базы + категории — да · О-4 массовая правка — owner/admin · О-5 выгрузка CSV + PDF,
интеграции AVS/Feratel — external · О-6 ручная цена на стойке — v1 нет · О-7 «заселён» — отметка времени,
не статус FSM · О-8 уменьшение номеров ниже проданного — запрет · О-9 экран — подпункт «Sortiment» ·
О-10 номер документа в CSV не выгружаем, только печатный PDF. Вне v1: гарантия картой/no-show fee, allotment.

## 9. ECC-прогоны
| Шаг | Скиллы до кода | Агенты |
|---|---|---|
| Z-0 | `django-tdd`, `python-testing`, `e2e-testing` | Playwright-стенд GP-4 (390 px), `django-reviewer` |
| Z-1 | `django-tdd`, `error-handling`, `database-migrations` | `django-reviewer`, `silent-failure-hunter`, `database-reviewer` |
| Z-2 | `django-patterns`, `postgres-patterns`, `database-migrations` | `django-reviewer`, `database-reviewer` (prefetch диапазоном, без N+1), `silent-failure-hunter` (паритет) |
| Z-3 | + `accessibility`, `django-security` | `django-reviewer`, `security-reviewer`, `database-reviewer`, `a11y-architect`, Playwright 1440/390 |
| Z-4 | `database-migrations` | `django-reviewer`, `database-reviewer`, `security-reviewer` (чужой rate_plan) |
| Z-5 | `django-security` | `django-reviewer`, `security-reviewer`, `silent-failure-hunter`, Playwright Heute |
| Z-6 | `django-security` | `django-reviewer`, `security-reviewer`, `silent-failure-hunter` |
| перед мержем | — | ruff целиком, pytest затронутых модулей (`--create-db` после миграций), `i18n_quickcheck`, `template_comments`, `build:css`, CI |
