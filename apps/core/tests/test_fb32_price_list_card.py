"""FB-32 (вопрос владельца 2026-11-18): у прайс-листа и меню «Kartenform» в панели нет — они
рисуют строки, а не карточки; у сетки поле остаётся."""

import pytest
from django.test import RequestFactory

from apps.core import list_panel
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _names(style):
    request = RequestFactory().get("/")
    request.tenant = TenantFactory.build(business_type="bakery", site_config={})
    groups = list_panel.groups(request, {}, {"source": "products", "style": style})
    return {f["name"] for g in groups for f in g["fields"]}


@pytest.mark.parametrize("style", ("preisliste", "preisliste_foto", "preisliste_karte"))
def test_price_list_styles_have_no_card_form(style):
    assert "card" not in _names(style) and "style" in _names(style)


def test_grid_keeps_the_card_form():
    assert "card" in _names("")
