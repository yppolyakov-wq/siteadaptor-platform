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

from apps.catalog.option_styles import VARIANT_STYLES
from apps.tenants import sitetemplates

STUDIO_PREFIX = "/dashboard/site/home/"

# STU-12g: тот же перечень гарнитур, что был в Студии (реестр siteconfig.FONTS).
# Без записей в селекте пересохранение типографики сбрасывало Look на system.
FONT_OPTIONS = [
    ("system", _("System")),
    ("serif", _("Serif")),
    ("rounded", _("Rounded")),
    ("editorial", _("Playfair Display")),
    ("organic", _("Nunito")),
    ("condensed", _("Barlow Condensed")),
    ("bricolage", _("Bricolage Grotesque")),
    ("space", _("Space Grotesk")),
    ("schibsted", _("Schibsted Grotesk")),
]


def _studio_back_url(request) -> str:
    """STU-12a (1B): возврат из «Design des Shops» — ТОЛЬКО в Студию.

    Чужой путь кабинета, схема, `//host` или бэкслэш (WHATWG нормализует его в
    слэш — класс T-6) → ссылки нет вовсе, а не «куда-нибудь».
    """
    from django.utils.http import url_has_allowed_host_and_scheme

    nxt = request.GET.get("next", "") or ""
    if not nxt.startswith(STUDIO_PREFIX) or "\\" in nxt or nxt.startswith("//"):
        return ""
    if not url_has_allowed_host_and_scheme(
        nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return ""
    return nxt


# STU-12g (1B): глобальный дизайн — настройка САЙТА, а не канвы. Пишем targeted-write
# (прецедент W9-3): полная копия конфига + только свои ключи, чужие (sections/board/
# seo/page_blocks/menus) не трогаем. Форма карточки (`sd_card_style`) сюда НЕ переезжает —
# она в реестре studio_pages с охватом «для всех / только здесь».
def _save_design_settings(request) -> None:
    import re

    from apps.tenants import siteconfig

    tenant = request.tenant
    post = request.POST
    cfg = siteconfig.normalize(tenant.site_config)
    update_fields = ["site_config", "updated_at"]

    if "font" in post:
        cfg["font"] = post.get("font", "")
    typo = dict(cfg.get("typography") or {})
    if "typo_weight_head" in post:
        typo["weight_head"] = post.get("typo_weight_head", "")
    if "typo_line_height" in post:
        typo["line_height"] = post.get("typo_line_height", "")
    cfg["typography"] = typo
    # Сентинел, а не `"theme" in post`: снятый чекбокс браузер не шлёт вовсе, и по
    # присутствию поля тёмную тему было бы НЕ ВЫКЛЮЧИТЬ (в Студии её гасило hidden-поле).
    if post.get("theme_present") == "1":
        if post.get("theme") == "dark":
            cfg["theme"] = "dark"
        else:
            cfg.pop("theme", None)

    sd = dict(cfg.get("site_defaults") or {})
    if post.get("sd_cards_present") == "1":  # блок «Карточки и фото» пришёл целиком
        sd["card_radius"] = post.get("sd_card_radius", "")
        sd["card_shadow"] = post.get("sd_card_shadow") == "on"
        sd["card_padding"] = post.get("sd_card_padding", "")
        sd["card_bg"] = post.get("sd_card_bg", "") if post.get("sd_card_bg_on") == "on" else ""
        sd["card_chrome"] = post.get("sd_card_chrome", "")
        sd["media_shape"] = post.get("sd_media_shape", "")
        sd["variant_style"] = post.get("sd_variant_style", "")
        sd["card_slider"] = post.get("sd_card_slider") == "on"
    if post.get("sd_page_bg_present") == "1":  # свой сентинел (как в билдере)
        sd["page_bg"] = post.get("sd_page_bg", "") if post.get("sd_page_bg_on") == "on" else ""
    cfg["site_defaults"] = sd

    if post.get("quick_add_present") == "1":
        cfg["quick_add"] = post.get("quick_add") == "on"
    if post.get("wishlist_present") == "1":
        cfg["wishlist"] = post.get("wishlist") == "on"

    accent = (post.get("accent") or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", accent) and accent != tenant.primary_color:
        tenant.primary_color = accent
        update_fields.insert(1, "primary_color")

    tenant.site_config = siteconfig.normalize(cfg)
    tenant.save(update_fields=update_fields)


@login_required
def design_view(request):
    tenant = request.tenant
    if request.method == "POST":
        from apps.tenants import demo

        action = request.POST.get("action", "")
        # STU-12g: «Start» переехал сюда со Студии — шаблоны витрины и демо-контент.
        if action == "apply_template":
            if sitetemplates.apply_template(tenant, request.POST.get("template", "")):
                messages.success(request, _("Vorlage übernommen."))
            else:
                messages.error(request, _("Unbekannte Vorlage."))
            return redirect("design")
        if action == "load_demo":
            if demo.load_demo(tenant):
                messages.success(request, _("Demo-Inhalte geladen."))
            else:
                messages.info(request, _("Demo-Inhalte sind bereits vorhanden."))
            return redirect("design")
        if action == "clear_demo":
            if demo.clear_demo(tenant):
                messages.success(request, _("Demo-Inhalte gelöscht."))
            else:
                messages.info(request, _("Keine Demo-Inhalte vorhanden."))
            return redirect("design")
        if action == "design_settings":
            _save_design_settings(request)
            messages.success(request, _("Gespeichert."))
            return redirect("design")
        bundle = request.POST.get("bundle", "")
        look = request.POST.get("look", "")
        if bundle and sitetemplates.apply_bundle(tenant, bundle):
            messages.success(request, _("Vorlage übernommen."))
        elif look and sitetemplates.apply_look(tenant, look):
            messages.success(request, _("Vorlage übernommen."))
        else:
            messages.error(request, _("Unbekannte Vorlage."))
        return redirect("design")
    from apps.tenants import demo, siteconfig

    cfg = siteconfig.normalize(tenant.site_config)
    # DL-8a: активный выбор (ключ design пишут apply_bundle/apply_look).
    current = cfg.get("design") or {}
    sd = cfg.get("site_defaults") or {}
    return render(
        request,
        "tenant/design.html",
        {
            # STU-12g: глобальный дизайн сайта — цвет/шрифт/типографика/тема/карточки.
            "accent": tenant.primary_color or "#4f46e5",
            "font": cfg.get("font", ""),
            "font_options": FONT_OPTIONS,
            "typo_weight_head": (cfg.get("typography") or {}).get("weight_head", ""),
            "typo_line_height": (cfg.get("typography") or {}).get("line_height", ""),
            "typo_weight_options": [600, 700, 800],
            "typo_line_height_options": [1.4, 1.5, 1.6, 1.8, 2.0],
            "theme": cfg.get("theme", ""),
            "sd": sd,
            "quick_add": cfg.get("quick_add", False),
            "wishlist": cfg.get("wishlist", False),
            "variant_style_options": VARIANT_STYLES,
            "site_templates": sitetemplates.template_cards(tenant.business_type),
            "has_demo": demo.has_demo(tenant),
            # DL-13: подпись композиции на карточке (чем шаблон отличается по
            # структуре страницы — анализ DL-12, фидбэк «опять всё Fokus»).
            "bundles": [
                {**b, "composition_label": sitetemplates.composition_label(b)}
                for b in sitetemplates.bundles_for(tenant.business_type)
            ],
            "looks": sitetemplates.looks_for(tenant.business_type),
            "current_bundle": current.get("bundle", ""),
            "current_look": current.get("look", ""),
            "back_url": _studio_back_url(request),
        },
    )
