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
    base = code.split("@", 1)[0]
    current = next((r for r in rows if r.code == base), rows[0] if rows else None)
    # M21.11: у типа «Seite» — выбор страницы (у каждой свой набор блоков).
    sub_pages, sub = [], None
    if current and current.code == site_schema.TEXT:
        sub_pages = site_schema.text_pages()
        sub = next((p for p in sub_pages if p.code == code), sub_pages[0])
        code = sub.code
    else:
        code = current.code if current else "home"
    preview_url = sub.preview_url if sub else (current.preview_url if current else "")
    studio = reverse("site-home")
    if preview_url:
        studio = f"{studio}?{urlencode({'page': preview_url})}"
    return render(
        request,
        "tenant/site_schema.html",
        {
            "nav": "site-schema",
            "rows": rows,
            "current": current,
            "code": code,
            "sub_pages": sub_pages,
            "sub": sub,
            "preview_url": preview_url,
            "blocks": site_schema.blocks_for(config, code),
            "add_options": site_schema.add_options(code),
            "studio_url": studio,
        },
    )
