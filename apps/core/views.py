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
    from apps.tenants import onboarding

    setup_done, setup_total = onboarding.progress(request.tenant)
    return render(
        request,
        "tenant/dashboard.html",
        {
            "nav": "dashboard",
            "setup_done": setup_done,
            "setup_total": setup_total,
            "setup_completed": onboarding.get_state(request.tenant)["completed"],
        },
    )


@login_required
def setup_view(request):
    """Onboarding-Wizard (Track D / D0c): пошаговая настройка после регистрации.

    ≤5 шагов, одно решение на шаг, «Überspringen» на каждом; состояние в
    Tenant.site_config["onboarding"] (apps.tenants.onboarding) — мастер
    резюмируется с текущего шага.
    """
    from apps.core import modules as registry
    from apps.promotions import presets
    from apps.tenants import onboarding
    from apps.tenants.models import Tenant

    tenant = request.tenant
    state = onboarding.get_state(tenant)
    step = state["step"]

    if request.method == "POST":
        if request.POST.get("action") == "skip":
            onboarding.advance(tenant, skip=True)
            return redirect("setup")
        if request.POST.get("action") == "back":
            onboarding.back(tenant)
            return redirect("setup")
        if step == 1:
            business_type = request.POST.get("business_type", "")
            if business_type in dict(Tenant.BUSINESS_TYPES):
                # Пресет блоков по вертикали применяем ТОЛЬКО если владелец ещё
                # не настраивал модули сам (текущий набор == пресету прежнего
                # типа). Действующие компании (легаси [] = всё включено) и
                # ручные конфигурации мастер не перезаписывает — иначе у них
                # «пропадают» разделы кабинета (hotfix после деплоя D0–D3).
                untouched_preset = sorted(tenant.disabled_modules or []) == sorted(
                    registry.default_disabled_for(tenant.business_type)
                )
                tenant.business_type = business_type
                update_fields = ["business_type", "updated_at"]
                if untouched_preset:
                    tenant.disabled_modules = registry.default_disabled_for(business_type)
                    update_fields.insert(1, "disabled_modules")
                tenant.save(update_fields=update_fields)
        elif step == 2:
            enabled_keys = set(request.POST.getlist("modules"))
            tenant.disabled_modules = [
                spec.key for spec in registry.optional_modules() if spec.key not in enabled_keys
            ]
            tenant.save(update_fields=["disabled_modules", "updated_at"])
        elif step == 3:
            for field in ("address", "opening_hours", "contact_phone", "contact_email"):
                setattr(tenant, field, request.POST.get(field, "").strip())
            tenant.save(
                update_fields=[
                    "address",
                    "opening_hours",
                    "contact_phone",
                    "contact_email",
                    "updated_at",
                ]
            )
        # Шаг 4 — кнопки пресетов уводят в форму акции; «Weiter» просто двигает дальше.
        onboarding.advance(tenant)
        return redirect("setup")

    context = {"nav": "dashboard", "step": step, "total": onboarding.TOTAL_STEPS, "state": state}
    if step == 1:
        context["business_types"] = Tenant.BUSINESS_TYPES
    elif step == 2:
        context["module_rows"] = [
            {
                "spec": spec,
                "enabled": spec.key not in (tenant.disabled_modules or []),
                "recommended": tenant.business_type in spec.recommended_for,
            }
            for spec in registry.optional_modules()
        ]
    elif step == 4:
        context["presets"] = presets.presets_for(tenant.business_type)
    return render(request, "tenant/setup.html", context)


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
        # Не затираем состояние Onboarding-Wizard (D0c) — оно в том же JSON.
        previous = (
            request.tenant.site_config if isinstance(request.tenant.site_config, dict) else {}
        )
        if isinstance(previous.get("onboarding"), dict):
            config["onboarding"] = previous["onboarding"]
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
def modules_view(request):
    """Страница «Module» (Track D / D0b): тумблеры опциональных блоков кабинета.

    Core-модули показаны задизейбленными; запись — в Tenant.disabled_modules
    (храним выключенное). Read-only при gated-подписке обеспечивает
    SubscriptionGatingMiddleware (путь под /dashboard/).
    """
    from apps.core import modules as registry

    optional = registry.optional_modules()
    if request.method == "POST":
        enabled_keys = set(request.POST.getlist("modules"))
        request.tenant.disabled_modules = [
            spec.key for spec in optional if spec.key not in enabled_keys
        ]
        request.tenant.save(update_fields=["disabled_modules", "updated_at"])
        messages.success(request, "Gespeichert.")
        return redirect("modules")

    dep_labels = {spec.key: spec.label_de for spec in registry.REGISTRY}
    rows = [
        {
            "spec": spec,
            "active": registry.is_module_active(request.tenant, spec.key),
            "enabled": spec.core or spec.key not in (request.tenant.disabled_modules or []),
            "depends_on": [dep_labels[dep] for dep in spec.depends_on],
            "recommended": request.tenant.business_type in spec.recommended_for,
        }
        for spec in registry.REGISTRY
    ]
    return render(request, "tenant/modules.html", {"nav": "modules", "rows": rows})


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
