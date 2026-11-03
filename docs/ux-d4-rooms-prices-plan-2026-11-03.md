# UX-D · D4 — «Zimmer & Preise»: список номеров без настроек, тарифы своим экраном (план, 2026-11-03)

Основание: `ux-declutter-analysis-2026-11-03.md` §D4 (принципы П1–П6, решения Р-1…Р-5). Механики —
из D1/D2: шторка `apps/core/drawer.py` (контракт `docs/references/patterns/drawer.md`), вкладки
`templates/tenant/_i18n_switch.html`, экран-прецедент `booking_rules_view`. План — агент ECC
`planner`. **Миграций нет:** правка тарифа пишет существующие поля `RatePlan`.

**Решения (2026-11-03, по рекомендации; владелец может поменять):** «Tarife» — в Sortiment рядом с
«Preise & Verfügbarkeit»; экран Kurtaxe/Hausordnung/часов — «Unterkunft»; «＋ Zimmer» без права на
цены скрыт (цена — часть создания).

## Разведка
- `units()` (`apps/stays/views.py:1170-1697`) — один POST-диспетчер на 27 действий; 17 — настройки,
  не про номер: `rateplan*` (4) · `autodiscount_*` · `occupancy_*` · `gap_deal` · `booking_window` ·
  `restriction_*` · `kurtaxe` · `stay_hours` · `card_amenities`. Остальные 10 — действия номера.
  Гейт `RATE_EDIT_ACTIONS` требует `preise.edit` (кроме `card_amenities` — `sortiment.edit`).
  Редирект настроек — `_settings_sections` → `?tab=einstellungen&sec=preise|regeln|kurtaxe` (+ `next`).
- **W0:** `unit_settings`, `kurtaxe`, `gap_deal` (снятый `enabled` обнуляет), `booking_window` пишут
  поля безусловно → переносим ОДНОЙ формой каждый.
- **Тариф нельзя изменить** (только создать/охват/вкл/удалить); переводы имени/описания вводить негде.
  Правка безопасна для старых броней: `rate_snapshot`, `move_stay` по снимку, `book_stay` под локом.
- `units.html`: вкладки «Units / Settings», раскрытая `<details id="neu">`, 10 карточек настроек,
  два инлайн-скрипта, `onclick="this.select()"`; формы правил видны сотруднику без права. Страница
  номера: вкладки `data-ut-tab`, но POST мини-форм возвращает на «Basic data».
- Старые адреса `?tab=einstellungen&sec=…`: `_belegungsplan_body.html:15`, `price_calendar.html:16`,
  `_hotel_home.html:123`, `reports.html:10`, `units.html:153`; `?neu=1#neu`: `sellable_manage.py:57`,
  `setup_assistant.py:101`, `onboarding.py:489`.

## Инкременты
- **D4.0 — модуль действий (рефактор без изменения поведения).** `apps/stays/settings_actions.py`:
  17 обработчиков 1:1 из `units()`, `RATE_EDIT_ACTIONS`, карта `HOME = {action: (url_name, tab)}`;
  `units()` зовёт `dispatch()` (старые формы работают); новый экран принимает только свои действия.
- **D4.1 — «Tarife» своим экраном с правкой.** `stays:rate-plans` (список строками: имя · «−10 % /
  +12 €/Nacht» · Verpflegung · Storno · Vorkasse · охват · чип статуса · ›), `stays:rate-plan-new`
  (шторка, `drawer_aware` внутренним), `stays:rate-plan-edit` (одна форма `rateplan_update`: все поля +
  охват + переводы; удаление — `_danger_confirm`). Права `preise.view/edit`; подпункт Sortiment.
- **D4.2 — «Preise & Regeln»** (`stays:price-rules`, Einstellungen › Zimmer): вкладки Rabatte ·
  Dynamische Preise · Lücken-Deal · Verkaufsregeln (+ окно бронирования); `?tab=`/скрытое `tab`;
  карточки-входы «Tarife», «Preise & Verfügbarkeit»; сотрудник видит правила без форм.
- **D4.3 — «Unterkunft»** (`stays:stay-settings`): Kurtaxe & Hausordnung · Check-in & Check-out ·
  «Ausstattung auf der Zimmerkarte»; Kurtaxe/часы — `preise.edit`; осознанно: `card_amenities` →
  `einstellungen.edit` (замок + `test_perm_parity`). Входы «Kurtaxe-Meldung», «Meldescheine».
- **D4.4 — виджет и метапоиск → «Kanal-Manager»** (`channels.html`): секция «Website-Widget &
  Metasuche», копирование делегированным обработчиком `cabinet.js` вместо `onclick`.
- **D4.5 — список номеров + «＋ Zimmer» шторкой + старые адреса.** Список без вкладок/`#neu`/скриптов;
  `stays:unit-new` (шторка; Name · Typ · Preis · MwSt · Anzahl · Max. Gäste); `?neu=1` → 302;
  `?tab=einstellungen[&sec=X]` → 302 (preise/regeln → price-rules, kurtaxe → stay-settings, kanaele
  → channels) через `sales_page.legacy_redirect`; пять ссылок переписаны.
- **D4.6 — страница номера: вкладки рисует сервер** (`ROOM_TABS = basis, preise, regeln, zimmer,
  ical`), мини-формы несут `tab`, главная форма `unit_settings` — одна на трёх вкладках (W0).
- **D4.7 — стенд, i18n, доки.** Playwright hotel + retreat × 1600/390, замер «поля/формы/высота».

## Замки — до кода
D4.0: каждое действие — ровно в одной `HOME`; все записи `RatePlan/SeasonRate/StaySettings` — под
`RATE_EDIT_ACTIONS`; legacy-POST в `units()` пишет как прежде. D4.1: правка меняет поля; round-trip
формы без правок (с охватом и переводами); «some» без категорий → ошибка; мусорный uuid → 404;
сотрудник: GET без форм, POST без записи; правка тарифа не трогает `total_cents/rate_snapshot/deposit`
брони; фрагмент без скриптов, чужой `next`, `navigate`, без JS 302; бюджет запросов; `nav_title` = h1,
вход есть (X7). D4.2/D4.3: каждая прежняя форма на своём экране/вкладке; POST → `?tab=`; мусорный tab;
round-trip `kurtaxe`/`gap_deal`/`booking_window`; у сотрудника нет форм; на `units` нет полей
настроек. D4.4: `embed_url`/`feed_url` на `channels`, не на `units`, без `onclick`. D4.5: в строке
нет полей; нет раскрытой формы; старые адреса → 302; ни один шаблон не ссылается на `sec=`.
D4.6: все поля внутри `#unit-form`; нет вложенных форм; round-trip `unit_settings`; мини-формы → `?tab=`.

**Переписать осознанно:** `stays/tests/test_cabinet.py:480-527`, `test_gap_deal.py:220`,
`test_z5_hours.py:121`, `test_z6_kurtaxe.py:224`, `test_occupancy_pricing.py:174`,
`test_z4_rate_plan_units.py:433,446-455`, `test_restrictions.py` (URL редиректа),
`core/tests/test_price_nav.py`, `test_x6_mechanics.py:47-60`, `test_stu19g_setup_v2.py`,
`test_perm_parity.py:32`, `test_x4_navigation.py`/`test_sidebar_st4b.py`, `test_deal_card_shell.py:714`.

## ECC-прогоны
| Когда | Что |
|---|---|
| до кода | скиллы `django-patterns`, `django-tdd`, `django-security`, `accessibility`, `e2e-testing` |
| D4.0 | `django-reviewer`, `silent-failure-hunter` (паритет 17 обработчиков, сообщения, редиректы) |
| D4.1 | `django-reviewer`, `security-reviewer`, `database-reviewer`, `a11y-architect` |
| D4.2–D4.3 | `django-reviewer`, `security-reviewer`, `silent-failure-hunter`, `a11y-architect` |
| D4.4 | `django-reviewer`, `a11y-architect` |
| D4.5 | `django-reviewer`, `security-reviewer` (legacy-редиректы), `a11y-architect` |
| D4.6 | `django-reviewer`, `silent-failure-hunter`, `a11y-architect` |
| D4.7 | `e2e-runner`: hotel + retreat 1600/390 |

## Риски
Немецкая локаль в числах тарифа («−10», «12,50») — только `parse_money`/`_int`; рост подменю
(≤ 7); `nav`-литералы с якорем (замок W8); старые вкладки браузера шлют POST в `units()` — диспетчер
принимает до конца волны; ссылка «Lücken-Rabatt einrichten» на главной — гейт по новому экрану.
