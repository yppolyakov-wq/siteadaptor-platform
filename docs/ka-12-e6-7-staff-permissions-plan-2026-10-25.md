# KA-12 E6.7 — настраиваемые права сотрудников («Mitarbeiterrechte»)

**Запрос владельца (2026-10-25):** «для сотрудников нужно настраиваемые права, который выдает администратор». Уточнение: система общая для всего кабинета (Verkäufe, Sortiment, Marketing & Kunden, Website, Finanzen, Einstellungen, лёгкий кабинет, Mini App). Нужны права и на просмотр, и на правку. Любой будущий экран регистрирует своё право.

## 0. Что есть сегодня (разведка по коду)

- `apps/core/models.py::Membership` — OneToOne на user; роли owner, admin, staff. Других полей нет. Последняя миграция `core/0012` → новая будет **`core/0013`**.
- `apps/core/roles.py` — `role_of`, `has_cabinet_access`, `is_owner`, `can_edit_policy` (owner+admin), `can_export_finance` (owner+admin), декораторы `owner_required` и `finance_export_required` (ставят `_required_role` для замка E11.2), `OWNER_ONLY_PREFIXES` (21 префикс), `FINANCE_EXPORT_PREFIXES` (3).
- `apps/core/middleware.py::CabinetOwnerAccessMiddleware` — гейт по префиксам в `__call__`.
- **Ролевые проверки внутри экранов** (их тоже надо перевести на права):
  - `booking/views.py`: `_can_edit_policy` — правила отмены, правка чужих заметок мастера (`:353`); `_may_close_business` (`:737`, только owner).
  - `stays/views.py`: `RATE_EDIT_ACTIONS` (`:832`, `:906`), `can_price` (`:944`), `can_edit_prices` (`:1363`).
  - `stays/price_calendar_views.py:41`.
  - `core/refunds.py::may_refund` → `transactions.apply_action:483` — возврат при отмене (owner+admin).
  - `core/deal_card.py`: `_refund_form` (`:172`, только owner — возврат переплаты) и `_advance` (`:359`, счёт на предоплату — owner+admin).
  - `core/views.py`: банк/IBAN в оплате (`:1221`), `deal_refund` (`:6415`), `platform_bot_connect/disconnect` (`:6126`, `:6148`), уведомления Telegram (`:6031`), `sales_export_csv` (`:4888`), `betriebsferien` (`:6476`), `_gbp_hours_link`, `palette_search(owner=…)` — маскировка контактов.
  - `orders/views.py:683` — IBAN Vorkasse.
  - `finance/views.py`: `full_search` (`:580`), `credit_form` (`:669`, `:691`), маскировка контактов (`:814`, `:851`), три выгрузки (`:434–479`), банк (`:296`).
  - `crm/views.py`: `customer_export_csv` и три DSGVO-вьюхи (owner).
  - `events/views.py`: отмена события (`:162`, owner) и ростер (`:722`, owner).
  - `imports/views.py:274` — импорт с сайта.
  - `publishing/views.py` — `can_manage`.
  - `aggregator/owner_views.py` — статистика Stadtportal.
  - `promotions/views.py:1085`.
  - `lite_cabinet.py:93` и `:277`.
  - `templatetags/cabinet.py`: `cab_is_owner`, `cab_can_export_finance`.
  - `modules.owner_hidden_for` и `nav_registry.owner_only` / `entry_visible` (скрытие пунктов меню).
- **Не затрагиваем:** `community/access.role_of` — это роль участника пространства заезда, а не сотрудника. В E6.7b нужно отдельно проверить, как там определяется `STAFF`; если он выводится из `has_cabinet_access`, прицепить право `sales_view`.
- **Замки:** `apps/core/tests/test_staff_walk.py` (E11.2: обход всех экранов ролью; ожидания выводятся из `OWNER_ONLY_PREFIXES` и `_required_role`), `test_menu_label_equals_h1.py`, `test_ka_w2_finance_anchor.py`.
- **Mini App:** `tg_login.TG_LITE_VIEWS` — белый список экранов, сессия Telegram принадлежит владельцу (`OwnerTelegramLink.user_pk`).
- **Z-5 (стойка отеля), план §«Права check-out»** ждёт этот инкремент.

## 1. Модель прав

Три уровня:

1. **Вход в кабинет** — как сейчас (`has_cabinet_access`, fail-closed).
2. **Права** (`Perm`) — выдаются и отзываются. У ключа есть подпись на немецком, группа, описание, при необходимости зависимость `requires` (правка подразумевает просмотр) и пресеты по ролям.
3. **Inhaber-Vorbehalt** — бизнес-уровень, который НЕЛЬЗЯ выдать никому, включая admin. Это не права, а «пол» системы:
   - Abo & Rechnung (`/dashboard/billing/`);
   - Recht & Steuern, Impressum-данные лёгкого кабинета (`/dashboard/recht/`, `/dashboard/geschaeft/`);
   - банковские реквизиты IBAN/BIC/Kontoinhaber (`orders:save_payment…`, `core/views:1221`);
   - роль owner: назначить, передать владение, понизить последнего владельца;
   - удаление бизнеса;
   - импорт с чужого сайта (`/imports/website/` — согласие правообладателя, T-8.27).

### 1.1 Реестр прав — `apps/core/permissions.py` (новый)

Пресеты: **A** = admin, **S** = staff. Сокращение «всем» = A+S. «Сегодня» — текущее поведение, пресет ему равен (паритет).

| Ключ | Подпись (DE) | Группа | Что покрывает (по коду) | Сегодня | Пресет A / S |
|---|---|---|---|---|---|
| `sales_view` | Verkäufe ansehen | Verkäufe | Verkäufe, Heute, доска, календари (Belegungsplan, Tagesplan, Auftragsbuch), карточки сделок, Zusatzverkäufe, Lieferungen, KDS | всем | ✓ / ✓ |
| `sales_edit` | Verkäufe bearbeiten | Verkäufe | смена статуса (`kanban_action`, `apply_action`), ручные брони и заказы, клиент, внешний номер, связи сделок, массовая смена статуса, правка состава заказа; requires `sales_view` | всем | ✓ / ✓ |
| `sales_cancel` | Stornieren & No-Show | Verkäufe | переходы в роль cancelled или no_show (проверка в `transactions.apply_action` по роли цели) | всем | ✓ / ✓ |
| `sales_discount` | Rabatte auf Verkäufe | Verkäufe | `deal_discount_edit`, скидка в смете | всем | ✓ / ✓ |
| `frontdesk` | Check-in / Check-out | Verkäufe | стойка Z-5: заселение и выезд, оплата при выезде (новое; пресет согласовать с Z-5) | — | ✓ / ✓ (рекомендация) |
| `money_refund` | Geld bei Storno erstatten | Geld | возврат при отмене (`refunds.may_refund`), возврат долей рассрочки | A | ✓ / — |
| `money_correct` | Erstattung & Minderung | Geld | `/dashboard/erstattung/`, `deal_refund`, `_refund_form` (переплата), Minderung | только owner | — / — |
| `processes_edit` | Abläufe & Status anpassen | Verkäufe | `ablaeufe`, `status_labels_save`, `transitions_save`, `status_manager_save`, `board_settings`, панель «Anfrage-Formular» | всем | ✓ / ✓ (В-3) |
| `catalog_edit` | Sortiment bearbeiten | Sortiment | товары, услуги, номера, события, туры, наборы, категории, видимость, «распродано», варианты и опции, Teacher, Pässe, Extras | всем | ✓ / ✓ |
| `prices_edit` | Preise, Tarife & Stornoregeln | Sortiment | `can_edit_policy`, `RATE_EDIT_ACTIONS`, price-calendar, NightRate, сезоны, Kurtaxe, правила отмены услуги, правка чужих заметок мастера (`booking:353`) | A | ✓ / — |
| `stock_edit` | Lager & Einkauf | Sortiment | `stock`, `purchasing`, Mängelanzeige, Produktion, импорт CSV (`imports:start`) | всем | ✓ / ✓ |
| `events_cancel` | Veranstaltung absagen | Sortiment | `event_action target=cancelled` (массовые возвраты) | только owner | — / — |
| `customers_view` | Kunden & Nachrichten | Marketing & Kunden | CRM-список, карточка, фирмы, inbox (чтение и ответ), заметки клиента | всем (контакты маскированы) | ✓ / ✓ |
| `customers_contacts` | Kontaktdaten vollständig sehen | Marketing & Kunden | маскировка e-mail/телефона (`palette_search`, `finance._customer_context`, `customer_search`); requires `customers_view` | только owner | — / — |
| `pii_export` | Exporte mit Personendaten | Marketing & Kunden | `/crm/export.csv`, `/dashboard/verkaeufe/export.csv`, `/dashboard/stays/berichte/export.csv`, ростер события | только owner | — / — |
| `customers_dsgvo` | Datenschutz-Anfragen (Auskunft/Löschung) | Marketing & Kunden | `customer_dsgvo`, `_export`, `_erase` | только owner | — / — |
| `marketing_edit` | Aktionen & Marketing | Marketing & Kunden | акции (вкл. Schnell-Aktion), типы, кампании, ваучеры (создание), лояльность, newsletter, отзывы (ответы), публикации, Finder | всем | ✓ / ✓ |
| `vouchers_redeem` | Einlösen am Tresen | Marketing & Kunden | `promotions:redeem`, сканер, выдача «Zurücklegen» | всем | ✓ / ✓ |
| `channels_manage` | Externe Kanäle verbinden | Marketing & Kunden | Google (GBP, Merchant), `channels/config|connect|toggle`, свой Telegram-бот и общий бот, `telegram-aktivieren` | только owner | — / — |
| `portal_stats` | Stadtportal-Statistik | Marketing & Kunden | `/dashboard/stadtportal/`, ссылка в акциях | только owner | — / — |
| `site_edit` | Website gestalten | Website | Studio, Design, страницы, меню, SEO, медиа, превью и черновики | всем | ✓ / ✓ |
| `domains_manage` | Domains verwalten | Website | `domains`, `domain_add/verify/remove` | всем | ✓ / ✓ (В-3) |
| `finance_view` | Finanzen & Auswertungen ansehen | Finanzen | journal, rechnungen (список и деталь), ausgaben, ergebnis, offene, payments-page, analytics, stays-отчёты, Marketing-Puls | всем | ✓ / ✓ → **E6.7f: — для S** (В-2) |
| `invoices_edit` | Rechnungen & Ausgaben bearbeiten | Finanzen | счёт из сделки, отметка «bezahlt», Mahnung, Ausgaben, Eingangsrechnung; requires `finance_view` | всем | ✓ / ✓ |
| `accounting` | Buchhaltung (Export, Korrektur) | Finanzen | DATEV и журнал CSV (`FINANCE_EXPORT_PREFIXES`), Gutschrift/Storno/Rechnungskorrektur (`credit_form`), Anzahlungsrechnung (`_advance`), полный поиск получателя (`full_search`); requires `finance_view` | A | ✓ / — |
| `bank_view` | Bankauszüge | Finanzen | `/dashboard/finance/bank/` (IBAN и плательщики) | только owner | — / — |
| `settings_edit` | Einstellungen bearbeiten | Einstellungen | Mein Geschäft (кроме права и IBAN), Sprachen, Benachrichtigungen (матрица), Zahlung & Lieferung (тумблеры), Ressourcen, Öffnungszeiten, Channel-Manager, Google-Bewertungen | всем | ✓ / ✓ |
| `modules_manage` | Funktionen ein/aus | Einstellungen | `modules_view` (POST), `integrations_telegram_activate` (сейчас owner-floor → право) | всем (модули) | ✓ / ✓ (В-3) |
| `business_close` | Betriebsferien (ganzes Geschäft) | Einstellungen | `/dashboard/settings/betriebsferien/`, `_may_close_business` | только owner | — / — |
| `team_manage` | Team & Rechte verwalten | Einstellungen | экран команды: инвайт, права, отзыв (с ограничениями §3) | только owner | **✓** / — (В-1: это и есть запрос «выдаёт администратор») |

Итого 30 ключей в 7 группах: Verkäufe · Geld · Sortiment · Marketing & Kunden · Website · Finanzen · Einstellungen. Это больше, чем 8–15 из исходной оценки, но владелец уточнил, что система общая. Для UI их сворачивают шаблоны ролей (§5).

### 1.2 Экраны «для всех» — `OPEN_TO_ALL`

Явный список с причиной (паттерн `EXPECTED_UNLISTED` из X7): `dashboard`, `einstellungen-home` (обзор; сами плитки скрываются по правам), `palette_search`, `set-cabinet-lang`, `support:help`, `account_*` (свой пароль и выход), `tg-*`, `owner-confirm-resend`, `team-join` (публичный путь), Studio-превью, если оно не пишет. Новый экран обязан выбрать: право или запись здесь.

### 1.3 Покрытие разделов `nav_registry` (ответ на уточнение)

- **Verkäufe:** `verkaeufe`, `stays:checkins`, `orders:kitchen`, `orders:deliveries`, `verkaeufe-zusatz`, `orders:table-qr` → просмотр `sales_view`, POST по смыслу (`sales_edit`, `sales_cancel`, `frontdesk`). Table-QR — `settings_edit`.
- **Sortiment:** `sellable-manage`, `booking:services`, `stays:units` → `catalog_edit` (просмотр открыт, так как вход в кабинет уже подразумевает видимость ассортимента). `stays:price-calendar` → просмотр всем, запись `prices_edit` (как Z-4). `events:list`, `tour-list`, `teacher-list`, `booking:passes`, `combo-list`, `category-list` → `catalog_edit`. `stock`, `purchasing`, `imports:start` → `stock_edit`. `imports:website` → Vorbehalt.
- **Marketing & Kunden:** `inbox:list`, `crm:*` → `customers_view`. `promotions:*`, `reviews:list`, `publishing-posts`, `promotions:newsletter`, `finder-settings` → `marketing_edit`. `promotions:redeem` → `vouchers_redeem`. `portal-stats` → `portal_stats`. `channels`, `gbp-*` → просмотр `marketing_edit`, подключение `channels_manage`.
- **Website:** `site-home` и Studio, `seo`, `media`, `design`, `menu` → `site_edit`. `domains` → `domains_manage`.
- **Finanzen:** `finance:*` → `finance_view` / `invoices_edit` / `accounting` / `bank_view` (см. таблицу). `payments-page`, `promotions:analytics`, `stays:reports` → `finance_view`.
- **Einstellungen:** `settings`, `languages`, `notifications-settings`, `payment-settings`, `extras`, `booking:resources`, `booking:availability`, `stays:channels`, `google-reviews-settings`, `telegram-settings` (экран статуса) → `settings_edit`. `ablaeufe` → `processes_edit`. `modules` → `modules_manage`. `team` → `team_manage`. `betriebsferien` → `business_close`. `legal-docs`, `billing`, `billing-payments` → Vorbehalt.
- **Лёгкий кабинет** (`lite_cabinet.py`): `lite-business` → Vorbehalt (Impressum). `lite-share`, `lite-visibility` → `marketing_edit`. `lite-requests` → `sales_view`. Лёгкие формы акций → `marketing_edit`.
- **Mini App:** `TG_LITE_VIEWS` ∩ права. Сессию сегодня получает только владелец, поэтому на практике ничего не меняется. Но `TelegramLiteScopeMiddleware` и белый список проверяются ДО права — замок «белый список не расширяет права». Вход сотрудника через Telegram — вне объёма, это отдельное решение.

## 2. Хранение

**Рекомендация: дельта относительно пресета роли, а не полный набор.**

- `core/0013`: `Membership.perm_grants = JSONField(default=list, blank=True)` и `Membership.perm_denies = JSONField(default=list, blank=True)` (либо один JSON `permissions = {"grant": [...], "deny": [...], "template": "rezeption"}` — проще для миграции и normalize; **рекомендую один JSON `permissions`**, default=dict).
- Миграция только аддитивная: в Postgres 11+ константный default означает быстрое добавление, без бэкфилла. Пустой dict = «чистый пресет роли» → паритет без data-шага.
- **Почему дельта.** Новое право, добавленное в будущем, получает пресет роли и у уже настроенных сотрудников. Без этого новый экран молча закрылся бы у всех, кого владелец когда-то трогал. Решения владельца при этом сохраняются: явный deny остаётся deny.
- Эффективные права: owner → все ключи реестра; иначе `(PRESET[role] ∪ grant) − deny − OWNER_FLOOR`, затем замыкание по `requires` вниз (нет `sales_view` → нет и `sales_edit`).
- `normalize_permissions(role, raw)`: неизвестные ключи отбрасываются; ключи пола отбрасываются; grant, совпадающий с пресетом, и deny ключа, которого нет в пресете, схлопываются. Хранится минимальная дельта.
- Роли остаются три. «Шаблоны ролей» (Rollenvorlagen) — это не новые роли, а именованные дельты поверх staff (§5). `template` хранится только для подписи в UI.
- **Шаблон схемы.** D-1 `_template`: после деплоя `ensure_template_schema` пересоберёт шаблон (сверка структуры уже встроена); проверить на стенде.

## 3. Кто выдаёт (правила против эскалации)

Сервис `apps/core/permissions.py::set_member_permissions(actor, member, keys, template=None)` — единственный писатель:

1. Actor-owner может всё, кроме изменения собственных прав (у owner их нет — у него всё) и кроме пола (§1).
2. Actor-admin с `team_manage`:
   - правит **только staff** (не owner, не других admin, не себя);
   - может выдать только ключи, которые есть у него самого: `new_keys ⊆ effective(actor)`, иначе 403 и запись в audit;
   - может отозвать у staff любые ключи (отзыв не даёт эскалации);
   - приглашает только staff (роль admin выдаёт только owner);
   - отзывает доступ только у staff.
3. Роль admin назначает только owner, роль owner — никто через этот экран (передача владения — Vorbehalt, вне объёма).
4. Сохранение — в `transaction.atomic` + `select_for_update()` строки Membership, затем normalize, затем `update_fields=["permissions", "updated_at"]` (targeted-write).
5. Действует сразу: эффективные права считаются на каждый запрос (кэш только на объекте request и user внутри запроса), поэтому отзыв срабатывает на следующем же запросе. Сессии сбрасывать не нужно.
6. Инвайт: payload Redis-токена += `perms` (дельта) и `inviter_pk`. При выдаче — проверка ⊆ прав приглашающего. При принятии (`team_join` POST) — повторная проверка против прав приглашающего НА МОМЕНТ принятия. Если его понизили или удалили, лишние ключи отбрасываются; если приглашающий больше не owner или admin с `team_manage`, приглашение недействительно (fail-closed).
7. Понижение admin в staff или отзыв у admin права `team_manage` НЕ каскадирует на выданное им ранее. Это осознанно, поясняется в UI («Rechte bleiben, bis Sie sie ändern»).
8. Доступ admin к экрану команды. Сейчас `/dashboard/settings/team/` в `OWNER_ONLY_PREFIXES`. После E6.7b префикс уходит из списка пола, вьюха получает `@perm_required("team_manage")`. Admin видит всех участников, но кнопки правки — только у staff. Контакты owner показываются (это его коллеги). Последний-владелец-гарды остаются.

## 4. Единый резолвер и перевод проверок

### 4.1 API (`apps/core/permissions.py`)

- `PERMS: dict[str, Perm]`, `GROUPS`, `OWNER_FLOOR`, `PRESETS = {"admin": frozenset(...), "staff": frozenset(...)}`, `ROLE_TEMPLATES`.
- `effective(user) -> frozenset` — одна выборка Membership, мемо на `user._cab_perms` (переживает только текущий запрос, поскольку `request.user` новый на каждом запросе).
- `has_perm(user, key) -> bool`. Неизвестный ключ — `ImproperlyConfigured` в DEBUG и тестах (ловит опечатки), в проде — `False` + `logger.error` (fail-closed). Аноним или нет Membership → False. Owner → True для любого зарегистрированного ключа.
- `is_owner` остаётся только для Vorbehalt (пол).
- `perm_required(key, *, write=None)` — декоратор: GET проверяет `key`, POST, PUT и DELETE — `write or key`. Ставит атрибуты `_required_perm` и `_required_write_perm`. Ответ 403 рендерится `tenant/403_perm.html`: «Dafür fehlt Ihnen das Recht „<Label>“. Bitte wenden Sie sich an den Inhaber.»
- `owner_floor_required` — переименованный `owner_required` для пола; `_required_role` сохранить для обратной совместимости замков, пока они не переписаны.
- **Совместимость:** `can_edit_policy(u)` → `has_perm(u, "prices_edit")`; `can_export_finance(u)` → `has_perm(u, "accounting")`; `refunds.may_refund(u)` → `has_perm(u, "money_refund")`. Старые имена остаются тонкими алиасами с пометкой deprecated на один инкремент, затем grep-замок «нет вызовов».

### 4.2 Middleware

В `CabinetOwnerAccessMiddleware` добавляется `process_view(request, view_func, …)`: Django передаёт сюда уже найденную вьюху, поэтому пути с uuid посередине (ростер, сделки) тоже покрыты. Порядок проверок:

1. `has_cabinet_access`;
2. пол (`_owner_floor` на вьюхе ИЛИ префикс из `OWNER_FLOOR_PREFIXES` — урезанный `OWNER_ONLY_PREFIXES`, только Vorbehalt);
3. `_required_perm` / `_required_write_perm` (с учётом `functools` unwrap — `__wrapped__`).

`OWNER_ONLY_PREFIXES` и `FINANCE_EXPORT_PREFIXES` сворачиваются: префиксы, ставшие правами, переходят в декораторы вьюх. `required_role_for_path` → `required_perm_for_path` для замка E11.2. Вьюха проверяет право и сама, через декоратор, потому что прямые вызовы в тестах идут мимо middleware (известная грабля W9-10).

### 4.3 Проверки внутри экранов → `has_perm`

Перечень из §0 с целевыми ключами:

- `stays.RATE_EDIT_ACTIONS`, `can_price`, `can_edit_prices`, price-calendar → `prices_edit`.
- booking `_can_edit_policy` → `prices_edit`; `_may_close_business` → `business_close`.
- `apply_action`: возврат → `money_refund`; переход в cancelled или no_show → `sales_cancel` (НОВОЕ правило, по умолчанию у всех → паритет); `frontdesk` — для Z-5.
- `deal_card._refund_form`, `deal_refund` → `money_correct`; `_advance` → `accounting`.
- Маскировка контактов: `finance._customer_context`, `customer_search`, `palette_search` → `customers_contacts`.
- `finance.full_search`, `credit_form` → `accounting`.
- `events.event_action cancel` → `events_cancel`.
- `publishing.can_manage`, `channels`, `platform_bot_*` → `channels_manage`.
- `promotions:1085` (ссылка на статистику портала) → `portal_stats`.
- `notifications:6031` (привязка Telegram) → `channels_manage`.
- IBAN (`orders:683`, `core:1221`) → пол (Vorbehalt).
- `imports:274` → пол.
- `lite_cabinet:93/277` → пол или `marketing_edit` по экрану.

## 5. UI экрана команды

- `/dashboard/settings/team/` — список участников: роль, сводка («12 von 30 Rechten», имя шаблона) и кнопка «Rechte bearbeiten», если actor может править этого участника.
- Новый экран `/dashboard/settings/team/<uuid:pk>/rechte/` (`team-rights`, `@perm_required("team_manage")`; плюс запись в `nav_registry` с `palette_only` или в `EXPECTED_UNLISTED` с причиной — чеклист `cabinet-screen-dod.md`):
  - сверху «Vorlage»: кнопки шаблонов «Wie Admin», «Verkauf & Theke», «Empfang/Rezeption» (`sales_*`, `frontdesk`, `vouchers_redeem`, `customers_view`), «Küche» (`sales_view`, `sales_edit`), «Buchhaltung» (`finance_view`, `invoices_edit`, `accounting`, `sales_view`), «Nur ansehen» (`sales_view`, `finance_view` по В-2). Клик только отмечает чекбоксы на клиенте (без JS — POST `apply_template`), сохраняет «Speichern»;
  - `<fieldset>` на группу с `<legend>`; чекбокс, `<label>` и описание через `aria-describedby`; пара «ansehen / bearbeiten» в одной строке. Отметка «bearbeiten» отмечает и «ansehen»; снятие «ansehen» снимает «bearbeiten». Сервер дублирует это через `requires`, поэтому без JS работает так же;
  - ключи, которых нет у actor-admin, — `disabled` с подсказкой «Dieses Recht haben Sie selbst nicht». Сервер всё равно отбрасывает их (UI — не гейт). Disabled-чекбоксы не отправляются, поэтому сохранение берёт только РАЗРЕШЁННОЕ подмножество, а остальное сохраняет прежним — иначе admin молча снимал бы права, которые выдал owner. Состав формы фиксирует сентинел `perms_present` (класс W0);
  - блок «Nur Inhaber» (read-only) — список Vorbehalt, чтобы было видно, что это не забыто;
  - «Verlauf»: последние 50 событий `team.*` из audit (кто, кому, +/− ключи, когда).
- Инвайт: та же форма прав (свёрнутая) + выбор шаблона; admin видит роль только staff.
- Мобайл: поля 16px, «Speichern» над таб-баром (E6 батч E), без горизонтального скролла.
- Аудит: `audit_event(action="team.perms", resource_type="membership", resource_id=pk, actor, changes={"grant": [...], "revoke": [...], "template": ..., "by_role": actor_role})`. Отказ в эскалации → `team.perms_denied`. Персональных данных в changes нет.

## 6. Скрытие в кабинете (сервер — источник истины)

- `NavEntry.owner_only: bool` → `NavEntry.perm: str = ""` (+ `owner_floor: bool`). `entry_visible(entry, tenant, user_perms)`. `modules.owner_hidden_for` → `perm_hidden_for(user)`. Это даёт сайдбар, подменю, палитру Ctrl+K, обзор настроек (`settings_home`), плитки главной, мобильный таб-бар.
- Якорь раздела скрывается, если не виден ни один его подпункт. Пример: staff без `finance_view` теряет якорь «Finanzen» (fallback-группа в Einstellungen тоже пуста).
- Шаблоны: контекст-процессор `cab_can` — ленивый объект, `{% if cab_can.prices_edit %}`. Имя `perms` занято Django, использовать нельзя. При неизвестном ключе тег fail-closed. `cab_is_owner` и `cab_can_export_finance` переводятся на `cab_can` и удаляются после grep-замка.
- Кнопки внутри экранов (возврат, Gutschrift, отмена события, CSV) гейтятся тем же ключом, что сервер.

## 7. Тесты-замки (пишутся ДО кода, красные там, где нужно)

1. **Эталонный снимок паритета** (`test_perm_parity_golden.py`) — ПЕРВЫЙ коммит, на старом коде. Для каждой роли (admin, staff) × 6 представительных типов (как в E11.2) × каждой беспараметрной вьюхи кабинета × GET/POST записывается разрешено/запрещено плюс набор inline-флагов (`can_edit_prices`, `credit_form`, маскировка, `_refund_form`, `_advance`, `event cancel`). На каждом инкременте a–e снимок должен совпадать байт-в-байт. В E6.7f он осознанно перегенерируется по решениям В-2/В-3 с диффом в коммите.
2. **Каждая вьюха кабинета объявляет право** (`test_every_view_declares_perm.py`): обход `get_resolver()` для путей из `CABINET_PREFIXES`; у колбэка (с unwrap) есть `_required_perm`, или `_owner_floor`, или имя в `OPEN_TO_ALL` с причиной. Это и есть правило «новый экран регистрирует право».
3. **Реестр:** ключи уникальны и в snake_case; группа известна; цели `requires` существуют и не образуют цикл; пресеты ⊆ PERMS; пол ∩ PERMS = ∅; `"frontdesk" in PERMS` (контракт для Z-5).
4. **i18n:** каждая подпись и описание переведены в 5 `.po` (`scripts/i18n_quickcheck.py` + `i18n_gap` в CI); тест рендера экрана прав на ru без немецких msgid.
5. **Эскалация:** admin выдаёт ключ, которого у него нет → отказ + audit; admin правит admin или owner → 403; правка себя → отказ; admin приглашает роль admin → отказ; принятие инвайта после понижения приглашающего → лишние ключи срезаны; принятие после удаления приглашающего → инвайт недействителен; staff без `team_manage` на экране команды → 403; disabled-ключи не стираются при сохранении.
6. **Действует сразу:** отозвать `sales_view` → следующий запрос к Verkäufe даёт 403; меню без пункта.
7. **Inline-права:** `apply_action` с `money_refund` снят у admin → `RefundNotAllowed`; `sales_cancel` снят → отказ на доске, в массовой смене, на карточке и в Mini App (одна точка); `prices_edit` снят у admin → `RATE_EDIT_ACTIONS` и price-calendar дают 403; `customers_contacts` выдан staff → контакты без маски; `events_cancel` выдан → отмена работает.
8. **Пол:** owner_floor-экраны недоступны admin даже при `grant` со всеми ключами (подделанный JSON в БД); normalize вырезает ключи пола.
9. **Навигация:** `entry.perm` == `_required_perm` целевой вьюхи (сверка реестра и вьюх); `nav_registry` скрывает недоступное; якорь без видимых подпунктов скрыт.
10. **Mini App:** вьюха из `TG_LITE_VIEWS` с правом проходит обе проверки; белый список не расширяет права.
11. **Fail-closed:** аноним, нет Membership, повреждённый JSON (не dict, не list) → только пресет роли, без 500.
12. **Аудит:** каждое изменение пишет `team.perms` с дельтой; экран «Verlauf» не показывает персональные данные.
13. **Запросы:** `effective()` — одна выборка Membership на запрос (`django_assert_num_queries` на рендере сайдбара и экрана).
14. **E11.2 и `test_staff_walk.py`:** ожидания выводятся из `_required_perm` + `PRESETS`, а не из `OWNER_ONLY_PREFIXES`. `EXPECTED_OWNER_ONLY_UNLISTED` разделяется на «пол» и «право по умолчанию только owner».

Стенд Playwright (`scripts/` по образцу `golden_paths.py`): owner выдаёт admin `team_manage` → admin входит, открывает сотрудника, видит disabled-ключи, выдаёт «Empfang» → сотрудник входит, видит в меню только разрешённое, получает 403 на Finanzen по прямому адресу; размеры 390 и 1440, ru и de; клавиатурная навигация по чекбоксам.

## 8. Инкременты (батч-режим, FF в main по зелёному CI)

- **E6.7a — реестр + резолвер + эталон (без миграции).** `permissions.py` с пресетами только по ролям, эталонный снимок паритета (коммит 1 — на старом коде), `has_perm` и алиасы `can_*`, перевод всех inline-проверок §4.3 на `has_perm`, `cab_can`. Снимок не меняется. Риск: средний.
- **E6.7b — объявление прав на вьюхах + middleware `process_view`.** Декораторы на всех вьюхах кабинета (по разделам, по коммиту на раздел), `OPEN_TO_ALL`, замок «каждая вьюха объявляет право», `OWNER_ONLY_PREFIXES` → `OWNER_FLOOR_PREFIXES`, `NavEntry.perm`, перевод E11.2. Снимок не меняется. Риск: высокий (объём) — поэтому замок «каждая вьюха объявляет» включается первым, xfail-списком, который сжимается по разделам.
- **E6.7c — хранение и сервис выдачи (`core/0013`).** Поле `permissions`, normalize, `set_member_permissions` с правилами §3, audit, инвайт с дельтой. Замки эскалации. Снимок не меняется (пустой JSON = пресет). Риск: средний.
- **E6.7d — UI команды.** Admin получает доступ к экрану команды (`team_manage`; пресет admin += `team_manage` — **первое осознанное изменение снимка, В-1**), экран прав, шаблоны, «Verlauf», 403-страница с подписью права, i18n. Стенд Playwright, a11y. Риск: средний.
- **E6.7e — скрытие везде.** Сайдбар, подменю, палитра, обзор настроек, плитки главной, таб-бар, кнопки в экранах, Mini App. Стенд обхода всех экранов всеми ролями (как сверка «Кабинет-X»: 16 архетипов). Риск: низкий.
- **E6.7f — решения владельца по пресетам.** `finance_view` убрать у staff (В-2); `processes_edit`, `domains_manage`, `modules_manage` — только admin (В-3); новые пресеты действуют для всех staff без deny-дельты. Эталон перегенерируется осознанно, в коммите — таблица «было/стало»; build-log. Риск: средний — у пилотов меняется доступ, поэтому нужно предупреждение в release notes и письмо владельцам с сотрудниками (их сегодня мало).
- **Затем Z-5** использует `frontdesk` и `sales_cancel`.

## 9. Вопросы владельцу

- **В-1.** «Администратор» в запросе — это роль admin (тогда admin получает экран команды и выдаёт права staff в пределах своих) или сам владелец? *Рекомендация: роль admin, с правилами §3.*
- **В-2.** Скрыть по умолчанию от staff Finanzen и Auswertungen (`finance_view`)? *Рекомендация: да, в E6.7f; владелец может вернуть точечно.*
- **В-3.** Перевести по умолчанию на «только admin»: Abläufe & Status, Domains, Funktionen ein/aus? Сегодня это может staff. *Рекомендация: да для Domains и Funktionen, Abläufe — admin.*
- **В-4.** Какие из сегодняшних «только владелец» сделать выдаваемыми (как в таблице: возврат переплаты, PII-экспорт, DSGVO, внешние каналы, Stadtportal, Betriebsferien, отмена события, полные контакты, банковские выписки)? Неотзываемый пол — только Abo, Recht/Impressum, IBAN, владение, удаление, импорт с чужого сайта. *Рекомендация: так.*
- **В-5.** Пресет `frontdesk` для staff — да (стойку ведут сотрудники)? Undo check-in — только owner или admin? *Рекомендация: check-in/out — всем, undo — `sales_cancel`.*
- **В-6.** Вход сотрудников в Mini App через Telegram — сейчас вне объёма (Mini App = владелец). Ок?

## 10. Риски и меры

- **Молчаливое изменение доступа при переводе 60+ вьюх** → эталонный снимок паритета до первой правки + xfail-список, сжимающийся по разделам.
- **Два источника истины (префиксы и декораторы)** → `process_view` читает атрибут вьюхи; префиксы остаются только для пола; замок «префикс пола ⇒ вьюха помечена `_owner_floor`».
- **Эскалация через подделку формы или disabled-поля** → сервис выдачи — единственный писатель, проверка ⊆ прав actor на сервере, `perms_present` + сохранение ключей вне полномочий actor.
- **Устаревшие права в активной сессии** → вычисление на каждый запрос, никаких кэшей вне запроса.
- **Опечатка в ключе даёт тихий False** → исключение в DEBUG и тестах, замок «все ключи `has_perm` / `perm_required` / шаблонов есть в реестре» (AST и grep по шаблонам).
- **Новый экран без права** → замок §7.2 + чеклист `cabinet-screen-dod.md` (добавить строку «право в реестре»).
- **Декоратор «съеден» вставленным хелпером** (грабля `test_orphan_decorators`) → замок §7.2 видит отсутствие атрибута.
- **Шаблон схемы `_template`** → `ensure_template_schema` пересобирает его на деплое; проверить `migration_state` после деплоя.
- **N+1 на сайдбаре** → `effective()` мемоизируется на request.user, замок числа запросов.
- **Удаление `owner_only` из `nav_registry`** ломает старые замки (X0, W9, ST-4b) → переписывать осознанно, с картой в build-log.

## 11. i18n

Подписи и описания прав, группы, шаблоны, 403-текст, «Verlauf», подсказки disabled-ключей — `gettext_lazy` с базовым немецким msgid. Около 80 msgid × 5 каталогов (de/en/tr/ru/uk). Только канонические имена `_`/`gettext_lazy`: псевдонимы не извлекаются (урок «Кабинет-X»). Строки — не внутри f-строк. Перед пушем: `scripts/i18n_quickcheck.py` + проверка `msgid` шаблонов против `.po` (гейт `i18n_gap` в CI строже).

## 12. ECC-прогоны

| Когда | Скиллы (грузить до кода) | Агенты |
|---|---|---|
| Сразу после плана | `django-security`, `django-patterns`, `database-migrations` | `security-reviewer` — ревью плана: модель эскалации §3, пол, инвайт, `process_view`. `architect` (по желанию) — дельта или полный набор, один JSON или два поля |
| E6.7a/b (до кода) | `django-tdd`, `python-testing`, `django-verification` | `tdd-guide` — эталонный снимок и замок «каждая вьюха»; после — `django-reviewer` |
| E6.7c | `database-migrations`, `postgres-patterns` | `database-reviewer` — `core/0013` (быстрый default, шаблон схемы, `select_for_update`); `security-reviewer` — сервис выдачи, инвайт; `silent-failure-hunter` — `has_perm` и fail-closed пути |
| E6.7d | `accessibility`, `e2e-testing`, `error-handling` | `a11y-architect` — экран прав (fieldset/legend, aria-describedby, disabled-подсказки, клавиатура); `e2e-runner` (Python-Playwright стенд §7); `security-reviewer` + `django-reviewer` перед мержем |
| E6.7e | `e2e-testing` | обход всех экранов × ролей стендом; `django-reviewer` |
| E6.7f | — | `code-reviewer` — дифф эталона; `doc-updater` — build-log, task-catalog, CLAUDE.md §3 |

До мержа каждого инкремента все пункты его строки закрыты.

## 13. Критерии готовности

- [ ] В кабинете нет ни одной вьюхи без права или записи в `OPEN_TO_ALL` (замок).
- [ ] Эталонный снимок паритета зелёный на E6.7a–e; в E6.7f дифф совпадает с решениями В-2/В-3.
- [ ] Admin выдаёт staff только права, которые есть у него самого; owner и другого admin не правит; пол неотзываем.
- [ ] Отзыв действует на следующем запросе; меню, палитра и кнопки следуют правам.
- [ ] Каждое изменение прав есть в аудите и видно в «Verlauf».
- [ ] Ключ `frontdesk` готов для Z-5.
- [ ] i18n — 5 языков; a11y-ревью экрана прав пройдено; стенд Playwright зелёный.
- [ ] Записи в `docs/build-log.md`, `docs/task-catalog.md` (E6.7a–f), CLAUDE.md §3; миграция `core/0013` — в очереди деплоя.

## 14. Учёт рыночного исследования (`docs/market-analysis/staff-permissions-2026-10-25.md`)
Совпадает с рынком: шаблоны ролей + ручная настройка (Shopify/Square/Lightspeed/Mews); права
«область × действие»; отдельная группа «Geld»; строгий запрет эскалации (явно — только у Mews; у нас §3).
Добавить в v1: **письмо владельцу** при выдаче прав групп Geld/Finanzen/`team_manage`/`pii_export`/
`customers_contacts` (рынок журнала прав не описывает — наше отличие); значок 🔒 у чувствительных прав
в UI; шаблоны ролей по архетипу (Rezeption — отель, Theke — магазин/кафе, Küche — гастро, Buchhaltung —
все). В v2 (вне объёма): лимит скидки/возврата и подтверждение PIN менеджера (Shopify POS, Lightspeed);
режим «только свои записи/заявки» (салон, мастерская); просмотр «так видит сотрудник»; ступень клиентов
«только имя» (сейчас две: маскированные контакты / полные).

