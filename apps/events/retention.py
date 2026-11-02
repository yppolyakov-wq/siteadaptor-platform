"""SEC-G3 (аудит 2026-11-01): срок хранения ответов анкеты участника.

Ответы (аллергии, медпоказания, данные паспорта для поездки) нужны организатору до
события и короткое время после (вопросы, претензии). Решение владельца 2026-11-02 —
30 дней после окончания события; дальше ответы стираются, билет и имя остаются.
"""

from datetime import timedelta

from django.db.models import F, Q
from django.db.models.functions import Coalesce
from django.utils import timezone

#: Сколько дней после события храним ответы анкеты.
ANSWERS_RETENTION_DAYS = 30


#: Ежедневный проход смотрит только события, закончившиеся 30–90 дней назад: старые
#: уже очищены (шифротекст пустого {} в SQL от данных не отличить — без окна каждый
#: проход расшифровывал бы всю историю). Первый проход после деплоя — полный.
SCAN_WINDOW_DAYS = 90


def purge_answers(*, now=None, full=False) -> int:
    """Стереть ответы анкеты у билетов и участников событий, закончившихся раньше
    срока хранения (в текущей схеме). Возвращает число затронутых билетов."""
    from .models import Event, Ticket, TicketParticipant

    now = now or timezone.now()
    cutoff = now - timedelta(days=ANSWERS_RETENTION_DAYS)
    past = Event.objects.annotate(_end=Coalesce(F("ends_at"), F("starts_at"))).filter(
        _end__lt=cutoff
    )
    if not full:
        past = past.filter(_end__gte=now - timedelta(days=SCAN_WINDOW_DAYS))
    tickets = Ticket.objects.filter(event__in=past)
    count = 0
    # Шифротекст непредсказуем — «пусто ли» видно только после расшифровки.
    for ticket in tickets.only("pk", "answers").iterator(chunk_size=500):
        if ticket.answers:
            Ticket.objects.filter(pk=ticket.pk).update(answers={})
            count += 1
    for part in (
        TicketParticipant.objects.filter(ticket__in=tickets)
        .only("pk", "answers")
        .iterator(chunk_size=500)
    ):
        if part.answers:
            TicketParticipant.objects.filter(pk=part.pk).update(answers={})
    return count


def purge_all_tenants() -> int:
    """Beat: проход по всем схемам; сбой одной схемы не останавливает остальные."""
    import logging

    from django.core.cache import cache
    from django_tenants.utils import get_tenant_model, schema_context

    log = logging.getLogger(__name__)
    total = 0
    full = not cache.get(FULL_DONE_KEY)
    for schema in (
        get_tenant_model()
        .objects.exclude(schema_name="public")
        .filter(~Q(provisioning_status="failed"))
        .values_list("schema_name", flat=True)
    ):
        try:
            with schema_context(schema):
                total += purge_answers(full=full)
        except Exception:  # noqa: BLE001
            log.exception("answers retention failed for schema %s", schema)
    if full:
        cache.set(FULL_DONE_KEY, 1, 400 * 24 * 3600)
    return total


FULL_DONE_KEY = "events:answers-purge-full-done"
