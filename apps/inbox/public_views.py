"""Публичная страница «Frage stellen» + тред клиента (M22b): /nachricht/.

Гейтинг — модуль inbox (выключен → 404). honeypot + rate-limit по IP, как у
брони/заказа. Клиент видит свой тред по public_token (как код брони) и может
ответить. Письма — services.post_message → notifications.
"""

from django.contrib import messages
from django.core.cache import cache
from django.http import Http404, HttpResponse, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from apps.core import ratelimit

from . import services
from .models import Conversation, Message

RL_LIMIT = 5
RL_WINDOW = 600
# M22b: «печатает» живёт ТОЛЬКО в кэше и обязано протухать само — модель тут была
# бы вредна (мусор в БД + запись на каждое нажатие). TTL чуть больше интервала
# пинга, иначе индикатор мигает между нажатиями.
TYPING_TTL = 6


def _typing_key(conv_pk, role) -> str:
    """Ключ флага «печатает». `conv_pk` — UUID треда, поэтому ключи разных схем
    не пересекаются даже в общем Redis."""
    return f"inbox_typing:{conv_pk}:{role}"


def is_typing(conv_pk, role) -> bool:
    """Печатает ли сейчас сторона `role`. Кэш недоступен → False: индикатор
    просто не показывается, тред продолжает работать."""
    try:
        return bool(cache.get(_typing_key(conv_pk, role)))
    except Exception:  # noqa: BLE001 — упавший Redis не должен ронять тред
        return False


def mark_typing(conv_pk, role) -> None:
    try:
        cache.set(_typing_key(conv_pk, role), True, TYPING_TTL)
    except Exception:  # noqa: BLE001
        pass


def _require_inbox(request):
    tenant = getattr(request, "tenant", None)
    if tenant is None or not tenant.is_module_active("inbox"):
        raise Http404


def _ref(source):
    return {
        "ref_kind": (source.get("kind") or source.get("ref_kind") or "")[:20],
        "ref_id": (source.get("id") or source.get("ref_id") or "")[:64],
        "ref_label": (source.get("label") or source.get("ref_label") or "")[:200],
    }


def contact(request):
    """GET — форма «Frage stellen» (опц. префилл ref из query); POST — создать тред."""
    _require_inbox(request)
    if request.method == "POST":
        if request.POST.get("website"):  # honeypot
            return redirect("storefront-message")
        if ratelimit.hit("inbox", ratelimit.client_ip(request), limit=RL_LIMIT, window=RL_WINDOW):
            return HttpResponse(status=429)
        ref = _ref(request.POST)
        body = request.POST.get("body", "").strip()
        if not body:
            messages.error(request, _("Please write your message."))
            return render(
                request,
                "storefront/message_contact.html",
                {
                    **ref,
                    "prefill_subject": request.POST.get("subject", ""),
                    "problem": request.POST.get("problem", ""),
                },
            )
        # LS-6: маркер problem-кнопки + непустой ref сделки → приоритет high
        # (сырой ?priority= НЕ принимаем — аноним поставил бы high всем).
        problem = (
            bool(request.POST.get("problem"))
            and bool(ref.get("ref_kind"))
            and bool(ref.get("ref_id"))
        )
        conversation = services.start_conversation(
            subject=request.POST.get("subject", "").strip()[:200],
            body=body[:5000],
            name=request.POST.get("name", "").strip(),
            email=request.POST.get("email", "").strip(),
            phone=request.POST.get("phone", "").strip(),
            channel=Conversation.CHANNEL_WEB,
            priority=Conversation.PRIORITY_HIGH if problem else "",
            **ref,
        )
        return redirect("storefront-message-thread", token=conversation.public_token)

    # LS-4 «Слой доверия»: публичный бейдж времени ответа — только при ХОРОШЕМ
    # значении (≤ 2 ч; мало данных/медленно → без бейджа, честность важнее).
    from .views import avg_reaction_minutes

    minutes = avg_reaction_minutes()
    return render(
        request,
        "storefront/message_contact.html",
        {
            **_ref(request.GET),
            "prefill_subject": request.GET.get("subject", ""),
            "problem": request.GET.get("problem", ""),
            "reaction_minutes": minutes if minutes is not None and minutes <= 120 else None,
        },
    )


def thread(request, token):
    _require_inbox(request)
    conversation = get_object_or_404(Conversation, public_token=token)
    if request.method == "POST":
        if request.POST.get("website"):  # honeypot
            return redirect("storefront-message-thread", token=token)
        if ratelimit.hit("inbox", ratelimit.client_ip(request), limit=RL_LIMIT, window=RL_WINDOW):
            return HttpResponse(status=429)
        body = request.POST.get("body", "").strip()
        if body:
            services.post_message(
                conversation, body=body[:5000], author_role=Message.AUTHOR_CUSTOMER
            )
            messages.success(request, _("Your message was sent."))
        return redirect("storefront-message-thread", token=token)
    # M22b: «бизнес на связи» по часам работы — серверный рендер, без поллинга
    # (статус меняется раз в день, гонять его в JSON незачем).
    tenant = getattr(request, "tenant", None)
    open_status = tenant.open_status() if tenant is not None else None
    return render(
        request,
        "storefront/message_thread.html",
        {
            "conversation": conversation,
            "messages_list": conversation.messages.all(),
            # LS-3: карточки персональных предложений (reverse-FK orders.Offer).
            "offers_list": conversation.offers.prefetch_related("lines"),
            "open_status": open_status,
        },
    )


def thread_poll(request, token):
    """M22b realtime: последние сообщения треда в JSON — для лайв-обновления страницы
    клиента без перезагрузки. Клиент дедупит по id (pk — UUID). Read-only, гейтится
    модулем + public_token."""
    _require_inbox(request)
    conversation = get_object_or_404(Conversation, public_token=token)
    msgs = list(conversation.messages.order_by("-created_at")[:50])
    msgs.reverse()  # хронологический порядок
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
            # M22b: печатает ли СЕЙЧАС бизнес. Едет в уже существующем поллинге —
            # отдельного запроса на чтение флага не появляется.
            "typing": is_typing(conversation.pk, "staff"),
        }
    )


def thread_typing(request, token):
    """M22b: пинг «клиент печатает» — флаг в кэше на несколько секунд.

    Тред и так гейтится `public_token`, а ключ содержит его pk, так что чужой
    индикатор не поставить и не прочитать, не зная треда. Только POST: пинг
    мутирует состояние, GET обходил бы CSRF-защиту."""
    _require_inbox(request)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    conversation = get_object_or_404(Conversation, public_token=token)
    mark_typing(conversation.pk, "customer")
    return HttpResponse(status=204)
