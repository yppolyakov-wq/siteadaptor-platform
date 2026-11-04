"""FLT-3b: быстрые фильтры в строке каталога + форма сортировки не ломает мультивыбор.

План — `docs/flt3-storefront-filters-plan-2026-11-04.md` §2.
"""

import re

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import QueryDict
from django.test import RequestFactory

from apps.catalog.models import ProductVariant
from apps.catalog.tests.factories import CategoryFactory, ProductFactory
from apps.promotions import public_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _body(query=""):
    request = RequestFactory().get("/sortiment/?" + query)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(name="Studio Q", business_type="clothing")
    return public_views.product_list(request).content.decode()


def _shop():
    cat = CategoryFactory(slug="damen", name={"de": "Damen"})
    blue = ProductFactory(name={"de": "Blaues Kleid"}, category=cat, base_price="45.00")
    red = ProductFactory(name={"de": "Rotes Kleid"}, category=cat, base_price="55.00", brand="Nord")
    for size in ("S", "M", "L"):
        ProductVariant.objects.create(product=blue, size=size, color="Blau", stock_quantity=3)
        ProductVariant.objects.create(product=red, size=size, color="Rot", stock_quantity=3)
    ProductFactory(name={"de": "Gürtel"}, category=cat, base_price="19.00", brand="Süd")


def _pop(body, key):
    i = body.index(f'data-flt-pop="{key}"')
    return body[i : body.index("</details>", i)]


def _hidden(fragment):
    return re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)">', fragment)


def test_quick_filters_render_next_to_filter_button_on_desktop_only():
    _shop()
    body = _body()
    bar = body[body.index("data-quick-filters") - 200 : body.index("data-quick-filters")]
    assert "hidden sm:flex" in bar  # телефон — кнопка «Filter» и ящик
    for key in ("preis", "groesse", "farbe", "marke"):
        assert f'data-flt-pop="{key}"' in body, key


def test_popover_keeps_every_other_filter_but_not_its_own():
    _shop()
    body = _body("groesse=M&groesse=L&farbe=Blau&q=Kleid&sort=price_asc&marke=Nord")
    size = _hidden(_pop(body, "groesse"))
    assert ("farbe", "Blau") in size and ("q", "Kleid") in size and ("marke", "Nord") in size
    assert ("sort", "price_asc") in size
    assert not [p for p in size if p[0] == "groesse"]  # свой фасет — галочками
    color = _hidden(_pop(body, "farbe"))
    assert ("groesse", "M") in color and ("groesse", "L") in color
    assert not [p for p in color if p[0] == "farbe"]


def test_sort_form_carries_multi_select_value_by_value():
    """Раньше размер уходил в форму сортировки ОДНИМ значением «['M', 'L']»."""
    _shop()
    body = _body("groesse=M&groesse=L")
    i = body.index("data-listing-toolbar")
    form = body[i : body.index("</form>", i)]
    pairs = _hidden(form)
    assert ("groesse", "M") in pairs and ("groesse", "L") in pairs
    assert "['M'" not in form and "[&#x27;M" not in form


def test_sale_toggle_keeps_state_and_switches():
    from apps.catalog.models import Product
    from apps.promotions.models import Promotion

    _shop()
    kleid = Product.objects.get(name__de="Blaues Kleid")
    Promotion.objects.create(
        title={"de": "Sale"}, product=kleid, discount_percent=20, status="active"
    )
    body = _body("farbe=Blau")
    quick = body[body.index("data-quick-filters") :]
    href = re.search(r'<a href="\?([^"]+)" rel="nofollow"', quick)
    assert href, "toggle «Nur reduziert» missing"
    qd = QueryDict(href.group(1).replace("&amp;", "&"))
    assert qd.get("sale") == "1" and qd.get("farbe") == "Blau"
