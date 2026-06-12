"""Кабинет Light-Finance (Track D / D4a): /dashboard/finance/ — журнал выручки.

Период (?von=&bis=, по умолчанию текущий месяц), итоги по сумме и по ставкам
НДС, ручное добавление записи. Автозаписи приходят из хуков OrderSM/ReservationSM
(см. apps.finance.services). Гейтинг — модуль «finance» из реестра.
"""

from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import RevenueEntry
from .services import record_revenue


def _parse_date(raw, fallback):
    try:
        return date.fromisoformat(raw or "")
    except ValueError:
        return fallback


@login_required
def journal(request):
    if request.method == "POST":
        try:
            amount = Decimal(str(request.POST.get("amount", "")).replace(",", "."))
        except (InvalidOperation, ValueError):
            messages.error(request, _("Invalid amount."))
            return redirect("finance:journal")
        vat_raw = request.POST.get("vat_rate", "19.00")
        vat_rate = next(
            (rate for rate in RevenueEntry.VAT_RATES if str(rate) == vat_raw),
            Decimal("19.00"),
        )
        entry = record_revenue(
            source=RevenueEntry.SOURCE_MANUAL,
            amount=amount,
            vat_rate=vat_rate,
            date=_parse_date(request.POST.get("date"), timezone.localdate()),
            note=request.POST.get("note", "").strip(),
        )
        if entry is None:
            messages.error(request, _("Amount must be positive."))
        else:
            messages.success(request, _("Entry added."))
        return redirect("finance:journal")

    today = timezone.localdate()
    von = _parse_date(request.GET.get("von"), today.replace(day=1))
    bis = _parse_date(request.GET.get("bis"), today)
    entries = RevenueEntry.objects.filter(date__gte=von, date__lte=bis).select_related("customer")
    by_vat = entries.values("vat_rate").annotate(sum=Sum("amount")).order_by("-vat_rate")
    return render(
        request,
        "finance/journal.html",
        {
            "nav": "finance",
            "von": von,
            "bis": bis,
            "entries": entries[:500],
            "total": entries.aggregate(s=Sum("amount"))["s"] or Decimal("0"),
            "by_vat": by_vat,
            "vat_rates": RevenueEntry.VAT_RATES,
            "today": today,
        },
    )
