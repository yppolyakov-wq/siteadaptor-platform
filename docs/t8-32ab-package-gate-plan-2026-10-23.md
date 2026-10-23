# T-8.32a/b — гейт пакетов по направлению (пилот), 2026-10-23

План — агент planner; источники `ka-3-packages-2026-10-23.md`, `ka-11-synthesis §3 P7`,
`pilot-wave-plan-2026-10-23.md`. Вопросы §7 решены по рекомендации (владелец: «комплексные
решения по рекомендациям делаем»).

## Решения
1. Пакет в a/b **выводится** из `site_config["profile"]`: aktionen → aktionen, eintrag → eintrag,
   иначе laden. Ключ `site_config["package"]` — в T-8.32d (переключение). Normalize/golden не трогаем.
2. Закрытый адрес кабинета — **403-страница «In Ihrem Paket nicht enthalten»** с кнопкой на
   лёгкую главную (не 302 и не 404: 404 уже значит «модуль выключен»). POST/fetch — JSON 403.
3. Обхода для поддержки нет; поддержка смотрит `package_report`.
4. Таб-бар Aktionen: Start · Aktionen · Nachrichten · Sichtbar. Чат остаётся в пакете.
5. Планы/лимиты/`PRICING_PUBLIC` — отдельный T-8.32a2 (тарифы скрыты).

## Корень дефекта
Профиль «Nur Aktionen» прятал только каталог, модули не ограничивал: быстрый старт включает
пресет вертикали (blog/crm/customer_account рекомендованы всем) → «Neuigkeiten», 👤, ЛК.
«Angebote» — легаси-пункт `NAV_ITEMS["offers"]` → главная (дубль логотипа и «Aktionen»).
Лёгкий кабинет по прямым адресам открывал полный (P7).

## Реестр `apps/core/packages.py`
`Package(key, lite, modules, cabinet_allow, storefront_hidden_pages)`:
- aktionen — модули {promotions, inbox, jobs, publishing, telegram}; страница `offers` скрыта;
- eintrag — то же + экраны ассортимента/импорта;
- laden — без потолка, поведение прежнее (замок паритета).
Потолок — одна строка в `modules.is_module_active` после core. Без БД, fail-open → laden.
Демо — гейт действует (демо не богаче реального бизнеса), освобождено только от лимитов.

## Инкременты
- **a** — реестр + потолок модулей + витрина (offers) + `package_report` + «Nicht im Paket» на
  странице модулей. Замки: вывод пакета; паритет Laden по 16 типам; Aktionen без blog/crm/
  customer_account/loyalty/orders; витрина без «Neuigkeiten»/«Angebote», с «Aktionen» и чатом;
  потолок не пишет в БД; golden/демо-меню зелёные.
- **b** — `PackageScopeMiddleware` (после TelegramLiteScope) + страница «nicht enthalten»
  (EXPECTED_UNLISTED) + LITE_NAV с «Nachrichten» + inbox в `TG_LITE_VIEWS` ∩ пакет + палитра
  по `view_allowed` + чистка ссылок лёгких шаблонов. Замки: обход резолвера (Aktionen вне списка
  → 403, Laden — ни одного); POST/fetch JSON 403; каждый `{% url %}` лёгких шаблонов ⊆ список;
  owner-only цел; вход обязателен.
- **c** — заявки в Aktionen (Liste без доски/счёта), Eintrag-экраны. После фидбэка пилота.

## Риски
Живые лёгкие бизнесы с данными в гаснущих модулях — `package_report` до деплоя (данные не
удаляются, при подъёме пакета видны снова). Агрегатор снимет листинги гаснущих модулей —
колонка в отчёте. Письма владельцу со ссылками на закрытые экраны — grep `reverse(` в
notifications/digest на этапе b.
