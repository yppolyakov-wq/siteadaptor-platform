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


# Чат-фикс 2026-10-23: память ЭТОГО браузера — подписанная кука со списком
# public_token бесед, которые посетитель сам начал или в которых писал, и контакт,
# который он сам ввёл. Только функциональная память («продолжить разговор», не
# спрашивать почту заново), никакого трекинга. Ревью безопасности: контакт берём
# ТОЛЬКО из куки или подтверждённого входа в «Konto» — никогда из карточки клиента
# по совпадению почты (иначе чужая почта открывала бы имя и телефон).
THREADS_COOKIE = "sa_threads"
THREADS_COOKIE_SALT = "inbox-threads"
THREADS_COOKIE_MAX = 10
THREADS_COOKIE_AGE = 60 * 60 * 24 * 30


def _cookie_state(request) -> dict:
    """{"t": [tokens], "c": {name, email, phone}}; подделка/мусор → пусто."""
    import json
    import uuid

    from django.core.signing import BadSignature

    try:
        raw = request.get_signed_cookie(THREADS_COOKIE, default="{}", salt=THREADS_COOKIE_SALT)
        data = json.loads(raw)
    except (BadSignature, ValueError, TypeError):
        return {"t": [], "c": {}}
    if not isinstance(data, dict):
        return {"t": [], "c": {}}
    tokens = []
    for item in data.get("t") if isinstance(data.get("t"), list) else []:
        try:
            tokens.append(str(uuid.UUID(str(item))))
        except (ValueError, TypeError):
            continue
    raw_contact = data.get("c") if isinstance(data.get("c"), dict) else {}
    contact = {k: str(raw_contact.get(k) or "")[:200] for k in ("name", "email", "phone")}
    return {"t": tokens[:THREADS_COOKIE_MAX], "c": contact if contact["email"] else {}}


def _remember(response, request, conversation, *, contact=None):
    """Запомнить беседу (и введённый посетителем контакт) в этом браузере."""
    import json

    state = _cookie_state(request)
    token = str(conversation.public_token)
    tokens = [t for t in state["t"] if t != token]
    tokens.insert(0, token)
    if contact and contact.get("email"):
        state["c"] = {k: (contact.get(k) or "")[:200] for k in ("name", "email", "phone")}
    response.set_signed_cookie(
        THREADS_COOKIE,
        json.dumps({"t": tokens[:THREADS_COOKIE_MAX], "c": state["c"]}),
        salt=THREADS_COOKIE_SALT,
        max_age=THREADS_COOKIE_AGE,
        httponly=True,
        samesite="Lax",
        secure=request.is_secure(),
    )
    return response


def _account_customer(request):
    """Клиент подтверждённого входа в «Konto» (magic link / Telegram) или None."""
    from apps.account.auth import current_customer

    return current_customer(request)


def known_threads(request):
    """Беседы этого браузера (только из куки — их токены выдавались ему самому),
    свежие первыми, с последним сообщением."""
    from django.db.models import F

    from .display import with_last_message

    tokens = _cookie_state(request)["t"]
    if not tokens:
        return []
    qs = Conversation.objects.filter(public_token__in=tokens).select_related("customer")
    return list(
        with_last_message(qs).order_by(F("last_message_at").desc(nulls_last=True), "-created_at")[
            :THREADS_COOKIE_MAX
        ]
    )


def known_contact(request) -> dict:
    """Имя/почта/телефон, которые посетитель уже называл: вход в «Konto» → то, что он
    сам вводил в этом браузере. Пусто — форма спрашивает как раньше."""
    customer = _account_customer(request)
    if customer is not None and customer.email:
        return {
            "name": customer.name or "",
            "email": customer.email,
            "phone": getattr(customer, "phone", "") or "",
        }
    return _cookie_state(request)["c"]


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
        if request.POST.get("action") == "forget":
            # «Auf diesem Gerät vergessen» — память браузера стирается целиком.
            response = redirect("storefront-message")
            response.delete_cookie(THREADS_COOKIE, samesite="Lax")
            return response
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
                    "my_threads": known_threads(request),
                    "known_contact": known_contact(request),
                },
            )
        # LS-6: маркер problem-кнопки + непустой ref сделки → приоритет high
        # (сырой ?priority= НЕ принимаем — аноним поставил бы high всем).
        problem = (
            bool(request.POST.get("problem"))
            and bool(ref.get("ref_kind"))
            and bool(ref.get("ref_id"))
        )
        threads = known_threads(request)
        known = known_contact(request)
        typed = {k: request.POST.get(k, "").strip() for k in ("name", "email", "phone")}
        contact = {k: typed[k] or known.get(k, "") for k in typed}
        # Тот же вопрос по той же сделке/акции, пока беседа открыта, — продолжаем её,
        # а не плодим новую. Только среди бесед ЭТОГО браузера и только если почта не
        # сменилась (иначе посетитель явно пишет от другого имени).
        same = None
        if ref["ref_kind"] and ref["ref_id"] and not problem:
            for c in threads:
                if (
                    c.ref_kind == ref["ref_kind"]
                    and c.ref_id == ref["ref_id"]
                    and c.status in (Conversation.STATUS_OPEN, Conversation.STATUS_PENDING)
                    and (
                        not typed["email"]
                        or (c.customer_id and c.customer.email.lower() == typed["email"].lower())
                    )
                ):
                    same = c
                    break
        if same is not None:
            services.post_message(same, body=body[:5000], author_role=Message.AUTHOR_CUSTOMER)
            messages.success(request, _("Your message was sent."))
            return _remember(
                redirect("storefront-message-thread", token=same.public_token),
                request,
                same,
                contact=contact,
            )
        conversation = services.start_conversation(
            subject=request.POST.get("subject", "").strip()[:200],
            body=body[:5000],
            name=contact["name"],
            email=contact["email"],
            phone=contact["phone"],
            channel=Conversation.CHANNEL_WEB,
            priority=Conversation.PRIORITY_HIGH if problem else "",
            **ref,
        )
        from apps.aggregator import conversions

        conversions.count(request, "contact", "conversation", conversation)  # В5 V5-5
        return _remember(
            redirect("storefront-message-thread", token=conversation.public_token),
            request,
            conversation,
            contact=contact,
        )

    # LS-4 «Слой доверия»: публичный бейдж времени ответа — только при ХОРОШЕМ
    # значении (≤ 2 ч; мало данных/медленно → без бейджа, честность важнее).
    from .views import avg_reaction_minutes

    minutes = avg_reaction_minutes()
    from apps.core import attribution

    threads = known_threads(request)
    return render(
        request,
        "storefront/message_contact.html",
        {
            **_ref(request.GET),
            # Чат-фикс: прежние беседы — продолжить; известная почта — не спрашивать.
            "my_threads": threads,
            "known_contact": known_contact(request),
            "prefill_subject": request.GET.get("subject", ""),
            "problem": request.GET.get("problem", ""),
            "reaction_minutes": minutes if minutes is not None and minutes <= 120 else None,
            "attr": attribution.context(request),  # В5 V5-5: канал → скрытые поля
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
            # Написал в беседе — она «своя» для этого браузера (вернётся на /nachricht/).
            return _remember(
                redirect("storefront-message-thread", token=token), request, conversation
            )
        return redirect("storefront-message-thread", token=token)
    # M22b: «бизнес на связи» по часам работы — серверный рендер, без поллинга
    # (статус меняется раз в день, гонять его в JSON незачем).
    tenant = getattr(request, "tenant", None)
    open_status = tenant.open_status() if tenant is not None else None
    from .display import labelled_messages

    return render(
        request,
        "storefront/message_thread.html",
        {
            "conversation": conversation,
            "messages_list": labelled_messages(conversation, viewer=Message.AUTHOR_CUSTOMER),
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
    from .display import author_label

    conversation = get_object_or_404(
        Conversation.objects.select_related("customer"), public_token=token
    )
    msgs = list(conversation.messages.select_related("author_user").order_by("-created_at")[:50])
    msgs.reverse()  # хронологический порядок
    return JsonResponse(
        {
            "messages": [
                {
                    "id": str(m.pk),
                    "role": m.author_role,
                    "author": author_label(m, conversation, viewer=Message.AUTHOR_CUSTOMER),
                    "body": m.body,
                    "created": date_format(m.created_at, "d.m.Y H:i"),
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
