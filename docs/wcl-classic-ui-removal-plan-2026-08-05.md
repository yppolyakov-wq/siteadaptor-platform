# W-CL: снос classic_ui (решение владельца Р-1 «удалить», 2026-08-05)

Разведка — фоновый агент 2026-08-05 (полная карта в этом плане); контекст —
`cabinet-unification-plan-2026-08-05.md §4`. Порядок: W7 ✅ → **W-CL** → W8.

**Не путать:** `nav_style="classic"` (стиль ШАПКИ ВИТРИНЫ, NAV_STYLES
classic/centered/minimal — siteconfig, demo_kits, sitetemplates, storefront)
— НЕ ТРОГАЕТСЯ. Сносится только режим КАБИНЕТА `site_config["classic_ui"]`.

**Объём:** умирает ФЛАГ и вторая IA кабинета (classic-сайдбар с группами AB1,
classic-ветки вьюх/шаблонов, тумблер, endpoint). Легаси-СТРАНИЦЫ продаж
(board/order_list/календари) живут до W10 (схлопывание по паритету).

## §0. Решения по открытым вопросам разведки

1. **normalize:** ключ `classic_ui` ДРОПАЕТСЯ (прецедент `orders_view`,
   siteconfig ~:2220 + тест-замок «normalize drops retired key»).
2. **Simple-скрытие (§3.1 разведки) — переносим В ЭТОЙ ЖЕ волне**, не оставляя
   окно лжи UI: `hub_tabs` получает гейт `module_key in simple_hidden_modules(tenant)`
   (Finanzen/Auswertungen прячутся в Простом как табы), каталожным табам обоих
   хабов проставляется `module_key="catalog"` (core → is_module_active True,
   гейт активности не меняется; но архетип-скрытие catalog у friseur/hotel/… в
   Простом начинает работать в новом UI). Подсказки тумблера остаются правдой.
   Полная унификация «advanced=Experte» — W12, как планом.
3. **NAV_TASK_LABELS:** сузить до 4 живых ключей (board/dashboard/promotions/
   settings — читаются сайдбаром); лишние msgid в .po не трогаем (unused
   безвреден, гейт i18n_gap ловит только отсутствующие).
4. **NavItem/ModuleSpec.nav_items:** НЕ в этой волне — поглотит W8 (реестр).
   Тесты-замки `nav_items == ()` пока живут.
5. **context.nav_modules:** зачистить попутно (мёртвый ключ) + перецелить его тест.
6. **JS сайдбара:** обработчики `data-nav-group*`/localStorage групп и дубль
   `id="nav-empty"` вычищаются в том же шаге, что classic-ветка шаблона.
7. **HUB_TABS["board"]:** реестр урезается до `events:list`+`jobs:list`
   (4 записи навсегда покрыты covered); covered-логика упрощается до безусловной.
8. **Studio на public:** поведение уже «новый UI» (processor → {}); не меняется.
9. **Docs:** правило §8b (`studio-concept-2026-07-18.md`) официально отменяется
   пометкой + CLAUDE.md; сами ST-планы не редактируем (история).

## §1. Шаги (порядок безопасности; каждый — компилируем+тесты)

- **Шаг 1. Тумблеры UI:** карточка «Klassische Ansicht» (modules.html:41-55),
  подсказка на dashboard.html:95-104. Тесты тумблера — снять.
- **Шаг 2. Endpoint+маршрут:** set_classic_ui_view (views.py:2960-2977),
  urls_tenant.py:43,123-124 (строго после шага 1 — NoReverseMatch).
- **Шаг 3. Листовые гейты:** crm (LTV всегда + грид), sellable_manage (грид,
  удалить `_sellable_manage_row.html`), мастер looks_classic (Look-галерея
  всегда), Studio site_home (брендинг/рейка/лента/скрипт всегда), verkaeufe
  (без редиректа), dashboard-вьюха (widgets/hubs/sections всегда, CTA-гейт).
- **Шаг 4. Сайдбар:** _base_dashboard.html:46,65-110 → компакт безусловно;
  context nav_primary безусловно, ключи nav_groups/has_sellables/nav_modules
  удалить; modules.py: гейт :656 снять, grouped_active_modules/NAV_GROUPS/
  _GROUP_BY_KEY удалить, NAV_TASK_LABELS сузить; JS групп вычистить.
- **Шаг 5. Теги:** nav_task_label-тег удалить; covered безусловно; реестр
  board-хаба урезать; orders_view_switch: гейт только `tenant is None`.
- **Шаг 6. orders_view:** entry_url_name → `"verkaeufe"` (switch_options/
  create_option/resolve_view/default_view ЖИВУТ — их держат легаси-страницы и
  CTA главной).
- **Шаг 7. Ридер флага:** modules.classic_ui удалить; grep classic_ui пуст
  (кроме siteconfig-дропа и docs).
- **Шаг 8. normalize-дроп + simple-перенос (§0.2) + i18n:** осиротевшие msgid
  не блокер (makemessages пометит `#~`; вручную не чистим).
- **Тесты:** по карте разведки §4 — файл test_classic_ui удалить; отдельные
  classic-тесты снять; test_ui_mode переориентировать с grouped_active_modules
  на simple_hidden_modules + новый hub_tabs-гейт; test_orders_view/test_looks/
  test_presence подрезать. Каждое снятие — осознанное (замки легаси-контракта).

## §2. Критерии готовности

- `grep -rn "classic_ui\|looks_classic\|grouped_active_modules\|NAV_GROUPS" apps/ templates/ config/` → пусто.
- Простой режим в новом UI впервые честен: Finanzen/Auswertungen-табы и
  каталожные табы (по архетипу) скрываются; подсказка тумблера соответствует.
- Полный broad-прогон зелёный; снятые замки перечислены в build-log.
