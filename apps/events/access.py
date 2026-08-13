"""Кто есть кто для тура (MT-1) — резолвер аудитории маршрута.

Маршрут тура закрыт по умолчанию, поэтому «кем является этот запрос» решается
в одном месте и fail-closed: любая неопределённость → посторонний. Тот же
резолвер понадобится MT-2 (документы участника) и MT-3 (пространство тура),
поэтому он живёт отдельно от вьюх.

Три аудитории (значения — из `itinerary`, чтобы не плодить словари):
* `OWNER` — вошедший в кабинет сотрудник/владелец (видит всё);
* `PARTICIPANT` — клиент с непогашенным билетом на любой заезд тура;
* `GUEST` — все остальные.
"""

from apps.account.auth import SESSION_KEY as ACCOUNT_SESSION_KEY
from apps.core import status_registry
from apps.core.roles import has_cabinet_access

from . import itinerary
from .models import Ticket

OWNER = itinerary.OWNER
PARTICIPANT = itinerary.PARTICIPANT
GUEST = itinerary.GUEST


def is_participant(tour, *, customer_id=None, email: str = "") -> bool:
    """Есть ли у клиента действующий билет на любой заезд тура.

    Идентификация — по id клиента (сессия ЛК) ИЛИ по e-mail (ссылка из письма).
    Пустые входные данные → False (fail-closed), лишних запросов не делаем.

    «Действующий» = НЕ отменённый: считаем через реестр статусов (SM-3), иначе
    владелец, заведший свой статус («Angezahlt»), лишил бы участника доступа.
    Билет в рассрочке или уже съездивший тоже сохраняет доступ.
    """
    if tour is None or (not customer_id and not email):
        return False
    qs = Ticket.objects.filter(event__tour=tour).exclude(
        status__in=status_registry.cancelled_statuses_for("ticket")
    )
    if customer_id:
        qs = qs.filter(customer_id=customer_id)
    else:
        qs = qs.filter(customer__email__iexact=email.strip())
    return qs.exists()


def route_audience(request, tour) -> str:
    """Аудитория маршрута для этого запроса (owner/participant/public)."""
    user = getattr(request, "user", None)
    if user is not None and has_cabinet_access(user):
        return OWNER
    customer_id = (getattr(request, "session", None) or {}).get(ACCOUNT_SESSION_KEY)
    if customer_id and is_participant(tour, customer_id=customer_id):
        return PARTICIPANT
    return GUEST
