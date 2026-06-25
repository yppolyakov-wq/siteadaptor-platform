"""M20U: primary_item registry — «главный товар» по архетипу."""

from apps.core import archetypes


class _Tenant:
    """Лёгкий стенд: активные модули + site_config (без БД)."""

    def __init__(self, active, site_config=None):
        self._active = set(active)
        self.site_config = site_config or {}

    def is_module_active(self, key):
        return key in self._active


def test_primary_module_by_priority_events_first():
    t = _Tenant(active={"events", "catalog", "stays"})
    # events приоритетнее stays/catalog
    assert archetypes.primary_module(t) == "events"


def test_primary_module_catalog_when_only_shop():
    t = _Tenant(active={"catalog", "promotions"})
    assert archetypes.primary_module(t) == "catalog"


def test_storefront_root_overrides_priority():
    # явный storefront_root=stays перебивает приоритетный events
    t = _Tenant(active={"events", "stays"}, site_config={"storefront_root": "stays"})
    assert archetypes.primary_module(t) == "stays"


def test_storefront_root_ignored_if_inactive():
    t = _Tenant(active={"catalog"}, site_config={"storefront_root": "stays"})
    assert archetypes.primary_module(t) == "catalog"  # stays неактивен → фолбэк


def test_primary_section_mapping():
    assert archetypes.primary_section(_Tenant({"events"})) == "events"
    assert archetypes.primary_section(_Tenant({"catalog"})) == "products"
    assert archetypes.primary_section(_Tenant({"stays"})) == "stay_rooms"
    # A3: booking → блок услуг «Leistungen & Preise».
    assert archetypes.primary_section(_Tenant({"booking"})) == "services"


def test_booking_outranks_catalog_for_salon():
    # A3 (Friseur/Werkstatt): booking активнее catalog (мерч/Teile вторичны) —
    # главным товаром на главной становится услуга, а не товар.
    t = _Tenant(active={"booking", "catalog", "promotions"})
    assert archetypes.primary_module(t) == "booking"
    assert archetypes.primary_section(t) == "services"


def test_primary_item_descriptor_carries_landing_and_label():
    item = archetypes.primary_item(_Tenant({"events"}))
    assert item["module"] == "events" and item["section"] == "events"
    assert item["landing"] == "storefront-events"  # из ModuleSpec
    assert item["label"]  # непустой заголовок архетипа
    assert item["mode"] == "booking"  # M20U-5: способ покупки


def test_purchase_mode_by_archetype():
    assert archetypes.purchase_mode("catalog") == "cart"
    assert archetypes.purchase_mode("events") == "booking"
    assert archetypes.purchase_mode("stays") == "booking"
    assert archetypes.purchase_mode("jobs") == "request"
    assert archetypes.purchase_mode("unknown") == "request"  # безопасный фолбэк


def test_purchase_label_by_archetype():
    assert archetypes.purchase_label("catalog") == "In den Warenkorb"
    assert archetypes.purchase_label("events") == "Jetzt buchen"
    assert archetypes.purchase_label("stays") == "Jetzt buchen"
    assert archetypes.purchase_label("jobs") == "Anfrage senden"
    assert archetypes.purchase_label("unknown") == "Anfrage senden"  # фолбэк


def test_primary_none_when_no_archetype_active():
    assert archetypes.primary_module(_Tenant(active=set())) is None
    assert archetypes.primary_item(_Tenant(active=set())) is None
