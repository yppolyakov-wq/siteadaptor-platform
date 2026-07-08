# Упрощение кабинета — план реализации (инкременты S1..Sn), 2026-07-08

Направление утверждено владельцем по макету (`admin-simplification-analysis §7`).
Идём инкрементами: ветка → локальный гейт → CI → FF-merge. Каждый — шиппабельный.

## Общий приём: «хаб = 1 пункт меню + tab-bar по под-страницам»
Переиспользуемый партиал `tenant/_hub_tabs.html` + тег `{% hub_tabs "<hub>" %}`
(реестр `HUB_TABS` в `templatetags/cabinet.py`): рендерит tab-bar по под-страницам
хаба, подсветка по текущему `nav`. Под-страницы остаются прежними вьюхами (низкий
риск) — меняется только: (а) сайдбар показывает ОДИН пункт хаба, (б) вверху страниц
хаба — общий tab-bar.

## S1 — хаб «Sortiment» (эталон, 5→1)  ← СТАРТ
- `_hub_tabs.html` + тег `hub_tabs` + `HUB_TABS["catalog"]` = Produkte / Kategorien /
  Lager / Kombi / Import (nav_key: catalog/categories/stock/combos/imports).
- Включить `{% hub_tabs "catalog" %}` в 5 страниц каталога.
- `modules.catalog.nav_items` → один `NavItem(product-list, "Sortiment", "catalog")`;
  url_prefixes не трогаем (middleware-гейт цел). NAV_TASK_LABELS: catalog→Sortiment.
- Тесты: сайдбар = 1 пункт каталога; каждая страница рендерит tab-bar + активный таб.

## S2 — хаб «Verkäufe» (доска-центр)
- Свести списки Bestellungen/Termine/Übernachtungen/Tickets/Aufträge в tab-bar доски
  (`/dashboard/board/` уже имеет вкладки по kind). Сайдбар: board + per-тип списки →
  один пункт «Verkäufe». Списки-вьюхи остаются (переход с карточки доски).

## S3 — хаб «Einstellungen» (портянка → табы + Erweitert)
- `settings.html` (10 секций) → tab-bar Kontakt&Zeiten / Recht / Zahlungen / Versand /
  Benachrichtigungen; ящик «Erweitert»: Sprachen/Medien/Domains/Funktionen/Abrechnung/Hilfe.
- Сайдбар: 10 settings-пунктов → один «Einstellungen» (+ Website остаётся хабом).

## S4 — хабы «Marketing» + «Kunden»
- Marketing: Aktionen/Reservierungen/Einlösen/Gutscheine/Treue/Kampagnen/Bewertungen → tab-bar.
- Kunden: Kontakte/Nachrichten/Newsletter → tab-bar.

## S5 — режим «Простой / Эксперт» (зонтик)
- Флаг `site_config["ui_mode"]` (без миграции; дефолт simple для новых, expert для
  существующих — обсудить). Тумблер в шапке кабинета. Простой: скрывает «продвинутые»
  хабы/табы (помечены `advanced`); Эксперт: всё. Модули по-прежнему на «Funktionen».

## S6 — реальные архетипы (миграция) + скрытие по архетипу
- Новые `business_type`: friseur/handwerker/werkstatt/events (+ маппинг демо-китов с
  «other»; обновить `recommended_for`/`suited_for`; jobs/events → recommended для своих).
  Существующие «other» остаются (или ручной ре-маппинг владельцем).
- Простой-режим прячет нерелевантные хабы по архетипу (Friseur без Sortiment/Lager,
  Hotel без корзины) — поверх готового `recommended_for`/middleware-гейта.

## S7+ — витрина-first ввод (L2) + простой мастер (L3)
- L2: «+ добавить» в секциях, инлайн категория/discount_percent/остаток/контакты.
- L3: мастер ≤5 шагов, не переспрашивать тип, один индикатор, убрать «обрыв», право.

## Риски/замки
- Свод nav-пунктов → проверять nav-тесты (`test_nav`/`test_modules`) на каждом шаге.
- Каждая правка шаблонов → `test_template_comments`; новые Tailwind-классы → `build:css`.
- Секции главной рендерят карточки → гейт включает `apps/tenants` (урок CI 1145).
