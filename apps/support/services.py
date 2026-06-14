"""Сервисы платформенной поддержки (M22c)."""

from django.db import transaction
from django.utils import timezone

from .models import SupportMessage, SupportThread


def open_thread(*, tenant, subject, body):
    with transaction.atomic():
        thread = SupportThread.objects.create(tenant=tenant, subject=(subject or "").strip()[:200])
        add_message(thread, body=body, author_role=SupportMessage.AUTHOR_OWNER)
    return thread


def add_message(thread, *, body, author_role):
    message = SupportMessage.objects.create(
        thread=thread, author_role=author_role, body=(body or "").strip()
    )
    thread.last_message_at = timezone.now()
    if author_role == SupportMessage.AUTHOR_OWNER:
        thread.unread_for_platform = True
        thread.unread_for_owner = False
        if thread.status in (SupportThread.STATUS_RESOLVED, SupportThread.STATUS_CLOSED):
            thread.status = SupportThread.STATUS_OPEN
    else:  # ответ платформы
        thread.unread_for_owner = True
        thread.unread_for_platform = False
    thread.save(
        update_fields=[
            "last_message_at",
            "unread_for_platform",
            "unread_for_owner",
            "status",
            "updated_at",
        ]
    )
    return message
