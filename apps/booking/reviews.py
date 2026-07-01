"""UA4-4b: верификация покупателя для отзывов об УСЛУГЕ (generic `reviews.Review`).

Оставить отзыв об услуге может лишь тот, у кого есть неотменённая бронь
(`booking.Booking`) этой услуги на его e-mail. Любая ошибка (модуль/таблицы
недоступны) → False (**fail-closed**): отзыв нельзя, страница не падает.
"""


def has_booked(service, email: str) -> bool:
    """True, если по email есть неотменённая бронь этой услуги.

    Сравнение email без регистра. Учитываем pending/confirmed/fulfilled (исполненная
    бронь = точно был клиентом), исключаем cancelled/no_show. Ошибка → False."""
    email = (email or "").strip().lower()
    if not email:
        return False
    try:
        from apps.booking.models import Booking

        return (
            Booking.objects.filter(service=service, customer__email__iexact=email)
            .exclude(status__in=[Booking.STATUS_CANCELLED, Booking.STATUS_NO_SHOW])
            .exists()
        )
    except Exception:  # noqa: BLE001 — booking может быть выключен; тогда верификации нет
        return False
