"""UA4-1: единый реестр секций детали + обобщённый нормализатор (siteconfig).

Гейт: generic-нормализатор ведёт себя как прежние per-архетипные функции (паритет),
KEYS выводятся из реестра, неизвестные ключи отбрасываются, hide-only vs order+hide.
"""

from apps.core import detail_sections
from apps.tenants import siteconfig


# --- реестр -----------------------------------------------------------------
def test_registry_keys_match_legacy_constants():
    # KEYS выводятся из реестра; порядок и состав — как исторически захардкожено.
    assert siteconfig.EVENT_DETAIL_SECTION_KEYS == (
        "for_whom",
        "idea",
        "includes",
        "program",
        "venue",
        "accommodation",
        "food",
        "hosts",
        "price",
        "bring",
        "faq",
        "testimonials",
        "before_after",
        "certifications",
    )
    assert siteconfig.PRODUCT_DETAIL_SECTION_KEYS == ("description", "info", "reviews", "related")


def test_registry_flags():
    # event — orderable+hideable; product — hide-only.
    assert all(s.orderable for s in detail_sections.sections_for("events"))
    assert not any(s.orderable for s in detail_sections.sections_for("catalog"))
    assert all(s.hideable for s in detail_sections.sections_for("catalog"))
    assert detail_sections.sections_for("unknown") == ()


# --- slice C: service/stay реестр + конфиг-ключи + нормализация ---------------
def test_registry_service_stay_keys_and_flags():
    assert detail_sections.section_keys("booking") == (
        "description",
        "attributes",
        "faq",
        "team",
        "reviews",
    )
    assert detail_sections.section_keys("stays") == (
        "description",
        "amenities",
        "reviews",
        "similar",
    )
    # обе — hide-only (порядок фиксирован шаблоном)
    assert not any(s.orderable for s in detail_sections.sections_for("booking"))
    assert not any(s.orderable for s in detail_sections.sections_for("stays"))


def test_config_keys_for_service_stay():
    assert siteconfig.detail_section_config_key("booking") == "service_detail"
    assert siteconfig.detail_section_config_key("stays") == "stay_detail"


def test_detail_section_hidden_service_stay():
    cfg = {
        "service_detail": {"hidden": ["reviews", "zzz"]},
        "stay_detail": {"hidden": ["similar"]},
    }
    assert siteconfig.detail_section_hidden(cfg, "booking") == {"reviews"}
    assert siteconfig.detail_section_hidden(cfg, "stays") == {"similar"}


def test_normalize_adds_service_stay_detail():
    out = siteconfig.normalize(
        {"service_detail": {"hidden": ["faq"]}, "stay_detail": {"hidden": ["amenities", "bad"]}}
    )
    assert out["service_detail"] == {"hidden": ["faq"]}
    assert out["stay_detail"] == {"hidden": ["amenities"]}  # неизвестный ключ отброшен


def test_section_labels_present_for_each_key():
    labels = detail_sections.section_labels("events")
    assert set(labels) == set(siteconfig.EVENT_DETAIL_SECTION_KEYS)
    assert str(labels["for_whom"])  # ленивая i18n-строка резолвится в непустую


# --- normalize_detail_sections ---------------------------------------------
def test_normalize_events_keeps_order_dedups_and_drops_unknown():
    raw = {"order": ["zzz", "idea", "idea", "for_whom"], "hidden": ["food", "nope"]}
    assert siteconfig.normalize_detail_sections(raw, "events") == {
        "order": ["idea", "for_whom"],
        "hidden": ["food"],
    }


def test_normalize_catalog_is_hide_only():
    out = siteconfig.normalize_detail_sections(
        {"hidden": ["info", "zzz"], "order": ["x"]}, "catalog"
    )
    assert out == {"hidden": ["info"]}  # никакого order у hide-only модуля


def test_normalize_garbage_is_safe():
    assert siteconfig.normalize_detail_sections(None, "events") == {"order": [], "hidden": []}
    assert siteconfig.normalize_detail_sections("garbage", "catalog") == {"hidden": []}


# --- order/hidden ридеры ----------------------------------------------------
def test_detail_section_order_full_registry_when_empty():
    assert siteconfig.detail_section_order({}, "events") == list(
        siteconfig.EVENT_DETAIL_SECTION_KEYS
    )


def test_detail_section_order_saved_first_then_rest_minus_hidden():
    cfg = {"event_detail": {"order": ["price", "idea"], "hidden": ["food"]}}
    got = siteconfig.detail_section_order(cfg, "events")
    assert got[:2] == ["price", "idea"]  # сохранённый порядок вперёд
    assert "food" not in got  # скрытая выпала
    assert set(got) == set(siteconfig.EVENT_DETAIL_SECTION_KEYS) - {"food"}


def test_detail_section_hidden_catalog():
    cfg = {"product_detail": {"hidden": ["reviews"]}}
    assert siteconfig.detail_section_hidden(cfg, "catalog") == {"reviews"}


# --- обратная совместимость (старые имена = обёртки) ------------------------
def test_legacy_wrappers_match_generic():
    raw = {"order": ["idea"], "hidden": ["food"]}
    assert siteconfig.normalize_event_detail(raw) == siteconfig.normalize_detail_sections(
        raw, "events"
    )
    cfg = {"event_detail": raw}
    assert siteconfig.event_detail_order(cfg) == siteconfig.detail_section_order(cfg, "events")
    praw = {"hidden": ["info"]}
    assert siteconfig.normalize_product_detail(praw) == siteconfig.normalize_detail_sections(
        praw, "catalog"
    )
    pcfg = {"product_detail": praw}
    assert siteconfig.product_detail_hidden(pcfg) == siteconfig.detail_section_hidden(
        pcfg, "catalog"
    )


def test_legacy_normalize_event_detail_shape_unchanged():
    # прежний контракт: {order, hidden} с отсортированным уникальным hidden
    assert siteconfig.normalize_event_detail({"hidden": ["food", "food"]}) == {
        "order": [],
        "hidden": ["food"],
    }
