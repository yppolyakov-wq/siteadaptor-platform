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
def extras_view(request):
    """#7: универсальные доп-услуги (Extra) — CRUD на одной странице.

    Один движок на все архетипы (stays/booking/events); scope ограничивает
    применимость. Сейчас на витрине подключены stays."""
    from apps.core.models import Extra

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "add":
            label = request.POST.get("label", "").strip()[:120]
            if label:
                try:
                    cents = max(
                        0, round(float(request.POST.get("price", "0").replace(",", ".")) * 100)
                    )
                except (TypeError, ValueError):
                    cents = 0
                Extra.objects.create(
                    label=label,
                    price_cents=cents,
                    scope=request.POST.get("scope", Extra.SCOPE_ALL),
                    per_night=bool(request.POST.get("per_night")),
                )
                messages.success(request, _("Extra added."))
        elif action == "toggle":
            extra = get_object_or_404(Extra, pk=request.POST.get("extra"))
            extra.is_active = not extra.is_active
            extra.save(update_fields=["is_active", "updated_at"])
        elif action == "delete":
            Extra.objects.filter(pk=request.POST.get("extra")).delete()
            messages.success(request, _("Extra removed."))
        return redirect("extras")

    return render(
        request,
        "tenant/extras.html",
        {
            "nav": "extras",
            "extras": Extra.objects.all(),
            "scopes": Extra.SCOPES,
        },
    )


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


def _parse_opening_hours(request) -> dict:
    """Структурные часы из формы (P1b): по дню оба поля заполнены → интервал."""
    out = {}
    for wd in range(7):
        o = (request.POST.get(f"oh_{wd}_open") or "").strip()
        c = (request.POST.get(f"oh_{wd}_close") or "").strip()
        if o and c:
            out[str(wd)] = [o, c]
    from apps.tenants import openinghours

    return openinghours.normalize(out)  # валидация (open<close, формат)


def _opening_hours_rows(tenant) -> list:
    """7 строк для редактора часов: (индекс, DE-метка, open, close)."""
    from apps.tenants import openinghours

    hours = openinghours.normalize(tenant.opening_hours_structured)
    rows = []
    for wd in range(7):
        rng = hours.get(str(wd)) or ["", ""]
        rows.append(
            {"wd": wd, "label": openinghours.WEEKDAYS_DE[wd], "open": rng[0], "close": rng[1]}
        )
    return rows


@login_required
def settings_view(request):
    """Настройки бизнеса: контакты, часы работы (структурно) и правовые тексты."""
    form = BusinessSettingsForm(request.POST or None, instance=request.tenant)
    if request.method == "POST" and form.is_valid():
        tenant = form.save(commit=False)
        tenant.opening_hours_structured = _parse_opening_hours(request)
        tenant.save()
        messages.success(request, "Gespeichert.")
        return redirect("settings")
    return render(
        request,
        "tenant/settings.html",
        {
            "form": form,
            "nav": "settings",
            "opening_hours_rows": _opening_hours_rows(request.tenant),
        },
    )


def _upload_gallery_images(request) -> None:
    """Сохранить загруженные фото в site_config['gallery'] (M20 ⑤b).

    Переиспользуем catalog.images.save_product_image (валидация Pillow + storage);
    галерея — FileRef-список в site_config, как Product.images.
    """
    from django.core.exceptions import ValidationError

    from apps.catalog.images import save_product_image
    from apps.tenants import siteconfig

    files = request.FILES.getlist("images")
    if not files:
        return
    cfg = siteconfig.normalize(request.tenant.site_config)
    gallery = list(cfg.get("gallery") or [])
    for f in files:
        if len(gallery) >= siteconfig._MAX_GALLERY:
            messages.info(request, "Galerie-Limit erreicht.")
            break
        try:
            gallery.append(save_product_image(f, sort_order=len(gallery), folder="gallery"))
        except ValidationError as exc:
            messages.error(request, f"{f.name}: {'; '.join(exc.messages)}")
    cfg["gallery"] = gallery
    request.tenant.site_config = siteconfig.normalize(cfg)
    request.tenant.save(update_fields=["site_config", "updated_at"])
    messages.success(request, "Bilder hochgeladen.")


def _delete_gallery_image(request, image_id: str) -> None:
    """Удалить одно фото галереи (из storage + site_config)."""
    from apps.catalog.images import delete_stored_image
    from apps.tenants import siteconfig

    cfg = siteconfig.normalize(request.tenant.site_config)
    gallery, removed = [], None
    for ref in cfg.get("gallery") or []:
        if ref.get("id") == image_id:
            removed = ref
        else:
            gallery.append(ref)
    if removed is not None:
        delete_stored_image(removed)
        cfg["gallery"] = gallery
        request.tenant.site_config = siteconfig.normalize(cfg)
        request.tenant.save(update_fields=["site_config", "updated_at"])
        messages.success(request, "Bild gelöscht.")


@login_required
def site_view(request):
    """Конструктор витрины v1 (Track C2): секции главной + тексты hero/about.

    Сверху — галерея шаблонов (ранний срез M20, apps.tenants.sitetemplates):
    выбор готовой раскладки в один клик поверх того же секционного движка.
    """
    from apps.tenants import demo, siteconfig, sitetemplates, storefront

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
        # Галерея (M20 ⑤b): загрузка/удаление фото (multipart, отдельно от save).
        if request.POST.get("action") == "upload_gallery":
            _upload_gallery_images(request)
            return redirect("site")
        if request.POST.get("action") == "delete_gallery_image":
            _delete_gallery_image(request, request.POST.get("image_id", ""))
            return redirect("site")
        # S2b: композиция главной (порядок/видимость секций + тизеры архетипов)
        # живёт на отдельной странице «Startseite» (home_builder_view). Здесь —
        # дизайн/контент/навигация; секции и оверрайды тизеров переносим как есть.
        current = siteconfig.normalize(request.tenant.site_config)
        config = {"sections": current["sections"], "archetypes": current["archetypes"]}
        for field in siteconfig.TEXT_FIELDS:
            config[field] = request.POST.get(field, "")
        config["hero_style"] = "accent" if request.POST.get("hero_accent") == "on" else "plain"
        config["hero_image"] = request.POST.get("hero_image", "").strip()
        config["font"] = request.POST.get("font", "system")  # P2a: шрифт витрины
        # S7b: навигация витрины правится в билдере меню (/dashboard/site/menu/).
        # Легаси-nav здесь только переносим (из него выводится menus для тенантов,
        # ещё не трогавших билдер) — пустая форма «Site» не должна его гасить.
        config["nav"] = current["nav"]
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
        # P4: «как мы работаем» (title|text) и команда (name|role); фото — позже/демо.
        config["process"] = siteconfig.text_to_pairs(
            request.POST.get("process_text", ""), "title", "text"
        )
        config["team"] = [
            {"name": p["name"], "role": p["text"], "photo": ""}
            for p in siteconfig.text_to_pairs(request.POST.get("team_text", ""), "name", "text")
        ]
        # Знаки доверия (P3): год + метки построчно.
        config["trust"] = {
            "since": request.POST.get("trust_since", "").strip(),
            "marks": [
                m.strip()
                for m in (request.POST.get("trust_marks", "") or "").splitlines()
                if m.strip()
            ],
        }
        # T1: видео в галерее — один URL (YouTube/Vimeo/файл).
        config["gallery_video"] = request.POST.get("gallery_video", "").strip()
        # T2c: быстрый заказ («+»/модалка) на карточках — тумблер владельца.
        config["quick_add"] = request.POST.get("quick_add") == "on"
        # Не затираем состояние Onboarding-Wizard (D0c) и реестр демо — тот же JSON.
        previous = (
            request.tenant.site_config if isinstance(request.tenant.site_config, dict) else {}
        )
        if isinstance(previous.get("onboarding"), dict):
            config["onboarding"] = previous["onboarding"]
        if isinstance(previous.get("demo"), dict):
            config["demo"] = previous["demo"]
        if isinstance(previous.get("gallery"), list):
            config["gallery"] = previous["gallery"]  # фото грузятся отдельной формой
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
            # S2: тизер-архетипы для блока «Unsere Bereiche» (заголовок/описание/видимость).
            "archetype_specs": storefront.teaser_specs(request.tenant),
            "nav_items": nav_items,
            "nav_style": config["nav"]["style"],
            "nav_sticky": config["nav"]["sticky"],
            "nav_styles": siteconfig.NAV_STYLES,
            "font_choices": list(siteconfig.FONTS),
            "faq_text": siteconfig.pairs_to_text(config["faq"], "q", "a"),
            "testimonials_text": siteconfig.pairs_to_text(config["testimonials"], "name", "text"),
            "trust_marks_text": "\n".join(config["trust"]["marks"]),
            "process_text": siteconfig.pairs_to_text(config["process"], "title", "text"),
            "team_text": "\n".join(
                f"{m['name']} | {m['role']}".rstrip(" |") for m in config["team"]
            ),
            "has_demo": demo.has_demo(request.tenant),
        },
    )


@login_required
def home_builder_view(request):
    """Конструктор главной (S2b): порядок/видимость блоков главной + тизеры
    архетипов. Отдельная страница — «подключать/выключать выведение блоков».

    Контент блоков (тексты hero/about, FAQ, галерея, цвета, шрифты, навигация)
    правится на «Site»; здесь — только композиция главной. Сохранение мёржит в
    текущий site_config (остальные настройки не затрагиваются).
    """
    from apps.tenants import siteconfig, storefront

    if request.method == "POST":
        config = siteconfig.normalize(request.tenant.site_config)
        rows = []
        for key, _label, _default in siteconfig.SECTIONS:
            # Не присланный порядок (новая секция) → в конец, не в начало.
            try:
                order = int(request.POST.get(f"order_{key}", "999"))
            except (TypeError, ValueError):
                order = 999
            rows.append((order, key, request.POST.get(f"enabled_{key}") == "on"))
        rows.sort(key=lambda row: row[0])
        config["sections"] = [{"key": key, "enabled": on} for _o, key, on in rows]
        # Пер-архетипные оверрайды тизеров (заголовок/описание/видимость).
        arch = dict(config.get("archetypes") or {})
        for spec in storefront.teaser_specs(request.tenant):
            key = spec["key"]
            arch[key] = {
                "label": request.POST.get(f"arch_label_{key}", "").strip(),
                "blurb": request.POST.get(f"arch_blurb_{key}", "").strip(),
                "hidden": request.POST.get(f"arch_visible_{key}") != "on",
            }
        config["archetypes"] = arch
        # S4: стартовая страница витрины (общая главная или один архетип).
        config["storefront_root"] = request.POST.get("storefront_root", "home").strip() or "home"
        request.tenant.site_config = siteconfig.normalize(config)
        request.tenant.save(update_fields=["site_config", "updated_at"])
        messages.success(request, "Gespeichert.")
        return redirect("site-home")

    from apps.core import modules

    config = siteconfig.normalize(request.tenant.site_config)
    labels = {key: label for key, label, _default in siteconfig.SECTIONS}
    root_options = [{"key": "home", "label": _("Combined homepage")}] + [
        {"key": a.key, "label": a.label} for a in modules.storefront_archetypes(request.tenant)
    ]
    sections = [
        {"key": s["key"], "label": labels[s["key"]], "enabled": s["enabled"], "order": index}
        for index, s in enumerate(config["sections"], start=1)
    ]
    archetypes_enabled = any(s["key"] == "archetypes" and s["enabled"] for s in config["sections"])
    return render(
        request,
        "tenant/site_home.html",
        {
            "nav": "site",
            "sections": sections,
            "archetype_specs": storefront.teaser_specs(request.tenant),
            "archetypes_enabled": archetypes_enabled,
            "root_options": root_options,
            "storefront_root": config.get("storefront_root", "home"),
        },
    )


def _cover_archetype_keys(tenant) -> set:
    from apps.tenants import storefront

    return {s["key"] for s in storefront.cover_specs(tenant)}


def _upload_cover_gallery(request, key: str) -> None:
    """S3b: загрузить фото в галерею раздела key (site_config['archetypes'][key])."""
    from django.core.exceptions import ValidationError

    from apps.catalog.images import save_product_image
    from apps.tenants import siteconfig

    if key not in _cover_archetype_keys(request.tenant):
        return
    files = request.FILES.getlist("images")
    if not files:
        return
    cfg = siteconfig.normalize(request.tenant.site_config)
    arch = dict(cfg.get("archetypes") or {})
    cur = dict(arch.get(key) or {})
    gallery = list(cur.get("gallery") or [])
    for f in files:
        if len(gallery) >= siteconfig._MAX_COVER_GALLERY:
            messages.info(request, "Galerie-Limit erreicht.")
            break
        try:
            gallery.append(save_product_image(f, sort_order=len(gallery), folder="cover"))
        except ValidationError as exc:
            messages.error(request, f"{f.name}: {'; '.join(exc.messages)}")
    cur["gallery"] = gallery
    arch[key] = cur
    cfg["archetypes"] = arch
    request.tenant.site_config = siteconfig.normalize(cfg)
    request.tenant.save(update_fields=["site_config", "updated_at"])
    messages.success(request, "Bilder hochgeladen.")


def _delete_cover_image(request, key: str, image_id: str) -> None:
    from apps.catalog.images import delete_stored_image
    from apps.tenants import siteconfig

    cfg = siteconfig.normalize(request.tenant.site_config)
    arch = dict(cfg.get("archetypes") or {})
    cur = dict(arch.get(key) or {})
    gallery, removed = [], None
    for ref in cur.get("gallery") or []:
        if ref.get("id") == image_id:
            removed = ref
        else:
            gallery.append(ref)
    if removed is not None:
        delete_stored_image(removed)
        cur["gallery"] = gallery
        arch[key] = cur
        cfg["archetypes"] = arch
        request.tenant.site_config = siteconfig.normalize(cfg)
        request.tenant.save(update_fields=["site_config", "updated_at"])
        messages.success(request, "Bild gelöscht.")


@login_required
def site_preview(request):
    """Live-предпросмотр витрины (Z): актуальный сайт в iframe + переключатель
    ширины (Desktop/Tablet/Mobile)."""
    return render(request, "tenant/site_preview.html", {"nav": "site"})


@login_required
@require_POST
def site_preview_draft(request):
    """V1 live-preview: принять черновик композиции главной (sections +
    оверрайды тизеров) из конструктора, смёржить в текущий site_config и
    положить в сессию. Витрина `/?preview=1` рендерит этот черновик — без записи
    в БД. Возврат 204."""
    import json

    from django.http import HttpResponse

    from apps.tenants import siteconfig

    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        data = {}
    cfg = siteconfig.normalize(request.tenant.site_config)
    if isinstance(data.get("sections"), list):
        known = {k for k, _l, _d in siteconfig.SECTIONS}
        seen, rows = set(), []
        for item in data["sections"]:
            key = item.get("key") if isinstance(item, dict) else None
            if key in known and key not in seen:
                rows.append({"key": key, "enabled": bool(item.get("enabled"))})
                seen.add(key)
        if rows:
            cfg["sections"] = rows
    if isinstance(data.get("archetypes"), dict):
        arch = dict(cfg.get("archetypes") or {})
        for key, ov in data["archetypes"].items():
            if isinstance(ov, dict):
                cur = dict(arch.get(key) or {})
                cur["label"] = str(ov.get("label", "")).strip()
                cur["blurb"] = str(ov.get("blurb", "")).strip()
                cur["hidden"] = bool(ov.get("hidden"))
                arch[key] = cur
        cfg["archetypes"] = arch
    request.session["site_preview_draft"] = siteconfig.normalize(cfg)
    return HttpResponse(status=204)


@login_required
@require_POST
def site_inline_edit(request):
    """V3 inline-edit: сохранить одно текстовое поле, отредактированное прямо на
    превью (contenteditable). Белый список полей — тексты hero/about; запись в
    site_config. Возврат 204."""
    import json

    from django.http import HttpResponse, HttpResponseBadRequest

    from apps.tenants import siteconfig

    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        return HttpResponseBadRequest()
    field = data.get("field")
    if field not in siteconfig.TEXT_FIELDS:
        return HttpResponseBadRequest()
    value = data.get("value", "")
    cfg = siteconfig.normalize(request.tenant.site_config)
    cfg[field] = value.strip() if isinstance(value, str) else ""
    request.tenant.site_config = siteconfig.normalize(cfg)
    request.tenant.save(update_fields=["site_config", "updated_at"])
    return HttpResponse(status=204)


@login_required
def sections_view(request):
    """Обложки разделов (S3): интро-текст + hero-фото на каждый лендинг архетипа.
    Рендерятся поверх его публичной страницы (storefront/_archetype_cover.html).
    Сохранение мёржит в site_config, сохраняя оверрайды тизеров (label/blurb)."""
    from apps.tenants import siteconfig, storefront

    if request.method == "POST":
        # S3b: загрузка/удаление фото галереи раздела (multipart, отдельно).
        action = request.POST.get("action")
        if action == "upload_cover_gallery":
            _upload_cover_gallery(request, request.POST.get("archetype", ""))
            return redirect("site-sections")
        if action == "delete_cover_image":
            _delete_cover_image(
                request, request.POST.get("archetype", ""), request.POST.get("image_id", "")
            )
            return redirect("site-sections")
        config = siteconfig.normalize(request.tenant.site_config)
        arch = dict(config.get("archetypes") or {})
        for spec in storefront.cover_specs(request.tenant):
            key = spec["key"]
            cur = dict(arch.get(key) or {})
            cur["intro"] = request.POST.get(f"intro_{key}", "").strip()
            cur["hero_image"] = request.POST.get(f"hero_{key}", "").strip()
            arch[key] = cur
        config["archetypes"] = arch
        request.tenant.site_config = siteconfig.normalize(config)
        request.tenant.save(update_fields=["site_config", "updated_at"])
        messages.success(request, "Gespeichert.")
        return redirect("site-sections")

    return render(
        request,
        "tenant/site_sections.html",
        {"nav": "site", "cover_specs": storefront.cover_specs(request.tenant)},
    )


@login_required
def menu_builder_view(request):
    """Билдер меню витрины (S7b): дерево пунктов top + bottom, привязка к
    архетипам/категориям/страницам/URL/якорям, вложенность 2 уровня.

    Редактор — на клиенте (ванильный JS): модель сериализуется в скрытый JSON,
    сервер санитайзит через siteconfig.normalize (источник правды по схеме).
    Сохранение мёржит в текущий site_config, прочие настройки не затрагивая.
    """
    import json

    from apps.core import modules
    from apps.tenants import siteconfig

    if request.method == "POST":
        try:
            data = json.loads(request.POST.get("menus_json", "") or "{}")
        except (ValueError, TypeError):
            data = None
        config = siteconfig.normalize(request.tenant.site_config)
        # Битый/пустой payload не трогает меню (не затираем при сбое редактора);
        # валидное дерево (есть top/bottom) — пишем, normalize санитайзит.
        if isinstance(data, dict) and ("top" in data or "bottom" in data):
            config["menus"] = data
        request.tenant.site_config = siteconfig.normalize(config)
        request.tenant.save(update_fields=["site_config", "updated_at"])
        messages.success(request, "Gespeichert.")
        return redirect("site-menu")

    tenant = request.tenant
    menus = siteconfig.normalize(tenant.site_config)["menus"]
    # Доступные цели для выпадашек редактора.
    archetype_targets = [
        {"value": s.key, "label": s.storefront_label or s.label_de}
        for s in modules.active_modules(tenant)
        if s.storefront_landing
    ]
    category_targets = []
    if modules.is_module_active(tenant, "catalog"):
        from apps.catalog.models import Category

        category_targets = [
            {"value": c.slug, "label": c.name}
            for c in Category.objects.filter(is_active=True).order_by("name")
        ]
    page_targets = [
        {"value": "home", "label": "Startseite"},
        {"value": "about", "label": "Über uns"},
    ]
    promo_group_targets = []
    if modules.is_module_active(tenant, "promotions"):
        from apps.promotions.models import Promotion

        groups = (
            Promotion.objects.filter(status="active")
            .exclude(group="")
            .values_list("group", flat=True)
            .distinct()
        )
        promo_group_targets = [{"value": g, "label": g} for g in sorted(set(groups))]
    builder = {
        "menus": menus,
        "types": list(siteconfig.MENU_NODE_TYPES),
        "archetypes": archetype_targets,
        "categories": category_targets,
        "pages": page_targets,
        "promo_groups": promo_group_targets,
        "styles": list(siteconfig.NAV_STYLES),
    }
    return render(request, "tenant/site_menu.html", {"nav": "site", "builder": builder})


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
