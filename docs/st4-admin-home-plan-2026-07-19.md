# ST-4 «Админ-хоум 5 хабов» — план (2026-07-19)

Этап B2 ТЗ `next-gen-master-tz-2026-07-19.md §3`: главная кабинета отвечает на
«что сегодня» без кликов — виджеты + 5 плиток-хабов + канбан (есть); сайдбар
5+Website; SVG-иконсет стартует здесь; classic_ui = прежний вид (Р7).
Разведка — фоновый Explore 2026-07-19 (карта точна, файл:строка в отчёте).

## 1. Решения

- **Разбивка на два инкремента.** **ST-4a ХОУМ**: виджеты «сегодня» +
  5 хаб-плиток + SVG-иконки + classic-гейт — чистая добавка, ничего не ломает.
  **ST-4b САЙДБАР** (5+Website, легаси в «Erweitert», лендинг Integrationen) —
  отдельным инкрементом с чекпоинтом владельца (перестройка навигации —
  owner-facing решение по виду).
- **Виджеты — `apps/core/dashboard.py::home_widgets(tenant)`** (рядом с
  dashboard_tiles; паттерн `digest.collect_digest`: per-module гейты +
  simple_hidden + fail-safe):
  1. **Umsatz**: сегодня + 7-дневный SVG-спарклайн —
     `RevenueEntry.filter(date__gte=today-6).values("date").annotate(Sum)`
     (гейт finance; первый чарт кабинета — инлайн `<polyline>`, утилита в том же
     модуле). Ссылка → /dashboard/finance/.
  2. **Abholbereit**: `Order.objects.filter(status="ready").count()` → ссылка
     `order-list?status=ready`; при активном booking — второй строкой pending
     из digest-паттерна.
  3. **Marketing-Puls (v1)**: Σ `Promotion.views` активных акций + кампании
     issued/redeemed (`CouponCampaign` annotate). Featured-показы (public-схема,
     `tenant_schema=connection.schema_name`) — ОТЛОЖЕНЫ в v2 (риск кросс-схемы,
     рекомендация разведки).
  4. **Bewertungen**: `reviews.services.owner_overview()` (avg/count/
     **unanswered** — «непрочитанных» нет, unanswered = честный прокси).
- **5 хаб-плиток `hub_tiles(tenant)`**: Bestellungen→`board` ·
  Angebot→`sellable-manage` · Marketing→`promotions:list` ·
  Integrationen→НОВЫЙ лёгкий лендинг `/dashboard/integrationen/` (карточки-
  ссылки на существующие точки: Zahlung&Versand, Telegram/Benachrichtigungen,
  Domains, Channel Manager (stays), Publishing — гейты по модулям; хаба-свода
  сейчас не существует — риск 3 разведки) · Einstellungen→`settings`; шестая
  широкая — «Website → Studio» (`site-home`). Плитки заменяют прежние
  task-плитки AB7 (их job-to-be-done уходит в виджеты+readiness; бейдж
  «Nicht ausgefüllt» переносится на хабы, где применимо).
- **SVG-иконсет (Р5, старт)**: партиал-спрайт `templates/tenant/_icons.html`
  (`<symbol id="ic-...">` × ~7: orders/offer/marketing/integrations/settings/
  website/star) + тег `{% icon "<key>" %}` в cabinet.py; подключение в
  `_base_dashboard.html`. Emoji сайдбара НЕ трогаем (полный переезд — v2,
  рассинхрон осознан концептом).
- **classic_ui (Р7)**: view отдаёт пустые widgets/hubs при classic (прецедент
  tiles/sections); вся новая разметка под `{% if not classic_ui %}`;
  classic-ветка шаблона не тронута.

## 2. ST-4b Сайдбар (после чекпоинта)

NAV_GROUPS → якоря Dashboard · Bestellungen(board) · Angebot(sellable) ·
Marketing(promotions) · Integrationen · Einstellungen(settings+site?) + Website;
Sortiment/Kunden/Finance/Analytics — в «Erweitert»-ящики соответствующих хабов
(HUB_TABS advanced; Kunden — вопрос владельцу: S4b-хаб сворачивать?). Бейдж
непрочитанного inbox переносится на хаб-пункт. Мобильный nav_primary — та же
5-ка. Все правки — modules.py NAV_GROUPS/NAV_TASK_LABELS + cabinet.py HUB_TABS,
механика готова (S1–S4).

## 3. Замки/приёмка

Виджеты уважают модульные гейты и simple_hidden (тест per-модуль); classic —
прежний вид байт-в-байт (замок-рендер); спарклайн не падает на пустой выручке;
Umsatz считает только сегодня/7 дней; плитка хаба ведёт на существующий URL
(smoke-reverse тест всех 6); Integrationen-лендинг показывает только активные
модули. Приёмка ТЗ: «хоум отвечает на "что сегодня" без кликов» ✅,
«classic_ui = прежний вид» ✅. Без миграций.
