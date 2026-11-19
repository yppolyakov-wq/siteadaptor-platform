"""FB-33 M2f: семь разделов страницы товара — отдельными строками схемы; LMIV у еды."""

import pytest

from apps.core import detail_parts
from apps.core.tests.test_fb31p5_detail_golden import _req
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db

NEW = ("sizes", "trust", "anprobe", "waitlist", "instore", "question", "recent")


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _product_html(cfg, business_type="cafe"):
    from apps.catalog.tests.factories import ProductFactory
    from apps.promotions import public_views

    p = ProductFactory(name={"de": "Bauernbrot"}, description={"de": "Sauerteig."})
    req = _req(f"/sortiment/{p.pk}/", cfg)
    req.tenant.business_type = business_type
    req.tenant.address = "Hauptstr. 1"
    return public_views.product_detail(req, pk=p.pk).content.decode()


def test_new_sections_are_registered_in_page_order():
    assert siteconfig.PRODUCT_DETAIL_SECTION_KEYS == (
        "description", "info", *NEW[:-1], "reviews", "related", "recent",
    )  # fmt: skip
    assert set(NEW[:-1]) <= set(detail_parts.FIRST_SCREEN["product_detail"])


def test_hiding_instore_removes_only_that_part():
    shown = _product_html({}, business_type="clothing")
    hidden = _product_html({"product_detail": {"hidden": ["instore"]}}, business_type="clothing")
    assert "Im Laden erhältlich." in shown and "Hauptstr. 1</p>" in shown
    assert "Im Laden erhältlich." not in hidden and "Hauptstr. 1</p>" not in hidden


def test_hidden_recent_writes_nothing_to_the_browser():
    shown = _product_html({}, business_type="clothing")
    hidden = _product_html({"product_detail": {"hidden": ["recent"]}}, business_type="clothing")
    assert "sf_seen_products" in shown and "data-recent-strip" in shown
    assert "sf_seen_products" not in hidden and "data-recent-strip" not in hidden


@pytest.mark.parametrize(
    "business_type", ("bakery", "butcher", "grocery", "cafe", "restaurant", "catering")
)
def test_food_cannot_hide_ingredients(business_type):
    assert not detail_parts.hideable("product_detail", "info", business_type)
    assert detail_parts.food_locked("catalog", business_type) == {"info"}


def test_non_food_can_hide_ingredients():
    assert detail_parts.hideable("product_detail", "info", "clothing")
    assert detail_parts.food_locked("catalog", "clothing") == frozenset()


def test_blocks_saved_after_related_stay_at_the_tail():
    """Строки, сохранённые до «Zuletzt angesehen», держат хвост там же (блоки не пропадают)."""
    rows = [{"key": k} for k in ("description", "info", "reviews", "related")]
    rows.append({"key": "text", "id": "x1"})
    a = detail_parts.anchors(rows, "product_detail", list(siteconfig.PRODUCT_DETAIL_SECTION_KEYS))
    assert a["tail"] == ["x1"]


def test_block_between_related_and_recent_has_its_own_place():
    keys = siteconfig.PRODUCT_DETAIL_SECTION_KEYS
    rows = [{"key": k} for k in keys if k != "recent"]
    rows += [{"key": "text", "id": "w1"}, {"key": "recent"}, {"key": "text", "id": "t1"}]
    parts = detail_parts.fixed_parts(rows, "product_detail")
    assert parts["wide"] == "ids:w1"
    a = detail_parts.anchors(rows, "product_detail", list(keys))
    assert a["tail"] == ["t1"]


def test_own_blocks_of_one_product_after_related_have_a_place():
    """Ревью M2f HIGH: свои блоки товара со своей схемой после «Ähnliche» не пропадают."""
    keys = siteconfig.PRODUCT_DETAIL_SECTION_KEYS
    own = {"host": "product:x", "lead": [], "after": {"related": ["o1"]}, "tail": []}
    parts = detail_parts.fixed_parts([], "product_detail", own)
    assert parts["wide_own"] == "ids:o1"
    assert "related" in keys


def test_stay_tail_is_unchanged():
    """Ревью M2f: смена хвоста — только у товара; у номера хвост — после последнего раздела реестра."""
    from apps.core import detail_sections

    keys = list(detail_sections.section_keys("stays"))
    rows = [{"key": k} for k in keys[:-1]] + [{"key": "text", "id": "s1"}]
    a = detail_parts.anchors(rows, "stay_detail", keys)
    assert a["tail"] == []  # блок после предпоследнего раздела — не хвост (как было)


def test_shared_hidden_reader_respects_lmiv(monkeypatch):
    from django.db import connection

    from apps.tenants.tests.factories import TenantFactory

    cfg = {"product_detail": {"hidden": ["info", "reviews"]}}
    monkeypatch.setattr(
        connection, "tenant", TenantFactory.build(business_type="bakery"), raising=False
    )
    assert siteconfig.detail_section_hidden(cfg, "catalog") == {"reviews"}
    monkeypatch.setattr(
        connection, "tenant", TenantFactory.build(business_type="clothing"), raising=False
    )
    assert siteconfig.detail_section_hidden(cfg, "catalog") == {"info", "reviews"}


def test_audit_sees_the_saved_hiding_even_inside_the_food_schema():
    from apps.catalog.management.commands import lmiv_info_audit

    assert lmiv_info_audit.site_hides_info({"product_detail": {"hidden": ["info"]}})
