"""CA2: сбор содержимого ЛК клиента по активным модулям бизнеса.

Customer — хаб: к нему привязаны заказы/брони/счета/… Каждый раздел виден,
только если соответствующий модуль активен у бизнеса (is_module_active). Ссылки
ведут на уже существующие публичные страницы статуса (без логина по коду/токену).
Каждый раздел обёрнут в try/except — сбой одной выборки не рушит весь ЛК.
"""

from django.urls import reverse

from apps.core.transactions import transaction_for

LIMIT = 10  # последних записей в разделе


def _safe(fn):
    try:
        return fn()
    except Exception:  # cross-app выборка — раздел не должен ронять ЛК
        return None


def sections_for(request, customer):
    """[{key,title,icon,items:[{title,sub,status,url}]}] по активным модулям."""
    tenant = request.tenant
    out = []

    def active(mod):
        return tenant.is_module_active(mod)

    # --- Bestellungen (orders) ---
    if active("orders"):
        out.append(_safe(lambda: _orders(customer)))

    # --- Termine (booking) + Mehrfachkarte ---
    if active("booking"):
        out.append(_safe(lambda: _bookings(customer)))
        out.append(_safe(lambda: _passes(customer)))

    # --- Übernachtung (stays) ---
    if active("stays"):
        out.append(_safe(lambda: _stays(customer)))

    # --- Tickets (events) ---
    if active("events"):
        out.append(_safe(lambda: _tickets(customer)))

    # --- Angebote/Aufträge (jobs) ---
    if active("jobs"):
        out.append(_safe(lambda: _jobs(customer)))

    # --- Rechnungen (finance) ---
    if active("finance"):
        out.append(_safe(lambda: _invoices(customer)))

    # --- Reservierungen (promotions) + Gutscheine ---
    if active("promotions"):
        out.append(_safe(lambda: _reservations(customer)))
        out.append(_safe(lambda: _vouchers(customer)))

    # --- Bonuskarte (loyalty) ---
    if active("loyalty"):
        out.append(_safe(lambda: _loyalty(customer)))

    # --- Nachrichten (inbox) ---
    if active("inbox"):
        out.append(_safe(lambda: _messages(customer)))

    # пустые секции и сбои (None) убираем
    return [s for s in out if s and s["items"]]


# --- сборщики разделов -------------------------------------------------------------


# UD1-2: транзакционные разделы (заказы/брони/проживание/билеты/заявки/резервы)
# строятся из единого контракта `transaction_for`: статус-подпись и публичная
# ссылка приходят из адаптера (одна точка правды с доской), а презентация
# title/sub/extra остаётся per-kind (даты/суммы/«Nochmal bestellen» и т.п.).


def _orders(customer):
    from apps.orders.models import Order

    items = []
    for o in Order.objects.filter(customer=customer).order_by("-created_at")[:LIMIT]:
        tx = transaction_for("order", o)
        items.append(
            {
                "title": f"#{tx.reference_code}",
                "sub": f"{o.total} {o.currency} · {o.created_at:%d.%m.%Y}",
                "status": tx.status_label,
                "url": tx.detail_url_customer,
                "reorder": tx.reference_code,  # CA4: «Nochmal bestellen»
            }
        )
    return {"key": "orders", "title": "Bestellungen", "icon": "🛍️", "items": items}


def _bookings(customer):
    from apps.booking.models import Booking

    cancelable = (Booking.STATUS_PENDING, Booking.STATUS_CONFIRMED)
    items = []
    for b in Booking.objects.filter(customer=customer).order_by("-start")[:LIMIT]:
        tx = transaction_for("booking", b)
        items.append(
            {
                "title": f"{b.start:%d.%m.%Y %H:%M}",
                "sub": str(getattr(b, "service", "") or b.resource or ""),
                "status": tx.status_label,
                "url": tx.detail_url_customer,
                # CA4: отмена — только для будущих неотменённых/невыполненных.
                "cancel": b.reference_code if b.status in cancelable else "",
            }
        )
    return {"key": "bookings", "title": "Termine", "icon": "📅", "items": items}


def _passes(customer):
    from apps.booking.models import Pass

    items = [
        {
            "title": p.label,
            "sub": p.code,
            "status": f"{p.credits_left}/{p.credits_total}",
            "url": "",
        }
        for p in Pass.objects.filter(customer=customer).order_by("-created_at")[:LIMIT]
    ]
    return {"key": "passes", "title": "Mehrfachkarten", "icon": "🎫", "items": items}


def _stays(customer):
    from apps.stays.models import StayBooking

    items = []
    for s in StayBooking.objects.filter(customer=customer).order_by("-arrival")[:LIMIT]:
        tx = transaction_for("stay", s)
        items.append(
            {
                "title": f"{s.arrival:%d.%m.%Y}–{s.departure:%d.%m.%Y}",
                "sub": str(s.unit or ""),
                "status": tx.status_label,
                "url": tx.detail_url_customer,
            }
        )
    return {"key": "stays", "title": "Übernachtungen", "icon": "🛏️", "items": items}


def _tickets(customer):
    from apps.events.models import Ticket

    items = []
    for t in (
        Ticket.objects.filter(customer=customer)
        .select_related("event")
        .order_by("-created_at")[:LIMIT]
    ):
        tx = transaction_for("ticket", t)
        items.append(
            {
                "title": str(t.event),
                "sub": f"×{t.quantity} · {t.event.starts_at:%d.%m.%Y %H:%M}",
                "status": tx.status_label,
                "url": tx.detail_url_customer,
            }
        )
    return {"key": "tickets", "title": "Tickets", "icon": "🎟️", "items": items}


def _jobs(customer):
    from apps.jobs.models import Job

    items = []
    for j in Job.objects.filter(customer=customer).order_by("-created_at")[:LIMIT]:
        tx = transaction_for("job", j)
        items.append(
            {
                "title": j.title or f"#{tx.reference_code}",
                "sub": f"#{tx.reference_code}",
                "status": tx.status_label,
                # публичная ссылка jobs — по public_token (адаптер знает это)
                "url": tx.detail_url_customer,
            }
        )
    return {"key": "jobs", "title": "Angebote & Aufträge", "icon": "🧾", "items": items}


def _invoices(customer):
    from apps.finance.models import Invoice

    items = [
        {
            "title": f"Rechnung Nr. {inv.number}" if inv.number else "Entwurf",
            "sub": f"{inv.gross} € · {inv.issued_at:%d.%m.%Y}"
            if inv.issued_at
            else f"{inv.gross} €",
            "status": inv.get_status_display(),
            "url": "",
        }
        for inv in Invoice.objects.filter(customer=customer).order_by("-created_at")[:LIMIT]
    ]
    return {"key": "invoices", "title": "Rechnungen", "icon": "💶", "items": items}


def _reservations(customer):
    from apps.promotions.models import Reservation

    items = []
    for r in (
        Reservation.objects.filter(customer=customer)
        .select_related("promotion")
        .order_by("-created_at")[:LIMIT]
    ):
        tx = transaction_for("reservation", r)
        items.append(
            {
                "title": str(r.promotion),
                "sub": f"#{tx.reference_code} · {r.created_at:%d.%m.%Y}",
                # Reservation.status без choices — адаптер даёт читаемую подпись
                # (раньше get_status_display() падал → раздел скрывался).
                "status": tx.status_label,
                "url": tx.detail_url_customer,
            }
        )
    return {"key": "reservations", "title": "Reservierungen", "icon": "🔖", "items": items}


def _vouchers(customer):
    from apps.loyalty.models import Voucher

    items = [
        {
            "title": v.label,
            "sub": v.code,
            "status": "" if v.is_redeemable else "verbraucht",
            "url": "",
        }
        for v in Voucher.objects.filter(customer=customer).order_by("-created_at")[:LIMIT]
    ]
    return {"key": "vouchers", "title": "Gutscheine", "icon": "🏷️", "items": items}


def _loyalty(customer):
    from apps.loyalty.models import LoyaltyCard

    items = [
        {
            "title": c.program.reward_label,
            "sub": c.program.label,
            "status": f"{c.stamps}/{c.program.stamps_required}",
            "url": "",
        }
        for c in LoyaltyCard.objects.filter(customer=customer)
        .select_related("program")
        .order_by("-updated_at")[:LIMIT]
    ]
    return {"key": "loyalty", "title": "Bonuskarten", "icon": "⭐", "items": items}


def _messages(customer):
    from apps.inbox.models import Conversation

    items = [
        {
            "title": c.subject or "Nachricht",
            "sub": f"{c.updated_at:%d.%m.%Y}",
            "status": c.get_status_display(),
            "url": reverse("storefront-message-thread", args=[c.public_token]),
        }
        for c in Conversation.objects.filter(customer=customer).order_by("-updated_at")[:LIMIT]
    ]
    return {"key": "messages", "title": "Nachrichten", "icon": "💬", "items": items}
