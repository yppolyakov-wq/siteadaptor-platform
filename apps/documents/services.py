"""Правила досье: кто может видеть документ, когда он истекает, как удаляется."""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.core.roles import has_cabinet_access

from .models import SecureDocument
from .storage import delete_blob, save_encrypted


def retention_days() -> int:
    """Сколько дней документ живёт после поездки (владелец может переопределить)."""
    return int(getattr(settings, "DOCUMENT_RETENTION_DAYS", 90) or 90)


def _ticket_expiry(ref_kind: str, ref_id: str):
    """Дата удаления по привязанной сделке: конец поездки + retention."""
    if ref_kind != "ticket" or not ref_id:
        return None
    from apps.events.models import Ticket

    ticket = Ticket.objects.filter(pk=ref_id).select_related("event").first()
    if ticket is None:
        return None
    event = ticket.event
    end = event.ends_at or event.starts_at
    return (end + timedelta(days=retention_days())).date()


def store(uploaded, *, owner, kind, ref_kind="", ref_id="", note="", uploaded_by):
    """Сохранить документ участника (шифрует содержимое, считает срок хранения)."""
    path, mime, size = save_encrypted(uploaded)
    return SecureDocument.objects.create(
        owner=owner,
        kind=kind,
        ref_kind=ref_kind,
        ref_id=str(ref_id or ""),
        path=path,
        original_name=(getattr(uploaded, "name", "") or "")[:255],
        mime=mime,
        size=size,
        note=note,
        uploaded_by=uploaded_by,
        consent_at=timezone.now(),
        expires_at=_ticket_expiry(ref_kind, ref_id),
    )


def can_access(request, document) -> bool:
    """Доступ к документу: его владелец (сессия ЛК) или сотрудник кабинета.

    Fail-closed: всё остальное — нет. Вьюха на отказе отдаёт 404, а не 403,
    чтобы не подтверждать существование документа.
    """
    user = getattr(request, "user", None)
    if user is not None and has_cabinet_access(user):
        return True
    from apps.account.auth import SESSION_KEY

    session = getattr(request, "session", None) or {}
    customer_id = session.get(SESSION_KEY)
    return bool(customer_id) and str(document.owner_id) == str(customer_id)


def purge(document) -> None:
    """Удалить и запись, и зашифрованный blob (иначе бакет копит PII)."""
    delete_blob(document.path)
    document.delete()


def purge_expired(today=None) -> int:
    """Удалить документы с истёкшим сроком. → сколько удалено (для beat/логов)."""
    today = today or timezone.localdate()
    stale = list(SecureDocument.objects.filter(expires_at__lt=today))
    for document in stale:
        purge(document)
    return len(stale)
