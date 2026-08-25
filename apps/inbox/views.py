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
from .public_views import is_typing, mark_typing
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
                message = services.post_message(
                    conversation,
                    body=body[:5000],
                    author_role=Message.AUTHOR_STAFF,
                    author_user=request.user,
                )
                # C3: тот же текст дополнительно в Telegram (e-mail ушёл всегда).
                # Сервисная коммуникация внутри существующего треда — вне UWG §7.
                if request.POST.get("via_telegram") and conversation.customer_id:
                    _send_reply_telegram(conversation, message)
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
            # C3: внешние каналы — Telegram доступен только при живой привязке
            # клиента к боту; WhatsApp — ссылка на чат с НОМЕРОМ КЛИЕНТА
            # (отправка через API — external-backlog, платный Business API).
            "telegram_linked": _telegram_linked(conversation.customer),
            "wa_url": _customer_wa_url(conversation),
        },
    )


def _telegram_linked(customer) -> bool:
    """C3: клиент привязан к боту бизнеса (иначе канала нет). Fail-safe."""
    try:
        from apps.telegram.models import TelegramLink
        from apps.telegram.notify import active_bot

        if customer is None or active_bot() is None:
            return False
        return TelegramLink.objects.filter(customer=customer, chat_id__gt="").exists()
    except Exception:  # noqa: BLE001 — канал опционален, тред важнее
        return False


def _customer_wa_url(conversation) -> str:
    """C3: wa.me-чат с клиентом (тема — тред). Пусто без телефона."""
    from apps.core.whatsapp import wa_link

    customer = conversation.customer
    phone = getattr(customer, "phone", "") or ""
    if not phone:
        return ""
    return wa_link(phone, conversation.ref_label or conversation.subject or "")


def _send_reply_telegram(conversation, message) -> None:
    """C3: продублировать ответ владельца в Telegram клиента (fail-safe;
    dedupe по id сообщения — повтор POST не задваивает пуш)."""
    try:
        from apps.telegram.notify import send_to_customer

        send_to_customer(
            conversation.customer,
            type="inbox_reply",
            dedupe_key=f"inbox:msg:{message.id}:telegram",
            text=message.body,
        )
    except Exception:  # noqa: BLE001 — дополнительный канал не роняет ответ
        pass


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


@login_required
def deal_thread(request, kind, pk):
    """C1 «✉️ Nachricht an den Kunden»: тред сделки с карточки заказа/записи/
    брони/заявки.

    Тред уже есть (в т.ч. заведённый клиентом через «⚠️ Etwas stimmt nicht») →
    открываем его: переписка по сделке живёт в ОДНОМ месте. Нет — GET показывает
    маленький композер, POST создаёт тред owner-first и шлёт клиенту штатное
    письмо со ссылкой на публичный тред (post_message в start_conversation).
    """
    from django.http import Http404
    from django.shortcuts import get_object_or_404

    from apps.core import transactions

    from .deal_threads import deal_ref_label, find_thread

    if kind not in transactions.TRANSACTION_KINDS:
        raise Http404("unknown kind")
    obj = get_object_or_404(transactions.model_for(kind), pk=pk)
    customer = getattr(obj, "customer", None)
    code = getattr(obj, "reference_code", "") or ""
    existing = find_thread(kind, code, pk=obj.pk)
    if existing is not None:
        return redirect("inbox:thread", pk=existing.pk)

    label = deal_ref_label(kind, code)
    back_url = transactions.transaction_for(kind, obj).manage_url or ""
    if request.method == "POST":
        body = request.POST.get("body", "").strip()
        if not body:
            messages.error(request, _("Please write a message."))
        elif customer is None or not customer.email:
            messages.error(request, _("Der Kunde hat keine E-Mail-Adresse hinterlegt."))
        else:
            conversation = services.start_conversation(
                subject=label,
                body=body[:5000],
                customer=customer,
                ref_kind=kind,
                ref_id=code,
                ref_label=label,
                author_role=Message.AUTHOR_STAFF,
                author_user=request.user,
            )
            messages.success(request, _("Nachricht gesendet."))
            return redirect("inbox:thread", pk=conversation.pk)
    return render(
        request,
        "inbox/deal_start.html",
        {
            "nav": "inbox",
            "kind": kind,
            "deal": obj,
            "customer": customer,
            "deal_label": label,
            "back_url": back_url,
        },
    )


@login_required
def unread_count(request):
    """M22b realtime: число тредов с непрочитанным для staff — живой бейдж в нав.

    `@login_required` обязателен: без него счётчик обращений бизнеса читался
    анонимом (Membership-гейт middleware анонима не трогает — он рассчитывает
    на этот декоратор)."""
    from django.http import JsonResponse

    n = Conversation.objects.filter(unread_for_staff=True).count()
    return JsonResponse({"count": n})


@login_required
def thread_poll(request, pk):
    """M22b realtime: последние сообщения треда в JSON для кабинета — staff видит
    ответ клиента без перезагрузки. Сбрасывает бейдж непрочитанного (тред открыт).

    `@login_required` обязателен: эндпоинт отдаёт ТЕЛА сообщений и пишет
    `unread_for_staff` — анонима сюда пускать нельзя (найдено ревью 2026-08-03;
    дыра была с появления поллинга)."""
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
            ],
            # M22b: печатает ли СЕЙЧАС клиент (другая сторона треда).
            "typing": is_typing(conversation.pk, "customer"),
        }
    )


@login_required
def thread_typing(request, pk):
    """M22b: пинг «сотрудник печатает» — клиент увидит его своим поллингом."""
    from django.http import HttpResponse, HttpResponseNotAllowed

    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    conversation = get_object_or_404(Conversation, pk=pk)
    mark_typing(conversation.pk, "staff")
    return HttpResponse(status=204)


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
