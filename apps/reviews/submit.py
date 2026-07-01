"""UA4-4b: единый обработчик приёма отзыва о продаваемой сущности.

Одна функция для service/stay/event (и, потенциально, product): rate-limit → парсинг/
валидация → per-kind верификация (fail-closed) → `update_or_create` в generic
`reviews.Review`. Вью каждой сущности лишь достаёт объект и строит `detail_url`.
"""

from django.contrib import messages
from django.shortcuts import redirect
from django.utils.translation import gettext as _

from apps.core import ratelimit
from apps.reviews import services as review_services
from apps.reviews.models import Review


def handle_review_submit(request, *, entity_kind, obj, detail_url):
    """Принять POST отзыва об `obj` (kind=`entity_kind`) и вернуть redirect.

    Только верифицированный покупатель (per-kind проверка брони/билета по e-mail).
    Один отзыв на (kind, id, email) — повтор обновляет. Не-POST → редирект на деталь.
    """
    if request.method != "POST":
        return redirect(detail_url)
    # Рейтлимит по IP (анти-спам), как в остальных публичных формах.
    if ratelimit.hit(f"review:{entity_kind}", ratelimit.client_ip(request), limit=10, window=3600):
        messages.error(request, _("Zu viele Versuche. Bitte später erneut."))
        return redirect(detail_url)
    name = (request.POST.get("author_name") or "").strip()[:120]
    email = (request.POST.get("email") or "").strip()
    comment = (request.POST.get("comment") or "").strip()
    try:
        rating = int(request.POST.get("rating") or 0)
    except (TypeError, ValueError):
        rating = 0
    if not (name and email and 1 <= rating <= 5):
        messages.error(request, _("Bitte Name, E-Mail und Bewertung (1–5) angeben."))
        return redirect(detail_url)
    if not review_services.is_verified_buyer(entity_kind, obj, email):
        messages.error(
            request,
            _(
                "Nur verifizierte Kund:innen können bewerten — wir haben keine Buchung "
                "mit dieser E-Mail gefunden."
            ),
        )
        return redirect(detail_url)
    Review.objects.update_or_create(
        entity_kind=entity_kind,
        entity_id=obj.pk,
        email=email.lower(),
        defaults={
            "rating": rating,
            "author_name": name,
            "comment": comment,
            "verified": True,
            "is_published": True,
        },
    )
    messages.success(request, _("Danke für Ihre Bewertung!"))
    return redirect(detail_url + "#bewertungen")
