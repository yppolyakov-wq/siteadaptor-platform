"""T-8.35 R5: премодерация отзывов портала о бизнесе (решение владельца 2026-11-17).

Единственный писатель статуса отзыва:
* `submit` — житель оставил или изменил отзыв → «pending» (неизменённый опубликованный
  отзыв остаётся опубликованным);
* `decide` — оператор (админка) публикует или отклоняет с обоснованием; автор получает
  письмо с решением (DSA Art. 17), агрегат рейтинга пересчитывается;
* `object_to` — бизнес возражает против отзыва (Einwand) из кабинета; решает оператор.
Публичные выборки берут только `published` (рейтинг, витрина, JSON-LD).
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from .models import BusinessReview

MAX_TEXT = 2000
DEFAULT_REJECT_REASON = (
    "Die Bewertung verstößt gegen unsere Nutzungsbedingungen (Abschnitt „Bewertungen“)."
)
DECISIONS = (BusinessReview.STATUS_PUBLISHED, BusinessReview.STATUS_REJECTED)


def submit(*, user, business, slug: str, rating: int, comment: str) -> BusinessReview:
    comment = (comment or "").strip()[:MAX_TEXT]
    with transaction.atomic():
        review = (
            BusinessReview.objects.select_for_update()
            .filter(author=user, tenant_schema=business.schema_name)
            .first()
        )
        unchanged = (
            review is not None
            and review.status == BusinessReview.STATUS_PUBLISHED
            and review.rating == rating
            and review.comment == comment
        )
        if unchanged:
            return review
        if review is None:
            review = BusinessReview(author=user, tenant_schema=business.schema_name)
        was_published = review.status == BusinessReview.STATUS_PUBLISHED and review.pk
        review.tenant_slug = slug
        review.business_name = business.name
        review.rating = rating
        review.comment = comment
        review.status = BusinessReview.STATUS_PENDING
        review.decision_reason = ""
        review.decided_at = None
        review.objection_text = ""
        review.objection_at = None
        review.save()
    if was_published:  # изменённый отзыв уходит из рейтинга до решения
        from .reviews import recompute_rating

        recompute_rating(business.schema_name)
    return review


def decide(review: BusinessReview, status: str, *, reason: str = "") -> bool:
    """Решение оператора. True — статус изменился (и письмо автору поставлено в очередь)."""
    if status not in DECISIONS:
        raise ValueError(status)
    if status == BusinessReview.STATUS_REJECTED:
        reason = (reason or "").strip() or DEFAULT_REJECT_REASON
    changed = review.status != status
    review.status = status
    review.decision_reason = (reason or "").strip()[:MAX_TEXT]
    review.decided_at = timezone.now()
    review.save(update_fields=["status", "decision_reason", "decided_at", "updated_at"])
    from .reviews import recompute_rating

    recompute_rating(review.tenant_schema)
    if changed:
        notify_author(review)
    return changed


def notify_author(review: BusinessReview) -> None:
    from .tasks import send_review_decision_email

    email = getattr(review.author, "email", "") or ""
    if not email:
        return
    stamp = review.decided_at.isoformat() if review.decided_at else ""
    transaction.on_commit(
        lambda: send_review_decision_email.delay(
            dedupe_key=f"review-decision:{review.pk}:{review.status}:{stamp}",
            review_id=review.pk,
        )
    )


def object_to(review: BusinessReview, text: str) -> None:
    """Einwand бизнеса — оператор видит его в очереди админки."""
    review.objection_text = (text or "").strip()[:MAX_TEXT]
    review.objection_at = timezone.now() if review.objection_text else None
    review.save(update_fields=["objection_text", "objection_at", "updated_at"])
