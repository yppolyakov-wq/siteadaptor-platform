"""FB-33 M4: ⚙ Студии → окно блока «Seitenaufbau» (GET, только 302, ничего не пишет)."""

from __future__ import annotations

import logging
from urllib.parse import urlsplit

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.views.decorators.http import require_GET

from apps.core import window_links

logger = logging.getLogger(__name__)


def _inside_schema(url: str) -> str:
    """Адрес перехода — только экран «Seitenaufbau» (страховка поверх `window_links`)."""
    base = window_links.schema_url()
    parts = urlsplit(url)
    if parts.scheme or parts.netloc or parts.path != base:
        logger.error("window link: target outside the schema screen dropped: %r", url)
        return base
    return url


@login_required
@require_GET
def site_schema_open(request):
    """`?page=<путь канвы>&block=<ключ секции>[&tab=]` → окно блока. Путь — тем же
    фильтром, что старт канвы Студии (`_safe_preview_page`: только внутренний путь витрины)."""
    from apps.core.views import _safe_preview_page

    path = _safe_preview_page(request.GET.get("page"))
    url = window_links.studio_settings_url(
        request, path, request.GET.get("block", ""), request.GET.get("tab", "")
    )
    return redirect(_inside_schema(url))
