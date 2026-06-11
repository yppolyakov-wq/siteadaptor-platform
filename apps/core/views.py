"""Общие tenant-facing вьюхи (живут в схеме арендатора)."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.tenants import domains
from apps.tenants.forms import BusinessSettingsForm
from apps.tenants.models import CustomDomain


@login_required
def dashboard(request):
    """Главная кабинета владельца."""
    return render(request, "tenant/dashboard.html", {"nav": "dashboard"})


@login_required
def settings_view(request):
    """Настройки бизнеса: контакты и правовые тексты для витрины."""
    form = BusinessSettingsForm(request.POST or None, instance=request.tenant)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Gespeichert.")
        return redirect("settings")
    return render(request, "tenant/settings.html", {"form": form, "nav": "settings"})


@login_required
def site_view(request):
    """Конструктор витрины v1 (Track C2): секции главной + тексты hero/about."""
    from apps.tenants import siteconfig

    if request.method == "POST":
        rows = []
        for key, _label, _default in siteconfig.SECTIONS:
            try:
                order = int(request.POST.get(f"order_{key}", "0"))
            except (TypeError, ValueError):
                order = 0
            rows.append((order, key, request.POST.get(f"enabled_{key}") == "on"))
        rows.sort(key=lambda row: row[0])
        config = {"sections": [{"key": key, "enabled": on} for _o, key, on in rows]}
        for field in siteconfig.TEXT_FIELDS:
            config[field] = request.POST.get(field, "")
        request.tenant.site_config = siteconfig.normalize(config)
        request.tenant.save(update_fields=["site_config", "updated_at"])
        messages.success(request, "Gespeichert.")
        return redirect("site")

    config = siteconfig.normalize(request.tenant.site_config)
    labels = {key: label for key, label, _default in siteconfig.SECTIONS}
    sections = [
        {
            "key": s["key"],
            "label": labels[s["key"]],
            "enabled": s["enabled"],
            "order": index,
        }
        for index, s in enumerate(config["sections"], start=1)
    ]
    return render(
        request,
        "tenant/site.html",
        {"nav": "site", "sections": sections, "config": config},
    )


@login_required
def domains_view(request):
    """Список custom-доменов бизнеса + форма добавления и DNS-инструкция."""
    return render(
        request,
        "tenant/domains.html",
        {
            "nav": "domains",
            "domains": request.tenant.custom_domains.all(),
            "target_ip": getattr(settings, "CUSTOM_DOMAIN_TARGET_IP", ""),
        },
    )


@login_required
@require_POST
def domain_add(request):
    try:
        domain = domains.validate_new_domain(request.POST.get("domain", ""))
    except domains.DomainError as exc:
        messages.error(request, str(exc))
        return redirect("domains")
    CustomDomain.objects.create(domain=domain, tenant=request.tenant)
    messages.success(request, _("Domain added. Set the DNS A record, then verify."))
    return redirect("domains")


@login_required
@require_POST
def domain_verify(request, pk):
    custom = get_object_or_404(CustomDomain, pk=pk, tenant=request.tenant)
    if domains.verify(custom):
        messages.success(request, _("Domain verified and active."))
    else:
        messages.error(request, custom.last_check_error or _("Verification failed."))
    return redirect("domains")


@login_required
@require_POST
def domain_remove(request, pk):
    custom = get_object_or_404(CustomDomain, pk=pk, tenant=request.tenant)
    domains.remove(custom)
    messages.success(request, _("Domain removed."))
    return redirect("domains")
