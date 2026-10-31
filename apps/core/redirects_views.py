"""M21.1: экран «Weiterleitungen» (Website → старые адреса после переезда).

Список правил с поиском и пагинацией, добавление/удаление, CSV-импорт/экспорт.
Право — Website (``view_perms``: чтение W, запись WE); ввод — через
``apps.core.legacy_redirects`` (цель только локальная).
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core import legacy_redirects
from apps.core.models import LegacyRedirect

PAGE_SIZE = 50


@login_required
def redirects_view(request):
    if request.method == "POST":
        try:
            status = int(request.POST.get("status") or LegacyRedirect.STATUS_MOVED)
        except ValueError:
            status = 0
        try:
            _obj, created = legacy_redirects.upsert(
                request.POST.get("source", ""), request.POST.get("target", ""), status=status
            )
        except legacy_redirects.RedirectError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(
                request,
                _("Weiterleitung angelegt.") if created else _("Weiterleitung aktualisiert."),
            )
        return redirect("site-redirects")

    q = (request.GET.get("q") or "").strip()[:200]
    qs = LegacyRedirect.objects.all()
    if q:
        qs = qs.filter(Q(source_path__icontains=q) | Q(target__icontains=q))
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("seite"))
    totals = LegacyRedirect.objects.aggregate(hits=Sum("hits"))
    return render(
        request,
        "tenant/redirects.html",
        {
            "page": page,
            "q": q,
            "total": LegacyRedirect.objects.count(),
            "total_hits": totals["hits"] or 0,
            "status_choices": LegacyRedirect.STATUS_CHOICES,
            "nav": "redirects",
        },
    )


@login_required
@require_POST
def redirect_delete(request, pk):
    # pk приходит конвертером <uuid:pk> — мусор в адресе даёт 404 роутера, не 500.
    if LegacyRedirect.objects.filter(pk=pk).delete()[0]:
        messages.success(request, _("Weiterleitung gelöscht."))
    return redirect("site-redirects")


@login_required
@require_POST
def redirects_import(request):
    upload = request.FILES.get("file")
    if upload is None:
        messages.error(request, _("Bitte eine CSV-Datei wählen."))
        return redirect("site-redirects")
    result = legacy_redirects.import_csv(upload.read(legacy_redirects.CSV_MAX_BYTES + 1))
    if result.created or result.updated:
        messages.success(
            request,
            _("Importiert: %(c)s neu, %(u)s aktualisiert.")  # noqa: UP031
            % {"c": result.created, "u": result.updated},
        )
    for err in result.errors[:20]:
        messages.error(request, err)
    return redirect("site-redirects")


@login_required
def redirects_export(request):
    body = legacy_redirects.export_csv(LegacyRedirect.objects.all())
    response = HttpResponse(body, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="weiterleitungen.csv"'
    return response
