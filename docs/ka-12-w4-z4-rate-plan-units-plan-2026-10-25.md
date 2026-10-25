# KA-12 · Zimmer Z-4 (E4.6c): тарифы по категориям и пересечения сезонов. План от 2026-10-25

План составлен агентом `planner` по `main`. Родительский план — `ka-12-w4-zimmer-plan-2026-10-25.md` (§1 строки 13/21/25/49/63/64/78, §4.2–4.4, §8 О-3).
Нумерация миграций сдвинулась относительно таблицы §3 родителя: `0041` = night_prices, `0042` = NightRate. Поэтому Z-4 получает **одну аддитивную миграцию `stays/0043`** (M2M), а `0044` остаётся за Z-5.

## 0. Что проверено в коде

**`RatePlan`** — `apps/stays/models.py:169–234`.
- Модель привязана ко всему тенанту, поля категорий нет.
- `Meta.ordering = ["sort_order", "name"]`.
- У `StayUnit` нет атрибута `rate_plans`, поэтому reverse-имя свободно.

**`SeasonRate`** — `models.py:237–256`.
- Docstring говорит: «гард — на стороне кабинета», но гарда нет.
- Единственный писатель в кабинете — `views.units()`, action `"rate"` (`views.py:897–913`). Правки сезона нет, есть только `rate` и `rate_delete`.
- Второй писатель — сидер `demo_kits.py:25787`.

**Колл-сайты, которые берут активные тарифы:**

| Где | Строка | Что там происходит |
|---|---|---|
| `public_views.unterkunft_index` | 208 | Через `_unit_from_price_cents` (114–140) берётся «ab»-цена как минимум по **всем** тарифам. |
| `public_views.unterkunft_unit` | 343 | Карточки `rate_options` (382–408), дельта к первому тарифу, `any_prepay` → `deposit_required` (413–414). |
| `public_views.unterkunft_book` | 686–690 | **fail-open:** неизвестный или чужой pk молча заменяется первым активным тарифом. |
| `views.stay_create` | 657–661 | **fail-open**, тот же код. Опции «без тарифа» нет, по умолчанию первый (строка 64 родителя ещё не сделана). |
| `views.stay_new` | 73 | Контекст walk-in формы. |
| `views.calendar` | 314 | Контекст walk-in формы. |
| `views.units` | 1229 | Список тарифов в кабинете, `RatePlan.objects.all()`. |
| `aggregator/hotel_search.py` | 42–55 | Минимум по всем тарифам. |
| `demo_kits.py` | 26773, 26856 | Демо-брони берут тарифы по кругу. |

**Тарифы НЕ используют:**
- фид G8 `stays_feed` (`public_views.py:1045`) — отдаёт базовую цену ночи без тарифа;
- `core/deal_discount.py:147` и `services.move_stay` — читают тариф уже существующей брони (`_rate_for_booking`: живой тариф или снимок);
- `events/services`, каталог города (`_stay_snapshot` → `unit.price_cents`).

**`services.book_stay`** (308–445) принимает `rate_plan` как объект и не проверяет его. Вызывают его: витрина, стойка, импорты iCal/OTA (`services.py:647/678`, без тарифа), демо-сидер.

**`move_stay`** вызывается только из кабинета (`views.py:398` — drag/Move, `views.py:496` — форма «Buchung bearbeiten»). Самостоятельного переноса номера гостем нет.

**Шаблоны:**
- `templates/stays/units.html:401–460` — список и форма создания тарифа, подпись «Apply to all rooms».
- `templates/stays/_walkin_form.html:36–43` — `<select name="rate_plan">` без пустой опции.
- `templates/storefront/_buybox_stay_form.html:13–23` — радио `rate_plan`, первое отмечено.

**Права.** Весь `views.units()` открыт любому с `@login_required`. Цены правят owner/admin через `roles.can_edit_policy` — так сделано в Z-3, `price_calendar_views.py:41`.

**Удаление категорий.** В кабинете удаления `StayUnit` нет. Удалить можно только через ORM/админку или пересев демо. Риск разобран в Р-6.

## 1. Требования
1. `RatePlan.units` — M2M к `StayUnit`, `blank=True`. **Пустой набор = тариф для всех категорий**: существующие тарифы ведут себя так же, как сейчас.
2. Применимость тарифа к категории определяется в одной точке. Листинги не дают N+1.
3. Fail-closed:
   - на витрине и на стойке непустой `rate_plan`, который не применим к юниту, неактивен, несуществует или мусорный, даёт отказ без брони;
   - `book_stay` перепроверяет тариф под локом юнита.
4. В кабинете у тарифа есть чекбоксы категорий при создании и отдельная правка категорий у существующего тарифа. Сентинел `rateplan_units_present` (W0). В списке подпись «für alle Kategorien» или «nur: …».
5. Новый сезон, который пересекается с сезоном той же категории, получает отказ. В сообщении — название и даты конфликтующего сезона. Уже существующие пересечения помечаются в списке.
6. Стойка: тариф выбирается явно, первая опция — «— ohne Tarif —». Решение — включить в Z-4, обоснование в Р-4.

## 2. Решения по развилкам

**Р-1. Хелпер применимости — новый модуль `apps/stays/rate_plans.py`.** Только чтение и выбор, без побочных эффектов:
- `active_plans()` → `list(RatePlan.objects.filter(is_active=True).prefetch_related("units"))`, ровно 2 запроса.
- `plans_for(unit, plans)` → фильтр в памяти по prefetch-кэшу, 0 запросов, порядок `sort_order, name` сохраняется. Через него идут листинги (`unterkunft_index`, `hotel_search`, демо-сидер).
- `class RatePlanInvalid(Exception)`.
- `resolve_choice(unit, raw_pk, *, plans, empty="first"|"none")` возвращает `RatePlan | None`. Правила:
  - пустое значение и `empty="first"` (витрина) → первый применимый тариф или `None`. Это паритет с радио, где первое отмечено.
  - пустое значение и `empty="none"` (стойка) → `None`.
  - непустое значение, которое не является целым числом или не найдено среди `plans_for(unit, plans)` → `RatePlanInvalid`.
- На модели:
  - `RatePlan.applies_to(unit)` → `not ids or unit.pk in ids`, где `ids` = `{u.pk for u in self.units.all()}` (использует prefetch-кэш);
  - `RatePlanQuerySet.for_unit(unit)` → `filter(~Exists(through(rateplan=OuterRef pk)) | Exists(through(rateplan=OuterRef pk, stayunit=unit)))`. Через `Exists`, а не JOIN по `units__isnull`: без дублей и без `distinct()`, `ordering` сохраняется.
  - `objects = RatePlanQuerySet.as_manager()`.

**Р-2. Проверка в `book_stay`.** Внутри `atomic`, сразу после `select_for_update` юнита (до MinStay, цены и `claim_units` акции): если `rate_plan is not None` и `not RatePlan.objects.for_unit(unit).filter(pk=rate_plan.pk, is_active=True).exists()` → `raise RatePlanInvalid`.
- Одна строка запроса.
- Закрывает гонку «деактивировали или сузили тариф между формой и POST».
- Закрывает будущих вызывающих, которые передадут объект мимо `resolve_choice`.
- Исключение реэкспортируется как `services.RatePlanInvalid`.

**Р-3. `move_stay` в категорию, к которой тариф не применим: перенос разрешён, бронь сохраняет согласованный тариф.** Сервис меняется только докстрингом.
- Как это принято в PMS: смена номера или апгрейд у стойки не меняют договорённость с гостем — питание, отмену и предоплату.
- Почему не другие варианты:
  - отказ сломал бы drag на Belegungsplan (409) и форму правки ради ограничения, которое задумано для онлайн-продажи;
  - сброс тарифа молча поменял бы условия отмены и питание — это деньги и закон.
- Цена при `reprice=True` считается по `_rate_for_booking` (живой тариф или снимок) — те же модификаторы, паритет цел.
- Во вьюхах (`views.py:398` и `:496`) после успешного переноса, если тариф живой и `not booking.rate_plan.applies_to(booking.unit)`, выводится `messages.warning`: «Der Tarif „%(rate)s“ gilt nicht für „%(unit)s“ — die Buchung behält den vereinбarten Tarif.»
  - Для fetch-drag (204): предупреждение через `messages` появится при следующей загрузке. Отдельного канала не делаем.

**Р-4. «— ohne Tarif —» на стойке — включаем в Z-4.**
- Причина: строки 657–661 `stay_create` переписываются всё равно, а fail-open пустого значения и есть дефект строки 64 родителя.
- Что меняется: опция `value=""` первая и выбрана по умолчанию. Пустое значение → `None` (база). Непустое неприменимое → отказ с сообщением и редиректом на `back`.
- Опции несут `data-units="pk,pk"` (пусто = все) и подпись `· nur: Suite`.
- Делегированный JS на `document` (урок Ф1) скрывает или отключает неприменимые опции при смене `#walkin-unit` и сбрасывает выбор на «ohne Tarif», если текущая опция стала неприменимой.
- Без JS форма тоже работает: решает сервер.
- Тумблер авто-скидок на стойке, способ оплаты и блок через `create_block` остаются в Z-5.

**Р-5. Пересечение сезонов — сервисная функция, а не constraint БД.** `services.add_season_rate(unit, *, label, start_date, end_date, price_cents)`:
- выполняется в `atomic`, `StayUnit.select_for_update()` по pk (две параллельные вставки не проскочат);
- конфликт ищется так: `SeasonRate.objects.filter(unit=unit, start_date__lte=end_date, end_date__gte=start_date).order_by("start_date").first()` — границы включительно, сезоны `[1–10]` и `[10–20]` пересекаются;
- при конфликте → `raise SeasonOverlap(conflict)`.
- Отказ от `ExclusionConstraint`: нужен `btree_gist`, а на проде могут быть **уже пересекающиеся** сезоны — миграция упала бы на данных.
- Существующие пересечения не чиним. В списке сезонов категории (`units.html:263`) у таких строк бейдж «⚠ Überschneidung» — считается в Python по уже загруженным `season_rates`, без запросов. Цена при пересечении по-прежнему «первое по `start_date`», это видно в бейдже-подсказке.
- Сидер `demo_kits.py:25787` гард не использует (он пишет напрямую), но замок проверяет, что ни один кит не создаёт пересечений.

**Р-6. Удаление категории не должно молча расширить тариф до «всех».**
- Проблема: при удалении `StayUnit` (ORM, админка, пересев) cascade чистит строки through. Если удалялась последняя категория тарифа, набор станет пустым — то есть «для всех».
- Решение: `pre_delete` на `StayUnit` (`apps/stays/signals.py` или существующий модуль сигналов). Тарифы, у которых все `units` ⊆ удаляемых, получают `is_active=False`.
- Тест обязателен.
- Деактивация категории (toggle) тариф не трогает: тариф без активных категорий просто нигде не виден.

**Р-7. Права на тарифы и сезоны: owner/admin, как цены в Z-3 (О-4).**
- Действия `rate`, `rate_delete`, `rateplan`, `rateplan_units`, `rateplan_toggle`, `rateplan_delete` в `views.units()` проверяют `_can_edit(request.user)` (обёртка над `roles.can_edit_policy`, как в `price_calendar_views.py:41`). Иначе — `messages.error` и редирект, а в шаблоне формы скрыты для staff.
- Остальные действия диспетчера не трогаем.
- Если владелец против — убрать этот пункт (одна проверка), остальной Z-4 от него не зависит.

**Р-8. Сообщение гостю на витрине** — честный отказ без технических деталей: «Dieser Tarif ist für dieses Zimmer nicht verfügbar. Bitte wählen Sie erneut.» Редирект на `back` с датами; никакого тихого фолбэка на другой тариф и другую цену.

## 3. Точки изменения

| # | Файл | Что |
|---|---|---|
| 1 | `apps/stays/models.py:169` | `units = models.ManyToManyField(StayUnit, blank=True, related_name="rate_plans")`, `RatePlanQuerySet.for_unit`, `applies_to()`, `units_label` (для подписи, через prefetch); docstring «на тенанта» → «пусто = alle Kategorien»; docstring `SeasonRate` — «гард в `services.add_season_rate`». |
| 2 | `apps/stays/migrations/0043_rateplan_units.py` | Один `AddField` (M2M, через auto-through). Без data-шага: пустой набор = прежнее поведение. |
| 3 | `apps/stays/rate_plans.py` (новый) | `active_plans`, `plans_for`, `resolve_choice`, `RatePlanInvalid`. |
| 4 | `apps/stays/services.py` | `book_stay`: проверка Р-2 после лока (~строка 361), реэкспорт `RatePlanInvalid`; `add_season_rate` + `SeasonOverlap`; docstring `move_stay` про Р-3. |
| 5 | `apps/stays/public_views.py:208–213` | `plans = rate_plans.active_plans()` один раз; `_unit_from_price_cents(unit, von, bis, rate_plans.plans_for(unit, plans))`. |
| 6 | `public_views.py:343, 382–414` | `rate_plans = rate_plans_mod.plans_for(unit, active_plans())`. Применимые тарифы используются и в `rate_options`, и в `any_prepay` (иначе предоплата чужой категории включила бы оплату). |
| 7 | `public_views.py:686–690` | `resolve_choice(unit, POST["rate_plan"], plans=active_plans(), empty="first")`; `except RatePlanInvalid` → `messages.error` (Р-8) + `redirect(back)`; в блок `except` вокруг `book_stay` добавить `services.RatePlanInvalid` (гонка) с тем же текстом. |
| 8 | `apps/stays/views.py:657–661` | `resolve_choice(..., empty="none")`; ошибки RatePlanInvalid (до и из `book_stay`) → «Dieser Tarif gilt nicht für die gewählte Kategorie.» + `redirect(back or "stays:calendar")`. |
| 9 | `views.py:73, 314` | Контекст `rate_plans = rate_plans_mod.active_plans()` (prefetch для `data-units`). |
| 10 | `views.py:398, 496` | Предупреждение Р-3 после `move_stay`. |
| 11 | `views.py:897–915` | `rate` → `services.add_season_rate`, `except SeasonOverlap` → сообщение с label и датами (`date_format(..., "SHORT_DATE_FORMAT")`); `rate`/`rate_delete` под `_can_edit` (Р-7). |
| 12 | `views.py:1001–1025` | `rateplan`: после `create` — `units.set(_parse_unit_pks(POST.getlist("units")))` (только существующие pk `StayUnit`, мусор отбрасывается). Новый action `rateplan_units`: `get_object_or_404(RatePlan, pk=…)`; при `rateplan_units_present` — `set()` (пусто = alle), без сентинела — ничего. Все `rateplan*` под `_can_edit`. |
| 13 | `views.py:1229` | `RatePlan.objects.prefetch_related("units")` (подпись без N+1); в контекст `can_edit_prices`; пометки пересечений сезонов (можно фильтром или в цикле `units`). |
| 14 | `templates/stays/units.html:401–460` | Подпись «für alle Kategorien / nur: …»; чекбоксы категорий в форме создания; в строке тарифа `<details>` «Kategorien» с формой `rateplan_units` + hidden `rateplan_units_present`; help-текст без «Apply to all rooms»; формы скрыты, если `not can_edit_prices`. Сезоны (263–280): бейдж пересечения. |
| 15 | `templates/stays/_walkin_form.html:36–43` | Опция «— ohne Tarif —» первой и выбранной; `data-units`; подпись «· nur: …»; делегированный JS (Р-4) рядом с формой, не внутри своп-зоны. |
| 16 | `templates/storefront/_buybox_stay_form.html` | Разметка не меняется (получает уже отфильтрованные `rate_options`); паритет-замки `test_buybox_parity` должны остаться зелёными. |
| 17 | `apps/aggregator/hotel_search.py:42–55` | `plans = active_plans()` внутри `schema_context`; `plans_for(unit, plans)` по юниту; пустой список → цена без тарифа (как сейчас). |
| 18 | `apps/tenants/demo_kits.py:26773, 26856` | `applicable = plans_for(unit, rate_plans)`; `rate_plan = applicable[idx % len(applicable)] if applicable else None`. Вывод сидера идентичен (у демо M2M пуст) → `SEEDER_VERSION` НЕ поднимаем (отпечатки и данные те же). Поддержка ключа `units` в спеке `rate_plans` — в Z-7 вместе с демо. |
| 19 | `apps/stays/signals.py` (или существующий модуль сигналов) | `pre_delete StayUnit` → деактивация осиротевших тарифов (Р-6). |

## 4. Тесты-замки — до кода

Файлы: `apps/stays/tests/test_z4_rate_plan_units.py` и `apps/stays/tests/test_z4_season_overlap.py`.

**Модель и хелпер**
1. Тариф без категорий применим к любой категории (`applies_to`, `for_unit`). Это замок обратной совместимости.
2. Тариф с `units=[A]` применим к A и не применим к B.
3. `for_unit` без дублей при двух назначенных категориях; порядок `sort_order, name` сохранён.
4. `active_plans()` — ровно 2 запроса; `plans_for` для N юнитов — 0 запросов (`django_assert_num_queries`).
5. `resolve_choice`:
   - `empty="first"` → первый применимый;
   - `empty="none"` → `None`;
   - pk тарифа чужой категории → `RatePlanInvalid`;
   - pk неактивного тарифа → `RatePlanInvalid`;
   - `"abc"`, `"999999"`, `"1 OR 1"` → `RatePlanInvalid`;
   - нет применимых тарифов и пустое значение → `None`.

**Сервис**
6. `book_stay` с тарифом другой категории → `RatePlanInvalid`. Броней нет, лимит акции не списан (акция на номер в тесте), `Customer` не создан.
7. `book_stay` с тарифом, деактивированным после чтения формы (объект в памяти активен, в БД — нет) → `RatePlanInvalid`.
8. `book_stay` с тарифом «für alle» → прежний итог байт-в-байт (сверка с `test_rate_plans.py:68`).
9. `move_stay` в категорию, к которой тариф не применим → успех; `rate_plan_id` и `rate_snapshot` неизменны. При `reprice=True` итог = `quote_total_cents(dest, …, rate_plan=тот же) × rooms − авто-скидка …`, паритет с `test_rate_plans.py:97`.
10. `pre_delete`: удаление последней категории тарифа → `is_active=False`; удаление одной из двух категорий → тариф активен и сужен.

**Витрина**
11. `unterkunft_unit`:
    - радио `rate_plan` содержит только применимые тарифы, pk тарифа чужой категории отсутствует в теле;
    - дельта считается к первому применимому;
    - предоплата 100 % только у тарифа чужой категории → `deposit_required` = False.
12. `unterkunft_index`: «ab»-цена не использует более дешёвый тариф чужой категории.
13. POST брони с pk тарифа чужой категории → 302 на `back`, сообщение Р-8, `StayBooking.count()` не изменился. Это замок fail-closed.
14. POST с pk неактивного тарифа и с мусорным pk → то же, без 500. Раньше молча брался первый тариф — это осознанная переписка поведения.
15. POST без `rate_plan` при наличии применимых тарифов → первый применимый (замок паритета с радио).

**Стойка**
16. `stay_create`:
    - без `rate_plan` → `rate_plan_id is None`, итог по базе (новое поведение «ohne Tarif»);
    - pk тарифа чужой категории → сообщение, броней нет;
    - `test_front_desk.py:64` (явный pk) остаётся зелёным.
17. Рендер walk-in формы (`stay_new` и календарь): первая опция `value=""` «— ohne Tarif —» `selected`; у тарифа с категориями есть `data-units`; `test_front_desk.py:135` зелёный.

**Кабинет**
18. `rateplan` с `units=[A]` → M2M = {A}; без чекбоксов → пусто («alle»); несуществующий pk в `units` → отброшен, без 500.
19. `rateplan_units`:
    - с сентинелом и без чекбоксов → набор очищен;
    - **без сентинела → набор не тронут (W0)**;
    - с сентинелом и `[B]` → {B}.
20. Роли:
    - staff POST `rateplan`, `rateplan_units`, `rate` → данных не меняет, сообщение;
    - owner и admin — меняют;
    - формы скрыты у staff.
21. Подпись в списке: «für alle Kategorien» / «nur: Suite» — без N+1 (`django_assert_max_num_queries` при 5 тарифах).
22. Предупреждение Р-3 появляется после `action=update` со сменой категории.

**Сезоны**
23. Новый сезон `[10–20]` при существующем `[1–10]` → отказ; в сообщении есть label и даты. Касание `[11–20]` → проходит. Вложенный и охватывающий сезоны → отказ.
24. Сезон другой категории на те же даты → проходит.
25. Без label → сообщение с датами без пустых кавычек.
26. `end < start` → прежнее «Invalid dates.».
27. Существующее пересечение (создано ORM) → бейдж «Überschneidung» в списке, цена не изменилась (первое по `start_date`).
28. Замок по всем демо-китам: ни один `kit` не создаёт пересекающихся сезонов в одной категории (проверка на спеке, без засева).

**Grep/AST-замок класса**
29. Литерал `RatePlan.objects.filter(is_active=True)` запрещён в `apps/` вне `apps/stays/rate_plans.py` и тестов — новые колл-сайты обязаны идти через хелпер.

**Регресс**
30. `test_buybox_parity`, `test_golden_zimmer`, `test_z1_night_snapshot`, `test_z2_night_rates`, `test_rate_plans`, `test_prepayment`, `test_stay_flow_b`, `test_front_desk`, `test_demo_kits` (hotel: 4 активных тарифа), `aggregator` hotel_search — зелёные без правок, кроме осознанных пп. 14 и 16.

**Playwright-стенд** (демо hotel, 1440 и 390 px; тарифу «Halbpension» в стенде назначается одна категория):
- витрина двух категорий: тариф виден только у своей;
- подделанный POST → сообщение;
- walk-in: смена категории прячет тариф, выбор сбрасывается на «ohne Tarif»;
- кабинет: правка категорий тарифа;
- сезон с пересечением → сообщение.

## 5. i18n

Базовые msgid — немецкие, перевод во все 5 `.po`. Проверка: `scripts/i18n_quickcheck.py`, CI-гейт `i18n_gap`.
- «— ohne Tarif —»
- «für alle Kategorien»
- «nur: %(names)s»
- «Kategorien»
- «Kategorien speichern»
- «Ohne Auswahl gilt der Tarif für alle Kategorien.»
- Новый help-текст списка тарифов вместо «… Apply to all rooms.»: «Verschiedene Arten, dieselben Zimmer zu verkaufen — Basis, nicht erstattbar, mit Frühstück, Halbpension … Gäste wählen beim Buchen.» Старый msgid остаётся в `.po` до чистки — не удалять вручную.
- «Dieser Tarif ist für dieses Zimmer nicht verfügbar. Bitte wählen Sie erneut.»
- «Dieser Tarif gilt nicht für die gewählte Kategorie.»
- «Der Tarif „%(rate)s“ gilt nicht für „%(unit)s“ — die Buchung behält den vereinbarten Tarif.»
- «Überschneidet sich mit der Saison „%(label)s“ (%(start)s – %(end)s).»
- «Überschneidet sich mit einer Saison (%(start)s – %(end)s).»
- «Überschneidung»
- «Bei Überschneidung gilt die früher beginnende Saison.» (подсказка бейджа)
- «Preise und Tarife ändern nur Inhaber und Admins.» (сверить: возможно, такой msgid уже есть с Z-3 — тогда переиспользовать)

Правило проекта (I18N-11/13): никаких `gettext` внутри f-строк, псевдонимы только `_`/`gettext_lazy`.

## 6. Инкременты — один батч, коммиты по шагам
- **Z-4a** — модель, `0043`, `rate_plans.py`, `book_stay` (Р-2), сигнал (Р-6) + тесты 1–10 и 29.
- **Z-4b** — витрина (пп. 5–7 таблицы §3), `hotel_search`, демо-сидер + тесты 11–15.
- **Z-4c** — стойка (Р-4), JS walk-in, предупреждение move (Р-3) + тесты 16–17 и 22.
- **Z-4d** — кабинет тарифов (чекбоксы, `rateplan_units`, права Р-7) + тесты 18–21.
- **Z-4e** — сезоны (Р-5) + тесты 23–28.
- **Z-4f** — i18n ×5, `npm run build:css` (новые классы бейджей и подписей), стенд, ревью, доки (`build-log`, `task-catalog`, §3 `CLAUDE.md`, очередь миграций `stays/0043`).

## 7. Риски
- **Дефолт «пусто = все».** Удаление последней категории расширило бы тариф — закрыто Р-6. Снятие всех чекбоксов в правке — осознанное «alle», подписано в форме.
- **Поведение витрины меняется** (мусорный pk → отказ вместо первого тарифа). Легитимные формы шлют только применимые pk, поэтому затрагивает только подделку или устаревшую вкладку. Устаревшая вкладка после сужения тарифа получит честное сообщение, а не другую цену.
- **Стойка** по умолчанию «ohne Tarif», а не первый тариф. Сотрудники, привыкшие к молчаливому первому, увидят базовую цену. Это осознанное решение (строка 64 родителя); упомянуть владельцу в чекпоинте.
- **Паритет цены.** Листинг, деталь, `hotel_search` и бронь используют один `plans_for`. Замок 29 запрещает обход.
- **Найдено вне объёма:** `hotel_search` зовёт `auto_discount(cents, nights, von)` без `unit=`/`departure=`/`extra=`, поэтому портал может показать цену без Lücken-Deal и акции на номер (расхождение с витриной). В Z-4 не чиним, в roadmap §Отложено.
- **Миграция M2M** создаёт through-таблицу. Шаблонная схема T-10 должна пересобраться (`ensure_template_schema` на шаге 6a деплоя видит новую миграцию); сверить, что имя UNIQUE through-таблицы сохраняется при копировании (грабля T-10 `…_uniq` → `…_key` уже закрыта функцией восстановления, но тест копии гнать).
- **Гонка сезонов** закрыта локом юнита. Существующие пересечения на проде не чиним данными, только бейджем.
- **Права (Р-7)** сужают доступ staff к тарифам и сезонам — согласовано с О-4; если владелец против — один пункт.
- **Кэши:** `hotel_search` 300 с, витрина 120 с — новое сужение тарифа видно с задержкой до 5 минут; допустимо, как в Z-3.

## 8. ECC-прогоны

| Шаг | Скиллы до кода | Агенты / проверки |
|---|---|---|
| Сразу после плана | `database-migrations`, `django-security`, `django-patterns` | `database-reviewer` — ревью плана: M2M через auto-through, `Exists` вместо JOIN в `for_unit`, нужен ли индекс through по `stayunit_id` (FK-индексы Django создаёт), лок юнита в `add_season_rate`. `security-reviewer` — ревью Р-2/Р-7/Р-8 до кода. |
| Z-4a | `django-tdd`, `database-migrations` | Тесты 1–10 и 29 красные до кода; `--create-db` после `0043`; `database-reviewer` — миграция и бюджет запросов `active_plans`. |
| Z-4b/Z-4c | `django-security`, `e2e-testing` | `security-reviewer`: чужой, неактивный и мусорный `rate_plan` на витрине и стойке, гонка «тариф деактивирован между формой и POST», отсутствие тихого фолбэка, утечка тарифов чужой категории в разметку. `silent-failure-hunter`: деньги — ветки `except` вокруг `book_stay`, отсутствие проглоченного `RatePlanInvalid`, паритет «показано = списано». |
| Z-4d | `django-security`, `accessibility` | `security-reviewer`: роли и подделка `units[]`; `a11y-architect`: чекбоксы в `<fieldset><legend>`, `<details>` правки, подписи опций select. |
| Z-4e | `django-tdd` | `django-reviewer`: сервис сезонов, сообщения, бейдж без запросов. |
| Перед мержем | — | `django-reviewer` по всей ветке (обязательно); Playwright-стенд §4 (1440/390, JS walk-in); `ruff check .` + `ruff format --check .` целиком; pytest `apps/stays apps/aggregator apps/tenants` (`--create-db`); `scripts/i18n_quickcheck.py`; `apps/core/tests/test_template_comments.py`; `npm run build:css` + коммит `static/css/app.css`; `scripts/i18n_untranslated.py` (базовая линия); зелёный CI → FF в `main`. |

**ops после деплоя:** `./scripts/deploy.sh single` (`stays/0043`). Пересев демо не нужен: данные кита не меняются, `SEEDER_VERSION` не поднимается.
