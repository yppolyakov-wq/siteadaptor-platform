"""Регрессия: карта агрегатора (_map.html) не должна допускать XSS из
tenant-редактируемых title/url листинга.

Две дыры (аудит 2026-07-01):
1. `map_points_json|safe` в <script> шёл мимо экранирования → `</script>` в title
   вырывался из блока. Фикс — `{{ map_points|json_script }}` (экранирует < > &).
2. Leaflet `bindPopup('<a ...>' + p.title)` вставлял title/url как innerHTML →
   `<img onerror>` / `javascript:` исполнялись. Фикс — попап через DOM (textContent).
"""

import uuid
from decimal import Decimal

import pytest
from django.test import RequestFactory

from apps.aggregator import views
from apps.aggregator.models import AggregatorListing

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _public_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_public"


def _listing(**kw):
    defaults = {
        "tenant_schema": "t1",
        "tenant_slug": "x",
        "business_name": "B",
        "business_type": "bakery",
        "city": "München",
        "promo_uuid": uuid.uuid4(),
        "title": {"de": "Angebot"},
        "detail_url": "https://x.siteadaptor.de/p/1/",
        "is_active": True,
        "latitude": Decimal("48.1372"),
        "longitude": Decimal("11.5755"),
    }
    defaults.update(kw)
    return AggregatorListing.objects.create(**defaults)


def _render_city_map():
    req = RequestFactory().get("/entdecken/München/")
    return views.city_listing(req, city="München").content.decode()


def test_map_json_escapes_script_breakout():
    _listing(title={"de": "</script><script>alert(1)</script>"})
    body = _render_city_map()
    # json_script экранирует `<` → сырого закрытия <script> с полезной нагрузкой быть не должно
    assert "</script><script>alert(1)" not in body
    assert "\\u003cscript\\u003ealert(1)" in body  # экранированная форма присутствует


def test_map_popup_built_via_dom_not_innerhtml():
    _listing()
    body = _render_city_map()
    # попап собирается безопасно через DOM, а не конкатенацией в innerHTML
    assert "popupLink" in body
    assert "a.textContent" in body
    assert "bindPopup('<a href=\"'" not in body
