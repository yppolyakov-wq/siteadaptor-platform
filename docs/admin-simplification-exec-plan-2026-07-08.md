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

## S3 — хаб «Einstellungen» (свод сайдбара + Erweitert) ✅
- Сделано: сайдбар 10 settings-пунктов → 2 (Website остаётся отдельным + один хаб
  «Einstellungen»). `HUB_TABS["settings"]` расширен `advanced`-флагом (5-кортеж):
  прямые табы Einstellungen/Benachrichtigungen/Rechtstexte/Zusatzleistungen + ящик
  «Erweitert ▾» (Sprachen/Medien/Domains/Funktionen/Hilfe). `_hub_tabs.html` рендерит
  ящик `<details>` (open, если активна его вкладка). Тег `hub_tabs` вернул tabs/more_tabs.
- Отложено **S3b**: табификация самой длинной страницы `settings.html` (её form-секции
  Kontakt/Zeiten/Zahlungen/Versand в in-page табы) — отдельный инкремент, трогает форму.

## S4 — хабы «Marketing» + «Kunden»
- **S4a ✅ Marketing** — хаб-якорь на модуле promotions; promotions/reviews/loyalty/publishing
  сведены (nav_items=()), «Kampagnen» перенесён из CRM во вкладку хаба. HUB_TABS["marketing"]:
  прямые Aktionen/Bewertungen/Kampagnen/Gutscheine + Erweitert Reservierungen/Einlösen/
  Treuepunkte/Kanäle/Beiträge (гейт каждой вкладки по своему модулю). 9 страниц + тесты.
  ⚠️ Краевой случай: promotions выключен, reviews on → Bewertungen недоступен из сайдбара
  (только по URL). Чистое устранение — «группа=хаб» механика (roadmap-полиш, если нужно).
- **S4b — Kunden** (дальше): хаб-якорь на CRM; inbox/telegram сводятся; HUB_TABS["kunden"]
  Kontakte/Nachrichten/Telegram. 3 страницы.

## S5 — режим «Простой / Эксперт» (зонтик) ✅
- Сделано: флаг `site_config["ui_mode"]` (без миграции; **дефолт expert** — не ломает
  существующих). Хелперы `modules.ui_mode/is_simple`; `normalize` сохраняет ключ ТОЛЬКО
  при "simple" (golden-паритет). Тумблер «Ansicht: Einfach/Experte» на странице
  «Funktionen» (`modules_view` пишет ui_mode прямо в site_config, без normalize — прочие
  ключи целы). Простой: `grouped_active_modules` прячет `SIMPLE_HIDDEN_MODULES`
  ({finance, analytics}) из сайдбара (страницы остаются по URL). Эксперт: всё.
  `test_ui_mode.py`. Проверено рендером на тенанте shop (expert→скрытие→expert).
- Расширяемо: набор скрываемого в Простом (SIMPLE_HIDDEN_MODULES) + скрытие ХАБОВ по
  архетипу — доводится в S6 (Friseur без Sortiment/Lager и т.п.).

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
