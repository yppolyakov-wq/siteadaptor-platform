"""Пространство поездки на витрине: лента, чат, приглашение, модерация (MT-3).

Доступ решает `access.role_of` — вьюхи только применяют вердикт. Посторонний
получает 404 (а не 403): существование группы конкретной поездки не подтверждаем.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core import ratelimit

from . import access, services
from .models import FeedPost, FeedSpace

RL_LIMIT = 20
RL_WINDOW = 600
#: Сколько последних реплик чата отдаём при первой загрузке.
CHAT_TAIL = 50


def _space_or_404(pk):
    return get_object_or_404(FeedSpace, pk=pk)


def _require_reader(request, space):
    role = access.role_of(request, space)
    if not access.can_read(role):
        raise Http404
    return role


def _customer(request):
    from apps.promotions.models import Customer

    customer_id = access.current_customer_id(request)
    return Customer.objects.filter(pk=customer_id).first() if customer_id else None


def space_view(request, pk):
    """Лента поездки + вкладка чата."""
    space = _space_or_404(pk)
    role = _require_reader(request, space)
    tab = "chat" if request.GET.get("tab") == "chat" else "feed"
    staff = role == access.STAFF
    kind = FeedPost.KIND_MESSAGE if tab == "chat" else FeedPost.KIND_POST
    posts = list(services.visible_posts(space, kind, for_staff=staff))
    if tab == "chat":
        posts = posts[-CHAT_TAIL:]
    return render(
        request,
        "community/space.html",
        {
            "space": space,
            "role": role,
            "is_staff": staff,
            "tab": tab,
            "posts": posts,
            "can_post": access.can_post(role, space),
            "last_id": posts[-1].pk if posts else "",
        },
    )


@require_POST
def space_post(request, pk):
    """Новая запись ленты или реплика чата."""
    space = _space_or_404(pk)
    role = _require_reader(request, space)
    if not access.can_post(role, space):
        raise Http404
    if request.POST.get("website"):  # honeypot
        return redirect("community-space", pk=space.pk)
    if ratelimit.hit(
        f"community:{space.pk}", ratelimit.client_ip(request), limit=RL_LIMIT, window=RL_WINDOW
    ):
        messages.error(request, _("Zu viele Beiträge — bitte kurz warten."))
        return redirect("community-space", pk=space.pk)
    kind = FeedPost.KIND_MESSAGE if request.POST.get("kind") == "message" else FeedPost.KIND_POST
    body = request.POST.get("body", "")
    images = _uploaded_images(request)
    if body.strip() or images:
        post = services.add_post(
            space,
            body=body,
            kind=kind,
            user=request.user if role == access.STAFF else None,
            customer=_customer(request) if role != access.STAFF else None,
            images=images,
        )
        _notify_space(space, post)
    tab = "chat" if kind == FeedPost.KIND_MESSAGE else "feed"
    return redirect(f"{_space_url(space)}?tab={tab}")


def _space_url(space) -> str:
    from django.urls import reverse

    return reverse("community-space", args=[space.pk])


def _uploaded_images(request) -> list:
    """Фото группы — обычным конвейером изображений (не досье: это не документы)."""
    from apps.catalog.images import save_product_image

    out = []
    for f in request.FILES.getlist("photos")[: services.MAX_IMAGES]:
        try:
            out.append(save_product_image(f, sort_order=len(out), folder="community"))
        except Exception:
            continue
    return out


def _notify_space(space, post) -> None:
    """Разослать уведомление и продублировать запись в TG-группу — fail-safe.

    Ни рассылка, ни мост не должны ронять саму публикацию: запись уже в ленте.
    """
    try:
        from .notifications import notify_new_post

        notify_new_post(space, post)
    except Exception:  # noqa: BLE001
        pass
    try:
        from .telegram_bridge import push_to_group

        push_to_group(post)
    except Exception:  # noqa: BLE001
        pass


@require_POST
def space_comment(request, pk, post_id):
    space = _space_or_404(pk)
    role = _require_reader(request, space)
    if not access.can_post(role, space):
        raise Http404
    post = get_object_or_404(FeedPost, pk=post_id, space=space)
    body = request.POST.get("body", "")
    if body.strip():
        services.add_comment(
            post,
            body=body,
            user=request.user if role == access.STAFF else None,
            customer=_customer(request) if role != access.STAFF else None,
        )
    return redirect(_space_url(space))


def space_poll(request, pk):
    """Последние реплики чата — JSON для поллинга (паттерн inbox `thread_poll`).

    Как в inbox: отдаём хвост, а клиент дедупит по id. Курсор не заводим — он
    ломается при правках/скрытии записей, а хвост из 50 строк дёшев и честен.
    Решение «что видно» остаётся на сервере: скрытые модерацией не уезжают.
    """
    space = _space_or_404(pk)
    role = _require_reader(request, space)
    qs = services.visible_posts(space, FeedPost.KIND_MESSAGE, for_staff=role == access.STAFF)
    items = [
        {
            "id": str(p.pk),
            "author": p.author_label,
            "staff": p.by_staff,
            "body": p.body,
            "time": p.created_at.strftime("%H:%M"),
        }
        for p in list(qs)[-CHAT_TAIL:]
    ]
    return JsonResponse({"items": items})


def space_join(request, token):
    """Приглашение сопровождающего: отмечаем в сессии и пускаем внутрь."""
    space = get_object_or_404(FeedSpace, invite_token=token)
    request.session[access.invite_session_key(space)] = True
    return redirect(_space_url(space))


@require_POST
def post_toggle(request, pk, post_id):
    """Модерация: скрыть/показать запись (только гид)."""
    space = _space_or_404(pk)
    if access.role_of(request, space) != access.STAFF:
        raise Http404
    post = get_object_or_404(FeedPost, pk=post_id, space=space)
    services.toggle_hidden(post)
    return redirect(_space_url(space))


@login_required
def event_space(request, pk):
    """Кабинет: пространство заезда — настройки, код привязки TG, приглашение.

    Пространство заводится по первому заходу гида: отдельной кнопки «создать»
    нет, иначе половина заездов осталась бы без группы.
    """
    from apps.events.models import Event

    event = get_object_or_404(Event, pk=pk)
    space = services.space_for_event(event)
    if request.method == "POST":
        space.is_open = bool(request.POST.get("is_open"))
        space.members_can_post = bool(request.POST.get("members_can_post"))
        space.save(update_fields=["is_open", "members_can_post", "updated_at"])
        messages.success(request, _("Einstellungen gespeichert."))
        return redirect("community:event-space", pk=event.pk)
    return render(
        request,
        "community/event_space.html",
        {
            "event": event,
            "space": space,
            "posts": services.visible_posts(space, FeedPost.KIND_POST, for_staff=True)[:20],
            "nav": "events",
        },
    )
