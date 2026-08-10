"""UA4-4b: верификация покупателя для отзывов о СОБЫТИИ (generic `reviews.Review`).

Оставить отзыв о событии может лишь тот, у кого есть неотменённый билет
(`events.Ticket`) на это событие по его e-mail. Любая ошибка → False (**fail-closed**).
"""


def has_ticket(event, email: str) -> bool:
    """True, если по email есть неотменённый билет на это событие.

    Без регистра; учитываем pending/confirmed/attended, исключаем cancelled.
    Ошибка (модуль/таблицы недоступны) → False."""
    email = (email or "").strip().lower()
    if not email:
        return False
    try:
        from apps.core import status_registry
        from apps.events.models import Ticket

        # SM-3: «отменённые» через реестр — билет в кастом-cancel статусе тоже
        # не даёт статуса верифицированного покупателя.
        return (
            Ticket.objects.filter(event=event, customer__email__iexact=email)
            .exclude(status__in=status_registry.cancelled_statuses_for("ticket"))
            .exists()
        )
    except Exception:  # noqa: BLE001 — events может быть выключен; тогда верификации нет
        return False
