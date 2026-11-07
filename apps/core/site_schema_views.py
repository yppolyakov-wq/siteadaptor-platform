"""FB-25: экран «Website › Seitenaufbau» — схема блоков страниц + уменьшенная живая страница."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import gettext as _

from apps.core import site_schema


@login_required
def site_schema_view(request):
    from apps.tenants import siteconfig

    tenant = request.tenant
    code = request.GET.get("seite") or request.POST.get("seite") or "home"
    if request.method == "POST":
        try:
            site_schema.apply(
                tenant,
                code,
                request.POST.get("op", ""),
                ref=request.POST.get("ref", ""),
                block_type=request.POST.get("type", ""),
            )
            messages.success(request, _("Gespeichert."))
        except site_schema.SchemaError:
            messages.error(request, _("Diese Änderung ist hier nicht möglich."))
        return redirect(f"{reverse('site-schema')}?{urlencode({'seite': code})}")
    config = siteconfig.normalize(tenant.site_config)
    rows = site_schema.page_rows(config)
    current = next((r for r in rows if r.code == code), rows[0] if rows else None)
    code = current.code if current else "home"
    studio = reverse("site-home")
    if current and current.preview_url:
        studio = f"{studio}?{urlencode({'page': current.preview_url})}"
    return render(
        request,
        "tenant/site_schema.html",
        {
            "nav": "site-schema",
            "rows": rows,
            "current": current,
            "blocks": site_schema.blocks_for(config, code),
            "add_options": site_schema.add_options(code),
            "studio_url": studio,
        },
    )
