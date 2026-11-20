"""FB-33 M2b-2b C5: свои вопросы FAQ в формах товара и номера — общий редактор услуги
(`tenant/_object_faq_fields.html`), запись — `object_faq.put`; без сентинела — не трогается."""

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.catalog import views as catalog_views
from apps.catalog.tests.factories import ProductFactory
from apps.catalog.tests.test_fb29_structure_tab import BASE
from apps.catalog.tests.test_views import _attach_session_user
from apps.stays import views as stay_views
from apps.stays.models import StayUnit
from apps.stays.tests.test_cabinet import _req

pytestmark = pytest.mark.django_db
OWN = [{"q": "Frisch?", "a": "Täglich."}, {"q": "Bio?", "a": "Ja."}]


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        username="owner2b", email="owner2b@test.de", password="pw12345678"
    )


def _product_edit(product, user, extra, method="post"):
    req = getattr(RequestFactory(), method)(
        f"/catalog/products/{product.pk}/edit/", {**BASE, **extra} if method == "post" else {}
    )
    _attach_session_user(req, user)
    resp = catalog_views.product_edit(req, pk=product.pk)
    product.refresh_from_db()
    return resp


def test_product_form_shows_and_saves_own_questions(user):
    p = ProductFactory(name={"de": "Tee", "en": ""}, base_price="2.00", faq=OWN)
    html = _product_edit(p, user, {}, method="get").content.decode()
    assert 'name="faq_present"' in html and 'value="Frisch?"' in html and 'name="faq_q_2"' in html
    _product_edit(
        p, user,
        {"faq_present": "1", "faq_q_0": "", "faq_a_0": "x", "faq_q_1": "Bio?", "faq_a_1": "Ja.",
         "faq_q_2": "Neu?", "faq_a_2": "<b>n</b>"},
    )  # fmt: skip
    assert p.faq == [{"q": "Bio?", "a": "Ja."}, {"q": "Neu?", "a": "<b>n</b>"}]


def test_product_save_without_sentinel_keeps_questions(user):
    p = ProductFactory(name={"de": "Tee", "en": ""}, base_price="2.00", faq=OWN)
    _product_edit(p, user, {"faq_q_0": ""})
    assert p.faq == OWN


def test_unit_form_saves_own_questions():
    unit = StayUnit.objects.create(name="FeWo", price_cents=9000, faq=OWN)
    page = stay_views.units(_req(), pk=unit.pk).content.decode()
    assert "data-unit-faq" in page and 'value="Bio?"' in page
    stay_views.units(
        _req(
            "post",
            "/dashboard/stays/units/",
            {"action": "unit_settings", "unit": str(unit.pk), "price_eur": "90", "quantity": "1",
             "faq_present": "1", "faq_q_0": "Frisch?", "faq_a_0": "Täglich.", "faq_q_1": ""},
        )
    )  # fmt: skip
    unit.refresh_from_db()
    assert unit.faq == OWN[:1]


def test_unit_save_without_sentinel_keeps_questions():
    unit = StayUnit.objects.create(name="FeWo", price_cents=9000, faq=OWN)
    stay_views.units(
        _req("post", "/dashboard/stays/units/",
             {"action": "unit_settings", "unit": str(unit.pk), "price_eur": "90"})
    )  # fmt: skip
    unit.refresh_from_db()
    assert unit.faq == OWN


def test_forms_call_the_one_writer():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    for rel in ("apps/catalog/views.py", "apps/stays/views.py"):
        assert "object_faq.put(" in (root / rel).read_text(), rel
    for tpl in ("booking/service_page.html", "catalog/product_form.html", "stays/unit_page.html"):
        assert "tenant/_object_faq_fields.html" in (root / "templates" / tpl).read_text(), tpl
