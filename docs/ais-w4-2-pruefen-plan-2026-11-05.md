# AIS-W W4-2 — мастер v4: шаг «Angebot prüfen» без ИИ (2026-11-05)

План — агент ECC `planner` (2026-11-05). Источники: `ais-wizard-v4-structure-2026-11-05.md` §3
(шаг 2), §9 (пустой список + «Beispiele einfügen», **макет шага «Prüfen» на утверждение перед
кодом**); `ais-modules-directions-assistant-plan-2026-11-05.md` §5.3/§5.7 («Ich» у салона создаётся
сам, фото номеров обязательно для онлайн-брони, модули, выключенные владельцем, не трогаем);
`ais-ecc-plan-2026-11-05.md`, строка 5. Статус: **срез 0 ✅** — макет утверждён владельцем (артефакт «Angebot prüfen», 5 экранов), решения §10 — по рекомендации (2026-11-05). Срезы 1–4 сделаны (2026-11-05). Срез 4 по решению §10.3: витрина печатает `base_price` у товара «nur auf Anfrage» («0,00 €»), поэтому вид ввода «Anfragen» перенесён в W4-5; «Waren» в «Wie verkaufen Sie?» онлайн-продажу (`orders`) не включает — её открывает W4-5.

## 0. Что уже решено и что из этого следует

| Решение | Следствие |
|---|---|
| Пустой список + «Beispiele einfügen» | Образцы попадают в textarea, не в базу. Создаёт только «Übernehmen» |
| Макет «Prüfen» — до кода | Срез 0 = канвас (390 + 1440), код после «ок» |
| «Ich» у Termine создаётся сам | Ресурс-мастер при первом подтверждении услуг, если активного мастера нет |
| Фото номера обязательно для онлайн-брони | Номер без фото создаётся, `zimmer.room` честно «нет фото»; «📷» у каждого номера |
| Выключенное владельцем не трогаем | «Wie verkaufen Sie?» только включает, снятая галочка не выключает |
| ИИ — не здесь | Разбор строк — только правила |

## 1. Объём

Входит: новый v4-шаг `pruefen` вместо `offer` (v3 `offer` байт-в-байт); «Wie verkaufen Sie?»
(открыт у `other`/cafe/werkstatt/tour_operator, иначе «Sie verkaufen: … · ändern»); ввод строками
«Name — Preis» (+ длительность/гости/дата по направлению); «Beispiele einfügen» из статического
реестра; таблица «Prüfen» (на телефоне — карточки) с правкой и ошибками, **до «Übernehmen» в
базе ничего нет**; «Übernehmen» — по одной `.create()` в одной транзакции, идемпотентно, отчёт
«N angelegt · M übersprungen (Grund)»; авто-ресурс «Ich»; фото номера в шаге; «Schon angelegt».

Не входит: ИИ (W4-4), Google (W4-3), столы (`tisch` — ссылка «später»), аллергены, «Verkauf
öffnen» (W4-5), варианты/модификаторы/Grundpreis/категории.

**Миграций нет.** Черновик — сессия (≤ 50 строк, ≤ 8 КБ); маркеры идемпотентности и выбор
направлений — `site_config["onboarding"]`; модули — `modules.enable_module`.

## 2. Поток данных

- GET `?step=pruefen` → направления, kind'ы, черновик из сессии, «schon angelegt».
- `offer_directions` → `enable_module` отмеченных + `onboarding.directions` (позиции не создаются).
- `offer_examples` → черновик = образцы (база не трогается).
- `offer_preview` → `parse_lines` → черновик {batch_id, kind, text, rows} в сессию.
- `offer_confirm` → строки из POST заново через `validate_row`; под `select_for_update(Tenant)`:
  batch_id уже в `onboarding.offer_batches_done` → тот же отчёт; иначе atomic: создать валидные
  отмеченные + «Ich» + отметить batch_id (кольцо 10) → `readiness.invalidate` на commit.
- `offer_photo` → `stays.photos.add_unit_photos` → (saved, failed) с сообщением, не молча.
- `offer_discard` → удалить черновик. «Weiter» → `recht`, ничего не создаёт (`post=None`).

## 3. Разбор строки (`apps/core/offer_lines.py`, чистые функции)

`Line(idx, raw, name, price, price_from, duration_min, guests, starts_at, example, errors,
warnings)`; `parse_lines(text, kind)`; `validate_row(data, kind)` — одна точка истины.

- Нормализация: NBSP → пробел; `−–—` → разделитель; маркеры `• - * ·` и нумерация `1.`/`1)`
  срезаются; dot-leaders → разделитель; > 50 строк — обрезка с предупреждением; > 8000 символов —
  отказ.
- Разделители: ` — `, ` – `, ` - `, `:` (последний), таб, `;`, `|`; без разделителя — цена с хвоста;
  числа в имени остаются («Pizza 4 Käse — 9,50»).
- Цена — только через `money.parse_amount`: `3,50 €`/`€ 3,50`/`3.50 EUR` → 3.50; `12,-` → 12;
  `1.234,50` → 1234.50; `ab 9` → 9 + price_from; `9–12` → 9 + предупреждение; два ценника → первый
  + предупреждение; `/kg` → предупреждение «Grundpreis später»; `1,234` → ошибка; `-3`/> 1 млн →
  ошибка; `gratis` → 0 только у tickets/anfragen; пусто/`auf Anfrage` → ошибка кроме anfragen;
  `CHF` → предупреждение.
- Длительность (termine, обязательна): `30 Min`, `45'`, `1 Std`, `1,5 h`, `1:30 h`; общая регулярка
  с `setup_assistant._DURATION_RE`.
- Гости (zimmer): `2 Pers.`, `für 2`, `DZ`=2, `EZ`=1; нет → 2 + предупреждение.
- Дата (tickets, обязательна): `20.07.2026 19:00`, `20.07. 19 Uhr` (ближайший будущий год);
  прошедшая → ошибка; нет времени → 19:00 + предупреждение.
- Имя: ≤ 120 с предупреждением; пустое → ошибка; дубль в пачке → ошибка; существующее → `skipped`
  (решается в confirm под блокировкой).

## 4. Направление → сущность (только через `directions.active()`)

| Направление | Сущность | Поля | Создание |
|---|---|---|---|
| waren / speisekarte | `catalog.Product` | name, price | как `create_offer`; НДС — дефолт формы по типу (еда 7 %) |
| termine | `booking.Service` | name, duration, price | навыков нет → `service_pool` = все мастера |
| tisch | — | — | ссылка «Tische später» |
| zimmer | `stays.StayUnit` | name, guests, price | quantity=1 |
| tickets | `events.Event` | name, date, price | status=PUBLISHED (витрина скрыта W4-1) |
| anfragen | `Product(primary_action="request")` | name, (price) | по вопросу 3 |

Несколько направлений — радио «Was tragen Sie ein?». kind — только из
`setup_assistant.allowed_entities(tenant, user)`.

«Ich»: в той же транзакции, если нет активного `Resource(type=STAFF)` — создать (имя — вопрос 4);
расписание не создаём (E4.1b: часы бизнеса); нет часов — предупреждение со ссылкой на `company`.

Фото номера: `_add_unit_photos` выносится в `apps/stays/photos.py::add_unit_photos(unit, files) ->
(saved, failed)`; сейчас там `except Exception: continue` — **тихий провал**, станет
`logger.exception` + причина пользователю (и во вьюхе юнита).

«Wie verkaufen Sie?»: карточки `directions.REGISTRY`, только достижимые для типа; отметка по
умолчанию = active ∪ defaults_for; снятые не выключаем; модуль вне пакета — «nicht im Paket»;
после записи `is_active` ложно → сообщение с причиной.

## 5. Файлы

Новые: `apps/core/offer_lines.py`, `apps/core/offer_examples.py` (статический реестр образцов
тип × kind, замок «каждый разбирается»), `apps/core/offer_batch.py` (`confirm` → `Report(created,
skipped, failed)`), `apps/stays/photos.py`, `templates/tenant/setup/_step_pruefen.html`,
`_offer_review_table.html`. Правки: `setup_steps.py` (`_ctx_pruefen`, `HANDLERS["pruefen"]`,
`_parse_price_eur` → `money.parse_amount`), `views.py::setup_view` (6 action'ов), `onboarding.py`
(шаг `pruefen` с гейтом v4, `offer` → v3-only, ремап легаси-v4 `offer → pruefen`),
`stays/views.py`, 5 `.po` (~45 msgid; образцы не переводятся), `app.css`, доки.

## 6. Риски

1. `bulk_create` запрещён (обходит slug KAT-3, синк каталога T-8.11, `confirmed_at`) — `.create()`
   по одной, замки на slug и хук листинга.
2. Всё или ничего: сбой БД → откат пачки, `logger.exception`, черновик цел.
3. Отчёт сходится: `created + skipped + failed == отмеченных` (замок).
4. В `offer_batch` нет широких `except` вне одного обработчика с логом.
5. `readiness.invalidate` через `on_commit`.
6. Двойное нажатие/две вкладки — batch_id + кольцо под `select_for_update`; запись только ключа
   `onboarding`.
7. Новый batch_id с теми же именами → `skipped: gibt es schon`.
8. Протухший черновик → «Vorschau abgelaufen», ничего не создано.
9. Подделка POST (отрицательная цена, 10 000 строк, чужой kind) — отказ.
10. Цена 0 у товара — ошибка с подсказкой (иначе витрина «0,00 €»).
11. Образец без правки — бейдж «Beispiel — Preis prüfen», счёт в отчёте.
12. W0: все поля в DOM, без `required` на скрытых (урок X6-6); телефон — та же разметка CSS-ом.
13. Без JS работает целиком (PRG); JS — делегированием на `document`.

## 7. Тесты (до кода)

- `test_offer_lines.py`: таблица цен/разделителей/длительности/гостей/дат, лимиты, дубли,
  `validate_row == parse_lines`, скан-замок «нет float( и replace(',', '.')».
- `test_offer_examples.py`: ≥ 5 образцов на тип × kind, все разбираются; кнопка базу не трогает.
- `test_setup_pruefen.py`: рельса v4 `company → pruefen → recht → done`, v3 `offer` прежний,
  ремап легаси; preview ничего не создаёт; confirm N, двойной confirm N (не 2N), протухший 0,
  существующее → skipped, подделка → отказ, сбой БД на 3-й строке → 0 + лог; slug, хук листинга,
  НДС 7 %; `termine.service` готово после commit; «Ich» один раз, `service_pool` не пуст; номер без
  фото → `zimmer.room` False, фото → True, битый файл → видимая ошибка; направления (открыт/свёрнут,
  включает, не выключает, вне пакета, `onboarding.directions` переживает `normalize`); права
  сотрудника; W0; паритет `_parse_price_eur`.

## 8. Срезы

| Срез | Что |
|---|---|
| 0 | Макет «Prüfen» на утверждение (390/1440; пусто / примеры / ошибки / отчёт / фото) |
| 1 | `offer_lines` + `offer_examples` + тесты |
| 2 | шаг `pruefen`, ввод, примеры, preview, confirm; waren/speisekarte/termine(+Ich)/tickets |
| 3 | Zimmer + `stays/photos.py` (починка тихого провала) |
| 4 | «Wie verkaufen Sie?» + anfragen |
| 5 | стенд 5 персон × телефон, a11y, ревью, доки |

`SETUP_WIZARD_V4` выключен до W4-6 — срезы мержатся по отдельности.

## 9. ECC-прогоны

Скиллы до кода: `django-patterns`, `django-tdd`, `python-testing`, `accessibility`, `e2e-testing`,
`error-handling`; к срезу 3 — `django-security`. Перед кодом — `docs/pitfalls.md` (формы/W0, i18n,
шаблоны, тихие except).

| Агент | Когда | Фокус |
|---|---|---|
| planner | ✅ этот план | — |
| silent-failure-hunter | после срезов 2 и 3 | атомарность confirm, отчёт, фото, enable_module, invalidate |
| django-reviewer | каждый срез | блокировки, PRG, права, `.create()`, сессия |
| security-reviewer | срезы 2 и 3 | массовый POST, загрузка файлов, лимиты |
| a11y-architect | срезы 2 и 5 | textarea с форматом, таблица caption/scope, ошибка у поля, live-region отчёта, фокус после PRG, цели ≥ 44 px |
| e2e-runner | срез 5 | 5 персон × 390: Bäckerei, Friseur («Ich» → слот), Pension (фото), Events (дата), Other (направления) |
| database-reviewer | если confirm > 200 мс на 50 строках | запросы на строку |

## 10. Решения владельца (2026-11-05: «делай по рекомендации» — все пункты ниже приняты)

1. Отдельный шаг `pruefen` (v3 не трогаем) — **да**.
2. «ab»-цена у услуги: сохранить обычной ценой с предупреждением — **да** (альтернатива — вариант).
3. Anfragen как `Product(primary_action="request")` без цены — **да, если витрина не печатает
   «0,00 €»**, иначе отложить до W4-5.
4. Имя «Ich» на витрине — **имя владельца, иначе название бизнеса**.
5. Фото номера — **после создания** (не теряется при ошибке соседней строки).
6. Лимит 50 строк за раз — **да**, больше — CSV-импорт.
7. Снятая галочка направления модуль не выключает — **да**.
8. Галочка у строки-образца стоит по умолчанию (с бейджем) — **да**.
9. CHF — сохранять в € с предупреждением — **да**.
10. Столы вне W4-2 — **да**, «Wie viele Tische?» — кандидат в W4-5.
