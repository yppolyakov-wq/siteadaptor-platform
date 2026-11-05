# AIS-M M-1 — экран «Richtungen & Funktionen» + пресеты + `modules_report` (план, 2026-11-05)

Источники: `docs/ais-modules-directions-assistant-plan-2026-11-05.md` (Ч.1 §1.2–1.4; при расхождении действуют §5.1 п.1–3/10, §5.3 и §5.7), `docs/ais-ecc-plan-2026-11-05.md` строка 7, `CLAUDE.md` §5, `docs/pitfalls.md`, `docs/cabinet-screen-dod.md`. Кода нет. Тесты не запускались.

## §0. Коротко

- **Экран.** Адрес `/dashboard/modules/` и url-name `"modules"` остаются прежними: на них ссылаются помощник A-0 (`diagnoses.py:154,156`), главная (`dashboard.py:125`), права (`view_perms.py:419`) и настройки (`settings_home.py:29`). Внутри экрана вместо одной большой формы с 22 тумблерами будут четыре блока:
  1. карточки направлений;
  2. дополнения (только для активных направлений);
  3. «Weitere Richtung hinzufügen»;
  4. «Von Ihnen ausgeschaltet» — базовые модули, которые владелец когда-то выключил.
- **Запись.** Каждая карточка и каждый тумблер — отдельная маленькая POST-форма. Пишет один писатель с точечной записью под блокировкой строки тенанта. Большой Save со всем списком исчезает, а вместе с ним уходит класс дефектов W0/W6 (сохранение роняет ключи или чужой выбор).
- **Миграций нет.**
  - Слой модуля — новые поля `ModuleSpec`.
  - Режим Waren «zeigen/verkaufen» не хранится, а выводится из модуля `orders`.
  - Ключ `site_config["directions"]` в normalize резервируется сразу, чтобы его не уронил Save. Писать в него начнёт W4-5, там появится первый потребитель (обоснование — §2.2).
- **Пресеты новых бизнесов** — по §5.3.
- **Живые тенанты** — команда `modules_report`: сначала отчёт, затем `--apply`. Она только включает модули, причём только тенантам, чей `disabled_modules` в точности совпадает с одним из исторических пресетов (решение §5.7). Выключенное владельцем не трогает, ничего не выключает.
- **Aktionen у hotel / handwerker / werkstatt / tour_operator** (решение §5.7 п.1). Модуль включается пресетом, а пункт меню скрыт до первой акции. На экране вместо пункта — карточка «Lücken-Deal & Frühbucher» (у ремесла — своя подпись). Это часть M-1: без неё смена пресета сразу показала бы пустой пункт меню.

## §1. Что уже есть в коде

| Где | Что | Значение для M-1 |
|---|---|---|
| `apps/core/directions.py:117-174` | `REGISTRY` из 7 направлений: waren, speisekarte, termine, tisch, zimmer, tickets, anfragen. Поля `modules`, `active_when` | Основа карточек. `waren` активно по типу ∪ `orders` ∪ «есть товары» (`:69`), `speisekarte` — по типу (`:73`). Через модули их выключить нельзя |
| `directions.py:179-196` | `DEFAULT_FOR` по типу; `tour_operator` = tickets+anfragen, `werkstatt` = termine+anfragen+waren | Эталон, с которым сверяются пресеты модулей |
| `directions.py:93-103` | `_anfragen`: в лёгком пакете `jobs` не считается направлением | Писатель не должен выключать `jobs` у лёгкого пакета (заявки по акции, T-8.2) |
| `apps/core/modules.py:37-66` | `ModuleSpec` с полями `core`, `premium`, `recommended_for`, `suited_for`, `depends_on`; полей `layer`/`addon_for` нет | Добавить их |
| `modules.py:119-135` | `promotions` у hotel / tour_operator / handwerker / werkstatt есть только в suited — пресет его выключает | Исправить (§5.3) |
| `modules.py:236` | `booking` в `recommended_for` у tour_operator | Убрать (§1.1, §5.3) |
| `modules.py:348` | `jobs` рекомендован handwerker / werkstatt / catering. `tour_operator` нет, хотя в `DEFAULT_FOR` у него anfragen | Добавить `tour_operator` |
| `modules.py:461-477` | `customer_account` рекомендован hotel | Убрать hotel (§5.3) |
| `modules.py:538-576` | `is_module_active` и `inactive_reason` с паритет-замком | Без изменений; писатель использует ту же цепочку |
| `modules.py:579-598` | `enable_module`: под блокировкой, `auto_create_schema=False`, умеет только включать | Обобщить до `set_module(on/off)` |
| `modules.py:810-816` | `default_disabled_for` = все не-core модули минус `recommended_for` | Пресет остаётся производным от `recommended_for` |
| `apps/core/views.py:4311-4395` | `modules_view`: одна форма, POST переписывает весь список (`:4329-4338`), блокировки нет, есть «locked by package» guard | Переписать |
| `templates/tenant/modules.html` + `_module_row.html` | Три секции AB2 | Заменить |
| `apps/core/offer_batch.py:91-142` | `direction_choices` и `choose_directions` (мастер W4-2). Запись `site_config["onboarding"]["directions"]` под блокировкой, но **без `auto_create_schema=False`** (`:129-135`, грабля `pitfalls.md:339`) | Перенести `direction_choices` в `directions.py`; `choose_directions` переводится на общий писатель |
| `apps/core/nav_registry.py:1143-1169` | `direction_active`: гейты gastro / reservations / waren, мемо на тенанте | Добавить гейт `"aktionen"` по образцу `"reservations"` |
| `nav_registry.py:344-352` | Запись `promotions:promotion-list` (marketing, group «aktionen») | Сюда ставится `direction="aktionen"` |
| `nav_registry.py:1005-1014` | Запись `modules` с подписью «Funktionen» | Подпись → «Richtungen & Funktionen»; замок «подпись меню = заголовок» DE+RU |
| `apps/tenants/siteconfig.py:4365+` | `_normalize_impl`: presence-minimal ключи; `onboarding` (`:4744`) и `notify` (`:4766`) проходят насквозь | Добавить `normalize_directions` |
| `apps/core/setup_steps.py:37-56` | `apply_business_type`: «нетронутый пресет» = равенство с `default_disabled_for(старый тип)` | После смены пресета живые тенанты считаются «тронутыми» — консервативно, не ломается |
| `apps/tenants/services.py:80`, `:211-213` | `_new_tenant` применяет пресет; `start_quick_provisioning` дополнительно включает promotions и publishing | Пресет действует только на новые бизнесы; быстрый старт не затронут |
| `apps/tenants/demo_kits.py:25142-25144`, `:25699-25708` | `kit_enabled_modules`: явный список плюс то, что следует из контента (blog, booking) | Киты hotel и tour_operator проверить после смены пресета |
| `apps/tenants/demo_fingerprint.py:26,61` | `SEEDER_VERSION` | Поднять |
| `apps/core/diagnoses.py:136-156` | `_module_finding` ведёт на `"modules"`, текст «ist ausgeschaltet» | Экран обязан показать контрол любого выключенного модуля, на который ссылается диагноз |
| `apps/core/diagnoses.py:350-356` | `_direction(key)` → `directions.is_active` | Ключи направлений не переименовываем |
| `apps/tenants/management/commands/package_report.py:55-94` | `report_for`, флаги `--tenant` / `--json`, исключение `public` | Образец для `modules_report` |
| `apps/core/settings_hints.py:64-68` | Подпись «N Module aktiv»; `test_sr5_settings.py:28` ищет «Module» | Обновить подпись и замок осознанно |
| Тесты, которые меняются | `test_modules.py:184-343` (`test_default_disabled_for_vertical`), `:400`, `:422`, `:477-510` (POST `modules`); `test_packages.py:159` (POST `modules`); `test_archetypes_s6.py`; `test_demo_menus.py:38-52`; `test_demo_lists`; `test_nav_reachability` | Переписываются осознанно, с записью в build-log |

## §2. Решения по данным

### 2.1. Слои модулей — поля `ModuleSpec`, без миграции

В `ModuleSpec` добавляются два поля:
- `layer: str` со значениями `"core"` / `"base"` / `"direction"` / `"addon"`;
- `addon_for: tuple[str, ...]` — ключи направлений, `"*"` = любое активное, `"selling"` = любое продающее.

| Слой | Модули | `addon_for` |
|---|---|---|
| core (= `core=True`) | dashboard, board, catalog, settings, billing | — |
| base | promotions, crm, reviews, inbox | — |
| direction | orders, booking, stays, events, jobs | — |
| addon | loyalty | waren, termine, tisch, speisekarte |
| addon | gift | selling |
| addon | customer_account | waren, termine, tisch, tickets (без zimmer — §5.3) |
| addon | finance | selling |
| addon | telegram, publishing, blog, analytics | * |

- **Видимость дополнения:** у тенанта есть подходящее активное направление **или модуль сейчас включён**. Второе условие нужно, чтобы включённое (например, `customer_account` у живого отеля) можно было выключить.
- `core` остаётся флагом, базовые модули **не** становятся `core` (§5.1 п.3: core обходит потолок пакета, и лёгкий пакет получил бы crm/reviews).
- `recommended_for` и `suited_for` остаются входом пресета. Экран читает только `layer`.

### 2.2. Режим zeigen/verkaufen

- **Waren:** «verkaufen» ⇔ модуль `orders` активен, «zeigen» = `orders` выключен при активном waren. Режим выводится, ничего не хранится.
- **Speisekarte:** только «zeigen», карточка информационная.
- **Termine / Tisch / Zimmer / Tickets / Anfragen:** в M-1 только Ein/Aus (= модуль). Режим «zeigen» у них пока ничем не исполняется — витрина его не читает. Показать его сейчас значило бы обещать без исполнения (класс STU-9). Поэтому режим откладывается в W4-5 «Verkauf öffnen».
- **Резерв ключа:** уже в M-1a в normalize добавляется `normalize_directions(raw) -> dict`.
  - Белый список: ключ — направление из `directions.REGISTRY`, значение — `{"mode": "zeigen" | "verkaufen"}`.
  - Ключ материализуется только при непустом значении (presence-minimal), golden-эталоны целы.
  - Нужно, чтобы первая же запись W4-5 не терялась на Save билдера (W0/W6). Писатель `set_state` принимает `mode`, но в M-1 UI его не шлёт.

### 2.3. Направление и пакеты, `disabled_modules`

- **Пакет — потолок.** Модуль вне пакета (`packages.module_allowed=False`): карточка или тумблер заперты с подписью «Nicht im Paket». Писатель отказывает, перепроверяя внутри блокировки (паритет с `views.py:4327-4332`).
- **Общий модуль.** Выключение направления не трогает модуль, который держит другое активное направление (общая проверка `booking` для termine и tisch). Писатель возвращает причину.
- **Лёгкий пакет** (`package_of(t).lite`): у `jobs`, `promotions`, `publishing`, `inbox`, `telegram` выключение отклоняется. Это зеркало `_LITE_MODULES` (`packages.py:46`): заявки по акции живут на `jobs`.
- **Waren и Speisekarte не выключаются:** их `active_when` зависит от типа и данных. Карточка Waren даёт только zeigen ↔ verkaufen.

### 2.4. Единственные писатели (`select_for_update`)

- **`modules.set_module(tenant, key, on) -> bool`** — обобщение `enable_module`:
  - свежая строка под блокировкой, `auto_create_schema=False`;
  - `update_fields=["disabled_modules", "updated_at"]`;
  - пишет только этот ключ;
  - core модуль не трогает;
  - `enable_module` становится обёрткой.
- **`directions.set_state(tenant, key, state, *, mode=None) -> list[str]`** (список проблем):
  - одна транзакция: блокировка, затем правка `disabled_modules` модулей направления и (при `mode`) `site_config["directions"]`;
  - `site_config` берётся из заблокированной копии, а не из объекта запроса (класс W6);
  - `update_fields` ровно по изменённым полям.
- **`offer_batch.choose_directions`** вызывает `set_state(…, "on")`. Заодно закрывается пропущенный `auto_create_schema=False`.

### 2.5. Риски класса W0/W6

- Большой формы больше нет: каждая форма шлёт один ключ и одно состояние.
- Скрытый модуль владельца не стирается: POST, не упомянувший модуль, его не меняет. Замок: «POST одной карточки не меняет ни одного другого ключа `disabled_modules` и ни одного ключа `site_config`».
- `normalize` сохраняет `directions`: golden-паритет плюс round-trip.

## §3. Файлы

| Файл | Что меняется |
|---|---|
| `apps/core/modules.py` | Поля `layer`/`addon_for` в 22 спеках; `set_module`; `recommended_for` (promotions +4 типа, booking −tour_operator, jobs +tour_operator, customer_account −hotel); хелперы `addons_for(tenant)`, `base_disabled(tenant)` |
| `apps/core/directions.py` | `choices_for(tenant)` (перенос из `offer_batch.direction_choices`, тот остаётся алиасом); `state_of(tenant, key)` с результатом off / zeigen / verkaufen / on; `set_state`; `SELLING`; `LATE_PROMO_TYPES = ("hotel", "tour_operator", "handwerker", "werkstatt")` |
| `apps/core/module_presets.py` (новый; имя свободно — проверить, `pitfalls.md:203`) | `LEGACY_DISABLED` — замороженные исторические пресеты по типам (варианты §4 M-1e) |
| `apps/core/offer_batch.py:91-142` | Делегирование в `directions` |
| `apps/tenants/siteconfig.py` | `normalize_directions` + строка в `_normalize_impl` |
| `apps/core/nav_registry.py` | Гейт `"aktionen"` в `direction_active` (мемо `_nav_has_promotions`, запрос только у `LATE_PROMO_TYPES`, лёгкий/aktionen-профиль — всегда виден); `direction="aktionen"` у `promotions:promotion-list`; подпись «Richtungen & Funktionen» |
| `apps/core/views.py:4311` | `modules_view` (GET → контекст 4 блоков; POST `action=direction|module` → писатели → PRG) |
| `templates/tenant/modules.html` | Переписать; `_module_row.html` либо удалить, либо оставить для блока дополнений; новый `tenant/_direction_card.html` |
| `apps/core/settings_home.py:29`, `apps/core/settings_hints.py:64` | Подписи |
| `apps/tenants/management/commands/modules_report.py` (новый) | Отчёт и `--apply` |
| `apps/tenants/demo_fingerprint.py:26` | `SEEDER_VERSION += 1` |
| `apps/tenants/demo_kits.py` | Киты hotel, tour_operator, moto, stadtfuehrung, handwerker, werkstatt: при необходимости `enable_modules += customer_account / booking` (по результату `test_demo_menus`) |
| `locale/*/LC_MESSAGES/django.po` (×5) | Новые msgid |
| `static/css/app.css` | Пересобрать при новых классах |
| `docs/build-log.md`, `docs/task-catalog.md`, `CLAUDE.md` §3 | Память |

## §4. Инкременты

Каждый инкремент сам по себе зелёный в CI и мержится отдельно. Порядок: a → b → c → d → e. Деплоить d и e вместе.

### M-1a. Слои, choices и резерв ключа (без изменения поведения)

Замки пишутся до кода (`apps/core/tests/test_m1_layers.py`):
1. Каждый не-core модуль имеет ровно один `layer` из base / direction / addon; core ⇔ `core=True`.
2. Каждый addon имеет непустой `addon_for` со значениями из ключей направлений, `"*"` или `"selling"`.
3. Модули `layer=direction` == ∪ `Direction.modules`.
4. `choices_for` даёт тот же результат, что прежний `offer_batch.direction_choices`, по 16 типам (паритет).
5. `normalize({"directions": {"termine": {"mode": "zeigen"}}})` сохраняет ключ; мусорные ключи и значения отбрасываются; пустой → ключа нет; golden-эталоны без изменений.
6. `LEGACY_DISABLED[t]` содержит текущий `default_disabled_for(t)` для всех 16 типов. Снимок делается **до** правки пресетов; в M-1d он становится литералом, который не меняется.

### M-1b. Писатели

Замки (`test_m1_writers.py`):
1. `set_module(off)` и затем `set_module(on)` меняют только свой ключ; core модуль не трогается.
2. Модуль вне пакета → отказ; `disabled_modules` без изменений.
3. Лёгкий пакет: выключение `jobs` → отказ.
4. `set_state("termine", "off")` у кафе с tisch не трогает `booking` — общий модуль, вернётся проблема.
5. `set_state` не ломается, если `site_config` объекта запроса устарел: чужой ключ, записанный параллельно, сохраняется (запись берётся из заблокированной копии).
6. Нет попытки создать схему: замок-шпион на `auto_create_schema`, сохранение заблокированной копии без создания схемы.
7. `choose_directions` идёт через `set_state`; прежние тесты W4-2 (`test_wizard_v4_pruefen.py:352-393`) зелёные.

### M-1c. Экран

Замки до кода (`test_m1_screen.py`); прежние POST-тесты `test_modules.py:400/422/477` и `test_packages.py:159` переписываются под новый протокол осознанно, гарантия «вне пакета не меняется» сохраняется:
1. Базовые и core модули не рендерятся тумблерами.
2. Дополнение без активного направления скрыто, если оно выключено; если включено — видно.
3. «Von Ihnen ausgeschaltet» показывает базовый модуль из `disabled_modules` с кнопкой «Wieder einschalten».
4. Для каждого модуля, который может вернуть `diagnoses._module_finding`, в выключенном состоянии на экране есть контрол. Замок перебирает все не-core ключи.
5. POST `action=module&key=loyalty&on=1` меняет только loyalty.
6. POST без права `funktionen.edit` → 403 (`view_perms`).
7. CSRF; неизвестный `key` или `state` → 400 без записи; PRG-редирект на `modules`.
8. Заголовок совпадает с подписью меню (замок nav_title DE+RU).
9. i18n: `scripts/i18n_quickcheck.py`, `test_template_comments`.

Плюс Playwright-стенд: карточки у bakery / friseur / hotel / cafe / werkstatt на 1440 и 390, клавиатура, фокус после PRG.

### M-1d. Пресеты, гейт Aktionen, демо

Замки:
1. `test_default_disabled_for_vertical` переписан: hotel — без promotions, плюс customer_account; handwerker/werkstatt — без promotions; tour_operator — плюс booking, без jobs, без promotions.
2. Согласованность: для каждого типа T и каждого направления d из `DEFAULT_FOR[T]` модули d входят в пресет. Исключение — waren у werkstatt и speisekarte (режим zeigen).
3. Базовые модули рекомендованы всем 16 типам, поэтому пресет их не выключает.
4. werkstatt без товаров: `directions.is_active(t, "waren")` = True, раздел склада виден (§5.3).
5. Гейт Aktionen:
   - hotel без акций — пункт скрыт;
   - hotel с одной акцией — пункт виден;
   - bakery — виден без запроса (assertNumQueries);
   - профиль «aktionen» / лёгкий пакет — виден всегда.
6. На экране у `LATE_PROMO_TYPES` без акций есть карточка «Lücken-Deal & Frühbucher» (у ремесла — своя подпись) со ссылкой на создание акции.
7. `test_demo_menus`, `test_demo_lists`, `test_nav_reachability` зелёные; `SEEDER_VERSION` поднят.

### M-1e. `modules_report`

Замки (`apps/tenants/tests/test_modules_report.py`):
1. По умолчанию только отчёт, без записи (`assertNumQueries` без UPDATE).
2. Класс `preset`: `sorted(disabled)` == одному из вариантов `LEGACY_DISABLED[type]`. Варианты:
   - снимок M-1a;
   - он же без `blog` (до E8.7);
   - для hotel — без `booking` (до E8.11);
   - с добавками миграций `0012` (stays) и `0017` (customer_account).

   Для класса `preset` `--apply` включает ровно {было выключено пресетом} ∩ {новый пресет включает}. Ничего не выключает — даже customer_account у живого отеля.
3. Класс `owner` (любое расхождение): не трогается; в отчёте перечислены выключенные базовые модули.
4. Пропускаются: `public`, `is_demo` (их пересеет сидер), `provisioning != done`. Лёгкий пакет попадает в `owner`, потому что быстрый старт сам правит набор.
5. `--apply` идемпотентен: второй прогон пишет 0 строк. Внутри блокировки — повторная проверка равенства (защита от гонки с владельцем).
6. `--json`, `--tenant <schema>`, сводка по классам.

Ops после деплоя: `modules_report` → владельцу на просмотр → `modules_report --apply` → `seed_demo_tenants --group all --changed`.

## §5. Риски

- **Живые тенанты теряют модули.** Исключено конструкцией: пресет действует только в `_new_tenant`, а `modules_report` только включает. Остаточный риск — неверный вариант в `LEGACY_DISABLED`. Последствие безобидное: тенант уйдёт в `owner` и не будет тронут. Отчёт до `--apply` показывает счётчики классов.
- **Скрытый, но выключенный базовый модуль.** Без блока «Von Ihnen ausgeschaltet» владелец потерял бы контрол — закрыто замком M-1c п.3/4.
- **`apply_business_type`** (`setup_steps.py:48`). После смены пресета живые тенанты считаются «тронутыми» и при повторе того же типа не сбрасываются. Это консервативно.
- **Демо-киты.**
  - hotel теряет `customer_account`: проверить ЛК и пункт «Mein Konto» в меню кита; при необходимости `enable_modules`.
  - tour_operator теряет `booking`: у китов с `services` его вернёт `kit_enabled_modules`.
  - Подъём `SEEDER_VERSION` пересеет все демо — долго (T-10), выполняется `--changed --jobs 3`.
- **Меню и замки.**
  - Мораторий на якоря цел: якоря не меняются, только гейт записи.
  - `EXPECTED_UNLISTED` не меняется: экран тот же.
  - Подпись «Funktionen» меняется в реестре, хинтах и `.po` — замок nav_title.
  - Гейт `aktionen` добавляет запрос в хром только четырём типам, с мемо на тенанте (§5.1 п.6).
- **Помощник A-0.** `_direction("waren"/"termine"/"zimmer")` и ссылка `"modules"` целы; ключи направлений не переименовываются. Риск «диагноз ведёт на экран без контрола» закрыт замком M-1c п.4.
- **Ctrl+K.** Палитра использует `entry_visible`, поэтому «Aktionen» у отеля без акций из палитры тоже исчезнет. Вход — карточка на экране и плитка «Marketing». Решение §5.7 это и предполагает.
- **Грабли** (`pitfalls.md`):
  - `:339` — `auto_create_schema` на заблокированной копии;
  - `:236` — пресет только при создании или смене типа;
  - `:450` — `select_for_update` вне транзакции;
  - `:203` — имя нового модуля свободно.

## §6. Открытые вопросы

1. **Режим «zeigen» у Termine / Zimmer / Tickets.** Рекомендация (заложена в план): в M-1 не показывать; ключ `site_config["directions"]` резервируется в normalize, а UI и потребитель появляются в W4-5. Подтвердить.
2. **«Unterkunft im Paket» (stays) для tour_operator (§5.3).** Рекомендация: в M-1 не делать отдельным дополнением — Zimmer доступен через «Weitere Richtung hinzufügen». Подпись-дополнение — в W4-5.

## §7. ECC-прогоны

| Шаг | Скиллы (грузить до кода) | Агенты и когда |
|---|---|---|
| Ревью плана (сразу) | django-patterns, product-lens | `architect` — сверка слоёв и режима с M-0 и W4-5 |
| M-1a | django-patterns, django-tdd | `django-reviewer` до мержа |
| M-1b | django-security, postgres-patterns, django-tdd | `django-reviewer`; `security-reviewer` (писатели под блокировкой, обход потолка пакета, подделанный POST); `silent-failure-hunter` (проблемы писателя возвращаются, а не глотаются) |
| M-1c | accessibility, e2e-testing, django-security | `django-reviewer`; `security-reviewer` (эндпоинт записи: CSRF, `view_perms`, белый список `key`/`state`); `a11y-architect` (карточки-формы, `aria-pressed`, фокус после PRG, контраст бейджей); `e2e-runner` — Python-Playwright-стенд 1440/390 × 5 типов, Chromium из `/opt/pw-browsers` |
| M-1d | django-tdd, database-migrations (пересев китов) | `django-reviewer`; `database-reviewer` (запрос гейта aktionen в хроме: мемо, `.exists()`) |
| M-1e | database-migrations, postgres-patterns, django-patterns | `database-reviewer` (пересчёт `disabled_modules` живых тенантов: блокировка, повторная проверка, идемпотентность); `silent-failure-hunter`; `django-reviewer` |
| Перед мержем каждого | — | Гейт: `ruff check .` + `ruff format --check .` + pytest затронутых модулей (`--reuse-db`) + `scripts/i18n_quickcheck.py` + `test_template_comments` + `npm run build:css` при новых классах |
| Финал | — | `doc-updater`: `docs/build-log.md`, `docs/task-catalog.md`, `CLAUDE.md` §3 |

## §8. Решения (2026-11-05)

Открытые вопросы §6 — по рекомендации плана (в духе «по рекомендации» владельца §5.7):
режим «zeigen» у Termine/Zimmer/Tickets в M-1 не показываем (ключ резервируется в normalize,
UI — в W4-5); «Unterkunft im Paket» у tour_operator — через «Weitere Richtung hinzufügen».
