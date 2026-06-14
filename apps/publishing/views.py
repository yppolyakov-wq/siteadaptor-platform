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
        token = oauth.exchange_code(provider, code)
    except Exception:  # noqa: BLE001 — показать аккуратную ошибку, не 500
        return HttpResponse(_("Could not complete the connection."), status=502)
    if not token:
        return HttpResponse(_("No token received. Please try again."), status=502)
    oauth.store_token(provider, schema, token)
    back = oauth.tenant_channels_url(schema)
    return redirect(back) if back else HttpResponse(_("Connected. You can close this tab."))
