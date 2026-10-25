# KA-12 E6.7c — хранение выданных прав и сервис выдачи (`core/0013`)

Основа: `ka-12-e6-7-staff-permissions-plan-2026-10-25.md` (§2, §3, §15, «Редакция 2», §H, E6.7b).
План — агент `planner` (2026-10-25). Ветка `claude/gifted-wozniak-k131jm` (батч, один CI на верхушке).

## Обзор
Сейчас права = только роль. E6.7c: у каждого члена команды дельта поверх пресета роли
(`Membership.permissions`), единственный писатель `set_member_permissions` с запретом эскалации
(§3, §15.3, A.6), журнал «до/после», письмо владельцу; инвайт несёт права и перепроверяет их при
принятии. Когда права стали выдаваемыми — снимаются префиксные гейты (`OWNER_ONLY_PREFIXES`,
`FINANCE_EXPORT_PREFIXES`) и декораторы `owner_required`/`finance_export_required` (иначе выданный
`kunden.export` не открыл бы CSV); префиксы остаются только у пола. UI нет (E6.7d). Пустой JSON =
пресет роли → эталон паритета не меняется.

## Находки разведки
- `permissions.effective()` — один `values_list("role")`, мемо нет → N запросов на сайдбаре.
- `view_perms.RULES` уже ставит owner-only ключи экранам под owner-префиксами; пол `FLOOR` — billing,
  recht, geschaeft, imports/website → снятие префиксов сохраняет паритет при пустой дельте.
- `owner_required` на 11 вьюхах (core/views 1515 пол, 4889 CSV продаж, 6474 Betriebsferien;
  lite_cabinet 277 пол; events 722 ростер; stays 1491 CSV; finance 296 банк; crm 101 экспорт,
  267/288/320 DSGVO), `finance_export_required` — finance 434/461/479.
- **`team.py::team_view` сам роль не проверяет** — держит только префикс. Снять префикс раньше
  укрепления = любой с `team.view` меняет роли. Поэтому фаза 5 (укрепить) идёт ДО фазы 6.
- Инвайт: payload `{email, role}`, `team_join` — `get_or_create` без перепроверки приглашающего.
- `TelegramLiteScopeMiddleware._revoked` уже проверяет `role=OWNER` на каждый запрос — нужен замок.
- `audit_event` пишет в SHARED `AuditEvent` → чистка одной beat-задачей.
- `notify` уже `on_commit` + Celery + дедуп; образец письма — `refunds._notify_owner_rest`.

## Решения внутри плана (по рекомендации; показать владельцу)
- **Р-c1** писатель — новый `apps/core/perm_grants.py` (не тянуть audit/notify в `permissions.py`);
  замок «единственный писатель» — grep/AST.
- **Р-c2** `team.edit`/`team.delete` — только у роли admin (normalize вырезает у staff).
- **Р-c3** область admin: выдать — `effective(actor) − SENSITIVE` (§15.10); отозвать — в пределах
  `effective(actor)`; ключи вне области сохраняются (§15.3).
- **Р-c4** чувствительные ключи хранятся в дельте как есть; замок замораживает
  `SENSITIVE ∩ PRESETS[role]` (§15.7).
- **Р-c5** легаси-инвайты (без `v`/`inviter_pk`, ≤ 7 дней, выпущены только владельцем) —
  принимаются с чистым пресетом роли.
- **Р-c6** журнал `team.*` — 3 года (В-8).

## Фазы
0. Скиллы ECC + `security-reviewer` по плану; `Membership.pk` — UUID, `membership_id` строго UUID.
1. **Замки ДО кода:** `test_perm_storage` (normalize, effective, повреждённый JSON → пресет,
   заморозка SENSITIVE∩пресет, мемо 1 запрос + `forget` + привязка к схеме), `test_perm_grants`
   (эскалация, правка себя/admin/owner, чувствительное от admin, сохранение ключей вне области,
   перепроверка роли в транзакции, аудит без PII, письмо + дедуп, действует сразу),
   `test_team_invite_perms` (выпуск/принятие/легаси/rate-limit), `test_team_view_roles`
   (через middleware), переписать `test_staff_walk` (ожидание из `view_perms.rule_for` + пресетов —
   ЗЕЛЁНЫЙ на старом коде), `test_view_perms` (замороженные `LEGACY_*_PREFIXES`, `_required_perm` ∈
   правила маршрута), `test_perm_floor` (пол при полном grant; выданный `kunden.export` открывает
   CSV — красный до фазы 6; лёгкий пакет; Mini App), grep-замки, осознанная переписка
   test_partial_refund/test_ka_w2_finance_anchor/test_e22_sales_csv/test_closures_owner_portal.
2. **Миграция и чтение:** `Membership.permissions = JSONField(default=dict, blank=True)`,
   `core/0013` (один AddField), `SENSITIVE`, `ROLE_LIMIT`, `normalize_permissions`,
   `effective_from(role, raw)`, `effective(user)` с мемо `(schema, frozenset)` + `forget`,
   `ROLE_TEMPLATES` (только данные).
3. **Сервис** `perm_grants.set_member_permissions(actor, member_pk, keys, template=None)`: atomic,
   `select_for_update` строк актора и цели одним запросом `order_by("pk")`, роли перечитываются,
   права актора — из заблокированной строки; `new = (old − revoke_scope) ∪ (requested ∩ revoke_scope)`;
   `added ⊄ grant_scope` → `team.perms_denied` (свой savepoint) + `PermsDenied`; дельта без изменений —
   без записи; `update_fields=["permissions","updated_at"]`; аудит `team.perms` в savepoint; `forget`;
   письмо владельцу при выдаче не-владельцем ключей `OWNER_ALERT_KEYS` (дедуп по хешу состояния, в
   try). `set_member_role` (только owner, перенормализация дельты, гарды последнего владельца).
4. **Инвайт:** `issue_invite(..., inviter, perms, template)` (admin не приглашает admin, ключи ⊆
   области), payload `v=2`; `team_join` перечитывает приглашающего под блокировкой (недействителен →
   404 без Membership), срезает лишнее, легаси → пресет, аудит `team.join` со `stripped`, rate-limit.
5. **Укрепить `team_view`** (ДО снятия префиксов): роли — только owner; revoke admin'ом — только staff
   и с `team.delete`; POST-действие `perms` с сентинелом `perms_present`.
6. **Снять ролевые префиксы и декораторы:** `OWNER_FLOOR_PREFIXES` (billing, recht, geschaeft,
   imports/website); удалить `OWNER_ONLY_PREFIXES`/`FINANCE_EXPORT_PREFIXES`/`required_role_for_path`/
   `owner_required`/`finance_export_required`; `owner_floor_required`; `view_perms.perm_required` для
   прямых вызовов; 14 мест декораторов (под `@login_required`); инлайн-пол IBAN/импорт/lite остаётся.
7. **Срок журнала:** beat `purge_team_audit` (3 года, пачками, `idempotent_task`,
   `TEAM_AUDIT_RETENTION_DAYS`).
8. **i18n и доки:** письмо владельцу, сообщения `team_view`, `PermsDenied` — 5 каталогов; build-log
   (карта переписанных замков), task-catalog, CLAUDE.md §3, очередь деплоя `core/0013`.

## Миграция
Один `AddField` JSONField с константным дефолтом — без перезаписи таблицы, бэкфилл не нужен (пустой
dict = пресет). ~136 схем, таблица крошечная. Шаблон `_template` пересобирается шагом 6a
`ensure_template_schema`; после деплоя — `migration_state`. Откат кода безопасен; `RemoveField` —
только с согласия владельца. Локально после миграции — `--create-db`.

## Риски
- HIGH снятие префиксов откроет экран → голден `LEGACY_OWNER_ONLY_PREFIXES` + E11.2 зелёные ДО фазы 6;
  фаза 5 раньше 6.
- HIGH эскалация через гонку → блокировка обеих строк, права актора из заблокированной строки.
- HIGH стирание прав, выданных владельцем, при сохранении admin'ом → формула области + замок.
- MEDIUM устаревшее мемо → `forget`, привязка к схеме; аудит в atomic → свой savepoint; письмо —
  только `owner_email`, без данных клиентов, дедуп; объём переписанных замков → карта в build-log.
- Пакетный и Telegram-гейты остаются сильнее прав (замки).

## Критерии готовности
- [ ] Пустой `permissions` = сегодняшний доступ (паритет, E11.2, view_perms зелёные).
- [ ] Выданный admin'у `kunden.export`/`finanzen.bank`/`geld.korrektur` открывает экран; пол — нет.
- [ ] Единственный писатель; эскалация/правка себя/правка не-staff/чувствительное от admin — отказ с аудитом.
- [ ] Отзыв действует на следующем запросе; одна выборка Membership на запрос.
- [ ] Инвайт перепроверяется при принятии.
- [ ] Журнал «до/после», письмо владельцу, чистка через 3 года.
- [ ] Нет `owner_required`/`OWNER_ONLY_PREFIXES`/`required_role_for_path` (grep-замок).
- [ ] `core/0013` в очереди деплоя.

## ECC-прогоны
| Когда | Скиллы (до кода) | Агенты |
|---|---|---|
| После плана | django-security, database-migrations, django-patterns | `security-reviewer` — ревью плана |
| Фаза 1 | django-tdd, python-testing | — |
| Фаза 2 | postgres-patterns, database-migrations | `database-reviewer` — `core/0013`, блокировки |
| Фазы 3–5 | error-handling, django-celery | `security-reviewer` — сервис/инвайт/письмо/IDOR; `silent-failure-hunter` — fail-closed effective, глушение audit/notify |
| Фаза 6 | django-verification | `django-reviewer` — декораторы, 14 мест, паритет |
| Перед мержем | — | `django-reviewer` по ветке; доки по конвенции памяти |

UI/Playwright/a11y — в E6.7d.

## Ревью безопасности плана (2026-10-25) — ПРИНЯТЬ
**HIGH**
- **A1** `telegram-connect/disconnect`, `platform-bot-connect/disconnect`, `integrations-telegram-activate`
  → `FLOOR` (токен своего бота подменяет бота клиентов; ссылка общего бота несёт `user_pk` и проверяется
  как ROLE_OWNER). Google/FB-каналы (`channel-*`, `gbp-*`) остаются под чувствительным `kanaele.edit` —
  выдаёт только владелец (решение записано).
- **A2** `set_member_role` и revoke — `atomic` + блокировка ВСЕХ строк Membership схемы одним
  `select_for_update().order_by("pk")` (таблица крошечная) — тот же порядок в выдаче прав и `team_join`;
  actor == target — отказ до блокировки; после блокировки роль цели перечитывается; нет строки актора — отказ.
- **A3** Семантика дельты: `{"add": [...], "remove": [...], "template": ""}` относительно `PRESETS[role]`;
  `added = effective_after − effective_before` ПОСЛЕ замыкания и лимита роли; замыкание только удаляет
  (выдача `edit` без `view` = no-op, тест). normalize никогда не бросает; повреждённая дельта у
  staff/admin → пресет МИНУС все чувствительные ключи + лог (fail-closed, а не «пресет»).
- **A4** Мемо — только на объекте `user` в пределах запроса, ключ `(schema, user_pk)`; глобального
  кэша нет; в Celery/командах не мемоизировать; тест «1 запрос Membership на рендер».
**MEDIUM**
- **B1** `team_view`: каждое POST-действие само проверяет `team.edit|team.delete` + правило цели; admin —
  только staff, не себя/admin/owner; строгий UUID; один ответ «Mitglied nicht gefunden» на чужое/мусор.
- **B2** инвайт: `inviter_pk` = pk Membership, перечитывается под блокировкой; rate-limit выпуска и
  принятия; лимит открытых инвайтов; легаси — аудит `legacy=True`.
- **B3** тесты формулы Р-c3, в т.ч. «чувствительный ключ пресета staff, отозванный владельцем, admin
  вернуть не может». `domains.edit` у staff — унаследованная слабость, кандидат на снятие в E6.7f.
- **B4** `team.*` вырезается у staff и в `effective`, не только при записи; e-mail участников на экране
  команды — только владельцу/admin с `team.edit`, иначе маска.
- **B5** письмо: `owner_email` → фолбэк на e-mail владельцев; без e-mail цели и клиентов; троттлинг
  «1 письмо на цель в час»; `PermsDenied` не перечисляет недостающие ключи.
- **B6** аудит: ошибка записи аудита ОТКАТЫВАЕТ выдачу (выдача — чувствительное действие); ошибка
  письма — нет. Чистка — только `team.*`, пачками.
- **B7** паритет фазы 6 — по маршрутам (голден `LEGACY_*_PREFIXES` + E11.2), а не только по префиксам.
**Прочее**: `cab_is_owner` на кнопках CSV → `cab_can`; `nav_registry.owner_only` → ключ права (E6.7e);
тест «POST налоговых полей в `settings` игнорируется»; тест «staff POST с банковскими полями их не меняет,
форма не 403»; тест «Membership схемы A не действует в схеме B»; grep `Membership….save()` без
`update_fields`; отзыв участника гасит его открытые инвайты.

## Разбиение на инкременты (батч, один CI на верхушке каждого)
- **E6.7c-1** миграция `core/0013` + `normalize_permissions`/`effective_from`/мемо (A3, A4, B4-strip) —
  без писателя; паритет цел.
- **E6.7c-2** `perm_grants.py`: `set_member_permissions` + `set_member_role` + revoke под блокировкой
  (A2, B3, B5, B6), аудит, письмо.
- **E6.7c-3** инвайт v2 (B2) + укрепление `team_view` (B1, B4-маска).
- **E6.7c-4** снятие префиксов/декораторов (A1 в пол, B7, `cab_is_owner`→`cab_can`, `perm_required`) +
  beat чистки журнала.
