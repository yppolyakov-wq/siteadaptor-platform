"""CM-8: карточка клиента 360° — сборка KPI и разделов для кабинета.

Отличие от apps/account/account_data.py (ЛК клиента): ссылки — owner-URL
кабинета, есть суммы/LTV. Каждый раздел за гейтом is_module_active и
fail-soft (сбой одного домена не валит деталь клиента). Отзывы матчатся
по email (у reviews.Review нет FK на Customer) — только при непустом email.
"""

from django.db.models import Count, Max, Sum
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

from apps.core import modules

_LIMIT = 10


def _safe(fn, default):
    try:
        return fn()
    except Exception:  # noqa: BLE001 — один домен не валит карточку
        return default


def _url(name, *args):
    try:
        return reverse(name, args=args)
    except NoReverseMatch:
        return ""


def _active(tenant, key) -> bool:
    """Гейт модуля, устойчивый к отсутствию тенанта (RequestFactory-тесты)."""
    if tenant is None:
        return False
    return _safe(lambda: modules.is_module_active(tenant, key), False)


def kpis(tenant, customer) -> dict:
    """CM-8.1: LTV из finance.RevenueEntry (единственный DB-агрегируемый
    источник — наполняют все 5 FSM) + счётчики по доменам."""

    def _rev():
        return customer.revenue_entries.aggregate(
            total=Sum("amount"), n=Count("id"), last=Max("date")
        )

    agg = _safe(_rev, {}) or {}
    counts = []
    for key, label, rel in (
        ("orders", _("Orders"), "orders"),
        ("booking", _("Appointments"), "bookings"),
        ("stays", _("Stays"), "stays"),
        ("events", _("Tickets"), "event_tickets"),
        ("jobs", _("Jobs"), "jobs"),
    ):
        if not _active(tenant, key):
            continue
        n = _safe(lambda rel=rel: getattr(customer, rel).count(), 0)
        if n:
            counts.append({"label": label, "n": n})
    return {
        "ltv_total": agg.get("total"),
        "ltv_n": agg.get("n") or 0,
        "ltv_last": agg.get("last"),
        "counts": counts,
    }


def sections(tenant, customer) -> list[dict]:
    """CM-8.2/8.3/8.4: недостающие readonly-разделы: [{key,title,items}];
    item = {title, sub, status, url}. Пустые разделы не возвращаем."""
    out = []

    def add(key, title, build):
        items = _safe(build, [])
        if items:
            out.append({"key": key, "title": title, "items": items})

    if _active(tenant, "booking"):
        add(
            "bookings",
            _("Appointments"),
            lambda: [
                {
                    "title": f"{b.service.name if b.service else b.resource}",
                    "sub": f"{b.start:%d.%m.%Y %H:%M} · {b.reference_code}",
                    "status": b.status,
                    "url": "",
                }
                for b in customer.bookings.select_related("resource", "service").order_by("-start")[
                    :_LIMIT
                ]
            ],
        )
        add(
            "passes",
            _("Passes"),
            lambda: [
                {
                    "title": p.label,
                    "sub": f"{p.code} · {p.credits_used}/{p.credits_total}",
                    "status": "" if p.is_valid else "expired",
                    "url": "",
                }
                for p in customer.passes.all()[:_LIMIT]
            ],
        )

    if _active(tenant, "stays"):
        add(
            "stays",
            _("Stays"),
            lambda: [
                {
                    "title": str(s.unit),
                    "sub": f"{s.arrival:%d.%m.%Y} → {s.departure:%d.%m.%Y} · {s.reference_code}",
                    "status": s.status,
                    "url": "",
                }
                for s in customer.stays.select_related("unit").order_by("-arrival")[:_LIMIT]
            ],
        )

    if _active(tenant, "events"):
        add(
            "tickets",
            _("Tickets"),
            lambda: [
                {
                    "title": t.event.title,
                    "sub": f"{t.event.starts_at:%d.%m.%Y} · {t.quantity}× · {t.reference_code}",
                    "status": t.status,
                    "url": "",
                }
                for t in customer.event_tickets.select_related("event").order_by("-created_at")[
                    :_LIMIT
                ]
            ],
        )

    if _active(tenant, "jobs"):
        add(
            "jobs",
            _("Jobs"),
            lambda: [
                {
                    "title": j.title,
                    "sub": f"{j.reference_code} · {j.gross} €" if j.gross else j.reference_code,
                    "status": j.status,
                    "url": _url("jobs:detail", j.pk),
                }
                for j in customer.jobs.order_by("-created_at")[:_LIMIT]
            ],
        )

    if _active(tenant, "finance"):
        add(
            "invoices",
            _("Invoices"),
            lambda: [
                {
                    "title": f"{i.number} · {i.gross} €",
                    "sub": f"{i.issued_at:%d.%m.%Y}" if i.issued_at else "",
                    "status": getattr(i, "status", ""),
                    "url": _url("finance:invoice-detail", i.pk),
                }
                for i in customer.invoices.order_by("-created_at")[:_LIMIT]
            ],
        )

    if _active(tenant, "inbox"):
        add(
            "conversations",
            _("Messages"),
            lambda: [
                {
                    "title": c.subject or str(c),
                    "sub": f"{c.updated_at:%d.%m.%Y}",
                    "status": "●" if c.unread_for_staff else "",
                    "url": _url("inbox:thread", c.pk),
                }
                for c in customer.conversations.order_by("-updated_at")[:_LIMIT]
            ],
        )

    # CM-8.4: отзывы — матч по email (FK на Customer нет), fail-soft.
    if customer.email:

        def _reviews():
            from apps.reviews.models import Review

            return [
                {
                    "title": "★" * int(r.rating),
                    "sub": (r.comment or "")[:120],
                    "status": r.entity_kind,
                    "url": "",
                }
                for r in Review.objects.filter(email__iexact=customer.email).order_by(
                    "-created_at"
                )[:_LIMIT]
            ]

        add("reviews", _("Reviews"), _reviews)

    return out
