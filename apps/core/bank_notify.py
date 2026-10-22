"""KA-H2: письмо владельцу о смене банковских реквизитов Vorkasse.

Письмо безопасности — матрица уведомлений его не выключает. Полный IBAN не
пишем ни в письмо, ни в лог: только маску. Шлём и когда меняет сам владелец —
внезапное письмо — первый сигнал, что аккаунт захвачен.
"""

import hashlib

from django.db import connection
from django.urls import reverse
from django.utils import timezone

from apps.notifications.services import notify
from apps.promotions.notifications import _base_url, _owner_email, _render, _tenant

from .iban import mask_iban


def notify_bank_change(tenant, old, new, actor: str) -> None:
    schema = connection.schema_name
    current = _tenant(schema) or tenant
    recipient = _owner_email(current)
    if not recipient:
        return
    old_holder, old_iban, old_bic = old
    new_holder, new_iban, new_bic = new
    now = timezone.now()
    ctx = {
        "business": getattr(current, "name", ""),
        "old_holder": old_holder,
        "old_iban": mask_iban(old_iban),
        "old_bic": old_bic,
        "new_holder": new_holder,
        "new_iban": mask_iban(new_iban),
        "new_bic": new_bic,
        "actor": actor,
        "changed_at": timezone.localtime(now),
        "settings_url": _base_url(schema) + reverse("payment-settings"),
    }
    subject, body, html = _render("bank_details_changed_owner", ctx)
    digest = hashlib.sha256(f"{old}|{new}|{now.isoformat()}".encode()).hexdigest()[:16]
    notify(
        dedupe_key=f"bank:{schema}:{digest}",
        type="bank_details_changed_owner",
        recipient=recipient,
        subject=subject,
        body=body,
        html=html,
    )
