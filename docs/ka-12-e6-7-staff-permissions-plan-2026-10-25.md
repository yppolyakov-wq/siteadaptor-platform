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


## 15. Ревью плана `security-reviewer` (2026-10-25, до кода) — принять
**HIGH**
1. **Инвайт:** payload = `{email, role, perms, inviter_pk}`; при принятии в `atomic` перечитать приглашающего
   (`select_for_update`): не owner / не admin с `team_manage` / неактивен → инвайт недействителен; `perms ∩
   effective(inviter)`, роль admin — только если приглашал owner; существующему пользователю права не менять;
   потеря Redis = fail-closed (отметить). GET принятия не раскрывает роль/права; POST — rate-limit.
2. **`process_view`:** атрибут искать по цепочке `__wrapped__` (лимит глубины), `view_class`, `.func`
   (partial); замок §7.2 — через реальный `resolve()` всех URL. **Вьюха кабинета без права и не в
   `OPEN_TO_ALL` → 403 на проде (fail-closed), не только красный тест.** GET/HEAD/OPTIONS — чтение.
   Декоратор сам проверяет право (прямые вызовы мимо middleware) — обязательно.
3. **Эскалация при правке:** admin меняет (grant И revoke) только ключи из своих `effective`; ключи вне его
   полномочий сохраняются: `new = (old ∩ ¬scope) ∪ (requested ∩ scope)` от сохранённого состояния под
   `select_for_update`. Роль цели перепроверять внутри транзакции (`membership_id` из POST — IDOR);
   лочить строки цели И actor (одновременное понижение actor).
4. **Сессии:** мемо прав — на `request`, сбрасывать после записи прав в том же запросе. Mini App-сессия —
   только owner: замок «owner → admin ⇒ Mini App-сессия мертва на следующем запросе» + `revoke_sessions` при
   понижении/удалении Membership.
5. **Пол:** IBAN — защита на уровне ПОЛЕЙ (`payment_settings` — экран `settings_edit`, ветка банковских
   реквизитов → `is_owner`) + замок «admin с полным grant не меняет IBAN»; golden-замок «каждый прежний
   префикс `OWNER_ONLY_PREFIXES` → либо пол, либо право из таблицы»; admin не меняет роли вообще.
**MEDIUM**
6. Неизвестный ключ в `perm_required` — падение при импорте модуля; повреждённый JSON → пустая дельта
   (пресет роли), никогда «всё».
7. Чувствительные ключи (`money_*`, `accounting`, `pii_export`, `customers_contacts`, `team_manage`,
   `bank_view`) — расширение пресета задним числом не действует (только явный grant); deny хранить как есть.
8. Grep-замок «нет `role_of(...) in (...)` вне permissions.py» — уже в E6.7a.
9. Палитра Ctrl+K / `customer_search` возвращают то же, что экран (маскировка) — замок.
10. Аудит: и отказы по полу, и срезанные ключи инвайта; **письмо владельцу — в E6.7c**; чувствительные права
    выдаёт только owner (admin — остальные).
11. **`team_manage` НЕ в пресете admin:** owner включает админу вручную — паритет для пилотов цел, «выдаёт
    администратор» — осознанное решение владельца. (Меняет рекомендацию к В-1.)
12. Пакетный (`PackageScopeMiddleware`) и Telegram-гейт сильнее права — замок «admin + полный grant на
    лёгком пакете → 403 вне белого списка».
**LOW** 13–16: team-join без раскрытия; замок «Telegram-сессия только owner»; `community.access` — проверить
сразу; роль и права меняются в одной транзакции под блокировкой.


# Редакция 2 (2026-10-25): учёт рыночного исследования
Заменяет §1.1, §1.3, §5, §8 выше; остальное в силе. Замечания security-ревью §15 действуют поверх (в т.ч. §15.11 — `team.edit` НЕ в пресете admin, owner включает вручную; §15.10 — чувствительные права выдаёт только owner).

## A. Модель: раздел × действие + ступени (v1)

### A.1 Ключ права

Ключ имеет вид `<раздел>.<действие>`. Действия:
- `view` — смотреть;
- `edit` — менять;
- `delete` — удалять;
- `export` — выгрузка (у Mews и Shopify это отдельное право).

Разделы заданы в реестре и сопоставлены с `nav_registry`: у каждого раздела есть свой набор подпунктов меню.

Зависимости в реестре: `edit` требует `view`; `delete` требует `edit`; `export` требует `view`. Если раздел не умеет какое-то действие (например, «delete» у Website), ключа для него просто нет — пустых галочек не будет.

### A.2 Ступени для клиентов и финансов

Это один выбор, а не набор галочек. Внутри они раскладываются в ключи, поэтому `has_perm` работает как прежде.

- **Kunden** (по образцу Timely):
  - `0 — keine` (выключено);
  - `1 — nur Name` — на сделке и в чате видны имя и код, телефон и e-mail замаскированы. Это сегодняшнее поведение staff;
  - `2 — Kontaktdaten` — без маски;
  - `3 — volle Kartei` — CRM, заметки, фирмы, теги, история.

  Отдельно (по умолчанию только владелец): `kunden.export` (CSV клиентов, CSV продаж, отчёт гостей, ростер), `kunden.dsgvo` (выгрузка и удаление по DSGVO, E6.1), `kunden.delete`.

- **Zahlen & Finanzen** (по образцу Square):
  - `0 — nichts`;
  - `1 — Kennzahlen` — «Umsatz heute», полоса дня, сводки и агрегаты на главной, Marketing-Puls;
  - `2 — Berichte` — Auswertungen, Belegungsbericht, Zahlungen, Offene Posten (только просмотр);
  - `3 — Finanzen` — Journal, Rechnungen, Ausgaben, Ergebnis.

  Отдельно: `finanzen.edit` (счета из сделки, Mahnung, Ausgaben, Eingangsrechnung), `finanzen.export` (DATEV и журнал, сегодня `FINANCE_EXPORT_PREFIXES`), `finanzen.korrektur` (Gutschrift, Storno, Rechnungskorrektur, Anzahlungsrechnung, полный поиск получателя — сегодня `can_export_finance`), `finanzen.bank` (выписки, owner).

### A.3 Группа «Geld» (v1, отдельные права да/нет)

Каждое право — отдельная галочка с 🔒.

| Ключ | Подпись | Из кода | Сегодня |
|---|---|---|---|
| `geld.erstatten` | Geld erstatten (Storno mit Erstattung) | `refunds.may_refund` → `apply_action` | owner+admin |
| `geld.korrektur` | Erstattung von Überzahlung & Minderung | `/dashboard/erstattung/`, `deal_refund`, `_refund_form` | owner |
| `geld.rabatt` | Rabatt vergeben | `deal_discount_edit`, скидка в смете и заказе | все |
| `geld.preis` | Preis in einer Buchung/Bestellung ändern | правка цены позиции в `orders/editing`, свободная строка сметы, цена в Sofort-Angebot | все |
| `geld.bezahlt` | Als bezahlt markieren / Barzahlung erfassen | `settle_payment` с карточки, «bezahlt» заявки, фолио | все |
| `geld.einloesen` | Gutschein/Coupon einlösen | `promotions:redeem`, сканер, Mini App | все |
| `geld.zahlungslink` | Zahlungslink senden | `deal_pay_link` | все |

«Kassenbuch» — в v2: модуля кассовой книги пока нет.

### A.4 Сетка разделов (v1)

Обозначения: «S» — сегодня доступно staff, «A» — сегодня доступно admin. Шаблоны ролей в A.5 могут отличаться — это осознанные изменения (E6.7f).

| Раздел (`nav_registry`) | view | edit | delete | export | Сегодня (паритет) |
|---|---|---|---|---|---|
| `verkaeufe` — доска, списки, календари, Heute, карточки, Zusatzverkäufe, Lieferungen, KDS, Mini App «Anfragen» | ✓ | ✓ (статус, ручная бронь, клиент, связи, массовая смена, состав) | ✓ = `verkaeufe.storno` (переход в cancelled или no_show) | → `kunden.export` | S/A всё |
| `rezeption` — check-in/out (Z-5) | — | ✓ `rezeption.edit` | — | — | новое |
| `ablaeufe` — статусы, переходы, колонки, анкета Anfrage | ✓ | ✓ | — | — | S/A |
| `sortiment` — товары, услуги, номера, события, туры, наборы, категории, Teacher, Pässe, Extras, видимость, «ausverkauft» | ✓ | ✓ | ✓ | — | S/A |
| `preise` — тарифы, NightRate и price-calendar, сезоны, Kurtaxe, правила отмены, авто-скидки; правка чужих заметок мастера | ✓ | ✓ | — | — | view всем, edit A (`can_edit_policy`, `RATE_EDIT_ACTIONS`) |
| `lager` — склад, закупки, Mängelanzeige, Produktion, импорт CSV | ✓ | ✓ | — | ✓ (CSV склада) | S/A |
| `veranstaltung.absagen` — отмена события (массовый возврат) | — | ✓ 🔒 | — | — | owner |
| `marketing` — акции, типы, кампании, ваучеры, лояльность, newsletter, отзывы, публикации, Finder, Schnell-Aktion | ✓ | ✓ | ✓ | — | S/A |
| `nachrichten` — inbox, ответ, ИИ-черновик | ✓ | ✓ | — | — | S/A |
| `kanaele` — Google GBP и Merchant, свой и общий Telegram-бот, подключение каналов | ✓ | ✓ 🔒 | — | — | edit owner |
| `stadtportal` — статистика | ✓ 🔒 | — | — | — | owner |
| `website` — Studio, Design, Seiten, SEO, Medien, Menü | ✓ | ✓ | — | — | S/A |
| `domains` | ✓ | ✓ 🔒 | — | — | S/A (В-3) |
| `einstellungen` — Mein Geschäft (без права и IBAN), Sprachen, Benachrichtigungen, Zahlung & Lieferung (тумблеры), Ressourcen, Öffnungszeiten, Channel-Manager, Google-Bewertungen | ✓ | ✓ | — | — | S/A |
| `funktionen` — модули вкл/выкл | ✓ | ✓ 🔒 | — | — | S/A (В-3) |
| `betriebsferien.ganz` — закрыть весь бизнес | — | ✓ 🔒 | — | — | owner |
| `team` — участники, инвайт, права | ✓ | ✓ 🔒 | ✓ (отзыв доступа) 🔒 | — | owner (В-1: admin) |

Плюс `kunden.*` и `finanzen.*` ступенями (A.2) и `geld.*` (A.3).

**Inhaber-Vorbehalt (не право, неотзываемо, вне сетки):** Abo & Rechnung, Recht & Steuern и Impressum лёгкого кабинета, банковские реквизиты (IBAN/BIC; у Square даже роль Full их не даёт), смена или передача владельца, удаление бизнеса, импорт с чужого сайта.

### A.5 Шаблоны ролей по архетипу (v1)

Шаблон хранится как набор кодов (пресет), без наследования. Пресет — это дельта поверх роли staff или admin (§2 прежнего плана). Карточки сверху экрана, у каждой одна строка «что может». Набор шаблонов зависит от `tenant.business_type` и активных модулей (реестр `ROLE_TEMPLATES[archetype]`).

- **Все типы:**
  - **Leitung** (admin): всё, кроме Vorbehalt и owner-only по умолчанию. Kunden 3, Finanzen 2, `geld.erstatten`, `team.edit` по В-1.
  - **Mitarbeiter** (staff): сегодняшний staff. Kunden 1, Finanzen 1, `geld.rabatt`, `geld.bezahlt`, `geld.einloesen`.
  - **Buchhaltung** (admin): Finanzen 3, `finanzen.edit`, `finanzen.export`, `finanzen.korrektur`, `geld.erstatten`, `verkaeufe.view`, Kunden 1.
  - **Aushilfe/Kasse** (staff): `verkaeufe.view` и `verkaeufe.edit`, `geld.einloesen`, `geld.bezahlt`, Kunden 1, Finanzen 0.
- **Отель:** + **Rezeption** (`verkaeufe` view/edit, `rezeption.edit`, `geld.bezahlt`, Kunden 2, Finanzen 1) и **Housekeeping** (`verkaeufe.view` + хаускипинг-статусы комнат, Kunden 0, Finanzen 0).
- **Салон, мастерская, Handwerker, туры:** «Mitarbeiter: nur eigene Termine» — v2 (B.1). В v1 — обычный «Mitarbeiter».
- **Гастро:** + **Küche** (`verkaeufe.view`, смена статусов заказов через KDS, Kunden 0).
- **Лёгкий пакет («Nur Aktionen», T-8.32):** только два шаблона — **Inhaber** и **Mitarbeiter**. Полный редактор прав скрыт: по исследованию рынка это функция роста, и Square держит свои наборы за платным планом. Редактор входит в пакеты «Laden» и Profi. Гейт — `package_scope`.

**Паритет.** Без выбранного шаблона роль даёт ровно сегодняшний доступ (эталонный снимок паритета §7.1 не меняется). Шаблоны применяются только явно — владельцем или при инвайте. Исключение — осознанное изменение дефолтов в E6.7f.

**Одна роль на человека** (как в POS-системах): `Membership` и так OneToOne. Несколько ролей и правило «максимум из ролей» (анти-пример Bitrix24) не вводим. Замок: модель не допускает второй роли.

### A.6 Запрет эскалации (уточнение §3 по Mews)

- Выдать можно только права ≤ своих. Ступени сравниваются числом: admin с Kunden 2 не может выдать Kunden 3.
- Свои права не меняются никогда, даже у admin с `team.edit` (у owner прав нет — у него всё).
- Управление командой — отдельное привилегированное право `team.edit` с 🔒. Admin правит только staff.
- Проверка — на сервере в `set_member_permissions`. Скрытые и disabled-галочки — это только UX.
- `team.delete` (отзыв доступа) admin применяет только к staff. Последний владелец защищён.

### A.7 Журнал и письмо владельцу (v1)

- `audit_event("team.perms", changes={"before": [...], "after": [...], "template": ..., "actor_role": ...})` — что было и что стало. Персональных данных нет (только коды прав и pk участника).
- Хранение журнала прав — **3 года**, затем beat-очистка (минимизация DSGVO). Срок — вопрос В-8.
- **Письмо владельцу** (на локали бизнеса, `notifications.services.email_locale`), когда **не владелец** (admin) выдал или расширил права из чувствительных групп: `geld.*`, `finanzen.*` ступень ≥ 2 или export, `kunden.export`/`dsgvo` или ступень 3, `team.*`, `kanaele.edit`. Прецедент — письмо при смене IBAN (KA-H2). Если выдаёт сам владелец, письма нет. Дедуп — `dedupe_key=schema:perms:<membership>:<hash after>`. Отправка через Celery и `on_commit`.
- Экран «Verlauf» на странице команды: последние 50 событий `team.*`.

## B. v2 (вне объёма E6.7, записать в roadmap §Отложено)

1. **«Nur eigene» — область данных** (Bitrix24, Timify): сотрудник видит только свои записи, заявки и свой календарь. Привязка `Membership.user` ↔ `booking.Resource`/Teacher/исполнитель заявки — нужна миграция и фильтры во всех выборках продаж, а это большой риск утечки. Шаблон «Mitarbeiter: nur eigene Termine» для салона, мастерской, гида.
2. **Лимиты:** «Rabatt bis N %», «Erstattung bis X €».
3. **«С подтверждением»** (Shopify POS): действие выше лимита требует PIN менеджера или подтверждения владельцем в Mini App.
4. **«So sieht es der Mitarbeiter»** — предпросмотр кабинета глазами сотрудника (рендер навигации и плиток по чужим `effective()`, только чтение).
5. **Журнал денежных действий** с экраном (возвраты, скидки, правки цены, «bezahlt», погашения) — поверх существующего audit.
6. **Kassenbuch** как право (когда появится модуль).
7. Вход сотрудников в Mini App через Telegram.
8. Свои именованные шаблоны (владелец сохраняет набор как «Wochenendaushilfe»).

## C. UI экрана прав (v1, заменяет §5)

- **Сверху:** карточки шаблонов архетипа с одной строкой «что может», выбранная выделена. После ручных правок подпись «Vorlage + angepasst».
- **Ниже:** группы-карточки Verkäufe · Geld · Sortiment · Kunden · Marketing · Website · Zahlen & Finanzen · Einstellungen · Team. У каждого раздела — **переключатели** по действиям (Ansehen / Ändern / Löschen / Export). У Kunden и Finanzen — **ступени**: radio-группа из 4 шагов с подписью «что видно».
- **🔒** у чувствительных прав (Geld, Finanzen ≥ 2, Export, DSGVO, Team, Kanäle, Domains, Funktionen) + подсказка «Inhaber wird per E-Mail informiert», когда выдаёт admin.
- Disabled с подсказкой «Dieses Recht haben Sie selbst nicht». Блок «Nur Inhaber» read-only.
- **a11y:** `fieldset`/`legend` на группу; переключатели — `<input type=checkbox role=switch>` с `aria-describedby`; ступени — `<fieldset>` с radio; работа с клавиатуры; без JS — обычный POST; сентинел `perms_present` (W0).
- **Мобайл:** группы аккордеоном, поля 16px, «Speichern» над таб-баром.

## D. Инкременты v1 (заменяет §8)

- **E6.7a — реестр и резолвер, без миграции.**
  - Реестр «раздел × действие» + ступени + Geld + Vorbehalt.
  - Сопоставление разделов с `nav_registry` (замок: каждый раздел сетки ↔ ≥1 запись реестра навигации, каждая запись навигации ↔ раздел или OPEN_TO_ALL).
  - Эталонный снимок паритета первым коммитом.
  - Inline-проверки (§4.3 прежнего плана) переведены на новые ключи: `can_edit_policy` → `preise.edit`; `can_export_finance` → `finanzen.korrektur` и `finanzen.export`; `may_refund` → `geld.erstatten`; маскировка контактов → `kunden` ступень ≥ 2; `_refund_form`/`deal_refund` → `geld.korrektur`; отмена события → `veranstaltung.absagen`; переход в cancelled или no_show → `verkaeufe.storno`.
  - Новые точки денег: `geld.rabatt`, `geld.preis`, `geld.bezahlt`, `geld.einloesen`, `geld.zahlungslink` — гейты добавляются, а пресеты дают «все» (паритет).
- **E6.7b — объявление прав на всех вьюхах + `process_view`.** Замок «каждая вьюха кабинета — право или OPEN_TO_ALL», `NavEntry.perm`, перевод E11.2.
- **E6.7c — хранение и сервис выдачи (`core/0013`).** Миграция, `set_member_permissions` (≤ своих, свои права не меняются, сравнение ступеней), шаблоны по архетипу, инвайт с шаблоном, журнал «до/после», письмо владельцу, срок хранения журнала.
- **E6.7d — экран прав** (C) + доступ admin к команде по В-1 + 403-страница с подписью права + гейт лёгкого пакета (два шаблона).
- **E6.7e — скрытие** в меню, палитре, плитках и кнопках по правам и ступеням + стенд обхода 16 архетипов × шаблонов.
- **E6.7f — дефолты по решениям владельца** (В-2: Finanzen 1 у Mitarbeiter; В-3: Domains/Funktionen/Abläufe — Leitung). Эталон перегенерируется осознанно, письмо владельцам, у кого есть сотрудники.
- **Затем Z-5** — `rezeption.edit` и шаблон «Rezeption».

## E. Новые замки сверх §7

1. Сетка ↔ `nav_registry` в обе стороны (A.5 E6.7a).
2. Ступени: Kunden 1 — на карточке сделки, в CRM, палитре, счёте и Mini App телефон и e-mail замаскированы (одна точка `kunden_level(user)`); Kunden 0 — пункт CRM скрыт, имя на сделке видно.
3. Finanzen 1 — главная показывает агрегаты, `/dashboard/finance/*` даёт 403; Finanzen 2 — отчёты открыты, журнал и счета дают 403.
4. Каждое право группы Geld проверяется на ВСЕХ поверхностях своего действия: доска, карточка, массовая смена, Mini App, сканер.
5. Шаблоны по архетипу: каждый шаблон проходит normalize идемпотентно; шаблоны лёгкого пакета ⊆ {Inhaber, Mitarbeiter}; каждый шаблон ⊆ пресета Leitung (выдавать может admin).
6. Эскалация по ступеням: admin с Kunden 2 не выдаёт 3; своя правка запрещена даже при `team.edit`.
7. Письмо владельцу: при выдаче adminом права из чувствительной группы — одно письмо (дедуп), при выдаче владельцем — нет, в тексте нет персональных данных клиентов.
8. Одна роль на человека (OneToOne; второй строки Membership на user не бывает).
9. Журнал прав старше срока удаляется beat'ом.

## F. Вопросы владельцу (добавлены к В-1…В-6)

- **В-7.** Шаблоны по архетипу — утвердить набор A.5 (Leitung, Mitarbeiter, Buchhaltung, Aushilfe/Kasse + Rezeption/Housekeeping у отеля + Küche у гастро)?
- **В-8.** Срок хранения журнала прав — 3 года? *Рекомендация: да* — совпадает со сроком заметок мастера E6.4d и с исковой давностью.
- **В-9.** Права в лёгком пакете — только Inhaber/Mitarbeiter, полный редактор — в Laden/Profi? *Рекомендация: да.*
- **В-10.** «Mitarbeiter» по умолчанию видит «Umsatz heute» (Finanzen 1) или ничего? Исследование советует «ничего» для Mitarbeiter и агрегаты для Leitung. *Рекомендация: «ничего» в E6.7f; сегодня staff видит всё.*

## G. ECC-прогоны (дополнение к §12)

- `market-research` уже есть — повторно не нужен.
- E6.7c: `security-reviewer` — сравнение ступеней, письмо владельцу (нет ли персональных данных и оракула), запрет правки своих прав; `silent-failure-hunter` — отправка письма и `on_commit`.
- E6.7d: `a11y-architect` — переключатели `role=switch`, radio-ступени, 🔒 с текстовой альтернативой (`aria-label` «sensibles Recht»); Playwright-стенд: шаблон «Rezeption» у отеля, «Küche» у кафе, лёгкий пакет — только два шаблона.

## H. Решения владельца (2026-10-25: «по рекомендации»)
В-1 права раздаёт admin, но `team.edit` в пресет admin НЕ входит — владелец включает вручную
(§15.11) · В-2 Finanzen у Mitarbeiter по умолчанию скрыт (E6.7f) · В-3 Abläufe/Domains/Funktionen —
только Leitung (E6.7f) · В-4 выдаваемые права — как в сетке A.4 · В-5 check-in/out всем, отмена
заезда — под `verkaeufe.storno` · В-6 Mini App сотрудникам не открываем · В-7 шаблоны A.5 · В-8
журнал прав — 3 года · В-9 лёгкий пакет — 2 шаблона · В-10 Mitarbeiter выручку не видит (E6.7f).

### E6.7a — что сделано (2026-10-25)
- `apps/core/permissions.py`: реестр 57 ключей (без подписей — подписи и переводы идут вместе с
  экраном прав в E6.7d, иначе мёртвые msgid), группы, `requires`, `sensitive`, пресеты ролей =
  сегодняшний доступ, `for_role`/`effective`/`has_perm` (опечатка в ключе → `ImproperlyConfigured`
  при `PERMS_STRICT`, в проде — False + лог).
- Ступени Kunden/Finanzen в коде — независимые ключи (`kunden.view`/`kunden.kontakte`/…): сегодняшний
  staff видит CRM, но с маской контактов в палитре и поиске получателя — линейной ступени это не
  соответствует. Сборка ступеней в UI — E6.7d.
- Новый ключ `geld.richtlinie` — флаг «ohne Erstattung» у своих статусов (сегодня только владелец).
- Переведены: booking (правила отмены, чужие заметки, Betriebsferien), stays (тарифы, цены,
  price-calendar), finance (Gutschrift, полный поиск, маска контактов), deal_card (возврат переплаты,
  Anzahlungsrechnung), core/views (Anzahlungsrechnung, «ohne Erstattung», Telegram/общий бот, GBP,
  палитра, `deal_refund`), events (отмена), publishing, promotions/aggregator/lite (Stadtportal),
  `refunds.may_refund`, шаблоны (`cab_can:"<ключ>"`); `roles.can_edit_policy`/`can_export_finance` —
  алиасы. `is_owner` остался только для пола и middleware/навигации (E6.7b/e) — grep-замок.
- Эталон `apps/core/tests/test_perm_parity.py`: место → ключ → роли с доступом сегодня.
