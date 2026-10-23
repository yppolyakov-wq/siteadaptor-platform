# KA-12 · Волна 2 «Структура кабинета» — план исполнения (2026-10-23)

> Источник: `ka-12-master-plan §E8 + Волна 2`, `ka-4-structure-2026-10-23` (целевая карта §3,
> решения В-1…В-6 «по рекомендации», прил. A, замки §8). Объём: E8.1–E8.8, E8.11, E8.12.
> Миграций НЕТ (реестр навигации статичен; дефолты модулей действуют только на НОВЫЙ онбординг —
> `disabled_modules` живых тенантов не трогаем). Инвариант: только навигация/подписи/дефолты,
> FSM/данные/вьюхи бизнеса целы; каждый батч держит зелёными `test_nav_reachability`,
> `test_every_cabinet_screen_listed_or_consciously_excluded`, `test_t830_tg_session`, `test_staff_walk`.

## 0. Мораторий X7 и решения владельца (вопросов нет)
Замок `test_x0_x7_locks.py::test_sidebar_anchor_composition_is_frozen` — ровно 6 якорей. KA-4
(«Решения владельца 2026-10-23: В-1…В-6 — по рекомендации»): «Седьмой якорь «Finanzen» — только при
Profi Finanzen или включённой аналитике (мораторий X7 снимается ровно для него) · «Marketing &
Kunden» · блог выключен по умолчанию · «Board» → «Spalten» · часы/ресурсы/блокировки →
Einstellungen · `marketing-home` и `integrations-home` убираются.»
- **E8.3:** замок переписывается осознанно (7-й кортеж). Пакета «Profi Finanzen» в коде нет →
  гейт = модуль `finance` ИЛИ `analytics` (оба выключены по умолчанию у всех типов); появится
  пакет — заменить гейт в одном месте.
- **E8.6:** якорь «Marketing» остаётся (KA-4 §2 п.1 «Якоря те же шесть»), меняется только цель;
  `integrations-home` — не якорь, а подпункт настроек.

## Батч 1 — замки и каркас гейтов (E8.12 + инфраструктура E8.1), без видимых изменений
1. `NavEntry` += `universal` (причина «для всех»), `modules_any`, `direction` (`waren`/`gastro`);
   резолвер `direction_active(tenant, d)` (waren: модуль orders ИЛИ тип ∈ WAREN_TYPES ИЛИ есть
   активные товары — мемо на тенанте, fail-open; gastro: FOOD_TYPES). Общий предикат
   `entry_visible(e, tenant, owner_hidden)` из `modules.sidebar_nav` — для сайдбара,
   `settings_home`, палитры и замков.
2. Поле `group` → подзаголовок подменю; реестр `SUBMENU_GROUPS = {hub: ((key, label), …)}`.
3. Замки (сначала с базовой линией долга): `test_every_entry_has_gate` (`GATE_DEBT`),
   `test_submenu_group_size` (≤ 7), `test_menu_label_equals_h1` (`H1_DEBT` = прил. A),
   `test_sidebar_matrix_snapshot` (16 типов × якорь, снимок json), `test_no_work_screen_palette_only`.
4. Тег `{% nav_title "fallback" %}` — `<h1>` из записи реестра (подключение — батч 4).

## Батч 2 — гейты, «работа ↔ настройка», дефолты модулей (E8.1, E8.2, E8.7, E8.11)
5. E8.1: категории/подборки/импорт `direction="waren"`; наборы waren∪gastro; склад/закупки waren;
   хаб `catalog` (дубль `sellables`) удалить; палитра `promotions:reservation-list` → легаси-302 на
   `verkaeufe?tab=reservation`.
6. E8.2: `booking:resources`/`availability` → settings группа «Termine» (свои nav_key);
   `stays:channels` → «Zimmer»; дубль `ablaeufe` из board удалить (кнопка тулбара VK-2 остаётся);
   `verkaeufe?tab=kunden` из подменю убрать (вкладка остаётся); `extras` → sellables с
   `modules_any=(booking, stays, events)`.
7. E8.7: `blog.recommended_for=()`; демо-киты с блогом получают `blog` в `enable_modules`.
8. E8.11: `events` += tour_operator, `booking` −= hotel; hotel-кит включает booking явно.
9. Осознанные переписки: test_modules (таблица дефолтов), test_blog, test_packages,
   test_sidebar_st4b, test_x4_navigation, test_hub_tabs, test_w8_nav_registry, test_x5_settings,
   test_cabinet_review_fixes (`TAB_GROUPS` → `SUBMENU_GROUPS`); обнулить `GATE_DEBT`. Ops:
   `seed_demo_tenants --group all --changed --jobs 3`.

## Батч 3 — разделы и якоря (E8.3, E8.4, E8.6)
10. `Anchor.targets` + `anchor_target(a, tenant)` — первый активный экран (сайдбар, палитра, подсветка).
11. E8.6 Marketing: якорь → `inbox:list` (targets inbox/promotions/reviews/crm), подпись «Marketing
    & Kunden»; `marketing-home` → 302 с GET-carry (`legacy_redirect`), шаблон удалить, модуль
    `marketing_home.py` остаётся для главной; переписать test_marketing_home + замки X0.
12. E8.6 Integrationen: `integrations-home` → 302 на `notifications-settings`; карточки статусов и
    «Eigener Telegram-Bot» → страница «Kanäle & Benachrichtigungen»; ссылки: platform_bot/menu.py,
    notifications.html, lite_visibility.html (через `lite_allowed`), settings_home, settings_hints;
    переписать test_w9_integrations, test_t829_integrations, test_modules.
13. E8.4: подзаголовки Marketing — Kunden (Nachrichten · Kunden · Bewertungen) · Aktionen (Aktionen ·
    Kampagnen · Aktionstypen · Einlösen · Gutscheine · Treuepunkte) · Reichweite (Newsletter ·
    Beiträge · Kanäle · Blog · Stadtportal); Telegram-бот → настройки; сайдбар печатает
    подзаголовок при смене группы.
14. E8.3: хаб `finance` (Zahlungen · Auswertungen · Journal · Berichte · Rechnungen · Ausgaben ·
    Ergebnis · Offene Posten · Bank); 7-й якорь «Finanzen» только при finance|analytics, иначе дети
    — группой «Zahlen & Finanzen» в Einstellungen; подсветка с фолбэком; замки
    `test_finance_anchor_hidden_by_default` / `…_shown_with_analytics`; на телефоне — в «Mehr».
15. Группы Einstellungen: Geschäft · Verkauf · Termine · Zimmer · Kanäle & Benachrichtigungen ·
    Zahlen & Finanzen · System; `settings_home._GROUPS` из реестра.

## Батч 4 — имена и телефон (E8.5, E8.8)
16. E8.5: подписи по KA-4 §5 (Küche · Blog · Kanal-Manager · Zahlarten & Lieferung · Kanäle &
    Benachrichtigungen · Kunden), «Board» → «Spalten»; 30 пар прил. A → `{% nav_title %}`;
    `H1_DEBT` пусто; msgid × 5; глоссарий += правило «подпись = h1 = глоссарий».
17. E8.8 таб-бар: Übersicht · Verkäufe · ＋ · Nachrichten · Mehr, подписи под иконками, «＋» →
    `sales_page.create_target`, бейдж inbox; замок test_pilot_e_phone; стенд 390 px; `app.css`.

## Риски
- 302 вместо удалённых страниц (закладки/письма) → `legacy_redirect` + `EXPECTED_UNLISTED` [302].
- Палитра: дедуп (url_name, query) уже есть; динамические цели якорей — reachability-замок.
- Mini App: ссылки только через `lite_allowed` (`test_t830_tg_session`).
- «Waren» не должен прятать Kategorien у типа с товарами (страховка по наличию товаров).
- Подсветка после переездов — свои nav_key; замок W8 «каждый nav-литерал имеет якорь».
- Дефолты модулей — только новый онбординг; демо пересевом `--changed`.
