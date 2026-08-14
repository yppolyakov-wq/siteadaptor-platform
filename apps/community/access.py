"""Кто входит в пространство поездки (MT-3).

Три пути внутрь, и все три сходятся здесь — чтобы «кто может читать/писать»
не расползлось по вьюхам:

* **гид/сотрудник** — вошедший в кабинет (`has_cabinet_access`);
* **участник** — клиент с непогашенным билетом на этот заезд (сессия ЛК);
* **приглашённый** — прошёл по ссылке-приглашению (сопровождающий без билета);
  факт приглашения живёт в сессии, чтобы ссылку не приходилось хранить в БД
  на каждого гостя.

Fail-closed: всё остальное — посторонний.
"""

from apps.account.auth import SESSION_KEY as ACCOUNT_SESSION_KEY
from apps.core import status_registry
from apps.core.roles import has_cabinet_access

STAFF = "staff"
MEMBER = "member"
GUEST = "guest"

#: Ключ сессии, которым отмечается принятое приглашение в конкретное пространство.
INVITE_SESSION_PREFIX = "community_invite:"


def invite_session_key(space) -> str:
    return f"{INVITE_SESSION_PREFIX}{space.pk}"


def _has_ticket(space, customer_id) -> bool:
    """Есть ли у клиента действующий билет на заезд этого пространства."""
    if space.ref_kind != "event" or not space.ref_id or not customer_id:
        return False
    from apps.events.models import Ticket

    return (
        Ticket.objects.filter(event_id=space.ref_id, customer_id=customer_id)
        .exclude(status__in=status_registry.cancelled_statuses_for("ticket"))
        .exists()
    )


def role_of(request, space) -> str:
    """Роль запроса в пространстве: staff / member / guest."""
    user = getattr(request, "user", None)
    if user is not None and has_cabinet_access(user):
        return STAFF
    session = getattr(request, "session", None)
    if session is None:
        return GUEST
    customer_id = session.get(ACCOUNT_SESSION_KEY)
    if customer_id and _has_ticket(space, customer_id):
        return MEMBER
    if session.get(invite_session_key(space)):
        return MEMBER
    return GUEST


def can_read(role: str) -> bool:
    return role in (STAFF, MEMBER)


def can_post(role: str, space) -> bool:
    """Писать может гид всегда; участник — пока пространство открыто и разрешено."""
    if role == STAFF:
        return True
    if role != MEMBER:
        return False
    return bool(space.is_open and space.members_can_post)


def current_customer_id(request):
    session = getattr(request, "session", None) or {}
    return session.get(ACCOUNT_SESSION_KEY)
