"""T-8.6 «Melden»: жалоба посетителя на карточку каталога города + автоскрытие.

План — docs/t8-6-catalog-hygiene-plan-2026-10-10.md §1. Постмодерация: жалоба уходит в
очередь админки; при `ListingReport.AUTO_HIDE_AT` открытых жалобах с РАЗНЫХ адресов
карточка скрывается до решения модератора (один человек трижды карточку не снимет).
"""

from __future__ import annotations

import hashlib

from django.conf import settings
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import ratelimit

from .models import AggregatorListing, ListingReport


def _ip_hash(request) -> str:
    raw = f"{settings.SECRET_KEY}:{ratelimit.client_ip(request)}"
    return hashlib.sha256(raw.encode()).hexdigest()


def file_report(listing, *, reason: str, message: str = "", ip_hash: str = "") -> ListingReport:
    """Сохранить жалобу и при необходимости скрыть карточку. Без HTTP — для тестов/бота."""
    report = ListingReport.objects.create(
        listing=listing, reason=reason, message=(message or "")[:1000], ip_hash=ip_hash
    )
    voices = (
        ListingReport.objects.filter(listing=listing, status=ListingReport.STATUS_OPEN)
        .exclude(ip_hash="")
        .values("ip_hash")
        .distinct()
        .count()
    )
    if voices >= ListingReport.AUTO_HIDE_AT and listing.hidden_at is None:
        AggregatorListing.objects.filter(pk=listing.pk, hidden_at__isnull=True).update(
            hidden_at=timezone.now(),
            hidden_reason=_("Automatisch: %(n)s Meldungen") % {"n": voices},
        )
    return report


def report_listing(request, pk):
    listing = get_object_or_404(AggregatorListing.objects.public(), pk=pk)
    portal = getattr(request, "portal", None)
    context = {
        "listing": listing,
        "portal": portal,
        "base_template": "aggregator/portal_base.html" if portal else "aggregator/_base.html",
        "reasons": ListingReport.REASONS,
        "sent": False,
        "error": "",
    }
    if request.method == "POST":
        reason = request.POST.get("reason", "")
        if (request.POST.get("website") or "").strip():
            context["sent"] = True  # бот — делаем вид, что приняли
        elif reason not in dict(ListingReport.REASONS):
            context["error"] = _("Bitte einen Grund wählen.")
        elif ratelimit.hit("listing-report", ratelimit.client_ip(request), limit=10, window=3600):
            context["error"] = _("Zu viele Versuche. Bitte später erneut.")
        else:
            file_report(
                listing,
                reason=reason,
                message=request.POST.get("message", ""),
                ip_hash=_ip_hash(request),
            )
            context["sent"] = True
    return render(request, "aggregator/report.html", context)
