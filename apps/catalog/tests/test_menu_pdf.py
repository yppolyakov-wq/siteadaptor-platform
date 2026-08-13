"""GK-13: Speisekarte-PDF из живого каталога — вьюха, генератор, кнопка."""

import pytest
from django.http import Http404
from django.test import RequestFactory

from apps.catalog.models import Category, Product
from apps.catalog.pdf import build_menu_pdf
from apps.promotions import public_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _req(path="/speisekarte.pdf", business_type="restaurant"):
    request = RequestFactory().get(path)
    request.tenant = TenantFactory.build(business_type=business_type)
    return request


def _product(name="Lasagne", price="12.90", **kw):
    return Product.objects.create(
        name={"de": name}, description={"de": "Hausgemacht."}, base_price=price, **kw
    )


def test_speisekarte_pdf_404_without_products():
    with pytest.raises(Http404):
        public_views.speisekarte_pdf(_req())


def test_speisekarte_pdf_renders_pdf_with_categories_and_legend():
    cat = Category.objects.create(name={"de": "Hauptgerichte"}, slug="haupt")
    _product(category=cat, allergens=["gluten", "milch"], diets=["vegetarisch"])
    _product(name="Suppe", price="5.50")  # без категории → группа «Other»
    resp = public_views.speisekarte_pdf(_req())
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


def test_build_menu_pdf_smoke_bytes():
    p = _product(allergens=["gluten"])
    pdf = build_menu_pdf(TenantFactory.build(), [("Karte", [p])])
    assert pdf[:4] == b"%PDF" and len(pdf) > 500


def test_catalog_button_gated_by_food_type_and_products():
    _product()
    body_food = public_views.product_list(_req("/sortiment/")).content.decode()
    assert "speisekarte.pdf" in body_food
    body_mode = public_views.product_list(
        _req("/sortiment/", business_type="clothing")
    ).content.decode()
    assert "speisekarte.pdf" not in body_mode


def test_catalog_button_hidden_without_products():
    body = public_views.product_list(_req("/sortiment/")).content.decode()
    assert "speisekarte.pdf" not in body


@pytest.mark.django_db
def test_pdf_groups_split_by_course_only_when_filled():
    """MEN-6: подгруппы по Gang'ам появляются только если Gang заполнен —
    у пекарни/ретейла карта остаётся прежней (байт-в-байт)."""
    from apps.catalog.tests.factories import ProductFactory
    from apps.promotions.public_views import _pdf_course_groups

    soup = ProductFactory(name={"de": "Suppe"}, course="suppe")
    main = ProductFactory(name={"de": "Filet"}, course="hauptgang")
    plain = ProductFactory(name={"de": "Brot"})

    assert _pdf_course_groups("Karte", [plain]) == [("Karte", [plain])]

    groups = _pdf_course_groups("Hochzeit", [main, soup, plain])
    titles = [t for t, _items in groups]
    assert titles == ["Hochzeit · Suppe", "Hochzeit · Hauptgericht", "Hochzeit"]
    assert groups[0][1] == [soup] and groups[-1][1] == [plain]
