"""Кабинет каналов публикации (TENANT, под логином).

Тумблеры включения каналов + панель статусов последних публикаций. Под gated-
статусом middleware блокирует POST (read-only) и уводит на биллинг.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import oauth
from .models import Channel, Publication


def _ensure_channels():
    """По строке Channel на каждый доступный тип (idempotent)."""
    for type_, _label in Channel.CHANNEL_TYPES:
        Channel.objects.get_or_create(type=type_)


@login_required
def channels(request):
    _ensure_channels()
    return render(
        request,
        "publishing/channels.html",
        {
            "nav": "channels",
            "channels": Channel.objects.all().order_by("type"),
            "publications": (Publication.objects.select_related("channel", "promotion").all()[:20]),
        },
    )


@login_required
@require_POST
def channel_toggle(request):
    channel = Channel.objects.filter(type=request.POST.get("type", "")).first()
    if channel is not None:
        channel.is_enabled = not channel.is_enabled
        channel.save(update_fields=["is_enabled", "updated_at"])
        messages.success(request, _("Channel updated."))
    return redirect("channels")


# Конфиг-ключи, редактируемые со страницы каналов (per type).
_CONFIG_FIELDS = {
    Channel.GOOGLE_BUSINESS: ("location", "refresh_token"),
    Channel.FACEBOOK: ("page_id", "access_token"),
    Channel.INSTAGRAM: ("ig_user_id", "access_token"),
    Channel.TELEGRAM: ("bot_token", "chat_id"),
    Channel.PINTEREST: ("access_token", "board_id"),
}


@login_required
@require_POST
def channel_config(request):
    """Сохранить настройки канала. Пустое значение не затирает сохранённое."""
    channel = Channel.objects.filter(type=request.POST.get("type", "")).first()
    fields = _CONFIG_FIELDS.get(channel.type) if channel else None
    if channel is not None and fields:
        from apps.secrets import crypto

        from .secrets import SECRET_KEYS

        config = dict(channel.config or {})
        for key in fields:
            value = request.POST.get(key, "").strip()
            if value:
                # секретные подключи шифруем at-rest; неизменённые остаются как есть
                config[key] = crypto.encrypt(value) if key in SECRET_KEYS else value
        channel.config = config
        channel.save(update_fields=["config", "updated_at"])
        messages.success(request, _("Channel configuration saved."))
    return redirect("channels")


# --- In-app OAuth подключение каналов (OAuth-A) ------------------------------


@login_required
def oauth_start(request, provider):
    """Увести владельца на провайдера для выдачи доступа (GBP/Pinterest)."""
    if not oauth.supports(provider):
        raise Http404
    return redirect(oauth.authorize_url(provider, connection.schema_name))


def oauth_callback(request, provider):
    """Единый callback на основном домене (public): code → токен → Channel.config.

    Без логина: доверяем подписанному state (схема арендатора). Ошибки —
    короткой страницей, успех — редирект на каналы арендатора.
    """
    if not oauth.supports(provider):
        raise Http404
    schema = oauth.read_state(request.GET.get("state", ""), provider)
    code = request.GET.get("code", "")
    if not schema or not code:
        return HttpResponse(_("Authorization failed. Please try again."), status=400)
    try:
        oauth.complete(provider, schema, code)
    except Exception:  # noqa: BLE001 — показать аккуратную ошибку, не 500
        return HttpResponse(_("Could not complete the connection."), status=502)
    back = oauth.tenant_channels_url(schema)
    return redirect(back) if back else HttpResponse(_("Connected. You can close this tab."))


@login_required
def posts(request):
    """CM-2: контент-календарь — собственные посты (текст/фото/ссылка) с
    отправкой в включённые каналы: «Planen» (к дате, beat send_due_content),
    «Jetzt senden», «Entwurf». Доставка per-канал — Publications (Channels).
    """
    from django.contrib import messages
    from django.core.exceptions import ValidationError
    from django.shortcuts import get_object_or_404, redirect
    from django.utils import timezone
    from django.utils.dateparse import parse_datetime
    from django.utils.translation import gettext as _t

    from apps.catalog.images import save_product_image

    from .models import Channel, SocialPost
    from .services import publish_post
    from .state_machine import POST_SCHEDULED, POST_SENT, SocialPostSM

    sm = SocialPostSM()

    def _send_now(post):
        post.scheduled_at = timezone.now()
        post.save(update_fields=["scheduled_at", "updated_at"])
        if post.status == SocialPost.DRAFT:
            sm.apply(post, POST_SCHEDULED)
        publish_post(post)
        sm.apply(post, POST_SENT)

    if request.method == "POST":
        action = request.POST.get("action", "")
        pk = request.POST.get("pk", "")
        if action in ("delete", "send_now") and pk:
            post = get_object_or_404(SocialPost, pk=pk)
            if action == "delete":
                post.delete()
                messages.success(request, _t("Post deleted."))
            elif post.status != SocialPost.SENT:
                _send_now(post)
                messages.success(request, _t("Post sent to channels."))
            return redirect("publishing-posts")
        text = (request.POST.get("text") or "").strip()
        if not text:
            messages.error(request, _t("Text is required."))
            return redirect("publishing-posts")
        image = {}
        uploaded = request.FILES.get("image")
        if uploaded is not None:
            try:
                image = save_product_image(uploaded, folder="posts")
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
                return redirect("publishing-posts")
        when = parse_datetime((request.POST.get("scheduled_at") or "").strip())
        if when is not None and timezone.is_naive(when):
            when = timezone.make_aware(when)
        post = SocialPost.objects.create(
            text=text,
            link_url=(request.POST.get("link_url") or "").strip(),
            image=image,
        )
        if action == "now":
            _send_now(post)
            messages.success(request, _t("Post sent to channels."))
        elif action == "schedule" and when is not None:
            post.scheduled_at = when
            post.save(update_fields=["scheduled_at", "updated_at"])
            sm.apply(post, POST_SCHEDULED)
            messages.success(request, _t("Post scheduled."))
        else:
            messages.success(request, _t("Draft saved."))  # без даты — черновик
        return redirect("publishing-posts")

    return render(
        request,
        "publishing/posts.html",
        {
            "nav": "posts",
            # CM-3: префилл из кнопок «Teilen» (блог/событие/товар) — GET-параметры.
            "prefill_text": (request.GET.get("text") or "")[:2000],
            "prefill_link": (request.GET.get("link") or "")[:500],
            "scheduled": SocialPost.objects.filter(status=SocialPost.SCHEDULED).order_by(
                "scheduled_at"
            ),
            "drafts": SocialPost.objects.filter(status=SocialPost.DRAFT),
            "sent": SocialPost.objects.filter(status=SocialPost.SENT).order_by("-scheduled_at")[
                :20
            ],
            "has_channels": Channel.objects.filter(is_enabled=True).exists(),
        },
    )
