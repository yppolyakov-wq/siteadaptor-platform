"""FB-33 D5: содержимое уведомлений — ретеншн и удаление по Art. 17.

План — `docs/fb33-stack13-plan-2026-11-24.md` §1 D5, §2 D5, §4 D5 и правки ревью §10.1 M2,
§10.2 H5 (все виды писем владельцу, pk сделок клиента через `dsgvo._related_specs()`, выборка
`startswith "<p>:<pk>:"` + `endswith ":owner" / ":owner:tg"`). Ответ владельца (§11): письма
владельцу о сделках клиента при удалении стираются (`payload`, `subject`); книга платежей,
суммы и intent остаются.
"""

import datetime
import pathlib
import re
import uuid
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.crm import dsgvo
from apps.notifications.models import Notification
from apps.notifications.tasks import PAYLOAD_RETENTION, purge_payloads
from apps.promotions.models import Customer

pytestmark = pytest.mark.django_db

OWNER_BODY = {"body": "Neue Bestellung von Erika Muster, Tel. 0170 1, Antwort: ohne Nüsse"}


def _note(key, *, status="sent", recipient="owner@example.com", age_days=0, **kw):
    n = Notification.objects.create(
        dedupe_key=key,
        type=kw.pop("type", "order_created_owner"),
        recipient=recipient,
        subject=kw.pop("subject", "Neue Bestellung — Erika Muster"),
        payload=kw.pop("payload", dict(OWNER_BODY)),
        status=status,
        **kw,
    )
    if age_days:
        Notification.objects.filter(pk=n.pk).update(
            updated_at=timezone.now() - datetime.timedelta(days=age_days)
        )
    return n


def _wiped(key) -> bool:
    n = Notification.objects.get(dedupe_key=key)
    return n.payload == {} and n.subject == ""


# ── ретеншн ─────────────────────────────────────────────────────────────────────────────────


def test_owner_mail_with_answers_purged_after_retention():
    """№4 (охранный): утверждение карты DSGVO — письмо владельцу с ответами стирается через
    30 дней после SENT/FAILED; строка (dedupe) остаётся."""
    old = PAYLOAD_RETENTION.days + 1
    _note("order:a:created:owner", age_days=old)
    _note("order:b:created:owner", status="failed", age_days=old)
    _note("order:c:created:owner", age_days=1)
    assert purge_payloads() == 2
    assert Notification.objects.get(dedupe_key="order:a:created:owner").payload == {}
    assert Notification.objects.get(dedupe_key="order:c:created:owner").payload == OWNER_BODY


def test_pending_notification_payload_purged():
    """Ревью §10.1 M2: `pending`, зависший дольше срока, — тоже стирается (доставка шла
    `on_commit` сразу; повтор берёт только FAILED за сутки — такую строку никто не отправит)."""
    _note("order:p:created:owner", status="pending", age_days=PAYLOAD_RETENTION.days + 1)
    assert purge_payloads() == 1
    assert Notification.objects.get(dedupe_key="order:p:created:owner").payload == {}


def test_fresh_pending_notification_kept():
    """Охранный: свежий `pending` (в очереди) не трогается — письмо уйдёт целым."""
    _note("order:q:created:owner", status="pending", age_days=PAYLOAD_RETENTION.days - 1)
    assert purge_payloads() == 0
    assert Notification.objects.get(dedupe_key="order:q:created:owner").payload == OWNER_BODY


# ── Art. 17: письма владельцу о сделках клиента ──────────────────────────────────────────────


def _customer(email="erika@example.com", name="Erika Muster"):
    return Customer.objects.create(name=name, email=email, phone="0170 1")


def _ref():
    return f"D5-{uuid.uuid4().hex[:6]}"


def _order(c):
    from apps.orders.models import Order

    return Order.objects.create(
        customer=c, reference_code=_ref(), status="picked_up", payment_state="paid", total=12
    )


def _offer(c):
    from apps.orders.models import Offer

    return Offer.objects.create(customer=c, status="declined")


def _job(c):
    from apps.jobs.models import Job

    return Job.objects.create(customer=c, reference_code=_ref(), title="Fenster", status="done")


def _booking(c):
    from apps.booking.models import Booking, Resource

    start = timezone.now() - datetime.timedelta(days=10)
    return Booking.objects.create(
        customer=c,
        resource=Resource.objects.create(name="Stuhl"),
        reference_code=_ref(),
        start=start,
        end=start + datetime.timedelta(hours=1),
        status="completed",
    )


def _stay(c):
    from apps.stays.models import StayBooking, StayUnit

    day = timezone.localdate() - datetime.timedelta(days=10)
    return StayBooking.objects.create(
        customer=c,
        unit=StayUnit.objects.create(name="Zimmer 1"),
        reference_code=_ref(),
        arrival=day,
        departure=day + datetime.timedelta(days=2),
        status="checked_out",
    )


def _ticket(c):
    from apps.events.models import Event, Ticket

    event = Event.objects.create(
        title="Kurs", starts_at=timezone.now() - datetime.timedelta(days=10)
    )
    return Ticket.objects.create(customer=c, event=event, reference_code=_ref(), status="used")


def _reservation(c):
    from apps.promotions.models import Reservation
    from apps.promotions.tests.factories import PromotionFactory

    return Reservation.objects.create(
        customer=c, promotion=PromotionFactory(), reference_code=_ref(), status="redeemed"
    )


def _conversation(c):
    from apps.inbox.models import Conversation

    return Conversation.objects.create(customer=c)


def _keys_order(c):
    o = _order(c)
    return [f"order:{o.id}:created:owner", f"order:{o.id}:created:owner:tg"]


def _keys_offer(c):
    return [f"offer:{_offer(c).id}:accepted:owner"]


def _keys_job(c):
    j = _job(c)
    return [f"job:{j.id}:created:owner", f"job:{j.id}:created:owner:tg"]


def _keys_booking(c):
    b = _booking(c)
    return [
        f"booking:{b.id}:created:owner",
        f"booking:{b.id}:created:owner:tg",
        f"booking:{b.id}:moved:owner",
        f"booking:{b.id}:moved:owner:tg",
    ]


def _keys_stay(c):
    s = _stay(c)
    return [f"stay:{s.id}:created:owner", f"stay:{s.id}:created:owner:tg"]


def _keys_ticket(c):
    t = _ticket(c)
    return [f"ticket:{t.id}:created:owner", f"ticket:{t.id}:created:owner:tg"]


def _keys_installment(c):
    from apps.events.models import InstallmentCharge, InstallmentPlan

    plan = InstallmentPlan.objects.create(ticket=_ticket(c))
    charge = InstallmentCharge.objects.create(
        plan=plan, sequence=2, due_date=timezone.localdate(), amount_cents=5000
    )
    return [f"installment:{charge.id}:failed:owner"]


def _keys_reservation(c):
    r = _reservation(c)
    return [f"resv:{r.id}:created:owner", f"resv:{r.id}:created:owner:tg"]


def _keys_inbox(c):
    from apps.inbox.models import Message

    conv = _conversation(c)
    msg = Message.objects.create(
        conversation=conv, author_role=Message.AUTHOR_CUSTOMER, body="Frage von Erika"
    )
    return [f"inbox:msg:{msg.id}:owner", f"inbox:conv:{conv.pk}:problem:owner:tg"]


KINDS = {
    "order": _keys_order,
    "offer": _keys_offer,
    "job": _keys_job,
    "booking": _keys_booking,
    "stay": _keys_stay,
    "ticket": _keys_ticket,
    "installment": _keys_installment,
    "reservation": _keys_reservation,
    "inbox": _keys_inbox,
}


def test_dsgvo_erase_wipes_owner_mails_of_customer_deals():
    """Ответ владельца §9 №7 «стирать»: письмо владельцу о заказе клиента (имя, телефон,
    ответы) теряет тему и содержимое; письмо самому клиенту — как раньше (по адресу)."""
    c = _customer()
    owner_keys = _keys_order(c)
    for key in owner_keys:
        _note(key)
    _note("order:x:created:customer", recipient="erika@example.com")
    dsgvo.erase_customer(c)
    assert all(_wiped(k) for k in owner_keys)
    mine = Notification.objects.get(dedupe_key="order:x:created:customer")
    assert (mine.recipient, mine.subject, mine.payload) == ("", "", {})
    kept = Notification.objects.get(dedupe_key=owner_keys[0])
    assert kept.recipient == "owner@example.com"  # адрес владельца — не данные клиента


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_erase_owner_mails_all_kinds(kind):
    """§10.1 M2 / §10.2 H5: все виды писем владельцу о сделке клиента, с `:tg`."""
    c = _customer()
    keys = KINDS[kind](c)
    for key in keys:
        _note(key)
    stats = dsgvo.erase_customer(c)
    assert all(_wiped(k) for k in keys), kind
    assert stats.get("notifications.owner") == len(keys)


def test_erase_owner_mails_only_of_this_customer_deals():
    """№6 (охранный): сделки другого клиента, письма клиенту по чужому адресу, письма владельцу
    без данных клиента (код и сумма) и ключ-«похожий» (pk-префикс без `:`) — не тронуты."""
    c = _customer()
    other = _customer(email="max@example.com", name="Max")
    mine = _order(c)
    theirs = _order(other)
    keys = [
        f"order:{theirs.id}:created:owner",
        f"order:{theirs.id}:created:owner:tg",
        f"order:{mine.id}:ready:customer-copy",  # не письмо владельцу
        f"refund-rest:public:order:{mine.id}",  # только код и сумма
        f"order:{mine.id}x:created:owner",  # другой «pk» с тем же началом
    ]
    for key in keys:
        _note(key, recipient="owner@example.com")
    dsgvo.erase_customer(c)
    for key in keys:
        n = Notification.objects.get(dedupe_key=key)
        assert n.payload == OWNER_BODY and n.subject, key


def test_owner_mail_keys_registry_covers_code():
    """Одна константа ключей: каждый ключ письма владельцу в коде (`…:owner`, `…:owner:tg`)
    либо в `dsgvo.OWNER_MAIL_KEYS`, либо в `dsgvo.OWNER_MAIL_EXEMPT` с причиной (письмо не
    о сделке клиента). Новое письмо владельцу о сделке без строки реестра — красный CI."""
    known = {p for specs in dsgvo.OWNER_MAIL_KEYS.values() for p, _path in specs}
    exempt = set(dsgvo.OWNER_MAIL_EXEMPT)
    pattern = re.compile(r'f"([a-z_:-]+?):\{[^"]*:owner(?::tg)?"')
    found = set()
    for path in pathlib.Path("apps").rglob("*.py"):
        if "/tests/" in str(path) or "/migrations/" in str(path):
            continue
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            found.add(match.group(1))
    assert {"order", "job", "booking", "inbox:msg"} <= found  # сам обход не пуст
    assert found - known - exempt == set()
    assert all(str(reason) for reason in dsgvo.OWNER_MAIL_EXEMPT.values())


def test_erase_keeps_money_rows_untouched():
    """Ответ владельца: книга платежей и суммы остаются (охранный)."""
    c = _customer()
    order = _order(c)
    dsgvo.erase_customer(c)
    order.refresh_from_db()
    assert order.total == Decimal("12") and order.payment_state == "paid"
