"""Сервисы платформенной поддержки (M22c).

AIS A-3b: обращение доходит в обе стороны — новое обращение/ответ владельца → письмо
платформе (без текста обращения, не чаще одного письма на тред за окно), ответ платформы →
письмо владельцу со ссылкой на тред. Письма — через `notify(dedupe_key=…)` после коммита;
сбой уведомления не ломает тред (только warning).
"""

import logging
import time

from django.conf import settings
from django.db import transaction
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from .models import SupportMessage, SupportThread

logger = logging.getLogger(__name__)

#: не больше одного письма платформе на тред за это окно (ответы владельца подряд)
PLATFORM_NOTIFY_WINDOW_S = 1800


def one_line(text) -> str:
    """Тема/имя в одну строку: перевод строки в заголовке письма роняет отправку
    (BadHeaderError) — письмо терялось бы молча (ревью A-3b)."""
    return " ".join(str(text or "").split())


def open_thread(*, tenant, subject, body):
    with transaction.atomic():
        thread = SupportThread.objects.create(tenant=tenant, subject=one_line(subject)[:200])
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
    if author_role == SupportMessage.AUTHOR_OWNER:
        transaction.on_commit(lambda: notify_platform(thread))
    elif author_role == SupportMessage.AUTHOR_PLATFORM:
        transaction.on_commit(lambda: notify_owner(thread, message))
    return message


def _in_tenant(tenant, fn):
    """Notification живёт в схеме бизнеса — писать туда и из админки платформы (public)."""
    from django_tenants.utils import schema_context

    with schema_context(tenant.schema_name):
        return fn()


def notify_platform(thread) -> None:
    """Письмо поддержке платформы: кто и о чём (текст обращения — только в админке)."""
    to = getattr(settings, "SUPPORT_NOTIFY_EMAIL", "") or getattr(
        settings, "PLATFORM_CONTACT_EMAIL", ""
    )
    if not to:
        return
    try:
        from apps.notifications.services import notify

        tenant = thread.tenant
        window = int(time.time() // PLATFORM_NOTIFY_WINDOW_S)
        with translation.override("de"):
            subject = _("Neue Support-Anfrage: %(firma)s — %(betreff)s") % {
                "firma": one_line(tenant.name),
                "betreff": one_line(thread.subject),
            }
            body = _("Antworten Sie in der Verwaltung: %(url)s") % {
                "url": f"{_platform_url()}/admin/support/supportthread/{thread.pk}/change/"
            }
        sent = _in_tenant(
            tenant,
            lambda: notify(
                dedupe_key=f"support-platform:{thread.pk}:{window}",
                type="support_platform",
                recipient=to,
                subject=one_line(subject)[:200],
                body=body,
            ),
        )
        if sent is None:  # уже было письмо по этому треду в окне — новое видно по флагу
            logger.info("support: platform mail for thread %s suppressed (window)", thread.pk)
    except Exception:  # noqa: BLE001 — письмо — дополнение: тред уже сохранён
        logger.exception("support: platform notification failed for thread %s", thread.pk)


def notify_owner(thread, message) -> None:
    """Письмо владельцу: поддержка ответила — ссылка на тред в кабинете."""
    try:
        from apps.notifications.services import notify, tenant_locale
        from apps.tenants.services import site_url_for

        tenant = thread.tenant
        to = (tenant.contact_email or tenant.owner_email or "").strip()
        if not to:
            logger.warning("support: tenant %s has no e-mail for the reply notice", tenant.pk)
            return

        def _send():
            with translation.override(tenant_locale()):
                subject = _("Antwort vom Support: %(betreff)s") % {
                    "betreff": one_line(thread.subject)
                }
                body = _("Der SiteAdaptor-Support hat geantwortet: %(url)s") % {
                    "url": f"{site_url_for(tenant)}/dashboard/help/{thread.pk}/"
                }
            return notify(
                dedupe_key=f"support-owner:{message.pk}",
                type="support_owner",
                recipient=to,
                subject=one_line(subject)[:200],
                body=body,
            )

        _in_tenant(tenant, _send)
    except Exception:  # noqa: BLE001 — письмо — дополнение: ответ уже в треде
        logger.exception("support: owner notification failed for thread %s", thread.pk)


def _platform_url() -> str:
    scheme = "http" if getattr(settings, "DEBUG", False) else "https"
    return f"{scheme}://{getattr(settings, 'TENANT_DOMAIN_BASE', 'siteadaptor.de')}"
