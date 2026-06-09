"""Кабинет каналов публикации (TENANT, под логином).

Тумблеры включения каналов + панель статусов последних публикаций. Под gated-
статусом middleware блокирует POST (read-only) и уводит на биллинг.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

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
