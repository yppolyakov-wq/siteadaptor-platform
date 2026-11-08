"""FB-20: метки карточки у акции, услуги, события и номера — общий реестр с товаром."""

import pytest
from django.template.loader import render_to_string
from django.test import RequestFactory

from apps.booking.models import Service
from apps.booking.tests.test_video_service import _req as svc_req
from apps.booking.tests.test_video_service import _services_view
from apps.catalog.models import BADGE_LABELS
from apps.core import labels
from apps.events.models import Event
from apps.promotions.models import Promotion
from apps.stays.models import StayUnit
from apps.stays.tests.test_cabinet import _req as stay_req

pytestmark = pytest.mark.django_db


def test_one_registry_for_products_and_the_rest():
    assert BADGE_LABELS is labels.LABELS
    assert labels.label_for("neu") == "Neu" and labels.label_for("<x>") == ""
    assert labels.clean("beliebt") == "beliebt" and labels.clean("<x>") == ""


@pytest.mark.parametrize("model", [Promotion, Service, Event, StayUnit])
def test_every_sellable_model_has_the_label(model):
    obj = model(badge="empfehlung")
    assert obj.badge_label == "Empfehlung"
    assert model(badge="").badge_label == ""


def test_service_page_saves_label_only_when_sent():
    service = Service.objects.create(name="Schnitt", badge="neu")
    base = {"action": "update", "service": str(service.pk), "duration": "30", "price_eur": "10"}
    _services_view(svc_req("post", base))  # чужой клиент формы без поля — метка цела
    service.refresh_from_db()
    assert service.badge == "neu"
    _services_view(svc_req("post", {**base, "badge": "beliebt"}))
    service.refresh_from_db()
    assert service.badge == "beliebt"
    _services_view(svc_req("post", {**base, "badge": "<script>"}))
    service.refresh_from_db()
    assert service.badge == ""


def test_unit_page_saves_label():
    from apps.stays import views

    unit = StayUnit.objects.create(name="Zimmer FB20", price_cents=8000)
    data = {"action": "unit_settings", "unit": str(unit.pk), "price_eur": "80", "badge": "neu"}
    views.units(stay_req("post", "/dashboard/stays/units/", data))
    unit.refresh_from_db()
    assert unit.badge == "neu"


def test_promotion_form_offers_the_label():
    from apps.promotions.forms import PromotionForm

    form = PromotionForm(instance=Promotion(badge="neu"))
    assert [c for c, _l in form.fields["badge"].choices] == [c for c, _l in labels.CHOICES]


def test_promo_card_shows_the_label():
    promo = Promotion.objects.create(title={"de": "Deal"}, status="active", badge="beliebt")
    html = render_to_string(
        "storefront/_promo_card.html", {"p": promo, "request": RequestFactory().get("/")}
    )
    assert "data-entity-label" in html and "Beliebt" in html
