"""KA-12 T-5 (EV-2): участники групповой брони — по строке на место билета.

Один источник для витрины (подписанная ссылка «Teilnehmerdaten ergänzen»),
кабинета (смена имени = правка здесь) и чтения (check-in, roster).

Ответы анкеты могут быть данными о здоровье (Art. 9 DSGVO), поэтому: ссылка
показывает данные, только пока их можно править (билет активен, событие не
началось), и не дольше `TOKEN_MAX_AGE`; экстренный контакт без права
«Kontaktdaten sehen» в кабинете не показывается и не затирается.
"""

from __future__ import annotations

from django.core import signing
from django.db import transaction
from django.urls import reverse

from . import registration
from .models import Ticket, TicketParticipant

_SALT = "event-ticket-participants"
NAME_MAX = 200
TOKEN_MAX_AGE = 400 * 24 * 3600  # потолок жизни ссылки (запись бывает за год вперёд)
#: Поля анкеты, которые считаются контактом (маска по `kunden.kontakte`).
CONTACT_KEYS = frozenset({"emergency_contact"})


def token(ticket) -> str:
    return signing.dumps(str(ticket.pk), salt=_SALT)


def ticket_pk(raw: str):
    """pk билета из подписанного токена; подделка или старше потолка → None."""
    try:
        return signing.loads(raw, salt=_SALT, max_age=TOKEN_MAX_AGE)
    except signing.BadSignature:
        return None


def url(ticket) -> str:
    return reverse("storefront-ticket-participants", args=[token(ticket)])


def editable(ticket) -> bool:
    """Гость правит, пока билет активен и событие не началось."""
    from django.utils import timezone

    return (
        ticket.status
        in (
            Ticket.STATUS_PENDING,
            Ticket.STATUS_CONFIRMED,
        )
        and ticket.event.starts_at > timezone.now()
    )


def wanted(ticket) -> bool:
    """Показывать ли ссылку: группа (> 1 места) или анкета у события."""
    return ticket.quantity > 1 or bool(registration.active(ticket.event.registration_fields))


def rows(ticket) -> list:
    """Участники в пределах мест билета (строки сверх `quantity` не читаем)."""
    return [p for p in ticket.participants.all() if p.position <= ticket.quantity]


def slots(ticket, *, hide_contacts=False) -> list[dict]:
    """По слоту на место: позиция, имя, поля анкеты с текущими значениями.
    Первый слот без имени подставляет покупателя (он чаще всего и едет)."""
    have = {p.position: p for p in rows(ticket)}
    fields = [
        f
        for f in registration.active(ticket.event.registration_fields)
        if not (hide_contacts and f["key"] in CONTACT_KEYS)
    ]
    out = []
    for pos in range(1, ticket.quantity + 1):
        row = have.get(pos)
        name = row.name if row else ""
        if not name and pos == 1:
            name = getattr(ticket.customer, "name", "") or ""
        answers = dict(row.answers) if row else {}
        out.append(
            {
                "position": pos,
                "name": name,
                "fields": [
                    {
                        **f,
                        "input": f"p{pos}_{registration.POST_PREFIX}{f['key']}",
                        "value": answers.get(f["key"], ""),
                    }
                    for f in fields
                ],
            }
        )
    return out


def save(ticket, post, *, actor=None, source="guest", ip="", hide_contacts=False) -> int | None:
    """Сохранить участников из POST (`p<N>_name`, `p<N>_reg_<key>`).

    Трогает только места, чьё поле имени ПРИШЛО в форме (пустая/чужая форма не
    стирает чужие данные); места сверх `quantity` удаляются. Гостю проверка
    «можно править» — под блокировкой билета (отмена могла успеть раньше).
    Скрытые контактные поля сохраняют прежнее значение. → число строк или None,
    если править уже нельзя."""
    from apps.core.audit import audit_event

    raw = ticket.event.registration_fields
    with transaction.atomic():
        locked = Ticket.objects.select_for_update().select_related("event").get(pk=ticket.pk)
        if source == "guest" and not editable(locked):
            return None
        have = {p.position: p for p in TicketParticipant.objects.filter(ticket=locked)}
        saved = 0
        for pos in range(1, locked.quantity + 1):
            if f"p{pos}_name" not in post:
                continue
            name = (post.get(f"p{pos}_name") or "").strip()[:NAME_MAX]
            answers = registration.collect(raw, post, prefix=f"p{pos}_{registration.POST_PREFIX}")
            old = have.get(pos)
            if hide_contacts and old:
                for key in CONTACT_KEYS:
                    if key in (old.answers or {}):
                        answers[key] = old.answers[key]
            if not name and not answers:
                if old:
                    old.delete()
                continue
            TicketParticipant.objects.update_or_create(
                ticket=locked, position=pos, defaults={"name": name, "answers": answers}
            )
            saved += 1
        TicketParticipant.objects.filter(ticket=locked, position__gt=locked.quantity).delete()
        audit_event(
            action="ticket.participants",
            resource_type="ticket",
            resource_id=str(locked.pk),
            actor=actor,
            changes={"count": saved, "source": source, **({"ip": ip} if ip else {})},
        )
    return saved


def names(ticket) -> list[str]:
    """Имена участников по порядку мест (для check-in и roster)."""
    return [p.name for p in rows(ticket) if p.name]
