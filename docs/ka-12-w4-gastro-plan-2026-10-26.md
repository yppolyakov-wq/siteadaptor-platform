# KA-12 Волна 4 · направление «Gastro» (cafe, restaurant) — план (2026-10-26)

Источник: `ka-5b-gastro-2026-10-23.md` §1 (сц. 1–2) и §6 (G-1, G-2, G-5); `ka-12-master-plan-2026-10-23.md`
строки E4.5 и E3.9. Уже закрыто другими волнами: гости в ручной брони (KA-H5), слоты из часов работы +
Betriebsferien (E4.1), кейтеринг (A-2/A-3), окно акции для товаров (W1.3), Tagesplan мастер×время (B5),
правила услуги (E4.4a), варианты услуги (E4.4b). План составлен агентом `planner` по коду (факты — с
файлами и строками в §0).

## 0. Факты из кода
- Бронь стола = запись `apps.booking` без услуги. `Resource` (`booking/models.py:38-74`): `type` по
  умолчанию `table`, `capacity`, `counts_party_size` (пул: места = сумма гостей), `require_manual_confirm`,
  `deposit_cents`. Полей «места за столом / зона / онлайн / объединяется с» нет.
- `Booking.party_size`, статус по умолчанию `pending`, слот держат `pending`/`confirmed`. `group_code` — это
  HF-6 (несколько периодов одной бронью) — слово «group» для «большой компании» НЕ используем.
- Анти-овербукинг `services._would_overfill`: для стола-не-пула считается ЧИСЛО броней, а не гостей —
  стол на 2 (capacity=1) примет 8 гостей; мест не сверяет никто. `overlapping()`/`free_slots_with_spots`
  фильтруют строго `resource=resource`.
- Онлайн (`termin_book`): `party_size` 1..50, без `auto_confirm` → ЛЮБАЯ онлайн-бронь стола в `pending`;
  мгновенного подтверждения нет; лимита размера компании нет. `require_manual_confirm` читается в трёх
  местах: `booking/payments.py:81`, `public_views.py:188`, `core/money_contract.py:435`.
- Дефект: письмо `created` всегда «Anfrage erhalten … sobald sie bestätigt ist» — ручная запись со стойки
  (сразу `confirmed`) шлёт гостю «Anfrage erhalten».
- Настройки — `site_config["booking"]` (`normalize_booking` — только `no_show_deposit`), образец записи —
  `views.no_show_rule_save`.
- Кабинет: Tagesplan ресурс×время с перетаскиванием (= посадка за стол, если столы — ресурсы); экран
  ресурсов: `int(capacity)` вне try (G9, 500) и правки вместимости после создания нет; «Heute» — без
  числа гостей; виджета booking на главной нет.
- Mittagstisch: пресет `mittag` — `recurrence="daily"` без окна; `_next_window` сдвигает на сутки →
  наследники и в Sa/So. `target_rules` (дни/часы) движок понимает, но в `PromotionForm` полей нет —
  окно задают только пресеты/ассистент. У `Product` дней недели нет.

## 1. Решения дизайна
| # | Решение |
|---|---|
| D1 | Правила столов — `site_config["booking"]["tables"] = {instant_max, online_max}`, presence-minimal; по умолчанию прежнее «всё — запрос». |
| D2 | Снимок «большая компания» на брони — `Booking.is_large_party` (вебхук/beat не видят живого конфига). |
| D3 | Одна точка `booking/table_rules.needs_manual_confirm(booking)` вместо трёх мест. |
| D4 | Столы = отдельные `Resource(type=table)` с `seats`, `min_seats`, `zone`, `sort_order`, `bookable_online`; пул остаётся режимом «просто». |
| D5 | Объединение — M2M `Resource.combines` + одна функция `occupancy_scope(resource)` во всех путях занятости. |
| D6 | План зала v1 — плитки по зонам, без координат/редактора. |
| D7 | Mittagstisch по будням — существующие `target_rules.weekdays` + пропуск дней в повторе; Tageskarte — `Product.available_weekdays`. |

## 2. Инкременты (порядок: GA-0 → GA-1 → GA-2 → GA-8 → GA-3 → GA-4 → GA-5 → GA-6 → GA-7 → GA-9)
- **GA-0** золотой путь GP-7 + серверный двойник (без миграций); дефекты фиксируются `xfail(strict=True)`
  с кодом инкремента-исправителя.
- **GA-1** (⚠️ `booking/0040` `is_large_party`) «Sofort bestätigen / Gruppenanfrage / Bitte anrufen»:
  `table_rules.decide` (INSTANT|REQUEST|CALL, только тип table, только онлайн); депозит не подтверждает
  REQUEST; письмо `confirmed` при мгновенном подтверждении и при ручной записи (чинит дефект); карточка
  «Online-Tischreservierung» на ресурсах + POST `booking:table-rules` (CFG).
- **GA-2** «Gruppenanfragen» у владельца (бейдж, фильтр `?anfrage=1`, кнопки FSM) + виджет «Gäste heute» и
  « · k Pers.» в «Termine heute» (без миграций).
- **GA-3** (⚠️ `booking/0041`) столы с местами: правка вместимости/мест, фикс G9, отказ «Tisch hat nur N
  Plätze» с флагом «Trotzdem eintragen», перенос — предупреждение.
- **GA-4** онлайн «Tisch reservieren» с автоподбором стола (`availability.table_slots`,
  `table_rules.assign_table`, попытки `book()` в savepoint, тест гонки).
- **GA-5** (⚠️ `booking/0042`) объединение столов через `occupancy_scope` во ВСЕХ путях занятости
  (book/book_many/move/самоперенос/слоты), блокировка области по pk; AST-замок; database-reviewer.
- **GA-6** экран «Tischplan» (плитки по зонам на время, walk-in, «Tisch zuweisen»); nav_registry,
  view_perms, палитра, DoD экрана, стенд Playwright.
- **GA-7** демо restaurant: 8 столов в двух зонах + комбинация + правило + брони; cafe — пул
  (`SEEDER_VERSION` +1).
- **GA-8** Mittagstisch Mo–Fr: окно «дни/часы» в полной форме акции (`target_rules`, presence-guard),
  пресет `mittag` с днями, повтор пропускает дни вне правила и закрытые (макс. 14 итераций).
- **GA-9** (⚠️ `catalog/0041`) Tageskarte: `Product.available_weekdays`, отказ на чекауте по дню выдачи,
  бейдж/фасет «Heute auf der Karte», фид «out of stock», PDF Speisekarte, демо.

## 3. Сквозные риски
Анти-овербукинг — только через `book`/`move` + `occupancy_scope`, блокировка по pk, тесты гонки (GA-4/5).
Ключ `tables` только при включении (golden). i18n — каждый msgid в 5 `.po`, письма `.txt` сверять
отдельно. Новые маршруты — `view_perms`; ссылки из общих шаблонов — `pkg_allowed`. «Tischplan» —
подпункт Verkäufe (мораторий якорей X7). Сидер → `SEEDER_VERSION`; ops: `seed_demo_tenants --kit
restaurant --recreate`. Миграции `booking/0040–0042`, `catalog/0041` — аддитивные.

## 4. Решения (2026-10-26, по рекомендации — как в прошлых волнах)
- **Р-1** Gruppenanfrage держит места до решения (как `pending`), без автоотмены в v1.
- **Р-2** «Sofort bestätigen» по умолчанию выключено (сегодняшнее «всё — запрос»); в демо включено.
- **Р-3** Объединение столов — в v1 (GA-5).
- **Р-4** Депозит для больших компаний — v2.
- **Р-5** Окна акции в полной форме нет (проверено grep) — GA-8 его добавляет.

## 5. ECC-прогоны
| Инкремент | Скиллы до кода | Агенты |
|---|---|---|
| GA-0 | e2e-testing, django-tdd | e2e-runner (стенд GP-7) |
| GA-1 | django-patterns, django-security, django-tdd, error-handling | django-reviewer, security-reviewer, silent-failure-hunter (payments/money_contract), database-reviewer (0040) |
| GA-2 | django-patterns, accessibility | django-reviewer, a11y-architect |
| GA-3 | django-patterns, database-migrations | django-reviewer, database-reviewer |
| GA-4 | django-security, postgres-patterns, seo, accessibility, e2e-testing | django-reviewer, security-reviewer, database-reviewer (гонка), e2e-runner, seo-specialist, a11y-architect |
| GA-5 | postgres-patterns, database-migrations, django-tdd | database-reviewer (обязательно), django-reviewer, silent-failure-hunter |
| GA-6 | django-patterns, accessibility, e2e-testing | django-reviewer, security-reviewer, e2e-runner, a11y-architect |
| GA-7 | django-tdd | django-reviewer |
| GA-8 | django-celery, django-patterns | django-reviewer, silent-failure-hunter |
| GA-9 | django-patterns, database-migrations, error-handling | django-reviewer, database-reviewer, security-reviewer, silent-failure-hunter |

Для всех: `ruff check .` + `ruff format --check .` целиком, `test_template_comments`, `i18n_quickcheck`,
`test_package_gate`/`test_orphan_decorators` при новых вьюхах; зелёный CI → FF в main.
