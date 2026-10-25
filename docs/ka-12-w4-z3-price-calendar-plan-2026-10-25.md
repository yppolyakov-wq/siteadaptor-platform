# KA-12 · Zimmer Z-3 (E4.6b) — экран «Preise & Verfügbarkeit», план 2026-10-25

План — агент `planner` по `main` (`726f6c1e`); родитель — `ka-12-w4-zimmer-plan-2026-10-25.md` (§4.1, §8 О-4/О-9,
§10). **Без миграций** (`NightRate` есть с `stays/0042`).

## 0. Проверено в коде
- Писателей `NightRate` нет — Z-3 первый. Читатели: `pricing`, `restrictions`, `public_views` (фид G8), `tasks`,
  `aggregator/hotel_search` (через pricing/restrictions).
- **Каталог города «ab»-цену номера не пересчитывает**: `aggregator/tasks._stay_snapshot` берёт `unit.price_cents`;
  экран `StayUnit` не сохраняет → реконсиляция не нужна. `hotel_search` кэширует 300 с, витрина — 120 с: допустимо.
  В roadmap: если «ab» станет минимумом по ночам — реконсиляция при записи `NightRate`.
- Права — `roles.can_edit_policy` (owner/admin) через обёртку `_can_edit` (monkeypatch в тестах, как booking).
- Журнал — `apps.audit.services.audit_event`. Деньги — `apps.core.money.parse_money` (не `_eur_to_cents`: мусор → 0).
- Блокировки — `StayUnit.select_for_update().filter(id__in=…).order_by("id")`.

## 1. Требования
1. Сетка категория × день (14/31, ← → «Heute»): эффективная цена без тарифа (`nightly_price_cents`), источник
   (Tagespreis / сезон / Wochenende / база), бейджи Stopp / min N / kein Check-in / kein Check-out, «frei N».
2. Массовая правка: категории × период × дни недели → цена = X € / ±N % / сброс; Stopp, CTA, CTD вкл/выкл;
   min_nights = N / сброс. По умолчанию «nicht ändern» (≠ «zurücksetzen»). Vorschau — GET без записи,
   «Übernehmen» — POST одной транзакцией + PRG.
3. Диалог дня `<dialog>`; без JS — обычная страница.
4. Смотрят все роли кабинета; правят owner/admin (О-4): staff форму не видит, POST → 403.
5. W0 без JS; телефон — карточки без горизонтального скролла. Журнал на каждую правку. msgid немецкие ×5 `.po`.
   Входы: Belegungsplan, страница номера (`?kat=`), секция `sec=preise`; подпункт «Sortiment» (О-9).

## 2. Архитектура
- `apps/stays/night_rates.py`: `DayState` / `Action` / `Change` / `Plan` (frozen dataclass);
  `select_days`, `validate_scope` (прошлое, bis<von, > today+732, пустые дни недели, кап 20 000 ячеек,
  мусор/чужой id — fail-closed), `parse_action` (`parse_money`, ≤2 знака, 0<цена≤99 999,99; % −90..300, ≠0;
  min 1..365; noop → ошибка), чистые `apply_action` (патч ТОЛЬКО полей действия; % от текущей эффективной цены
  дня, ROUND_HALF_UP, <1 → отказ) и `plan_changes` (только изменённые ячейки; нейтральные → delete;
  отпечаток sha256 состояния), `load_window` (хелпер `pricing.night_rates_window` — чтение остаётся в pricing),
  `apply_plan` (atomic: блокировка юнитов по id → перечитать окно и план под блокировкой → отпечаток ≠ →
  `StalePlan`; отказы → `PlanRejected`; `bulk_create(update_conflicts=…, batch_size=500)` только изменённых
  с явным `updated_at`; delete нейтральных; `forget_night_rates`; `audit_event` внутри atomic). Брони не трогаем
  (снимок Z-1); Vorschau сообщает число ночей с бронями.
- `grid_context`: юниты + сезоны + окно NightRate + `availability.occupancy_grid` — фиксированное число запросов.
- Вьюхи `apps/stays/price_calendar_views.py`: `price_calendar` (GET; `vorschau=1` строит план без записи),
  `price_calendar_apply` (POST, 403 не owner/admin, редирект из целых `von/tage` — без `next=`), `price_day`
  (GET `?box=1` фрагмент / страница; POST задаёт поля дня с сентинелом `day_present`).
- URL `preise/`, `preise/uebernehmen/`, `preise/<uuid>/<day>/`; nav-запись `stays:price-calendar` в «sellables»;
  `EXPECTED_UNLISTED` += приёмник.
- Шаблоны: `price_calendar.html`, `_price_grid.html` (hidden md:block), `_price_cards.html` (md:hidden),
  `_price_bulk_form.html`, `_price_preview.html`, `_price_day.html` + `price_day.html`; JS делегированием на document.

## 3. Тесты (до кода)
Сервис: дни недели/категории; keep≠reset; нейтральные удаляются; % от сезона/дня/выходных + ROUND_HALF_UP;
отказ ≤0 без записи; неизменённые не трогаются; идемпотентность; двойной POST ±% → StalePlan; validate_scope;
parse_action; FOR UPDATE ORDER BY id; бюджет запросов не зависит от дней; forget_night_rates; брони не меняются;
audit; нет `StayUnit.save`; grep-замок `NightRate.objects` вне pricing/restrictions/night_rates/tasks.
Вьюхи: сетка/бейджи/14/31; без N+1; Vorschau без записи; роли; GET apply → 405; день box/404; сентинел;
редирект без next; модуль выкл; навигация; входы; разметка mobile/desktop; i18n ru.
Стенд Playwright 1440/390: скролл, диалог, массовая правка, устаревшая форма, без JS, Esc/фокус.

## 4. Инкременты (один батч)
Z-3a сервис → Z-3b сетка/URL/nav → Z-3c массовая правка → Z-3d диалог дня + входы → Z-3e i18n, CSS, стенд,
ревью, доки.

## 5. Риски
Паритет цены (одна функция); перезапись чужих полей (патч только действия); нейтральная строка (delete до upsert);
двойной клик/гонка (отпечаток под блокировкой); deadlock (блокировки по id, кап); локаль чисел (`parse_money`,
текстовые поля, `value=` через stringformat); права (гейт во вьюхе, `@login_required` прямо над def).

## 6. ECC-прогоны
| Когда | Скиллы | Агенты |
|---|---|---|
| после плана | django-patterns, postgres-patterns, django-tdd, django-security, accessibility | `database-reviewer`, `security-reviewer` — ревью плана |
| Z-3a | python-testing, error-handling | `django-reviewer`, `silent-failure-hunter` |
| Z-3b/c | django-patterns, postgres-patterns | `database-reviewer` (N+1, SQL apply_plan) |
| Z-3d | accessibility, e2e-testing | `a11y-architect` |
| перед мержем | django-verification (проектно) | `django-reviewer`, `security-reviewer` по ветке; Playwright-стенд 1440/390 |
