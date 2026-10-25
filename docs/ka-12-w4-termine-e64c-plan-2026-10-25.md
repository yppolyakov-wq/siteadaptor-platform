# KA-12 Волна 4 · Termine — E6.4c «Anzahlung nach Nichterscheinen» + срок хранения заметок — план, 2026-10-25

План — агент `planner` по коду `main` (`7c26d7eb`). Решения владельца (2026-10-25, «по рекомендации»):
E6.4c — да, N=2 за 365 дней, без Stripe онлайн-запись закрыта с просьбой позвонить; заметки к процедурам —
без поля аллергий и без шифрования, срок хранения 3 года после последнего визита. В-A1…A5, В-B1…B3 — по
рекомендациям ниже. Оба инкремента БЕЗ миграций.

## 0. Что найдено в коде
- `site_config["booking"]` не существует; `normalize()` (`apps/tenants/siteconfig.py`) выбрасывает
  неизвестные ключи → нужен `normalize_booking` по образцу `normalize_presence`/`normalize_anfrage`.
- Витрина ищет клиента по `email__iexact` (`services._get_or_create_customer`); телефон — только из кабинета
  (KA-H7). E-mail на витрине необязателен.
- Депозит: `service_book` и `termin_book` (`apps/booking/public_views.py`); оба глушат `StripeError` через
  `pass`; у ресурсного пути есть обход «Rechnung» (`payment_methods.offline_payment`).
- `payments.deposit_checkout_url` сам ставит `start_online_hold`; неоплаченное снимает
  `core.payment_holds.expire_overdue` через FSM.
- Mehrfachkarte (`_redeem_pass_if_code`) — визит оплачен, депозит не нужен; остаётся раньше правила.
- Роли: `roles.can_edit_policy`; образец точечной записи конфига — `set_presence_view`.
- Образцы задач по сроку: `stays.tasks.purge_old_registrations`, `promotions.tasks.purge_reservation_pii`.
- Абзац Datenschutz — `Tenant._privacy_treatment_paragraph`.

## Инкремент B — срок хранения заметок (первым)
- `settings.SERVICE_NOTE_RETENTION_DAYS = 3 * 365` — одно место истины (задача + текст Datenschutz).
- `apps/crm/tasks.py::purge_due_service_notes(now=None) -> int`: якорь =
  `Greatest(Coalesce(<последняя запись клиента в любом статусе>, created_at), created_at)`; удалять
  `kind="service"` с якорем старше срока, пачками по pk. **В-B1** Greatest — заметка моложе 3 лет не
  удаляется никогда. **В-B2** любые статусы, будущая запись продлевает. **В-B3** чистим независимо от модуля.
- `@idempotent_task` `purge_old_service_notes()` по всем схемам, `tenant_context`, try/except +
  `logger.exception` на тенант; beat раз в сутки.
- Datenschutz: «…spätestens 3 Jahre nach Ihrem letzten Termin automatisch gelöscht…»; подпись в кабинете
  «Behandlungshistorie».
- Тесты: удаляется/остаётся (запись 2 г, будущая, свежая заметка, `kind="note"`), идемпотентность, падение
  одного тенанта не блокирует второй, без N+1, абзац Datenschutz, запись beat.

## Инкремент A — E6.4c
- Хранение: `site_config["booking"] = {"no_show_deposit": {"after": 2, "days": 365, "cents"?}}`,
  presence-minimal (выключено — ключа нет, golden целы). Клампы: after 1..10, days 30..730, cents 1..100000.
- `apps/booking/no_show_rule.py`: `rule(tenant)`, `recent_no_shows_for_email(email, days)` (по всем
  карточкам с этим e-mail, телефон — никогда), `decide(...) -> Decision(none|deposit|call, cents)`:
  сумма = депозит услуги/ресурса → `cents` конфига → цена (**В-A1** 100 %); кап «≤ к оплате» (цена минус
  сертификат; **В-A4** по сумме группы); сумма 0 (**В-A2**), Stripe не готов или «Rechnung» → `call`.
  Ресурсная запись без цены — без капа (**В-A3**).
- Решение ДО `book_many`/`book`: `call` → бронь не создаётся, нейтральное сообщение с телефоном
  («Für diese Buchung bitten wir um einen kurzen Anruf: …») — без причины и без упоминания e-mail.
- Принудительный депозит + `StripeError` → не `pass`: удержание, лог, сообщение, редирект на `/t/<code>/`
  («Jetzt bezahlen»). Обычный депозит — байт-в-байт как раньше.
- **В-A5** при включённом правиле e-mail обязателен для онлайн-записи ВСЕМ (иначе обход пустым полем).
- Прозрачность: общая строка политики в buy-box для всех («Nach wiederholtem Nichterscheinen bitten wir
  bei Online-Buchungen um eine Anzahlung.»), оракула не создаёт.
- Кабинет: панель на `/dashboard/booking/leistungen/` рядом с правилами отмены B6; приёмник
  `booking:no-show-rule` (POST, owner/admin, точечная запись), staff — только чтение.
- Тесты: normalize/golden/W6-замок, подсчёт, вьюхи (deposit/none/call/паритет/сертификат/Mehrfachkarte/
  StripeError/группа/termin_book/Rechnung), оракул (тексты одинаковы), кабинет (роли), один запрос.

## Риски
R-A1 остаточный оракул при подключённом Stripe (редирект на оплату) — принят, сдерживается rate limit и
реальной pending-бронью с письмом жертве · R-A2 обход другим e-mail закрыть нельзя · R-A4 Stripe пропал
после создания брони → отмена через FSM `actor="system:no-show-rule"` · R-A5 класс W6 — точечная запись +
замок · R-B1 подзапрос без индекса `(customer, start)` — проверить планом · R-B2 необратимое удаление —
тест «моложе 3 лет не удаляется» ДО beat.

## ECC-прогоны
| Когда | Что |
|---|---|
| До кода | скиллы `django-patterns`, `django-tdd`, `django-security`, `error-handling`, `django-celery`, `postgres-patterns`; `pitfalls.md` §1, §3, §4, §6 |
| После плана | `security-reviewer` — ревью плана A (оракул, решение до брони, Rechnung, ресурсный путь, пустой e-mail) |
| B после кода | `database-reviewer` (подзапрос/Greatest/пакеты), `django-reviewer` (задача/beat), `silent-failure-hunter` (try/except по тенантам) |
| A после кода | `django-reviewer`, `security-reviewer` (оракул, роли, `test_orphan_decorators`), `silent-failure-hunter` (StripeError, удержание) |
| A UI | `a11y-architect`; Playwright-стенд friseur 390/1440, de+ru |
| Перед пушем | `ruff format --check .`, `test_template_comments`, `i18n_quickcheck`, pytest серийно `--reuse-db` |
