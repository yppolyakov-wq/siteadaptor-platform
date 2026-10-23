"""KA-12 E2.5: счётчики Click & Collect для главной и лёгкой «Start».

Один источник фильтров: счётчик и список по его ссылке считают ОДНО И ТО ЖЕ
(`?abholung=heute`, `?zahlung=offen`, `?status=new`)."""

from django.db.models import Q
from django.utils import timezone

OPEN_STATUSES = ("new", "confirmed", "ready")


def pickup_today_q():
    return Q(pickup_slot__date=timezone.localdate(), status__in=OPEN_STATUSES)


def unpaid_q():
    from apps.core import money_contract

    return money_contract.open_q("order") & ~Q(status__in=("cancelled", "returned"))


def apply_list_filters(qs, params):
    """Фильтры списка заказов по параметрам счётчиков."""
    if (params.get("abholung") or "").strip() == "heute":
        qs = qs.filter(pickup_today_q())
    if (params.get("zahlung") or "").strip() == "offen":
        qs = qs.filter(unpaid_q())
    return qs


def counters():
    """[(key, icon, label, count, query)] — для плиток; порядок = важность у прилавка."""
    from django.utils.translation import gettext as _

    from .models import Order

    return [
        (
            "pickup_today",
            "🛍",
            _("Heute abholen"),
            Order.objects.filter(pickup_today_q()).count(),
            "?tab=order&view=liste&abholung=heute",
        ),
        (
            "new",
            "🆕",
            _("Neu"),
            Order.objects.filter(status="new").count(),
            "?tab=order&view=liste&status=new",
        ),
        (
            "unpaid",
            "💳",
            _("Unbezahlt"),
            Order.objects.filter(unpaid_q()).count(),
            "?tab=order&view=liste&zahlung=offen",
        ),
    ]


def active_label(params) -> str:
    """Подпись активного фильтра счётчика (для снимаемого чипа списка)."""
    from django.utils.translation import gettext as _

    if (params.get("abholung") or "").strip() == "heute":
        return _("Heute abholen")
    if (params.get("zahlung") or "").strip() == "offen":
        return _("Unbezahlt")
    return ""
