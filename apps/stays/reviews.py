"""UA4-4b: верификация покупателя для отзывов о НОМЕРЕ (generic `reviews.Review`).

Оставить отзыв о номере может лишь тот, у кого есть неотменённая бронь
(`stays.StayBooking`) этого юнита на его e-mail. Любая ошибка → False (**fail-closed**).
"""


def has_stayed(unit, email: str) -> bool:
    """True, если по email есть неотменённая бронь этого юнита.

    Без регистра; учитываем pending/confirmed/fulfilled, исключаем cancelled/no_show.
    Ошибка (модуль/таблицы недоступны) → False."""
    email = (email or "").strip().lower()
    if not email:
        return False
    try:
        from apps.stays.models import StayBooking

        return (
            StayBooking.objects.filter(unit=unit, customer__email__iexact=email)
            .exclude(status__in=[StayBooking.STATUS_CANCELLED, StayBooking.STATUS_NO_SHOW])
            .exists()
        )
    except Exception:  # noqa: BLE001 — stays может быть выключен; тогда верификации нет
        return False
