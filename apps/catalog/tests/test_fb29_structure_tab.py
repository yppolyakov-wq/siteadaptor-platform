"""FB-29.4b S2: вкладка «Seitenaufbau» в форме товара и на странице услуги — показ
разделов, шаблон страницы, сброс. Сохранение из другого места поле не трогает (W0)."""

import pathlib
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.catalog import views
from apps.catalog.tests.factories import ProductFactory
from apps.catalog.tests.test_views import _attach_session_user
from apps.core import object_structure as ost

BASE = {
    "name_de": "Tee", "name_en": "", "description_de": "", "description_en": "",
    "base_price": "2.00", "currency": "EUR", "sku": "", "is_active": "on",
}  # fmt: skip


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        username="owner29", email="owner29@test.de", password="pw12345678"
    )


def _edit(product, user, extra):
    req = RequestFactory().post(f"/catalog/products/{product.pk}/edit/", {**BASE, **extra})
    _attach_session_user(req, user)
    assert views.product_edit(req, pk=product.pk).status_code == 302
    product.refresh_from_db()
    return product


@pytest.mark.django_db
def test_tab_saves_shown_hidden_and_layout(user):
    p = ProductFactory(name={"de": "Tee", "en": ""}, base_price="2.00")
    _edit(p, user, {
        "page_override_present": "1", "ps_reviews": "hide", "ps_related": "show",
        "ps_description": "standard", "ps_layout": "breit",
    })  # fmt: skip
    assert p.page_override == {"hidden": ["reviews"], "shown": ["related"], "layout": "breit"}


@pytest.mark.django_db
def test_save_without_the_tab_keeps_the_override(user):
    p = ProductFactory(name={"de": "Tee", "en": ""}, base_price="2.00")
    p.page_override = {"hidden": ["reviews"]}
    p.save(update_fields=["page_override"])
    _edit(p, user, {"ps_reviews": "standard"})  # сентинела нет — чужая форма
    assert p.page_override == {"hidden": ["reviews"]}


@pytest.mark.django_db
def test_reset_returns_to_the_shared_view(user):
    p = ProductFactory(name={"de": "Tee", "en": ""}, base_price="2.00", card_style="overlay")
    p.page_override = {"hidden": ["reviews"], "layout": "tabs"}
    p.save(update_fields=["page_override"])
    _edit(p, user, {"page_override_present": "1", "ps_reviews": "hide", "ps_reset": "1"})
    assert p.page_override == {} and p.card_style == ""


def test_post_garbage_is_dropped():
    post = {"page_override_present": "1", "ps_reviews": "DROP", "ps_nope": "hide", "ps_layout": "x"}
    assert ost.from_post(post, "catalog") == {}
    assert ost.from_post({"ps_reviews": "hide"}, "catalog") is None


def test_panel_describes_every_section_for_the_tab():
    cfg = {"product_detail": {"hidden": ["related"]}}
    obj = SimpleNamespace(page_override={"shown": ["related"], "hidden": ["reviews"]})
    panel = ost.panel(cfg, "product", obj)
    rows = {r["key"]: r for r in panel["rows"]}
    assert rows["related"]["state"] == "show" and rows["related"]["shared_visible"] is False
    assert rows["reviews"]["state"] == "hide" and rows["reviews"]["shared_visible"] is True
    assert rows["description"]["state"] == "standard"
    assert panel["deviations"] == 2
    assert [o["value"] for o in panel["layouts"]][0] == ""  # «wie alle»


def test_templates_carry_the_tab_and_the_sentinel():
    part = pathlib.Path("templates/tenant/_object_structure.html").read_text()
    assert 'name="page_override_present"' in part and 'name="ps_reset"' in part
    assert 'type="radio"' in part and 'role="radiogroup"' in part and "aria-labelledby" in part
    assert 'aria-describedby="ps-reset-help"' in part
    form = pathlib.Path("templates/catalog/product_form.html").read_text()
    assert 'data-pf-tab="aufbau"' in form and 'data-pf-panel="aufbau"' in form
    assert "tenant/_object_structure.html" in form
    svc = pathlib.Path("templates/booking/service_page.html").read_text()
    assert "tenant/_object_structure.html" in svc
