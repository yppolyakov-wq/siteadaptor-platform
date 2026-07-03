"""CM-6.1: кабинет «Bewertungen» — список отзывов тенанта + скрыть/показать.

До этого владелец не мог модерировать отзывы вовсе (is_published жил только
в докстринге). Ответы владельца — CM-6.2 (review_reply подключается там же).
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import services
from .models import Review

_KINDS = [k for k, _label in Review.ENTITY_KINDS]


@login_required
def review_list(request):
    reviews = Review.objects.all()
    kind = request.GET.get("art", "")
    if kind in _KINDS:
        reviews = reviews.filter(entity_kind=kind)
    status = request.GET.get("status", "")
    if status == "hidden":
        reviews = reviews.filter(is_published=False)
    elif status == "published":
        reviews = reviews.filter(is_published=True)
    reviews = list(reviews.order_by("-created_at")[:200])
    labels = services.entity_labels(reviews)
    for r in reviews:  # подпись сущности прямо на объект (шаблону так проще)
        r.entity_label = labels.get((r.entity_kind, r.entity_id), "")
    return render(
        request,
        "reviews/review_list.html",
        {
            "nav": "reviews",
            "reviews": reviews,
            "overview": services.owner_overview(),  # CM-6.3: KPI-шапка
            "kinds": Review.ENTITY_KINDS,
            "active_kind": kind,
            "active_status": status,
        },
    )


@login_required
@require_POST
def review_reply(request, pk):
    """CM-6.2: ответ владельца (пустой текст = убрать ответ)."""
    from django.utils import timezone

    review = get_object_or_404(Review, pk=pk)
    text = (request.POST.get("reply_text") or "").strip()[:2000]
    review.reply_text = text
    review.replied_at = timezone.now() if text else None
    review.save(update_fields=["reply_text", "replied_at", "updated_at"])
    messages.success(request, _("Reply saved.") if text else _("Reply removed."))
    return redirect(f"{request.POST.get('next') or 'reviews:list'}")


@login_required
@require_POST
def review_toggle(request, pk):
    """Скрыть/показать отзыв (лёгкая модерация; удаление — сознательно нет)."""
    review = get_object_or_404(Review, pk=pk)
    review.is_published = not review.is_published
    review.save(update_fields=["is_published", "updated_at"])
    messages.success(request, _("Review shown.") if review.is_published else _("Review hidden."))
    return redirect(f"{request.POST.get('next') or 'reviews:list'}")
