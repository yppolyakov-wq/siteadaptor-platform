# Pattern: State Machine (явные переходы статусов)

Статус: Phase 1, Sprint 3 (Promotion/Reservation), Sprint 6 (Subscription).
Ссылается из: `phase1-plan-additions.md` §3.2, §6.6.

## Зачем

Статусы (`Promotion.status`, `Reservation.status`, `Tenant.subscription_status`)
нельзя менять разрозненными `obj.status = "..."` по коду — так появляются
невозможные переходы (`ended → active`), пропущенные side-effects (списание
остатка, рассылка) и невоспроизводимые баги. Решение: **одна таблица
разрешённых переходов на сущность** + единая точка применения перехода с
проверкой, хуком side-effect и audit-событием.

## Базовый механизм

```python
# apps/core/fsm.py
from dataclasses import dataclass


class IllegalTransition(Exception):
    def __init__(self, model, src, dst):
        super().__init__(f"{model}: {src} → {dst} запрещён")


@dataclass(frozen=True)
class Transition:
    src: str
    dst: str
    # имя события для audit-лога, напр. 'promotion.activated'
    event: str


class StateMachine:
    """Декларативная FSM поверх CharField-поля статуса."""

    field = "status"
    transitions: list[Transition] = []

    def __init__(self):
        self._index = {(t.src, t.dst): t for t in self.transitions}

    def can(self, src: str, dst: str) -> bool:
        return (src, dst) in self._index

    def apply(self, instance, dst: str, *, actor=None, **ctx):
        src = getattr(instance, self.field)
        if src == dst:
            return instance  # идемпотентно: повтор того же статуса — no-op
        t = self._index.get((src, dst))
        if t is None:
            raise IllegalTransition(type(instance).__name__, src, dst)

        setattr(instance, self.field, dst)
        instance.save(update_fields=[self.field, "updated_at"])

        # side-effect хук, переопределяется наследником
        self.on_transition(instance, t, actor=actor, **ctx)

        # audit с первого дня (см. patterns/audit-log.md)
        from apps.core.audit import audit_event
        audit_event(
            action=t.event,
            resource_type=type(instance).__name__.lower(),
            resource_id=str(instance.pk),
            actor=actor,
            changes={"status": [src, dst]},
            context=ctx,
        )
        return instance

    def on_transition(self, instance, t: Transition, **kw):
        """Side-effects конкретного перехода. Переопределяется."""
```

Применять переход **только** через `apply()` — прямые присваивания
`obj.status = ...` запрещены (ловится на code review / можно прикрыть
property-сеттером, бросающим исключение).

---

## Promotion FSM (Sprint 3)

```
draft ──────► scheduled ──────► active ──────► ended
  │                │               │
  └──► archived    └──► archived   └──► paused ──► active
                                   └──► ended
```

```python
# apps/promotions/state_machine.py
from apps.core.fsm import StateMachine, Transition


class PromotionSM(StateMachine):
    transitions = [
        Transition("draft",     "scheduled", "promotion.scheduled"),
        Transition("draft",     "archived",  "promotion.archived"),
        Transition("scheduled", "active",    "promotion.activated"),
        Transition("scheduled", "archived",  "promotion.archived"),
        Transition("active",    "paused",    "promotion.paused"),
        Transition("paused",    "active",    "promotion.activated"),
        Transition("active",    "ended",     "promotion.ended"),
        Transition("paused",    "ended",     "promotion.ended"),
    ]

    def on_transition(self, instance, t, **kw):
        if t.dst == "active":
            # публикация в каналы + материализация листинга агрегатора
            from apps.publishing.tasks import publish_to_channels_task
            publish_to_channels_task.delay(
                dedupe_key=f"publish:{instance.id}",
                promotion_id=instance.id,
            )
        elif t.dst == "ended":
            from apps.aggregator.tasks import sync_aggregator_listing
            sync_aggregator_listing.delay(
                dedupe_key=f"agg_sync:{instance.id}:ended",
                tenant_schema=connection.schema_name,
                promotion_id=instance.id,
            )
```

Переходы `scheduled → active` и `active → ended` дёргает beat-задача по
расписанию (`starts_at` / `ends_at`); она тоже идёт через `apply()`.

---

## Reservation FSM (Sprint 3)

```
pending ──► confirmed ──► fulfilled
   │            │
   └► cancelled └► cancelled  (возврат остатка)
              confirmed ──► expired (TTL)
```

```python
class ReservationSM(StateMachine):
    transitions = [
        Transition("pending",   "confirmed", "reservation.confirmed"),
        Transition("pending",   "cancelled", "reservation.cancelled"),
        Transition("confirmed", "fulfilled", "reservation.fulfilled"),
        Transition("confirmed", "cancelled", "reservation.cancelled"),
        Transition("confirmed", "expired",   "reservation.expired"),
    ]

    def on_transition(self, instance, t, **kw):
        # возврат остатка при отмене/истечении (см. anti-oversell.md::cancel)
        if t.dst in ("cancelled", "expired"):
            from django.db.models import F
            from apps.promotions.models import Promotion
            Promotion.objects.filter(id=instance.promotion_id).update(
                available_quantity=F("available_quantity") + instance.quantity
            )
        elif t.dst == "confirmed":
            from apps.notifications.tasks import send_notification_task
            send_notification_task.delay(
                dedupe_key=f"reservation_confirmed:{instance.id}",
                notification_type="reservation_confirmed",
                ...
            )
```

Важно: при `cancelled`/`expired` остаток возвращается **в той же транзакции**,
что и смена статуса, иначе при сбое получим утечку остатка.

---

## Subscription lifecycle (Sprint 6)

`Tenant.subscription_status` (SHARED-схема). Двигается **одним beat-таском раз
в сутки** по индексу `(subscription_status, trial_ends_at)` (см. §1.5) плюс
Stripe-webhook'ами.

```
trial ──(день 14, нет оплаты)──► trial_expired ──(день 21)──► suspended
  │                                    │
  └──(оплата)──► active ◄──────────────┘ (оплата)
active ──(stripe: payment_failed)──► past_due ──(grace 7д)──► suspended
past_due ──(оплата прошла)──► active
suspended ──(оплата)──► active
```

```python
class SubscriptionSM(StateMachine):
    field = "subscription_status"
    transitions = [
        Transition("trial",         "active",        "subscription.activated"),
        Transition("trial",         "trial_expired", "subscription.trial_expired"),
        Transition("trial_expired", "active",        "subscription.activated"),
        Transition("trial_expired", "suspended",     "subscription.suspended"),
        Transition("active",        "past_due",      "subscription.past_due"),
        Transition("past_due",      "active",        "subscription.activated"),
        Transition("past_due",      "suspended",     "subscription.suspended"),
        Transition("suspended",     "active",        "subscription.activated"),
    ]

    def on_transition(self, instance, t, **kw):
        if t.dst == "suspended":
            instance.is_active = False  # read-only доступ, данные НЕ удаляем
            instance.save(update_fields=["is_active"])
        # reminder-события (trial_ending:3d/1d, trial_expired) ставит сам
        # beat-таск с dedupe_key — см. §6.4, чтобы не дублить при повторном cron.
```

Reminder'ы (`trial_ending:{tenant_id}:3d/1d`) — это не переходы статуса, а
side-эффекты дней 11/13; их ставит планировщик с unique `dedupe_key`.
`suspended` = мягкое отключение (publish/рассылки выкл, дашборд read-only),
**не удаление**.

---

## Правила применения

- Любая смена статуса — только `sm.apply(obj, dst, actor=...)`.
- Повтор того же статуса — идемпотентный no-op (защита от двойных webhook/cron).
- Side-effect, меняющий БД (остаток, `is_active`), — в той же транзакции.
- Side-effect во внешний мир (рассылка, публикация) — через очередь с
  `dedupe_key` (см. `notification-dedupe.md`), а не синхронно.
- Каждый переход = audit-событие (`<resource>.<event>`).

## Чек-лист

- [ ] Таблица `transitions` объявлена декларативно на сущность.
- [ ] Нет прямых `obj.status = ...` вне `apply()`.
- [ ] Idempotent: повтор статуса — no-op.
- [ ] БД-side-effects в транзакции перехода; внешние — через очередь с dedupe.
- [ ] Каждый переход пишет audit-событие.
- [ ] Subscription FSM двигается beat-таском по индексу + Stripe-webhook'ами.
