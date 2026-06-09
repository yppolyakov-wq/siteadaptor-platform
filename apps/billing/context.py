"""Context processor: данные подписки для баннера в кабинете владельца.

Подключён в TEMPLATES (config/settings/base.py). subscription_status/gated ставит
middleware; здесь добавляем число оставшихся дней триала для баннера.
"""

from django.utils import timezone

from .state_machine import GATED_STATUSES, TRIAL


def subscription(request):
    tenant = getattr(request, "tenant", None)
    status = getattr(request, "subscription_status", None)
    if status is None:
        status = getattr(tenant, "subscription_status", "") if tenant is not None else ""

    trial_days_left = None
    if status == TRIAL and getattr(tenant, "trial_ends_at", None):
        trial_days_left = max(0, (tenant.trial_ends_at - timezone.now()).days)

    return {
        "subscription_status": status,
        "subscription_gated": status in GATED_STATUSES,
        "trial_days_left": trial_days_left,
    }
