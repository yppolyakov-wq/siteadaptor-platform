# AIS-A A-0: шторка «✨ Assistent» без ИИ — план (2026-11-05)

План — агент ECC `planner`. Источник: `ais-modules-directions-assistant-plan-2026-11-05.md` часть 2
(§2.1–2.4, §5.1 п.6–7, §5.2, §5.7) и `ais-ecc-plan-2026-11-05.md` строка 6. Миграций нет.
Решения §11 — по рекомендации (отмашка владельца «А0 делай», 2026-11-05).

## 0. Коротко

Кнопка «✨ Assistent» открывает шторку (контракт `references/patterns/drawer.md`) из четырёх
детерминированных блоков:
1. **«Auf dieser Seite fehlt»** — пункты реестра готовности, относящиеся к открытому экрану.
2. **«Gerade wichtig»** — 1–3 карточки на весь бизнес.
3. **«Funktioniert etwas nicht?»** — реестр диагнозов: симптом → проверки, **вызывающие настоящие
   гейты** → причина → ссылка.
4. **«Wo stelle ich das ein?»** — поиск по тому же отфильтрованному индексу, что палитра Ctrl+K.

Главное правило: **диагноз не повторяет гейт, а вызывает его**. Там, где гейт написан inline или
продублирован, сначала выносим его в функцию с замком паритета (срез A0.1).

## 1. Объём

Входит: GET-эндпоинт `assistant` (фрагмент для шторки, без JS — полная страница); модули
`apps/core/assistant.py` и `apps/core/diagnoses.py`; вынос гейтов (A0.1); входы — шапка кабинета,
главная лёгкого пакета / Mini App, мастер (ссылкой); регистрация в `view_perms.RULES`,
`packages._AKTIONEN_VIEWS`, `tg_login.TG_LITE_VIEWS`, `nav_registry` (palette_only); i18n ×5; замки;
стенд Playwright.

Не входит: ИИ и свободный вопрос (A-2), статьи справки (A-1), эскалация/журнал (A-3), бейдж-счётчик
на кнопке, любые изменения данных из шторки (кроме существующей POST-кнопки «Bestätigung erneut
senden»).

## 2. Поток

```
[✨] <a href="/dashboard/assistent/?seite=<view_name>" data-drawer data-drawer-key="assistant">
  JS: fetch ?box=1 → фрагмент в <dialog>; без JS — полная страница
assistant(request)  @login_required @require_GET
  seite = whitelist (имена nav_registry ∪ SCREEN_EXTRA), иначе ""
  build: here (readiness.items_for(..., unknown_on_error=True)) · important (≤3) ·
         diagnoses.applicable (дешёвые сразу, тяжёлые — кнопкой «Prüfen») · where (палитра)
  ?diagnose=<key> (whitelist) → тяжёлые, ratelimit
  каждая ссылка → assistant.link(request, url_name, query) → url | None
```

Межзапросного кэша нет; мемо фактов на объекте тенанта (`readiness.facts_for`) + на `request`.

## 3. Файлы

**A0.1 — единые гейты (поведение не меняется):**
- `aggregator/visibility.py`: `withheld_reasons(tenant)` (`inactive`/`suspended`/`email_pending`/
  `operator_off`/`internal`/`unpublished`), `listable = not withheld_reasons`.
- `promotions/where.py`: `_catalog_reason` поверх `withheld_reasons` (+ `is_demo`); **попутно**
  чиним дубль без `unpublished` (бот отвечал «Derzeit nicht sichtbar» вместо «не опубликован»).
- `core/storefront_state.py` (новый): `hidden_reasons(tenant)` (`email_pending`/`unpublished`);
  `PendingStorefrontMiddleware` берёт его вместо inline-условия.
- `orders/public_views.py`: `orders_active(tenant)`; `_require_orders_active` зовёт её.
- `nav_registry.palette_entries_for(request)` — фильтр палитры из тега `nav_palette` в функцию.
- `readiness.items_for(..., unknown_on_error=False)`: при True упавшая проверка даёт `done=None`.

**A0.2 — ядро:** `assistant.py` (`SCREEN_EXTRA`, `missing_here`, `important`, `where_search`,
`link`, `build`; `MAX_IMPORTANT=3`, `MAX_WHERE=8`) и `diagnoses.py` (`Diagnosis(key, symptom,
direction, cost, applies, run, gates)`, `Finding(level, text, url_name, query, owner_only)`,
`REGISTRY`, `applicable`, `run`).

**A0.3 — UI:** `core/assistant_views.py`, `urls_tenant` `dashboard/assistent/`, `view_perms`
`"assistant": _r(OPEN)`, пакеты/TG/nav, `templates/core/_assistant_body.html` (без `<script>`/
`on…=`), `templates/core/assistant.html` (extends dashboard), ссылка в шапке
`_base_dashboard.html` (**readiness в хроме не вызывается**), карточка «✨ Was fehlt noch?» на главной
лёгкого пакета, ссылка с возвратом в мастере; .po ×5; app.css при новых классах.

**A0.4 — тяжёлые диагнозы:** D4, D6 по кнопке, `ratelimit.hit("assistant-diag", schema:user, 20/60)`
с дружелюбным текстом.

**A0.5 — стенд и a11y:** Playwright 1440/390, Mini App, без JS, фокус/Esc.

## 4. Реестр диагнозов v1

| # | key — симптом | Когда | Вызываемые гейты | Причина → ссылка | Цена |
|---|---|---|---|---|---|
| D1 | `website_hidden` «Kunden sehen „Bald online“» | всегда | `storefront_state.hidden_reasons`; `onboarding.publish_blockers` | email → POST `owner-confirm-resend`; unpublished → `setup?step=recht` + блокеры | дёшево |
| D2 | `not_in_city` «Nicht im Stadtkatalog» | не demo/internal | `visibility.withheld_reasons`; `AggregatorListing.objects.public().filter(tenant_schema=…).exists()` | как D1; operator_off — текст; suspended → billing (владельцу); нет листингов → акции/ассортимент | дёшево |
| D3 | `cart_closed` «Kunden können nicht online bestellen» | направление waren | `orders_active`; `packages.module_allowed`; `storefront_profile.is_aktionen`; `readiness.sell_allowed`; `closures.closed_range_for`; `readiness.is_done("waren.product"/"waren.prepay")` | modules / пакет / betriebsferien / товар / payment-settings | дёшево |
| D4 | `no_slots` «Keine freien Termine» | termine | `availability.service_pool`, `next_free_slot`, `day_windows`, `booking_window`; `closures.is_closed` | услуги / ресурсы / каникулы / часы / правила / «ausgebucht» | кнопкой |
| D5 | `promo_invisible` «Meine Aktion ist nicht zu sehen» | promotions | `promotions.where.rows`; `limits.can_activate`/`usage` | правка акции / лимит / причина каталога | дёшево |
| D6 | `google_feed` «Produkte fehlen bei Google» | waren + канал есть | `Channel.objects.filter(...).first()` (НЕ `merchant.channel()` — он пишет); `merchant.feed_state`; `catalog.google.summary` | `gbp-merchant` | кнопкой |
| D7 | `rooms_not_bookable` «Zimmer nicht buchbar» | zimmer | `readiness.is_done("zimmer.room")`; `closures.current_or_next` | номера / каникулы | дёшево |
| D8 | `looks_closed` «Website zeigt „geschlossen“» | всегда | `closures.current_or_next`; `readiness.is_done("hours")` | betriebsferien / часы | дёшево |

Правило формулировок: упавшая проверка → «Konnte nicht geprüft werden»; «alles in Ordnung» —
только при нуле находок И нуле unknown.

## 5. «Gerade wichtig» (≤3, по приоритету)

E-Mail bestätigen → Website veröffentlichen (+ число блокеров) → Betriebsferien (идут или в 7 днях)
→ первый невыполненный MUST (+N weitere) → «Einige Prüfungen konnten nicht ausgeführt werden» →
«Alles Wichtige ist erledigt». Биллинг — только при праве биллинга.

## 6. Ссылки и права — `assistant.link`

1. `setup_assistant.reachable(request, url_name)` (TG-белый список, пакет, `view_perms`).
2. Есть запись в `nav_registry` → ещё `entry_visible(entry, tenant)` (иначе 404 выключенного модуля).
3. Алиасы лёгкого пакета: `settings → lite-business`, `site-home → None`.
4. `reverse()` в try; `NoReverseMatch` → лог, пункт без ссылки.
5. Не прошла: сотруднику — «Bitte den Inhaber fragen» (пункт остаётся); владельцу —
   «Im Browser öffnen» / «Nicht in Ihrem Paket». Биллинг и Team сотруднику не показываются вовсе.
6. `seite` — только ключ карты (whitelist), URL из запроса не берётся; `next` — только `safe_next`.

## 7. Риски

- Ложное «всё хорошо»: readiness по умолчанию fail-open → шторка зовёт `unknown_on_error=True`,
  диагнозы в try → unknown.
- Сбой не ломает кабинет: каждый блок в try с логом; ORM-чтение диагнозов в savepoint.
- GET без побочных эффектов (замок 0 INSERT/UPDATE/DELETE).
- Кросс-тенант: только `request.tenant`; в параметрах нет id объектов.
- Данные клиентов: ни одна проверка не выбирает Customer/Order/сообщения (замок).
- Бюджет: шторка ≤ 15 запросов; D4 ≤ 80, по кнопке.
- Хром: только ссылка; замок «readiness не в хроме» остаётся зелёным.

## 8. Тесты (до кода)

1. «Диагноз зовёт гейт»: monkeypatch каждого гейта из `gates` на противоположный результат → вывод
   меняется; AST-замок — `diagnoses.py`/`assistant.py` не читают `email_pending`/`published_at`/
   `in_city_catalog`/`subscription_status`/`is_internal`, не зовут `is_module_active("orders")` и
   `merchant.channel`.
2. Паритет A0.1 (listable, withheld_schemas, middleware 503, orders_active, палитра, where unpublished).
3. «Каждая ссылка проходит права»: все `href` шторки под ролями (владелец, Mitarbeiter, без прав,
   Aktionen, Eintrag, TG) проходят `allowed_quiet`/`view_allowed`/`TG_LITE_VIEWS`; владельческих
   экранов у сотрудника нет.
4. Fail-safe (сбой факта → «nicht geprüft», без «Alles erledigt»; сбой диагноза → 200).
5. Только чтение. 6. Нет данных клиентов. 7. Карта экранов реальна. 8. Мусорные параметры.
9. Бюджеты запросов. 10. Кросс-тенант. 11. Без JS / фрагмент. 12. Лимит (isolated_ratelimit).
13. Регистрация экрана (X7, nav_reachability, staff_walk). 14. Шаблоны (comments, без script).

## 9. Срезы

A0.1 гейты → A0.2 ядро (D1–D3, D5, D7, D8) → A0.3 вьюха/шаблоны/входы/i18n → A0.4 D4/D6 + лимит →
A0.5 стенд + a11y. Один батч — один CI, затем FF в main и доки.

## 10. ECC-прогоны

Скиллы до кода: `django-patterns`, `django-tdd`, `django-security`, `postgres-patterns`,
`accessibility`, `e2e-testing`, `error-handling`; `docs/pitfalls.md` §3–§5.

| Агент | Когда | Фокус |
|---|---|---|
| architect | сразу по плану, до A0.1 | диагнозы не дублируют гейты; полнота выносов; место `palette_entries_for` |
| django-reviewer | после каждого среза | декораторы, GET без записи, savepoint, N+1 |
| security-reviewer | после A0.2 и A0.3 | права сотрудника, кросс-тенант, параметры, клиентские данные, лимит |
| silent-failure-hunter | после A0.2 и A0.4 | ни один except не превращает сбой в «alles gut» |
| database-reviewer | A0.4 | бюджеты D4/D6, exists(), индекс tenant_schema |
| a11y-architect | после A0.3 | заголовки секций, role=status, цели, фокус |
| e2e-runner | A0.5 | десктоп/телефон, Mini App, без JS |

## 11. Решения (по рекомендации, 2026-11-05)

- **В-1** сотруднику пункт показывается с «Bitte den Inhaber fragen»; биллинг и Team скрыты.
- **В-2** бейджа на кнопке нет (реестр в хроме) — вернуться после замера AIS-0.
- **В-3** диагнозы v1 — восемь; «Tisch» (GA-4) — v1.1 после стенда.
- **В-4** в мастере v4 — полной страницей с возвратом; шторку в мастер — с W4-6.
- **В-5** «Bestätigung erneut senden» в шторке — да (существующая POST-вьюха).
- **В-6** подпись «✨ Assistent» без «KI» до A-2.

## 12. Ревью архитектора (2026-11-05) — правки к плану, приняты

**A0.1 шире, чем в §3:**
- третья копия причин каталога — `aggregator/owner_stats._status` → на `withheld_reasons` (+ замок);
- `core/health.py` (почта не подтверждена > 24 ч → нет TLS для своего домена) → `tls_withheld(tenant)`;
- проверка «онлайн-заказ включён» продублирована ещё в 6 местах (`orders/public_views`,
  `promotions/public_views`, `promotions/response`) → все на `orders_active`; «Kaufen» =
  `promotions.response` — D3/D5 зовут его;
- `stays_active`/`booking_active` вместо inline `_require_*_active`;
- readiness `_email_confirmed`/`_selling_goods` → через `storefront_state`/`orders_active`;
- D2 «нет листингов»: зовёт правило свежести (`freshness.is_stale`), снятие товаров лёгким
  профилем и пригодность товара из синка, а не гадает.

**«Не знаю ≠ готово» (все слои):** упавший факт из мемо (`failed_reads`, сделано), `_applies` и
`_module` при сбое → unknown, сбой направлений → строка unknown, `is_done(..., unknown_on_error=)`;
`closures` при сбое читает «не закрыто» → строгий вариант для D8.

**Диагнозы — гейты витрины, а не подсказки readiness:**
- D1: `publish_blockers` сбрасывает мемо → звать первым или вариант без сброса;
- D3: `closures.closed_now_message` (как checkout), `storefront_profile.redirect_if_aktionen`,
  `order_payments.available_methods`, `modules.inactive_reason(tenant, key)` (package/disabled/deps);
  `is_done("waren.*")` — подсказки, не гейты; `readiness.sell_allowed` вызывающих не имеет;
- D4: `booking_active`; кап ≤ 5 услуг, `max_days=14`;
- D5: `where.rows(portal_urls=False)`, ≤ 5 акций, канал Telegram читать один раз;
- D6: `feed_state` расшифровывает токен (может упасть → unknown), токен в контекст не класть;
- D7: `stays_active` + функция доступности/правил продаж, которую зовёт публичная бронь;
- D8: `Tenant.open_status()` (то, что печатает витрина).

**Ссылки:** `owner-confirm-resend` — правило в `view_perms` и `method="POST"`; цели вне
`nav_registry` (`setup`, `gbp-merchant`, `payment-settings`, `betriebsferien`) — явная карта
гейтов модуля/направления; алиас лёгкого пакета и для `legal-docs`; «Wo stelle ich das ein?»
пост-фильтрует палитру через `assistant.link` (палитра не знает белый список Mini App).

**Хром:** только ссылка; карточка на лёгкой главной — статичная или из уже посчитанного
`next_step`; замок «readiness не в хроме» распространить на контекст-процессоры.
