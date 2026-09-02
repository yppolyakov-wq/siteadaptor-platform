"""DL-7b: экран «Design» кабинета — переключатель шаблонов вне Studio.

Фидбэк владельца 2026-09-01: выбор темы жил только внутри областей Studio и
терялся среди настроек канвы. Здесь — отдельный подпункт раздела Website:
карточки Startpaket'ов с живыми мини-превью (stateless-оверлей
`?preview=1&look=…&bundle=…`, ничего не пишет) и Look'и архетипа; применение
POST'ом через apply_bundle/apply_look — СОХРАНЯЕТСЯ сразу, без зависимости от
Save канвы (класс «кликнул Look, ушёл — тема не применилась»).
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from apps.tenants import sitetemplates


@login_required
def design_view(request):
    tenant = request.tenant
    if request.method == "POST":
        bundle = request.POST.get("bundle", "")
        look = request.POST.get("look", "")
        if bundle and sitetemplates.apply_bundle(tenant, bundle):
            messages.success(request, _("Vorlage übernommen."))
        elif look and sitetemplates.apply_look(tenant, look):
            messages.success(request, _("Vorlage übernommen."))
        else:
            messages.error(request, _("Unbekannte Vorlage."))
        return redirect("design")
    from apps.tenants import siteconfig

    # DL-8a: активный выбор (ключ design пишут apply_bundle/apply_look).
    current = siteconfig.normalize(tenant.site_config).get("design") or {}
    return render(
        request,
        "tenant/design.html",
        {
            # DL-13: подпись композиции на карточке (чем шаблон отличается по
            # структуре страницы — анализ DL-12, фидбэк «опять всё Fokus»).
            "bundles": [
                {**b, "composition_label": sitetemplates.composition_label(b)}
                for b in sitetemplates.bundles_for(tenant.business_type)
            ],
            "looks": sitetemplates.looks_for(tenant.business_type),
            "current_bundle": current.get("bundle", ""),
            "current_look": current.get("look", ""),
        },
    )
