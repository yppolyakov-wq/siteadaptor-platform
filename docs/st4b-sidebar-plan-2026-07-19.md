# ST-4b «Сайдбар: 5 хабов + Website» — план (2026-07-19, одобрен владельцем)

ТЗ: `st4-admin-home-plan-2026-07-19.md §2`. Сайдбар (пост-S1–S4 ~8-10 пунктов) →
**Übersicht · Verkäufe(board) · Angebote(sellable-manage) · Marketing(promotions)
· Integrationen · Einstellungen** + **Website**; Sortiment/Kunden/Finanzen/
Auswertungen уезжают в «Erweitert»-ящики хабов. Без миграций.

## §1 Точки изменения (разведаны)

- Сайдбар = `nav_groups` (modules.grouped_active_modules ← NAV_GROUPS +
  nav_items активных модулей) + спец-пункт «Angebote» (has_sellables, шаблон)
  + мобильный `nav_primary` (первые 4 nav_items). classic_ui в processor есть.
- Пункты сейчас из nav_items: dashboard/board/catalog/promotions/crm/analytics/
  finance/blog/site/settings/billing (+Funktionen/inbox-бейдж в шаблоне).
- Замки: `test_hub_tabs` (состав/порядок вкладок хабов), `test_st4_home`,
  `test_classic_ui`; сайдбар-рендер тесты хабов S1-S4.

## §2 Решение

1. **Новый резолвер `modules.sidebar_nav(tenant)`**: НЕ-classic → фикс-набор
   6+1 якорей (Übersicht, Verkäufe→board, Angebote→sellable-manage при
   has_sellables, Marketing→marketing-home (ST-6!), Integrationen→
   integrations-home, Website→site-home, Einstellungen→settings) с гейтами по
   модулям; classic → прежний `grouped_active_modules` (Р7, легаси цел).
   Шаблон сайдбара ветвит по формату (или единый формат список-групп, где
   новый вид = одна группа без заголовков).
2. **Переезд в Erweitert**: HUB_TABS — «Sortiment»(catalog:product-list) якорем
   в advanced хаба «sellables» (нужен HUB_TABS["sellables"]: Angebote-экран
   становится хабом: Angebote + Erweitert: Sortiment/Lager/Kategorien/Kombis/
   Import/Einkauf — БЫВШИЙ хаб catalog становится вкладками);
   «Kunden»(crm)+Nachrichten+Telegram — advanced-вкладками Marketing-хаба;
   Finanzen/Auswertungen — advanced Einstellungen-хаба (уже там были в группе).
   Все правки замков test_hub_tabs — синхронно, с осознанной записью.
3. **Бейдж непрочитанного inbox** — на якорь Marketing (был на Kunden).
4. **nav_primary (мобайл)** — та же 5-ка из sidebar_nav (не первые nav_items).
5. Marketing-якорь сайдбара ведёт на `marketing-home` (центр ST-6), а не на
   promotion-list (обновить NAV_TASK_LABELS не нужно — метка та же).

## §3 Риски

- test_hub_tabs жёстко фиксирует состав — правки замков только вместе с кодом,
  с комментарием «ST-4b осознанно».
- catalog-хаб: url_prefixes-гейт хаба должен остаться (страницы доступны по
  URL); «Sortiment» из сайдбара исчезает ТОЛЬКО в новом виде.
- classic_ui: прежний сайдбар байт-в-байт (замок-рендер classic).
- Простой режим (ui_mode=simple) и simple_hidden_modules — сохранить семантику
  (скрытие хабов у архетипов) в новом резолвере.

## §4 Инкременты

1. sidebar_nav + шаблон + classic-замок + мобайл.
2. HUB_TABS переезды (sellables-хаб, Kunden→Marketing-advanced) + бейдж +
   синхронные правки test_hub_tabs.
3. Тесты (новый вид/classic/simple/гейты) + i18n (новых msgid почти нет — метки
   реюзятся) + докблок.
