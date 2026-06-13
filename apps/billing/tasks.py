"""Celery-beat биллинга: жизненный цикл подписок + напоминания о триале.

Tenant — SHARED (public-схема), поэтому задача работает по Tenant.objects
напрямую, без schema_context (в отличие от per-tenant задач promotions). Все
смены статуса — через SubscriptionSM.apply() (идемпотентно). Чистая логика
вынесена в roll_subscription_lifecycle / enqueue_trial_reminders — их и тестируем.
"""

from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from apps.core.jobs import idempotent_task
from apps.tenants.models import Tenant

from .state_machine import PAST_DUE, SUSPENDED, TRIAL, TRIAL_EXPIRED, SubscriptionSM

# Дни до конца триала, когда шлём напоминание (триал 14д → дни 11/13/14).
_REMINDER_DAYS = (3, 1, 0)


def roll_subscription_lifecycle(now=None) -> dict:
    """Просрочка триалов и past_due (public-схема). Возвращает счётчики переходов."""
    now = now or timezone.now()
    grace = timedelta(days=settings.BILLING_GRACE_DAYS)
    sm = SubscriptionSM()
    trial_expired = suspended = 0

    # Триал истёк → trial_expired (день 14).
    for tenant in Tenant.objects.filter(
        subscription_status=TRIAL, trial_ends_at__isnull=False, trial_ends_at__lte=now
    ):
        sm.apply(tenant, TRIAL_EXPIRED)
        trial_expired += 1

    # trial_expired без оплаты дольше grace → suspended (день 21).
    for tenant in Tenant.objects.filter(
        subscription_status=TRIAL_EXPIRED,
        trial_ends_at__isnull=False,
        trial_ends_at__lte=now - grace,
    ):
        sm.apply(tenant, SUSPENDED)
        suspended += 1

    # past_due дольше grace → suspended.
    for tenant in Tenant.objects.filter(
        subscription_status=PAST_DUE,
        subscription_ends_at__isnull=False,
        subscription_ends_at__lte=now - grace,
    ):
        sm.apply(tenant, SUSPENDED)
        suspended += 1

    return {"trial_expired": trial_expired, "suspended": suspended}


@idempotent_task()
def send_trial_reminder(*, tenant_id, days_left):
    """Письмо-напоминание владельцу об окончании триала."""
    tenant = Tenant.objects.filter(id=tenant_id).first()
    if tenant is None or not tenant.owner_email:
        return {"skipped": True}
    when = "heute" if days_left == 0 else f"in {days_left} Tagen"
    send_mail(
        subject="Ihre Testphase endet bald",
        message=(
            f"Ihre Testphase endet {when}. Aktivieren Sie Ihr Abo, "
            "um ohne Unterbrechung weiterzuarbeiten."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[tenant.owner_email],
    )
    return {"sent": True, "tenant_id": tenant_id, "days_left": days_left}


def enqueue_trial_reminders(now=None) -> int:
    """Поставить напоминания для триалов на днях 11/13/14 (dedupe по tenant+day)."""
    now = now or timezone.now()
    count = 0
    for tenant in Tenant.objects.filter(
        subscription_status=TRIAL, trial_ends_at__isnull=False, trial_ends_at__gte=now
    ):
        days_left = (tenant.trial_ends_at - now).days
        if days_left in _REMINDER_DAYS:
            send_trial_reminder.delay(
                dedupe_key=f"trial_reminder:{tenant.id}:{days_left}",
                tenant_id=tenant.id,
                days_left=days_left,
            )
            count += 1
    return count


@idempotent_task()
def roll_subscriptions():
    """Beat: ежедневный жизненный цикл подписок + напоминания (public-схема)."""
    now = timezone.now()
    result = roll_subscription_lifecycle(now)
    result["reminders"] = enqueue_trial_reminders(now)
    return result


@idempotent_task()
def bill_usage_fees():
    """Beat (раз в сутки): Nutzungsgebühr за прошлый месяц (вариант B, P2.5-fee).

    Идём по активным арендаторам, выставляем плату за завершённый месяц. Период
    бьётся один раз (UsageFeeRecord по tenant+период), поэтому ежедневный запуск
    безопасен. При проценте 0 (текущая настройка) — ничего не начисляем.
    """
    from django_tenants.utils import get_public_schema_name

    from .state_machine import ACTIVE
    from .usage import bill_tenant, previous_period

    period = previous_period()
    billed = 0
    for tenant in Tenant.objects.filter(subscription_status=ACTIVE).exclude(
        schema_name=get_public_schema_name()
    ):
        if bill_tenant(tenant, period) == "billed":
            billed += 1
    return {"period": period, "billed": billed}
