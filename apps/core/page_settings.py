"""STU-19a: one service that describes, validates and writes page settings.

Plan: docs/stu19-page-templates-cabinet-ai-plan-2026-11-01.md §3.

Why. Page-level output settings (page template, grid, card form, sort, …) are
moving out of the Studio panel into a "Seitenvorlage" tab per cabinet section,
and an AI helper will propose them. All three consumers need the same answers:

* `schema(tenant, types)` — what can be set on each page type, which values are
  allowed (and which are unavailable *right now* and why), the current value and
  where it comes from. Built ONLY from the existing registries
  (`studio_pages`, `compositions`, `card_forms`, `siteconfig`): this module adds
  no second list of templates.
* `write(tenant, code, value)` — the single site-level writer. It locks the tenant
  row, validates against the same choices the schema shows and writes ONE key in
  place (targeted write, like SEO/Finder/board settings). It never rebuilds
  `site_config` from a subset of keys — that is the W0/W6 data-loss class.
* `apply_override(cfg, code, value)` — the same mutation in memory, for the
  stateless cabinet preview (`?preview=1&tpl=<code>:<value>`); nothing is stored.

Object-level overrides (one category's own template) stay with
`studio_scope.write_value` and the object forms.

Settings that are about the ORDER of blocks (`*_sections`) stay in the Studio and
are not offered here (plan §2.1).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.core import card_forms, compositions, studio_pages

#: Module a page type belongs to: the cabinet only offers types whose module is on
#: (a hotel has no "Termine" page). None = always there (text pages, home).
TYPE_MODULES: dict[str, str | None] = {
    "home": None,
    "catalog": "catalog",
    "category": "catalog",
    "product": "catalog",
    "combos": "catalog",
    "wishlist": "catalog",
    "finder": "catalog",
    "lookbook": "catalog",
    "cart": "orders",
    "promos": "promotions",
    "promo_group": "promotions",
    "promo": "promotions",
    "services": "booking",
    "service": "booking",
    "stays": "stays",
    "stay": "stays",
    "events": "events",
    "event": "events",
    "tours": "events",
    "blog": "blog",
    "blog_post": "blog",
    "reviews": "reviews",
    "loyalty": "loyalty",
    "gift": "gift",
    "anfrage": "jobs",
    "text": None,
    "team": None,
    "gallery": None,
    "contact": None,
    "legal": None,
}

#: Every page type of the registry (19d). The lock
#: `test_every_supported_setting_has_a_spec` keeps the specs complete for them.
SUPPORTED_TYPES: tuple[str, ...] = tuple(t.code for t in studio_pages.PAGE_TYPES)

KIND_CHOICE = "choice"
KIND_BOOL = "bool"
KIND_LAYOUT = "layout"


class PageSettingError(ValueError):
    """Unknown setting or a value that is not allowed for it."""


@dataclass(frozen=True)
class Choice:
    value: str
    label: object
    hint: object = ""
    available: bool = True
    reason: object = ""


@dataclass(frozen=True)
class SettingState:
    code: str
    label: object
    axis: str
    kind: str
    value: object
    is_set: bool
    choices: tuple[Choice, ...] = ()
    has_object_scope: bool = False
    #: which mini-mockup the tiles get: "card", "page" or "" (text tiles)
    thumb: str = ""


@dataclass(frozen=True)
class TypeSchema:
    code: str
    label: object
    settings: tuple[SettingState, ...] = field(default_factory=tuple)


# ───────────────────────── choices ─────────────────────────

LAYOUT_OPTIONS = (
    ("list", _("List")),
    ("cols2", _("2 per row")),
    ("cols3", _("3 per row")),
    ("cols4", _("4 per row")),
    ("cols5", _("5 per row")),
    ("cols6", _("6 per row")),
    ("gallery", _("Gallery")),
)

SORT_OPTIONS = (
    ("newest", _("Newest")),
    ("price_asc", _("Price: low to high")),
    ("price_desc", _("Price: high to low")),
)

DETAIL_LAYOUT_OPTIONS = (
    ("", _("Untereinander")),
    ("tabs", _("Tabs")),
    ("breit", _("Volle Breite")),
)

#: Bool settings and their default when the key is absent (mirrors normalize).
BOOL_DEFAULTS = {
    "catalog_filters": True,
    "catalog_subcats": True,
    "catalog_menu_prices": True,
    "catalog_menu_labels": False,
    "cart_upsell": True,
}

#: Composition settings → the surface their templates and gates belong to.
_COMPOSITION_SURFACE = {
    "catalog_page_style": "catalog",
    "category_page_style": "category",
    "promo_page_style": "promos",
    "promo_group_style": "promo_group",
    "promo_detail_style": "promo",
    **{f"{s}_page_style": s for s in compositions.LISTING_SURFACES},
}

#: Layout settings: config key of the layout dict + page-specific extra presets.
_LAYOUT_KEYS = {
    "catalog_layout": "catalog_layout",
    "product_related": "detail_related_layout",
    "service_layout": "service_index_layout",
    "stay_layout": "stay_index_layout",
    "events_layout": "events_index_layout",
    "promo_index_layout": "promo_index_layout",
    "combos_layout": "combos_layout",
    "tours_layout": "tours_layout",
    "lookbook_layout": "lookbook_layout",
    "reviews_page_layout": "reviews_page_layout",
    "wishlist_layout": "wishlist_layout",
    "blog_index_layout": "blog_index_layout",
}

#: Detail page layouts (all four detail kinds share one axis, STU-15b).
_DETAIL_LAYOUTS = frozenset(
    {"product_detail_layout", "service_detail_layout", "stay_detail_layout", "event_detail_layout"}
)

#: Listing sorts whose values come from the listing's facet provider (STU-15c).
_LISTING_SORTS = {"services_sort": "service", "stays_sort": "stay", "events_sort": "event"}

PROMO_GROUPING_OPTIONS = (("", _("Nach Gruppen")), ("time", _("Nach Zeit")))

TEXT_WIDTH_OPTIONS = (
    ("", _("Wie bisher")),
    ("narrow", _("Schmale Spalte")),
    ("wide", _("Breite Spalte")),
    ("full", _("Volle Breite")),
)

UNAVAILABLE_REASON = _("Ohne Unterkategorien oder Sets nicht verfügbar")


def is_studio_only(setting: studio_pages.Setting) -> bool:
    """Block order / visibility stays in the Studio (plan §2.1)."""
    return setting.code.endswith("_sections")


def cabinet_settings(type_code: str) -> list[studio_pages.Setting]:
    return [s for s in studio_pages.settings_for(type_code) if not is_studio_only(s)]


def applies(tenant, setting: studio_pages.Setting) -> bool:
    """Settings that only mean something for some tenants (same gates as Studio)."""
    if setting.code == "catalog_menu_prices":
        # hiding prices is allowed only on a browse-only storefront (PAngV)
        return not tenant.is_module_active("orders")
    if setting.code == "catalog_menu_labels":
        from apps.catalog.views import FOOD_BUSINESS_TYPES

        return getattr(tenant, "business_type", "") in FOOD_BUSINESS_TYPES
    return True


def _optional_layout(key: str) -> bool:
    """Layouts normalize does NOT materialise: "Standard" removes the key and the
    page draws its old classes again (LAY-3a-2)."""
    from apps.tenants import siteconfig

    return key == "service_index_layout" or key in siteconfig.OPTIONAL_PAGE_LAYOUTS


def _layout_presets(code: str) -> tuple[tuple[str, object], ...]:
    from apps.tenants import siteconfig

    key = _LAYOUT_KEYS[code]
    extra = siteconfig.PAGE_EXTRA_PRESETS.get(key, ())
    head = (("", _("Standard")),) if _optional_layout(key) else ()
    return (
        head + LAYOUT_OPTIONS + tuple((k, siteconfig.SECTION_STYLE_LABELS.get(k, k)) for k in extra)
    )


def kind_of(setting: studio_pages.Setting) -> str:
    if setting.code in BOOL_DEFAULTS:
        return KIND_BOOL
    if setting.code in _LAYOUT_KEYS:
        return KIND_LAYOUT
    return KIND_CHOICE


def choices(setting: studio_pages.Setting, gate: dict | None = None) -> tuple[Choice, ...]:
    """Allowed values with availability. Raises PageSettingError if unsupported."""
    code = setting.code
    if code in BOOL_DEFAULTS:
        return (Choice("1", _("On")), Choice("0", _("Off")))
    if code in _COMPOSITION_SURFACE:
        surface = _COMPOSITION_SURFACE[code]
        off = (gate or {}).get(surface, set())
        return tuple(
            Choice(c, label, hint, c not in off, UNAVAILABLE_REASON if c in off else "")
            for c, label, hint in compositions.styles_for(surface)
        )
    if code == "product_card_form":
        return tuple(Choice(k, label, hint) for k, label, hint in card_forms.forms_for())
    if code == "promo_card_form":
        return tuple(
            Choice(k, label, hint) for k, label, hint in card_forms.forms_for(card_forms.PROMO)
        )
    if code in _LAYOUT_KEYS:
        return tuple(Choice(k, label) for k, label in _layout_presets(code))
    if code == "catalog_sort":
        return tuple(Choice(k, label) for k, label in SORT_OPTIONS)
    if code in _LISTING_SORTS:
        from apps.core.facets import provider_for

        return tuple(
            Choice(k, label) for k, label in provider_for(_LISTING_SORTS[code]).sort_options()
        )
    if code in _DETAIL_LAYOUTS:
        return tuple(Choice(k, label) for k, label in DETAIL_LAYOUT_OPTIONS)
    if code == "home_hero":
        from apps.tenants import siteconfig

        return tuple(Choice(k, label) for k, label in siteconfig.HERO_STYLE_LABELS)
    if code == "promo_grouping":
        return tuple(Choice(k, label) for k, label in PROMO_GROUPING_OPTIONS)
    if code == "text_width":
        return tuple(Choice(k, label) for k, label in TEXT_WIDTH_OPTIONS)
    raise PageSettingError(f"no cabinet spec for setting {code!r}")


# ───────────────────────── reading ─────────────────────────


def _walk(node, path):
    for part in path:
        if not isinstance(node, dict) or part not in node:
            return None, False
        node = node[part]
    return node, True


def current_value(raw_cfg: dict, setting: studio_pages.Setting, normalized: dict | None = None):
    """(value, is_set): value as the storefront sees it; is_set — key stored.

    `normalized` — the already normalized config (a screen with 80 settings must
    not normalize 80 times)."""
    from apps.tenants import siteconfig

    _stored, is_set = _walk(raw_cfg or {}, setting.site_key)
    if normalized is None:
        normalized = siteconfig.normalize(raw_cfg or {})
    value, _found = _walk(normalized, setting.site_key)
    kind = kind_of(setting)
    if kind == KIND_BOOL:
        if value is None:
            return BOOL_DEFAULTS[setting.code], is_set
        if setting.code == "catalog_menu_prices":
            return value is not False, is_set
        return bool(value), is_set
    if kind == KIND_LAYOUT and isinstance(value, dict):
        value = value.get("preset", "")
    return ("" if value is None else str(value)), is_set


def composition_gate(config: dict | None = None) -> dict[str, set[str]]:
    """Composition codes that have nothing to show on THIS storefront.

    Moved from `core.views._composition_gate` (STU-18c) so the cabinet, the Studio
    and the AI helper read one gate; `views._composition_gate` stays as an alias.
    v1 limitation (unchanged): "has subcategories" is store-wide, not per category.
    """
    from apps.booking.models import Service
    from apps.catalog.models import Category, Combo
    from apps.events.models import Event, Tour
    from apps.promotions.models import Promotion
    from apps.stays.models import StayUnit

    def _safe(qs) -> bool:
        try:
            return qs.exists()
        except Exception:  # noqa: BLE001 — the panel must open on broken data too
            return True

    children = _safe(Category.objects.filter(parent__isnull=False))
    combos = _safe(Combo.objects.all())
    groups = _safe(Promotion.objects.exclude(group=""))
    listing_children = {
        "services": _safe(Service.objects.filter(collections__isnull=False)),
        "stays": _safe(StayUnit.objects.filter(collections__isnull=False)),
        "events": _safe(Event.objects.exclude(category="")),
        "tours": _safe(Tour.objects.exclude(country="")),
        "combos": _safe(Combo.objects.filter(category__isnull=False)),
        "lookbook": False,
        "wishlist": False,
        "blog": False,
        "reviews": False,
    }
    cfg = config or {}
    heroes = cfg.get("heroes") or []
    has_photo = bool(
        cfg.get("hero_image")
        or (isinstance(heroes, list) and heroes and (heroes[0] or {}).get("image"))
    )

    out: dict[str, set[str]] = {}
    for surface, has_children in (
        ("catalog", children),
        ("category", children),
        ("promos", groups),
        ("promo_group", groups),
        ("promo", False),
        *sorted(listing_children.items()),
    ):
        offered = {code for code, _l, _h in compositions.styles_for(surface)}
        ok = {
            code
            for code, _l, _h in compositions.available_for(
                surface,
                has_children=has_children,
                has_combos=combos,
                # only listings depend on the site photo: a category's "Kopfbild"
                # uses its own photo
                has_photo=has_photo or surface not in compositions.LISTING_SURFACES,
            )
        }
        out[surface] = offered - ok
    return out


def _thumb(setting: studio_pages.Setting) -> str:
    if setting.axis == "card":
        return "card"
    if setting.code in _COMPOSITION_SURFACE:
        return "page"
    return ""


#: Types the storefront hides under the light "Nur Aktionen" profile (urls_tenant
#: wraps their views in `redirect_if_aktionen`).
_CATALOG_PAGES = frozenset({"catalog", "category", "product", "cart", "combos", "lookbook"})


def _storefront_shows(tenant, type_code: str) -> bool:
    """The same gates the storefront views use — a type the visitor can never open
    is not offered (its preview would be a 404 or a redirect)."""
    if type_code in _CATALOG_PAGES:
        from apps.core import storefront_profile

        if storefront_profile.is_aktionen(tenant):
            return False
    if type_code == "finder":
        from apps.core import finder

        return bool(finder.enabled(tenant))
    if type_code == "wishlist":
        from apps.orders import wishlist

        return bool(wishlist.enabled(tenant))
    if type_code == "gift":
        from apps.loyalty.public_views import gift_purchase_active

        return bool(gift_purchase_active(tenant))
    return True


def type_active(tenant, type_code: str) -> bool:
    """A page type is offered only when its module is on (no "Termine" for a hotel)
    and the storefront actually shows it."""
    module = TYPE_MODULES.get(type_code)
    if module is not None and not tenant.is_module_active(module):
        return False
    try:
        return _storefront_shows(tenant, type_code)
    except Exception:  # noqa: BLE001 — a broken gate must not hide the whole screen
        return True


def active_types(tenant, types: tuple[str, ...] | None = None) -> tuple[str, ...]:
    """Types of `types` (default: all) that are live and have a cabinet setting."""
    return tuple(
        code
        for code in (types or SUPPORTED_TYPES)
        if type_active(tenant, code) and any(applies(tenant, s) for s in cabinet_settings(code))
    )


def schema(tenant, types: tuple[str, ...] | None = None) -> list[TypeSchema]:
    """Machine-readable description for the cabinet tab and the AI helper.

    Types whose module is off are skipped (a passed-in tuple is filtered too).
    """
    from apps.tenants import siteconfig

    raw = tenant.site_config or {}
    gate = composition_gate(raw)
    normalized = siteconfig.normalize(raw)
    out = []
    axis_order = {code: i for i, (code, _label) in enumerate(studio_pages.AXES)}
    for code in active_types(tenant, types):
        page = studio_pages.page_type(code)
        rows = []
        for s in cabinet_settings(code):
            if not applies(tenant, s):
                continue
            value, is_set = current_value(raw, s, normalized)
            rows.append(
                SettingState(
                    code=s.code,
                    label=s.label,
                    axis=s.axis,
                    kind=kind_of(s),
                    value=value,
                    is_set=is_set,
                    choices=choices(s, gate),
                    has_object_scope=s.has_object_scope,
                    thumb=_thumb(s),
                )
            )
        rows.sort(key=lambda r: axis_order.get(r.axis, 99))
        out.append(TypeSchema(code=page.code, label=page.label, settings=tuple(rows)))
    return out


# ───────────────────────── writing ─────────────────────────


def _clean(setting: studio_pages.Setting, value, gate: dict, current) -> object:
    kind = kind_of(setting)
    if kind == KIND_BOOL:
        if isinstance(value, bool):
            return value
        text = str(value or "").strip().lower()
        if text in ("1", "on", "true", "yes"):
            return True
        if text in ("0", "off", "false", "no"):
            return False  # an EMPTY value is not "off": a lost field must not switch it off
        raise PageSettingError(f"not a bool for {setting.code}: {value!r}")
    text = str(value or "").strip()
    allowed = {c.value: c for c in choices(setting, gate)}
    if text and text == current:
        return text  # keeping a legacy value that is no longer offered is fine
    if text not in allowed:
        raise PageSettingError(f"value {text!r} not allowed for {setting.code}")
    # an unavailable template cannot be chosen anew
    if not allowed[text].available:
        raise PageSettingError(f"value {text!r} not available for {setting.code} here")
    return text


def apply_override(cfg: dict, code: str, value) -> dict:
    """Mutate a COPY of a raw config so that `code` has `value` (no validation of
    availability — callers validate). Writes one key; everything else is kept."""
    from apps.tenants import siteconfig

    setting = studio_pages.SETTINGS.get(code)
    if setting is None or is_studio_only(setting):
        raise PageSettingError(f"unknown page setting {code!r}")
    out = dict(cfg or {})
    kind = kind_of(setting)
    if kind == KIND_LAYOUT:
        key = _LAYOUT_KEYS[code]
        if key == "promo_index_layout" and value != "":
            # choosing a grid retires the legacy ribbon switch (LAY-7c); "Standard"
            # keeps it — the legacy ribbon IS what the owner sees as standard there
            out.pop("promo_layout", None)
        if value == "" and _optional_layout(key):
            out.pop(key, None)  # "Standard": the page draws its old classes again
            return out
        layout = dict(out.get(key) or {})
        layout["preset"] = value
        extra = siteconfig.PAGE_EXTRA_PRESETS.get(key, ())
        out[key] = siteconfig.normalize_layout(
            layout, siteconfig.PAGE_LAYOUT_DEFAULTS.get(key), extra_presets=extra
        )
        return out
    path = setting.site_key
    if len(path) == 1:
        if kind == KIND_CHOICE and value == "":
            out.pop(path[0], None)  # presence-minimal: "" = Standard, key removed
        else:
            out[path[0]] = value
        return out
    # nested (site_defaults.*, product_detail.layout): copy the parent dict
    parent = dict(out.get(path[0]) or {})
    if value == "":
        parent.pop(path[1], None)
    else:
        parent[path[1]] = value
    if parent or path[0] != "page_styles":
        out[path[0]] = parent
    else:
        out.pop(path[0], None)  # presence-minimal: no empty `page_styles` (golden)
    return out


def validate(tenant, code: str, value, gate: dict | None = None):
    """Return the cleaned value or raise PageSettingError (shared by write/preview)."""
    setting = studio_pages.SETTINGS.get(code or "")
    if setting is None or is_studio_only(setting):
        raise PageSettingError(f"unknown page setting {code!r}")
    if not any(
        code in {s.code for s in cabinet_settings(t)}
        for t in SUPPORTED_TYPES
        if type_active(tenant, t)
    ):
        raise PageSettingError(f"setting {code!r} is not offered for this business")
    if not applies(tenant, setting):
        raise PageSettingError(f"setting {code!r} does not apply to this business")
    raw = tenant.site_config or {}
    current, _set = current_value(raw, setting)
    return _clean(setting, value, composition_gate(raw) if gate is None else gate, current)


def write(tenant, code: str, value) -> object:
    """The single site-level writer. Returns the stored (cleaned) value."""
    from apps.core.pagecache import bump_storefront_cache
    from apps.tenants.models import Tenant

    # the gate runs ~10 EXISTS queries on tenant tables — outside the row lock
    gate = composition_gate(tenant.site_config or {})
    with transaction.atomic():
        locked = Tenant.objects.select_for_update().get(pk=tenant.pk)
        cleaned = validate(locked, code, value, gate)
        new_cfg = apply_override(locked.site_config or {}, code, cleaned)
        # A queryset UPDATE, not instance.save(): django-tenants' save() re-creates a
        # missing schema on every update (TenantMixin.save) and a fresh instance has
        # auto_create_schema=True — a settings write must never trigger that.
        Tenant.objects.filter(pk=locked.pk).update(site_config=new_cfg)
        # what the post_save hook does for site_config writes (SE-5a)
        transaction.on_commit(lambda: bump_storefront_cache(locked.schema_name))
    tenant.site_config = new_cfg
    return cleaned


def preview_config(tenant, raw_cfg: dict, tpl: str) -> dict | None:
    """`?tpl=<code>:<value>` → a copy of the SAVED config with one value applied.

    Invalid input → None (caller falls back to the normal config). Never stored,
    never reads the Studio session draft (a stale draft must not leak in).
    """
    code, sep, value = (tpl or "").partition(":")
    if not sep:
        return None
    try:
        cleaned = validate(tenant, code.strip(), value)
    except PageSettingError:
        return None
    return apply_override(raw_cfg or {}, code.strip(), cleaned)


def _may_preview(request) -> bool:
    """`?tpl=` is a cabinet tool: only a signed-in member with website rights. For
    anyone else it is ignored — no extra queries, no uncached variants for bots."""
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False):
        return False
    from apps.core.permissions import has_perm

    try:
        return has_perm(user, "website.view")
    except Exception:  # noqa: BLE001 — fail closed (public schema, no membership)
        return False


def preview_raw(request) -> tuple[dict, bool]:
    """Raw config a storefront view should render: (config, is_preview).

    `?preview=1&tpl=<code>:<value>` (cabinet tab) → the SAVED config with one value
    applied in memory; otherwise `?preview=1` → the Studio session draft (as before);
    otherwise the saved config. The `tpl` branch deliberately ignores the draft: a
    stale Studio draft must not leak into the cabinet preview.
    """
    tenant = request.tenant
    saved = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    if request.GET.get("preview") != "1":
        return saved, False
    tpl = request.GET.get("tpl") or ""
    if tpl and _may_preview(request):
        # memoised: the context processor and the view ask for the same thing
        cached = getattr(request, "_stu19_tpl_cfg", None)
        if cached is None:
            cached = preview_config(tenant, saved, tpl[:120]) or {}
            request._stu19_tpl_cfg = cached
        if cached:
            return cached, True
    session = getattr(request, "session", None)
    draft = session.get("site_preview_draft") if session is not None else None
    if isinstance(draft, dict):
        return draft, True
    return saved, False


def raw_config(request) -> dict:
    """STU-19d: the raw config a storefront view renders — preview-aware.

    One reader for every storefront page: `?preview=1&tpl=` (cabinet tab), the
    Studio draft under `?preview=1`, otherwise the saved config. Views used to copy
    the draft check by hand; pages without it (tours, blog, sets, …) showed the
    saved state in every preview.
    """
    return preview_raw(request)[0]


#: Settings whose ONLY writer is the cabinet tab. The Studio Save and its live draft
#: must not change them (plan §3, locks a/b). Filled per axis in STU-19e/19f together
#: with removing the Studio control; empty in 19a = the mechanism without effect.
#: 19e-1: listing templates and detail layouts (no "Nur hier" in the Studio).
CABINET_OWNED: frozenset[str] = frozenset(
    {f"{surface}_page_style" for surface in compositions.LISTING_SURFACES} | _DETAIL_LAYOUTS
)


def summaries(tenant, codes=None) -> dict[str, dict]:
    """What the Studio shows instead of a cabinet-owned control: the setting's
    current value in words and the cabinet screen that changes it."""
    from apps.core import page_templates

    codes = set(CABINET_OWNED if codes is None else codes)
    out: dict[str, dict] = {}
    for ts in schema(tenant):
        for st in ts.settings:
            if st.code not in codes or st.code in out:
                continue
            label = next((c.label for c in st.choices if c.value == st.value), st.value)
            out[st.code] = {
                "label": st.label,
                "value": label or _("Standard"),
                "url": page_templates.cabinet_url(ts.code),
            }
    return out


def protect_owned(tenant, new_cfg: dict, owned=None) -> dict:
    """Return `new_cfg` with every cabinet-owned key taken from the CURRENT stored
    config (a fresh read, not the request's possibly stale copy): an open Studio tab
    must not overwrite what the cabinet saved meanwhile."""
    owned = CABINET_OWNED if owned is None else owned
    if not owned:
        return new_cfg
    from apps.tenants.models import Tenant

    fresh = Tenant.objects.filter(pk=tenant.pk).values_list("site_config", flat=True).first() or {}
    out = dict(new_cfg)
    for code in owned:
        setting = studio_pages.SETTINGS[code]
        key = _LAYOUT_KEYS.get(code)
        path = (key,) if key else setting.site_key
        top = path[0]
        if len(path) == 1:
            if top in fresh:
                out[top] = fresh[top]
            else:
                out.pop(top, None)
            continue
        parent = dict(out.get(top) or {})
        stored, found = _walk(fresh, path)
        if found:
            parent[path[1]] = stored
        else:
            parent.pop(path[1], None)
        if parent or top != "page_styles":
            out[top] = parent
        else:
            out.pop(top, None)  # presence-minimal, as the Studio Save stores it
    return out
