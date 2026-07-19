"""Кабинет-inbox (M22a): /dashboard/inbox/ — список тредов + тред с ответом.

Владелец/сотрудник видит обращения клиентов, отвечает, меняет статус (FSM),
приоритет и назначение. Доставка писем клиенту — M22b. Гейтинг — модуль «inbox».
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from apps.core.fsm import IllegalTransition

from . import services
from .models import Conversation, Message
from .state_machine import ConversationSM


def _fmt_minutes(delta) -> str:
    """LS-6: «~12 Min» / «~3 Std» — грубая, честная величина реакции."""
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"~{max(minutes, 1)} Min"
    return f"~{minutes // 60} Std"


def _avg_reaction(days: int = 30, cap: int = 200):
    """⌀ время до ПЕРВОГО ответа staff по решённым тредам за `days` дней.

    Без миграции (план LS-6): Min(messages.created_at, staff) − created_at,
    ограничено `cap` тредами. None — данных нет."""
    from datetime import timedelta

    from django.db.models import Min, Q
    from django.utils import timezone

    qs = Conversation.objects.filter(
        status__in=(Conversation.STATUS_RESOLVED, Conversation.STATUS_CLOSED),
        created_at__gte=timezone.now() - timedelta(days=days),
    ).annotate(
        first_staff=Min(
            "messages__created_at", filter=Q(messages__author_role=Message.AUTHOR_STAFF)
        )
    )[:cap]
    deltas = [
        c.first_staff - c.created_at for c in qs if c.first_staff and c.first_staff > c.created_at
    ]
    if not deltas:
        return None
    return _fmt_minutes(sum(deltas, deltas[0] - deltas[0]) / len(deltas))


def avg_reaction_minutes(days: int = 30, cap: int = 200):
    """LS-4: ⌀ реакция в МИНУТАХ (int|None) — публичный бейдж доверия гейтится
    «хорошим значением» на вызывающей стороне (та же выборка, что _avg_reaction)."""
    from datetime import timedelta

    from django.db.models import Min, Q
    from django.utils import timezone

    qs = Conversation.objects.filter(
        status__in=(Conversation.STATUS_RESOLVED, Conversation.STATUS_CLOSED),
        created_at__gte=timezone.now() - timedelta(days=days),
    ).annotate(
        first_staff=Min(
            "messages__created_at", filter=Q(messages__author_role=Message.AUTHOR_STAFF)
        )
    )[:cap]
    deltas = [
        c.first_staff - c.created_at for c in qs if c.first_staff and c.first_staff > c.created_at
    ]
    if not deltas:
        return None
    avg = sum(deltas, deltas[0] - deltas[0]) / len(deltas)
    return max(int(avg.total_seconds() // 60), 1)


@login_required
def inbox_list(request):
    conversations = Conversation.objects.select_related("customer")
    status = request.GET.get("status", "")
    if status in dict(Conversation.STATUSES):
        conversations = conversations.filter(status=status)
    return render(
        request,
        "inbox/list.html",
        {
            "nav": "inbox",
            "conversations": conversations[:200],
            "statuses": Conversation.STATUSES,
            "active_status": status,
            "open_count": Conversation.objects.filter(status=Conversation.STATUS_OPEN).count(),
            # LS-6: ⌀ Reaktionszeit (30 дней, решённые) — SLA на виду у владельца.
            "avg_reaction": _avg_reaction(),
        },
    )


@login_required
def thread(request, pk):
    conversation = get_object_or_404(Conversation.objects.select_related("customer"), pk=pk)
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "reply":
            body = request.POST.get("body", "").strip()
            if body:
                services.post_message(
                    conversation,
                    body=body[:5000],
                    author_role=Message.AUTHOR_STAFF,
                    author_user=request.user,
                )
                messages.success(request, _("Reply sent."))
            else:
                messages.error(request, _("Please write a message."))
        elif action in dict(Conversation.STATUSES):
            try:
                ConversationSM().apply(conversation, action, actor=request.user)
                messages.success(request, _("Status updated."))
            except IllegalTransition:
                messages.error(request, _("This step is not possible in the current status."))
        elif action == "priority":
            priority = request.POST.get("priority", "")
            if priority in dict(Conversation.PRIORITIES):
                conversation.priority = priority
                conversation.save(update_fields=["priority", "updated_at"])
        elif action == "offer-cancel":
            # LS-3: отозвать открытое предложение (только из ЭТОГО треда).
            from apps.orders import offers as order_offers

            offer = conversation.offers.filter(pk=request.POST.get("offer_id")).first()
            if offer is not None:
                order_offers.cancel_offer(offer)
                messages.success(request, _("Angebot zurückgezogen."))
        return redirect("inbox:thread", pk=conversation.pk)

    # Открыли тред — для владельца прочитано.
    if conversation.unread_for_staff:
        conversation.unread_for_staff = False
        conversation.save(update_fields=["unread_for_staff", "updated_at"])
    return render(
        request,
        "inbox/thread.html",
        {
            "nav": "inbox",
            "conversation": conversation,
            "messages_list": conversation.messages.select_related("author_user"),
            "allowed": ConversationSM().allowed_targets(conversation.status),
            "priorities": Conversation.PRIORITIES,
            # LS-3: карточки предложений этого треда (reverse-FK orders.Offer).
            "offers_list": conversation.offers.select_related("order").prefetch_related("lines"),
            # LS-6: время первой реакции ЭТОГО треда (None — staff ещё не отвечал).
            "reaction_time": _thread_reaction(conversation),
        },
    )


@login_required
def offer_compose(request, pk):
    """LS-3: композер «Angebot senden» из треда — пикер позиций (FB-8
    sellable_manage, цены редактируемы) + свободные строки + срок + заметка.
    Server-rendered без JS; названия/kind позиций резолвятся ИЗ СЕКЦИЙ (не из
    hidden-инпутов) — клиентскому вводу доверяем только цену/кол-во."""
    from django.utils.dateparse import parse_date

    from apps.core.sellable_manage import sellable_manage_sections_for
    from apps.orders import offers as order_offers

    conversation = get_object_or_404(Conversation.objects.select_related("customer"), pk=pk)
    sections = sellable_manage_sections_for(request.tenant)
    if request.method == "POST":
        by_token = {f"{s['kind']}:{i.pk}": i for s in sections for i in s["items"]}
        lines = []
        for token in request.POST.getlist("pick"):
            item = by_token.get(token)
            if item is None:
                continue
            lines.append(
                {
                    "kind": item.kind,
                    "ref_id": str(item.pk),
                    "title": item.name,
                    "unit_price": request.POST.get(f"price:{token}", "") or item.price_value or "0",
                    "qty": request.POST.get(f"qty:{token}", "1"),
                }
            )
        for title, price, qty in zip(
            request.POST.getlist("free_title"),
            request.POST.getlist("free_price"),
            request.POST.getlist("free_qty"),
            strict=False,
        ):
            lines.append({"title": title, "unit_price": price, "qty": qty or "1"})
        try:
            order_offers.send_offer(
                conversation,
                lines=lines,
                valid_until=parse_date(request.POST.get("valid_until", "")),
                note=request.POST.get("note", "").strip()[:2000],
                author=request.user,
            )
            messages.success(request, _("Angebot gesendet."))
            return redirect("inbox:thread", pk=conversation.pk)
        except ValueError:
            messages.error(request, _("Bitte mindestens eine Position mit Preis angeben."))
    return render(
        request,
        "inbox/offer_compose.html",
        {"nav": "inbox", "conversation": conversation, "sections": sections},
    )


def unread_count(request):
    """M22b realtime: число тредов с непрочитанным для staff — живой бейдж в нав."""
    from django.http import JsonResponse

    n = Conversation.objects.filter(unread_for_staff=True).count()
    return JsonResponse({"count": n})


def thread_poll(request, pk):
    """M22b realtime: последние сообщения треда в JSON для кабинета — staff видит
    ответ клиента без перезагрузки. Сбрасывает бейдж непрочитанного (тред открыт)."""
    from django.http import JsonResponse
    from django.utils.formats import date_format

    conversation = get_object_or_404(Conversation, pk=pk)
    if conversation.unread_for_staff:
        conversation.unread_for_staff = False
        conversation.save(update_fields=["unread_for_staff", "updated_at"])
    msgs = list(conversation.messages.order_by("-created_at")[:50])
    msgs.reverse()
    return JsonResponse(
        {
            "messages": [
                {
                    "id": str(m.pk),
                    "role": m.author_role,
                    "body": m.body,
                    "created": date_format(m.created_at, "d.m. H:i"),
                }
                for m in msgs
            ]
        }
    )


def _thread_reaction(conversation):
    """LS-6: «~N Min» до первого staff-ответа треда (None — ответа ещё нет)."""
    first = (
        conversation.messages.filter(author_role=Message.AUTHOR_STAFF)
        .order_by("created_at")
        .first()
    )
    if first is None or first.created_at <= conversation.created_at:
        return None
    return _fmt_minutes(first.created_at - conversation.created_at)
