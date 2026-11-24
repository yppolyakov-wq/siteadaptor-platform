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


class InvalidAnswers(Exception):
    """FB-33 D6: значение select не из списка вариантов — ничего не сохранено.
    `errors` — {позиция места: [ключи полей]}."""

    def __init__(self, errors: dict[int, list[str]]):
        super().__init__("invalid select answers")
        self.errors = errors


def slots(ticket, *, hide_contacts=False, post=None, errors=None) -> list[dict]:
    """По слоту на место: позиция, имя, поля анкеты с текущими значениями.
    Первый слот без имени подставляет покупателя (он чаще всего и едет).

    FB-33 D6: `post` + `errors` (после `InvalidAnswers`) — форма из присланного: имя и ответы
    из POST, у поля с ошибкой — текст ошибки, а значение не возвращается."""
    have = {p.position: p for p in rows(ticket)}
    fields = [
        f
        for f in registration.active(ticket.event.registration_fields)
        if not (hide_contacts and f["key"] in CONTACT_KEYS)
    ]
    out = []
    first = True  # `autofocus` — только у первого поля с ошибкой
    for pos in range(1, ticket.quantity + 1):
        row = have.get(pos)
        name = row.name if row else ""
        if not name and pos == 1:
            name = getattr(ticket.customer, "name", "") or ""
        answers = dict(row.answers) if row else {}
        bad = (errors or {}).get(pos) or []
        prefix = f"p{pos}_{registration.POST_PREFIX}"
        if post is not None and f"p{pos}_name" in post:
            name = (post.get(f"p{pos}_name") or "").strip()[:NAME_MAX]
            posted = registration.collect(ticket.event.registration_fields, post, prefix=prefix)
            answers = {k: v for k, v in posted.items() if k not in bad}
        slot_fields = []
        for f in fields:
            item = _slot_field(
                f,
                f"{prefix}{f['key']}",
                answers,
                error=registration.select_error(f["key"]) if f["key"] in bad else "",
            )
            item["autofocus"] = bool(item["error"]) and first
            first = first and not item["error"]
            slot_fields.append(item)
        out.append({"position": pos, "name": name, "fields": slot_fields})
    return out


def _slot_field(field: dict, name: str, answers: dict, error: str = "") -> dict:
    """Поле слота с текущим ответом. Сохранённый ответ select, которого нет среди вариантов
    (старый вариант, ручная правка), дорисовывается вариантом `(value, value)` — иначе select
    встаёт на «—» и следующее сохранение формы стирает ответ. Каталог вариантов
    (`registration.FIELDS`) не меняется: список — копия на этот слот."""
    value = answers.get(field["key"], "")
    out = {**field, "input": name, "value": value, "error": error}
    if field.get("type") == "select" and value:
        options = list(field.get("options") or [])
        if value not in [v for v, _label in options]:
            out["options"] = [*options, (value, value)]
    return out


def save(ticket, post, *, actor=None, source="guest", ip="", hide_contacts=False) -> int | None:
    """Сохранить участников из POST (`p<N>_name`, `p<N>_reg_<key>`).

    Трогает только места, чьё поле имени ПРИШЛО в форме (пустая/чужая форма не
    стирает чужие данные); места сверх `quantity` удаляются. Гостю проверка
    «можно править» — под блокировкой билета (отмена могла успеть раньше).
    Скрытые контактные поля сохраняют прежнее значение. → число строк или None,
    если править уже нельзя.

    FB-33 D6: сначала проверяются ВСЕ слоты, потом пишется: значение select не из списка
    (кроме прежнего ответа слота — из строки БД под блокировкой, не из POST) →
    `InvalidAnswers`, ничего не записано."""
    from apps.core.audit import audit_event

    raw = ticket.event.registration_fields
    with transaction.atomic():
        locked = Ticket.objects.select_for_update().select_related("event").get(pk=ticket.pk)
        if source == "guest" and not editable(locked):
            return None
        have = {p.position: p for p in TicketParticipant.objects.filter(ticket=locked)}
        posted = [pos for pos in range(1, locked.quantity + 1) if f"p{pos}_name" in post]
        errors = {}
        for pos in posted:
            old = have.get(pos)
            bad = registration.invalid_selects(
                raw,
                post,
                prefix=f"p{pos}_{registration.POST_PREFIX}",
                keep=(old.answers if old else None),
            )
            if bad:
                errors[pos] = bad
        if errors:
            raise InvalidAnswers(errors)
        saved = 0
        for pos in posted:
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
