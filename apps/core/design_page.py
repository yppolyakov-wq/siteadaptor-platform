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
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import gettext as _

from apps.catalog.option_styles import VARIANT_STYLES
from apps.core import media_places
from apps.orders.wishlist import enabled as wishlist_enabled
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


def _studio_back_url(request, source=None) -> str:
    """STU-12a (1B): возврат из «Design des Shops» — ТОЛЬКО в Студию.

    Чужой путь кабинета, схема, `//host` или бэкслэш (WHATWG нормализует его в
    слэш — класс T-6) → ссылки нет вовсе, а не «куда-нибудь».
    """
    from django.utils.http import url_has_allowed_host_and_scheme

    nxt = (request.GET if source is None else source).get("next", "") or ""
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
        sd["media_places"] = media_places.from_post(post)  # FB-21
        sd["variant_style"] = post.get("sd_variant_style", "")
        sd["card_slider"] = post.get("sd_card_slider") == "on"
    if post.get("sd_page_width_present") == "1":  # FLT-3a: ширина витрины
        sd["page_width"] = post.get("sd_page_width", "")
    if post.get("sd_logo_size_present") == "1":  # M21.5: размер логотипа в шапке
        sd["logo_size"] = post.get("sd_logo_size", "")
    if post.get("sd_page_bg_present") == "1":  # свой сентинел (как в билдере)
        sd["page_bg"] = post.get("sd_page_bg", "") if post.get("sd_page_bg_on") == "on" else ""
    cfg["site_defaults"] = sd

    if post.get("quick_add_present") == "1":
        cfg["quick_add"] = post.get("quick_add") == "on"
    if post.get("wishlist_present") == "1":
        # Галочка показывает действующее состояние (умолчание зависит от типа бизнеса).
        # Пишем, только когда оно меняется: нетронутая форма не закрепляет умолчание (W0).
        wanted = post.get("wishlist") == "on"
        if wanted != wishlist_enabled(tenant):
            cfg["wishlist"] = wanted

    accent = (post.get("accent") or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", accent) and accent != tenant.primary_color:
        tenant.primary_color = accent
        update_fields.insert(1, "primary_color")

    tenant.site_config = siteconfig.normalize(cfg)
    tenant.save(update_fields=update_fields)


def _choices(current, options, default_label=None) -> list[tuple[str, str, bool]]:
    """Пункты списка (значение, подпись, выбран). Значение пишется без локали («1.6», не
    «1,6»), а сохранённое значение, которого нет среди пунктов (шрифт или жирность из
    готового дизайна), остаётся отдельным выбранным пунктом — иначе «Speichern» без правок
    молча сменило бы его (W0)."""
    current = "" if current in (None, "", 0, 0.0) else str(current)
    out = [("0", str(default_label), not current)] if default_label is not None else []
    seen = False
    for value, label in options:
        value = str(value)
        picked = bool(current) and (value == current or _same_number(value, current))
        seen = seen or picked
        out.append((value, str(label), picked))
    if current and not seen:
        out.append((current, current, True))
    return out


def _same_number(a: str, b: str) -> bool:
    try:
        return float(a) == float(b)
    except ValueError:
        return False


# FB-27 D-a (макет D1): вкладки экрана; первая открыта по умолчанию.
DESIGN_TABS = ("fertig", "farben", "karten")


def _tabs() -> list[dict]:
    labels = (_("Fertige Designs"), _("Farben & Schrift"), _("Karten & Fotos"))
    return [{"key": k, "label": lab} for k, lab in zip(DESIGN_TABS, labels, strict=True)]


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
            # Возврат на вкладку формы — только из своего списка, не из запроса.
            tab = request.POST.get("tab", "")
            query = {"tab": tab} if tab in DESIGN_TABS else {}
            # Путь возврата в Студию переживает сохранение (проверенный, не из запроса как есть).
            back = _studio_back_url(request, request.POST)
            if back:
                query["next"] = back
            return redirect(f"{reverse('design')}?{urlencode(query)}" if query else "design")
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
    back_url = _studio_back_url(request)
    tab = request.GET.get("tab", "")
    if tab not in DESIGN_TABS:
        tab = DESIGN_TABS[0]
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
            "font_options": _choices(cfg.get("font", "") or "system", FONT_OPTIONS),
            "typo_weight_head": (cfg.get("typography") or {}).get("weight_head", ""),
            "typo_line_height": (cfg.get("typography") or {}).get("line_height", ""),
            "typo_weight_options": _choices(
                (cfg.get("typography") or {}).get("weight_head"),
                [(w, w) for w in (600, 700, 800)],
                _("Default"),
            ),
            "typo_line_height_options": _choices(
                (cfg.get("typography") or {}).get("line_height"),
                [(v, v) for v in ("1.4", "1.5", "1.6", "1.8", "2.0")],
                _("Default"),
            ),
            "theme": cfg.get("theme", ""),
            "sd": sd,
            "quick_add": cfg.get("quick_add", False),
            # FB-27: дефолт Merkzettel зависит от типа бизнеса — показываем фактическое
            # состояние, иначе «Save» молча выключал его у магазинов.
            "wishlist": wishlist_enabled(tenant),
            "variant_style_options": VARIANT_STYLES,
            "media_place_rows": media_places.rows(sd.get("media_places")),
            "media_ratio_options": media_places.RATIO_LABELS.items(),
            "media_fit_options": media_places.FITS.items(),
            "site_templates": sitetemplates.template_cards(tenant.business_type),
            "has_demo": demo.has_demo(tenant),
            # DL-13: подпись композиции на карточке (чем шаблон отличается по
            # структуре страницы — анализ DL-12, фидбэк «опять всё Fokus»).
            "bundles": [
                {**b, "composition_label": sitetemplates.composition_label(b)}
                for b in sitetemplates.bundles_for(tenant.business_type, tenant)
            ],
            "looks": sitetemplates.looks_for(tenant.business_type),
            "current_bundle": current.get("bundle", ""),
            "current_look": current.get("look", ""),
            "back_url": back_url,
            "next_q": f"&{urlencode({'next': back_url})}" if back_url else "",
            "tab": tab,
            "tabs": _tabs(),
        },
    )
