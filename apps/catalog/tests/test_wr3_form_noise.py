"""KA-12 WR-3 (E3.11): шум формы товара по направлению — «Marke & Zustand» и UVP скрыты
у гастро (CSS, поля в DOM — W0), заполненное значение видно; Chargen-переключатель склада
только у продуктов питания (или уже включённый)."""

import pytest

from apps.catalog import views as catalog_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


class _Req:
    def __init__(self, bt):
        self.tenant = TenantFactory.build(business_type=bt)


def test_retail_fields_flag_by_business_type():
    assert catalog_views._product_form_flags(_Req("restaurant"))["show_retail_fields"] is False
    assert catalog_views._product_form_flags(_Req("clothing"))["show_retail_fields"] is True
    assert catalog_views._product_form_flags(_Req("retail"))["show_retail_fields"] is True


def test_template_keeps_fields_in_dom_and_shows_filled_values():
    from pathlib import Path

    src = Path("templates/catalog/product_form.html").read_text()
    assert "data-retail-fields" in src and "not form.instance.brand" in src
    assert "data-list-price" in src and "not form.instance.list_price" in src
    # UX-D D6.2b: тумблер партий переехал в настройки склада (Einstellungen › «Lager»).
    stock = Path("templates/inventory/stock_settings.html").read_text()
    assert "{% if show_lots_toggle %}" in stock
