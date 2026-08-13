"""Досье участника: раздел в ЛК, приватная выдача файла, матрица у организатора.

Выдача — только здесь. Отказ отвечает 404 (не 403): существование чужого
документа не подтверждаем.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.account.auth import current_customer

from . import services
from .models import SecureDocument


def _require_account(request):
    """ЛК клиента гейтится своим модулем; без входа — на страницу входа."""
    tenant = getattr(request, "tenant", None)
    if tenant is None or not tenant.is_module_active("customer_account"):
        raise Http404
    customer = current_customer(request)
    if customer is None:
        return None
    return customer


def documents_home(request):
    """Раздел «Dokumente» в ЛК: список своих документов + загрузка."""
    customer = _require_account(request)
    if customer is None:
        return redirect("account-login")
    if request.method == "POST":
        uploaded = request.FILES.get("file")
        if uploaded is None:
            messages.error(request, _("Bitte eine Datei auswählen."))
        elif not request.POST.get("consent"):
            # Явное согласие на хранение — храним момент как доказательство.
            messages.error(request, _("Bitte der Speicherung zustimmen."))
        else:
            try:
                services.store(
                    uploaded,
                    owner=customer,
                    kind=request.POST.get("kind") or SecureDocument.KIND_OTHER,
                    ref_kind=request.POST.get("ref_kind", "")[:20],
                    ref_id=request.POST.get("ref_id", "")[:64],
                    note=(request.POST.get("note") or "")[:500],
                    uploaded_by=SecureDocument.BY_CUSTOMER,
                )
                messages.success(request, _("Dokument gespeichert."))
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
        return redirect("account-documents")
    return render(
        request,
        "konto/documents.html",
        {
            "documents": SecureDocument.objects.filter(owner=customer),
            "kinds": SecureDocument.KINDS,
            "retention_days": services.retention_days(),
        },
    )


def document_download(request, pk):
    """Приватная выдача: расшифровка в памяти, отдача вложением."""
    document = get_object_or_404(SecureDocument, pk=pk)
    if not services.can_access(request, document):
        raise Http404
    from .storage import read_decrypted

    data = read_decrypted(document.path)
    if not data:
        raise Http404
    response = HttpResponse(data, content_type=document.mime or "application/octet-stream")
    name = document.original_name or "dokument"
    response["Content-Disposition"] = f'attachment; filename="{name}"'
    # Приватный файл не должен осесть в кэшах по пути к клиенту.
    response["Cache-Control"] = "private, no-store"
    return response


@require_POST
def document_delete(request, pk):
    """Удаление своего документа участником (вместе с blob)."""
    document = get_object_or_404(SecureDocument, pk=pk)
    if not services.can_access(request, document):
        raise Http404
    services.purge(document)
    messages.success(request, _("Dokument gelöscht."))
    return redirect("account-documents")


@login_required
def event_documents(request, pk):
    """Кабинет: матрица «участник × документ» по заезду — кто что сдал."""
    from apps.core import status_registry
    from apps.events.models import Event

    event = get_object_or_404(Event, pk=pk)
    tickets = (
        event.tickets.select_related("customer")
        .exclude(status__in=status_registry.cancelled_statuses_for("ticket"))
        .order_by("created_at")
    )
    owner_ids = [t.customer_id for t in tickets if t.customer_id]
    documents = SecureDocument.objects.filter(owner_id__in=owner_ids)
    by_owner: dict = {}
    for document in documents:
        by_owner.setdefault(str(document.owner_id), []).append(document)
    rows = [
        {
            "ticket": ticket,
            "customer": ticket.customer,
            "documents": by_owner.get(str(ticket.customer_id), []),
        }
        for ticket in tickets
    ]
    return render(
        request,
        "documents/event_documents.html",
        {"event": event, "rows": rows, "kinds": SecureDocument.KINDS, "nav": "events"},
    )
