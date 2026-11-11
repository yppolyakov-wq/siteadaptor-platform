"""FB-25 / FB-27: экран «Website › Seitenaufbau» — схема страницы рядами и её правка."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import gettext as _

from apps.core import site_schema


def _url(code: str, block: str = "") -> str:
    query = {"seite": code}
    if block:
        query["block"] = block
    # Якорь панели: после действия фокус возвращается к блоку, а не в начало страницы.
    return f"{reverse('site-schema')}?{urlencode(query)}" + ("#schema-panel" if block else "")


@login_required
def site_schema_view(request):
    from apps.tenants import siteconfig

    tenant = request.tenant
    code = request.GET.get("seite") or request.POST.get("seite") or "home"
    if request.method == "POST":
        op = request.POST.get("op", "")
        ref = request.POST.get("ref", "")
        try:
            ref = site_schema.apply(
                tenant, code, op, ref=ref, block_type=request.POST.get("type", "")
            )
            messages.success(request, _("Gespeichert."))
        except site_schema.SchemaError:
            messages.error(request, _("Diese Änderung ist hier nicht möglich."))
        # FB-27 R1: блок остаётся выбранным (новый — тоже), удалённый — нет.
        return redirect(_url(code, "" if op == "delete" else ref))
    config = siteconfig.normalize(tenant.site_config)
    groups = site_schema.type_groups(tenant, config)
    rows = [r for _label, items in groups for r in items]
    # Тип, которого у бизнеса нет (или мусор в адресе), не открывается — главная.
    current = next((r for r in rows if r.code == code), rows[0] if rows else None)
    code = current.code if current else "home"
    blocks = site_schema.blocks_for(config, code)
    selected = next((b for b in blocks if b["ref"] == request.GET.get("block")), None)
    preview_url = current.preview_url if current else ""
    studio = reverse("site-home")
    if preview_url:
        studio = f"{studio}?{urlencode({'page': preview_url})}"
    return render(
        request,
        "tenant/site_schema.html",
        {
            "nav": "site-schema",
            "groups": groups,
            "current": current,
            "code": code,
            "preview_url": preview_url,
            "blocks": blocks,
            "layout": site_schema.schema_layout(blocks),
            "selected": selected,
            "confirm_remove": bool(selected) and request.GET.get("entfernen") == "1",
            "add_options": site_schema.add_options(code),
            "studio_url": studio,
        },
    )
