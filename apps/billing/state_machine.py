"""Машина состояний подписки арендатора.

Спецификация: docs/references/patterns/state-machine.md §«Subscription lifecycle».
База — apps.core.fsm. Поле статуса — Tenant.subscription_status (SHARED-схема).
Двигается beat-таском (apps.billing.tasks) по индексу (subscription_status,
trial_ends_at) и Stripe-вебхуками (apps.billing.webhooks). Любая смена статуса —
только через apply(); повтор того же статуса — идемпотентный no-op (защита от
повторных webhook/cron).

    trial ──(д14, нет оплаты)──► trial_expired ──(д21)──► suspended
      │                               │
      └──(оплата)──► active ◄──────────┘ (оплата)
    active ──(stripe payment_failed)──► past_due ──(grace 7д)──► suspended
    past_due ──(оплата)──► active
    suspended ──(оплата)──► active
"""

from apps.core.fsm import StateMachine, Transition

# Значения Tenant.subscription_status.
TRIAL = "trial"
ACTIVE = "active"
TRIAL_EXPIRED = "trial_expired"
PAST_DUE = "past_due"
SUSPENDED = "suspended"

# Статусы, при которых дашборд read-only (middleware блокирует запись).
GATED_STATUSES = frozenset({TRIAL_EXPIRED, SUSPENDED})


class SubscriptionSM(StateMachine):
    field = "subscription_status"
    transitions = [
        Transition(TRIAL, ACTIVE, "subscription.activated"),
        Transition(TRIAL, TRIAL_EXPIRED, "subscription.trial_expired"),
        Transition(TRIAL_EXPIRED, ACTIVE, "subscription.activated"),
        Transition(TRIAL_EXPIRED, SUSPENDED, "subscription.suspended"),
        Transition(ACTIVE, PAST_DUE, "subscription.past_due"),
        Transition(PAST_DUE, ACTIVE, "subscription.activated"),
        Transition(PAST_DUE, SUSPENDED, "subscription.suspended"),
        Transition(SUSPENDED, ACTIVE, "subscription.activated"),
    ]

    def on_transition(self, instance, t, **kw):
        # suspended = мягкое отключение: дашборд read-only, publish/рассылки off,
        # данные НЕ удаляем. Реактивация (→active) возвращает доступ. is_active —
        # тот же флаг, по которому агрегатор/витрина фильтруют арендатора.
        if t.dst == SUSPENDED and instance.is_active:
            instance.is_active = False
            instance.save(update_fields=["is_active", "updated_at"])
        elif t.dst == ACTIVE and not instance.is_active:
            instance.is_active = True
            instance.save(update_fields=["is_active", "updated_at"])
