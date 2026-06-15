"""Общие tenant-facing вьюхи (живут в схеме арендатора)."""

import re

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
                # Гибрид (решение владельца 2026-06-12): набор блоков должен
                # подходить типу — при СМЕНЕ типа пресет вертикали применяется
                # заново (магазину Booking выключится). Если тип не менялся,
                # ручную/легаси конфигурацию не трогаем (hotfix run 122) —
                # кроме случая, когда набор ещё равен пресету (нечего терять).
                untouched_preset = sorted(tenant.disabled_modules or []) == sorted(
                    registry.default_disabled_for(tenant.business_type)
                )
                type_changed = business_type != tenant.business_type
                tenant.business_type = business_type
                update_fields = ["business_type", "updated_at"]
                if type_changed or untouched_preset:
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

        def _row(spec):
            return {
                "spec": spec,
                "enabled": spec.key not in (tenant.disabled_modules or []),
                "recommended": tenant.business_type in spec.recommended_for,
                "suited_label": registry.suited_label(spec),
            }

        optional = registry.optional_modules()
        # Гибрид: подходящие типу — сверху, остальные — «Weitere Bausteine».
        context["module_rows"] = [
            _row(spec) for spec in optional if registry.is_suited_for(spec, tenant.business_type)
        ]
        context["other_module_rows"] = [
            _row(spec)
            for spec in optional
            if not registry.is_suited_for(spec, tenant.business_type)
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
    """Конструктор витрины v1 (Track C2): секции главной + тексты hero/about.

    Сверху — галерея шаблонов (ранний срез M20, apps.tenants.sitetemplates):
    выбор готовой раскладки в один клик поверх того же секционного движка.
    """
    from apps.tenants import demo, siteconfig, sitetemplates

    if request.method == "POST":
        # Применение шаблона витрины (галерея).
        if request.POST.get("action") == "apply_template":
            if sitetemplates.apply_template(request.tenant, request.POST.get("template", "")):
                messages.success(request, "Vorlage übernommen.")
            else:
                messages.error(request, "Unbekannte Vorlage.")
            return redirect("site")
        # Демо-контент (M20): отдельные кнопки загрузки/удаления.
        if request.POST.get("action") == "load_demo":
            if demo.load_demo(request.tenant):
                messages.success(request, "Demo-Inhalte geladen.")
            else:
                messages.info(request, "Demo-Inhalte sind bereits vorhanden.")
            return redirect("site")
        if request.POST.get("action") == "clear_demo":
            if demo.clear_demo(request.tenant):
                messages.success(request, "Demo-Inhalte gelöscht.")
            else:
                messages.info(request, "Keine Demo-Inhalte vorhanden.")
            return redirect("site")
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
        config["hero_style"] = "accent" if request.POST.get("hero_accent") == "on" else "plain"
        # Навигация витрины (M20 ④): стиль + sticky + пункты (порядок числом).
        nav_rows = []
        for key, _label, _url, _module in siteconfig.NAV_ITEMS:
            try:
                order = int(request.POST.get(f"nav_order_{key}", "0"))
            except (TypeError, ValueError):
                order = 0
            nav_rows.append((order, key, request.POST.get(f"nav_enabled_{key}") == "on"))
        nav_rows.sort(key=lambda row: row[0])
        config["nav"] = {
            "style": request.POST.get("nav_style", "classic"),
            "sticky": request.POST.get("nav_sticky") == "on",
            "items": [{"key": key, "enabled": on} for _o, key, on in nav_rows],
        }
        # Контент-секции (M20 ⑤a): CTA / отзывы / FAQ.
        config["cta"] = {
            "title": request.POST.get("cta_title", ""),
            "text": request.POST.get("cta_text", ""),
            "button_label": request.POST.get("cta_button_label", ""),
            "button_url": request.POST.get("cta_button_url", ""),
        }
        config["faq"] = siteconfig.text_to_pairs(request.POST.get("faq_text", ""), "q", "a")
        config["testimonials"] = siteconfig.text_to_pairs(
            request.POST.get("testimonials_text", ""), "name", "text"
        )
        # Не затираем состояние Onboarding-Wizard (D0c) и реестр демо — тот же JSON.
        previous = (
            request.tenant.site_config if isinstance(request.tenant.site_config, dict) else {}
        )
        if isinstance(previous.get("onboarding"), dict):
            config["onboarding"] = previous["onboarding"]
        if isinstance(previous.get("demo"), dict):
            config["demo"] = previous["demo"]
        request.tenant.site_config = siteconfig.normalize(config)
        update_fields = ["site_config", "updated_at"]
        # Акцентный цвет (#rrggbb) → Tenant.primary_color (читает витрина для hero).
        accent = request.POST.get("accent_color", "").strip()
        if re.fullmatch(r"#[0-9a-fA-F]{6}", accent) and accent != request.tenant.primary_color:
            request.tenant.primary_color = accent
            update_fields.insert(1, "primary_color")
        request.tenant.save(update_fields=update_fields)
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
    business_type = request.tenant.business_type
    site_templates = [
        {
            "key": t["key"],
            "label": t["label"],
            "description": t["description_de"],
            "recommended": business_type in t["recommended_for"],
            # для мини-превью раскладки: ключ (стиль) + человеческая подпись
            "sections": [{"key": s, "label": labels[s]} for s in t["sections"]],
            "accent": t.get("accent", ""),
            "hero_style": t.get("hero_style", "plain"),
        }
        for t in sitetemplates.templates_for(business_type)
    ]
    # Навигация витрины (M20 ④): пункты в порядке владельца + метки/гейтинг.
    nav_labels = {key: label for key, label, _u, _m in siteconfig.NAV_ITEMS}
    nav_modules_map = {key: mod for key, _l, _u, mod in siteconfig.NAV_ITEMS}
    nav_items = [
        {
            "key": item["key"],
            "label": nav_labels[item["key"]],
            "enabled": item["enabled"],
            "order": index,
            "module": nav_modules_map[item["key"]] or "",
        }
        for index, item in enumerate(config["nav"]["items"], start=1)
    ]
    return render(
        request,
        "tenant/site.html",
        {
            "nav": "site",
            "sections": sections,
            "config": config,
            "site_templates": site_templates,
            "nav_items": nav_items,
            "nav_style": config["nav"]["style"],
            "nav_sticky": config["nav"]["sticky"],
            "nav_styles": siteconfig.NAV_STYLES,
            "faq_text": siteconfig.pairs_to_text(config["faq"], "q", "a"),
            "testimonials_text": siteconfig.pairs_to_text(config["testimonials"], "name", "text"),
            "has_demo": demo.has_demo(request.tenant),
        },
    )


@login_required
def modules_view(request):
    """Страница «Module» (Track D / D0b): тумблеры опциональных блоков кабинета.

    Core-модули показаны задизейбленными; запись — в Tenant.disabled_modules
    (храним выключенное). Read-only при gated-подписке обеспечивает
    SubscriptionGatingMiddleware (путь под /dashboard/).
    """
    from apps.core import modules as registry

    tenant = request.tenant
    optional = registry.optional_modules()
    if request.method == "POST":
        enabled_keys = set(request.POST.getlist("modules"))
        previously_disabled = set(tenant.disabled_modules or [])
        tenant.disabled_modules = [spec.key for spec in optional if spec.key not in enabled_keys]
        tenant.save(update_fields=["disabled_modules", "updated_at"])
        # Гибрид: включение неподходящего вертикали блока — с предупреждением
        # (осознанный выбор, не запрет).
        odd = [
            spec.label_de
            for spec in optional
            if spec.key in enabled_keys
            and spec.key in previously_disabled
            and not registry.is_suited_for(spec, tenant.business_type)
        ]
        if odd:
            messages.warning(
                request,
                _("Note: %(modules)s is untypical for your business type — enabled anyway.")
                % {"modules": ", ".join(odd)},
            )
        messages.success(request, "Gespeichert.")
        return redirect("modules")

    dep_labels = {spec.key: spec.label_de for spec in registry.REGISTRY}

    def _row(spec):
        return {
            "spec": spec,
            "active": registry.is_module_active(tenant, spec.key),
            "enabled": spec.core or spec.key not in (tenant.disabled_modules or []),
            "depends_on": [dep_labels[dep] for dep in spec.depends_on],
            "recommended": tenant.business_type in spec.recommended_for,
            "suited_label": registry.suited_label(spec),
        }

    # Гибрид: подходящие вертикали (и универсальные) — сверху, остальные — в
    # секции «Weitere Bausteine» с пометкой, для кого они.
    suited = [
        _row(spec)
        for spec in registry.REGISTRY
        if spec.core or registry.is_suited_for(spec, tenant.business_type)
    ]
    other = [
        _row(spec)
        for spec in registry.REGISTRY
        if not spec.core and not registry.is_suited_for(spec, tenant.business_type)
    ]
    return render(
        request,
        "tenant/modules.html",
        {"nav": "modules", "rows": suited, "other_rows": other},
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
