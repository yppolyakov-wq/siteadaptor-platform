"""FB-29.4b S2: своя структура страницы услуги — секция в форме услуги (сентинел W0)."""

import pytest

from apps.booking.models import Service
from apps.booking.tests.test_video_service import _req, _services_view

pytestmark = pytest.mark.django_db


def _base(service):
    return {"action": "update", "service": str(service.pk), "duration": "30", "price_eur": "10"}


def test_service_form_saves_the_override_only_with_the_sentinel():
    s = Service.objects.create(name="Schnitt")
    _services_view(_req("post", {**_base(s), "ps_team": "hide"}))
    s.refresh_from_db()
    assert s.page_override == {}
    _services_view(_req("post", {
        **_base(s), "page_override_present": "1", "ps_team": "hide", "ps_layout": "tabs",
        "card_style": "overlay",
    }))  # fmt: skip
    s.refresh_from_db()
    assert s.page_override == {"hidden": ["team"], "layout": "tabs"}
    assert s.card_style == "overlay"


def test_service_reset():
    s = Service.objects.create(
        name="Schnitt", page_override={"hidden": ["team"]}, card_style="overlay"
    )
    _services_view(_req("post", {**_base(s), "page_override_present": "1", "ps_reset": "1"}))
    s.refresh_from_db()
    assert s.page_override == {} and s.card_style == ""


def test_service_card_style_takes_only_registry_keys():
    s = Service.objects.create(name="Schnitt")
    _services_view(_req("post", {**_base(s), "page_override_present": "1", "card_style": "<x>"}))
    s.refresh_from_db()
    assert s.card_style == ""
