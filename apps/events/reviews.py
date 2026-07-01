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
        from apps.events.models import Ticket

        return (
            Ticket.objects.filter(event=event, customer__email__iexact=email)
            .exclude(status=Ticket.STATUS_CANCELLED)
            .exists()
        )
    except Exception:  # noqa: BLE001 — events может быть выключен; тогда верификации нет
        return False
