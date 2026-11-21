---
name: sa-cabinet-screen
description: Кабинет владельца бизнеса siteadaptor-platform — навигация и якоря сайдбара, права сотрудников, модули и направления, новый экран, шторка (drawer), списки и фильтры, поверхность продаж «Verkäufe», карточка сделки, вьюхи и формы кабинета. Грузить ДО кода при любой правке nav_registry, permissions, view_perms, perm_grants, modules, directions, readiness, sales_page, list_filters, deal_card, drawer, static/js/cabinet.js, при новом маршруте под /dashboard/ и при редизайне экрана.
metadata:
  origin: project
---

# Кабинет: навигация, права, экран, шторка, «Verkäufe»

Чеклист нового экрана — `docs/cabinet-screen-dod.md`; слова кабинета —
`docs/cabinet-glossary.md`; контракт шторки — `docs/references/patterns/drawer.md`; все единые
точки — `docs/project-memory.md` §3; грабли целиком — `docs/pitfalls.md` §3. Здесь — что
звать и на чём уже ошибались. Дата у грабли — последнее срабатывание.

## Когда грузить
До плана и до кода: новый экран или маршрут кабинета, пункт меню, право или роль, модуль или
направление, список с фильтрами, шторка, вид «Verkäufe», карточка сделки, форма кабинета,
редизайн экрана.

## Экран в пяти строках
- Вход в экран — запись реестра навигации; сайдбар, подпункты, палитра Ctrl+K и подсветка —
  производные от него. Шесть якорей: Übersicht, Verkäufe, Sortiment, Marketing, Website,
  Einstellungen.
- Доступ — три слоя: пакет (`apps/core/packages.py::view_allowed`), право экрана
  (`view_perms.py::RULES`), модуль или направление. Меню прячет, сервер закрывает.
- Списки — строки без редактируемых полей; создание — шторкой, правка — страницей с вкладками.
- Одна шторка `<dialog id="sf-drawer">` на весь кабинет; без JS ссылка и форма работают как
  обычные страница и POST.
- Подпись пункта меню = `<h1>` страницы = строка глоссария; строки — немецкие msgid в пяти
  каталогах.

## Единые точки
**Навигация:**
- реестр — `apps/core/nav_registry.py::ANCHORS, ENTRIES, NavEntry, Anchor`; подпункты —
  `nav_registry.py::sidebar_children, visible_children, SUBMENU_GROUPS`; палитра —
  `nav_registry.py::palette_entries, palette_entries_for`;
- подсветка: вьюха отдаёт `nav`, якорь ищется в `nav_registry.py::ANCHOR_BY_NAV, anchor_for,
  anchor_for_tenant`;
- видимость пункта — `nav_registry.py::entry_visible, entry_gate, allowed_for_business,
  direction_active, anchor_visible`; скрытое пользователю — `nav_registry.py::hidden_for`;
- сборка меню для шаблона — `modules.py::sidebar_nav, owner_hidden_for`; заголовок страницы —
  тег `apps/core/templatetags/cabinet.py::nav_title` (`HUB_TABS` там — производная от
  `nav_registry.py::legacy_hub_tabs`); ссылка под пакет — фильтр `pkg_allowed` там же.

**Права:**
- реестр прав и ролей — `apps/core/permissions.py::PERMS, GROUPS, PRESETS, SENSITIVE`; проверка —
  `permissions.py::has_perm, effective, chrome_allows, for_role`;
- право каждого экрана — `apps/core/view_perms.py::RULES, Rule` (маркеры `FLOOR`, `OPEN`);
  проверки — `view_perms.py::allowed, url_allowed, query_allowed`; декоратор —
  `view_perms.py::perm_required`; вкладки по query — `view_perms.py::QUERY_RULES`;
- единственный писатель прав участника — `apps/core/perm_grants.py::set_member_permissions,
  set_member_role, revoke_member, invite_perms, join_from_invite` (предпросмотр `preview`,
  области `scopes_for`);
- доступ в кабинет и роль — `apps/core/roles.py::has_cabinet_access, is_owner, role_of`;
  owner-only префиксы — `apps/core/middleware.py::CabinetOwnerAccessMiddleware`.

**Модули, направления, готовность:**
- реестр модулей — `apps/core/modules.py::REGISTRY, ModuleSpec`; чтение —
  `modules.py::is_module_active, inactive_reason, active_modules`; единственный писатель —
  `modules.py::set_modules` (проверка `module_switch_problem`);
- «как продаёт бизнес» — `apps/core/directions.py::REGISTRY, is_active, active, choices_for`;
  писатель — `directions.py::set_state`;
- «готово к продаже» — `apps/core/readiness.py::REGISTRY, items_for, missing, is_done`; гейт
  касс — `readiness.py::require_sell, sell_allowed, SellBlocked`; сброс — `invalidate`.

**Продажи и сделка:**
- тело «Verkäufe» и главной — `apps/core/sales_page.py::body_context, heute_columns,
  visible_kinds, tab_descriptors, view_descriptors` (шаблон `templates/core/_sales_body.html`);
  виды — `sales_page.py::KIND_VIEWS, resolve_view, default_view`; фильтр в адресе —
  `sales_page.py::view_for_filters, honored_filters`; кнопка «＋» — `create_target,
  opens_in_drawer`; старые адреса — `sales_page.py::legacy_redirect`;
- карточка сделки всех видов — `apps/core/deal_card.py::card_context, calendar_html`
  (`templates/core/deal_card_base.html`);
- смена статуса — `apps/core/fsm.py::apply`; из доски, календаря и карточки —
  `apps/core/transactions.py::apply_action`; строка сделки — `transactions.py::transaction_for`.

**Списки, шторка, ввод:**
- строка фильтров — `apps/core/list_filters.py::build, Field, ListFilters, url_without`
  (`templates/core/_list_filter_bar.html`); служебные параметры — `list_filters.py::DROP`;
- шторка: сервер `apps/core/drawer.py::is_box, fragment, drawer_aware, drawer_next,
  open_after, with_param`; разметка `templates/core/_drawer.html`; клиент `static/js/cabinet.js`;
- `next=` — только `apps/core/owner_login.py::safe_next, local_next`; сумма из формы —
  `apps/core/money.py::parse_amount`;
- язык кабинета (отдельный от витрины) — `apps/core/i18n_cabinet.py::resolve_cabinet_locale,
  set_cabinet_locale, CABINET_PREFIXES`; список — `config/settings/base.py::CABINET_LANGUAGES`.

## Нельзя
- Менять состав и порядок якорей сайдбара: заморожен замком, мораторий владельца. Новая
  функция — подпункт существующего якоря.
- Добавлять экран мимо реестра: запись в `nav_registry` (хаб или палитра) либо осознанно в
  `apps/core/tests/test_x0_x7_locks.py::EXPECTED_UNLISTED` с категорией и комментарием.
- В редизайне трогать FSM, вьюхи, URL, `nav_registry`: редизайн — только рендер, и только
  после утверждения владельцем вариантов на канвасе.
- Менять статус сделки мимо FSM `apply`; владелец может лишь скрывать не-danger переходы,
  отмена видна всегда.
- Заводить второй список навигации, прав, модулей, фильтров, вторую шторку, третий хром;
  восстанавливать classic_ui, режим Простой/Эксперт, таб-бары хабов, ящик «Erweitert».
- Писать права участника, модули и направления мимо их писателей; дополнять замороженный
  эталон `apps/core/tests/legacy_role_gates.py` (новый экран — только в `view_perms`).
- Класть `<script>` и `on…=` во фрагмент шторки; слать из шторки `X-Requested-With`; писать
  свою проверку `next=` и свой разбор суммы.

## Грабли
Навигация и вход в экран:
- Новый беспараметрный маршрут кабинета: кроме `packages.py` и `view_perms.py` — навигация
  или `EXPECTED_UNLISTED`; POST-приёмник панели — в исключения с комментарием · посл. 2026-10-26.
- Пункт меню, ссылка, плитка проходят тот же гейт, что вьюха-цель (CRM при выключенном
  модуле — 404); палитра не ведёт в `@require_POST`-вьюху (405) · посл. 2026-08-19.
- Подпись пункта ≠ `<h1>` — красный замок; заголовок тегом `nav_title` · посл. 2026-10-23.
- Ссылка в кабинет из шаблона, открытого лёгкому пакету, — через `pkg_allowed` · посл. 2026-10-26.
- Фильтр в адресе обязан быть исполнен: вид, игнорирующий `?status=`/`?q=`, заменяется видом,
  который умеет (`view_for_filters`) · посл. 2026-08-19.

Права и роли:
- Меню прячет — не значит закрыто: главная `/dashboard/` открыта всем, а рисовала деньги;
  закрывать на сервере каждую поверхность с данными раздела · посл. 2026-10-25.
- Ролевой гейт — по ВСЕМ писателям; смешанные формы — по полям · посл. 2026-10-25.
- `@perm_required` на вьюхе ломает тесты, зовущие её пользователем без Membership: искать
  `views.<имя>(` по всем тестам и дать реальное членство · посл. 2026-10-25.
- Подмена `roles.is_owner` в тесте молчит после перехода на `has_perm`: реальная Membership
  или подмена `apps.core.permissions.effective` · посл. 2026-10-25.
- Запертое право держит свои requires; новый ключ пресета ломает тесты отзыва · посл. 2026-10-25.
- Проверка хрома в контекст-процессоре — в try/except, fail-closed; `modules_nav` отдаёт `{}`
  на схеме `public` · посл. 2026-10-25.
- Membership-middleware анонима не трогает: без `@login_required` — 200 · посл. 2026-08-03.
- Хелпер, вставленный между декоратором и вьюхой, «съедает» `@login_required` и
  `@transaction.atomic` · посл. 2026-10-24.

Формы и ввод:
- Форма из нескольких вкладок — одна форма; каждое поле под замок round-trip; скрытие только
  CSS, обязательное поле в скрытой вкладке молча отменяет отправку · посл. 2026-11-03.
- Снятый чекбокс не приходит: сентинел `*_present` у секции, приёмник пишет только пришедшее
  · посл. 2026-09-09.
- Decimal в `value=` локализуется («19,00»): `stringformat:'s'` · посл. 2026-11-03.
- Числа из POST — `re.fullmatch` по `[0-9]`, не `isdigit()`; pk — через разбор UUID, иначе 500
  вместо 404 · посл. 2026-10-25.
- «Создать и привязать» — в `transaction.atomic()` с `select_for_update()` и повторной
  проверкой внутри: двойной клик давал сироту · посл. 2026-10-25.

Шторка и вёрстка:
- `@drawer.drawer_aware` — внутренний декоратор, под `login_required`/`require_POST`; ответ без
  метки `fragment` клиент не вставит; у `[data-drawer-refresh]` обязателен id · посл. 2026-11-04.
- `next` во фрагменте — без `box=1`; обработчики — делегированием в `cabinet.js`, после
  перерисовки области слушать `sf:region-updated` · посл. 2026-11-04.
- Детали кабинета — только классы с префиксом `ui-`; поля ввода 16 px · посл. 2026-10-30.
- Замки конвенций экрана находятся только полным прогоном `apps/core` · посл. 2026-11-14.

## Что гейтить
- `uv run python scripts/preflight.py`; новый экран — весь `apps/core`:
  `uv run pytest apps/core -q -n 4 --reuse-db -p no:cacheprovider`.
- Навигация: `apps/core/tests/test_x0_x7_locks.py` (якоря заморожены; каждый экран в реестре
  или в `EXPECTED_UNLISTED`; owner-only скрыт у сотрудников и в палитре),
  `apps/core/tests/test_w8_nav_registry.py` (каждый адрес реестра резолвится, каждый `nav`
  имеет якорь, палитра полна и без дублей), `apps/core/tests/test_ka_w2_nav_locks.py` (у записи
  есть гейт, рабочий экран не только в палитре, подменю не длиннее `MAX_SUBMENU`),
  `apps/core/tests/test_nav_reachability.py`, `apps/core/tests/test_menu_label_equals_h1.py`.
- Права: `apps/core/tests/test_view_perms.py`, `apps/core/tests/test_staff_walk.py` (меню
  сотрудника прячет ровно то, что запрещает `view_perms`),
  `apps/core/tests/test_perm_grants.py`, `apps/core/tests/test_package_gate.py`,
  `apps/core/tests/test_orphan_decorators.py`.
- Шторка: `apps/core/tests/test_drawer.py`; JS и навигация — Playwright-смок стендом; шаблоны:
  `apps/core/tests/test_template_comments.py` и `scripts/i18n_quickcheck.py`.
- Тесты вьюх — `RequestFactory` и `TenantFactory(auto_create_schema=False)`, схема не `public`.

## Агенты ECC
`django-reviewer` — каждый срез; `security-reviewer` — права, роли, ввод, `next=`, деньги;
`a11y-architect` — новый элемент экрана и шторка; `e2e-runner` — правка `cabinet.js`, шторки
и навигации; `silent-failure-hunter` — действия с деньгами из шторки и карточки сделки;
`database-reviewer` — тяжёлые запросы списков и «Verkäufe».
