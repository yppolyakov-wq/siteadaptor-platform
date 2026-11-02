# SEC волна 1 «деньги и зависимости» — план (2026-11-02)

Решение владельца 2026-11-02: «делай по рекомендации» по всем пунктам §4 отчёта
`security-audit-report-2026-11-01.md`. Волна 1 — пункты, где под угрозой деньги.

## Пункты и фикс

| ID | Дефект | Фикс | Замок (красный до фикса) |
|---|---|---|---|
| SEC-D4 | `StateMachine.apply` читает статус из объекта в памяти: две параллельные отмены обе проходят переход и дважды возвращают сертификат/лимит акции/склад | `apply` берёт строку `select_for_update` внутри `atomic` и перечитывает статус; уже в `dst` → no-op, иначе переход считается от фактического статуса | устаревший объект после отмены: второй `apply(..., "cancelled")` — no-op, `on_transition` не вызван второй раз |
| SEC-D4b | `.delay` в хуках событий/акций внутри новой транзакции мог уйти раньше коммита | `transaction.on_commit` в `EventSM`/`PromotionSM` | замки агрегатора с `django_capture_on_commit_callbacks` |
| SEC-D5 | `issue_invoice` не блокирует счёт: два клика — два номера, первый потерян (дыра GoBD) | блокировка строки счёта; уже не черновик → вернуть без нового номера | устаревший объект после выпуска: повторный `issue_invoice` не тратит номер |
| SEC-D6 | `start_online_hold` продлевает удержание +24 ч при каждом открытии страницы оплаты | потолок = `created_at + 24 ч`; меньше 45 мин до потолка — сессия без своего срока (поздняя оплата → штатный автовозврат `settle_late_payment`) | повторный вызов через 23 ч не сдвигает срок дальше потолка |
| SEC-D3 | Connect-оплаты (SEPA/Klarna) помечаются оплаченными на `checkout.session.completed` с `payment_status=unpaid` | общий шлюз в `handle_event`: `completed` без `paid` → ждём; `async_payment_succeeded` → как `completed`; `async_payment_failed` → лог (удержание снимет сделку); то же для `featured` | `completed` с `unpaid` не ставит оплату; `async_payment_succeeded` ставит |
| SEC-G2a | Django 5.1 EOL (9 CVE), Pillow 12 → 13, прочие | `uv lock` на 5.2 LTS / Pillow 13 / patch-версии; полный CI + стенд | CI целиком |

## Ops владельцу (после деплоя)
- Stripe Dashboard → Webhooks: добавить события `checkout.session.async_payment_succeeded`
  и `checkout.session.async_payment_failed` (иначе SEPA-оплаты не дойдут вовсе).

## ECC-прогоны
- До кода: `django-patterns`, `django-security`, `database-migrations` (миграций нет).
- После кода: `django-reviewer` (FSM-ядро), `security-reviewer` + `silent-failure-hunter`
  (вебхук/деньги), `database-reviewer` (блокировки).
