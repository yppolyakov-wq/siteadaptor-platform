"""Инлайн-правка акции на канве витрины (редактор): заголовок + цена (price_override)."""

import json
from types import SimpleNamespace

import pytest
from django.test import RequestFactory

from apps.promotions import views
from apps.promotions.tests.factories import PromotionFactory

pytestmark = pytest.mark.django_db


def _post(pk, field, value):
    body = json.dumps({"pk": str(pk), "field": field, "value": value})
    req = RequestFactory().post("/promotions/inline-edit/", body, content_type="application/json")
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = SimpleNamespace(schema_name="public")
    return views.promotion_inline_edit(req)


def test_promotion_inline_edit_title():
    p = PromotionFactory(title={"de": "Alt", "en": "Old"})
    assert _post(p.pk, "title", "  Neue Aktion  ").status_code == 204
    p.refresh_from_db()
    assert p.title["de"] == "Neue Aktion" and p.title["en"] == "Old"  # EN не затёрт


def test_promotion_inline_edit_price_override_comma_decimal():
    p = PromotionFactory()
    assert _post(p.pk, "price_override", "3,49").status_code == 204  # запятая → точка
    p.refresh_from_db()
    assert str(p.price_override) == "3.49"


def test_promotion_inline_edit_rejects_empty_title():
    p = PromotionFactory(title={"de": "Alt"})
    assert _post(p.pk, "title", "   ").status_code == 400
    p.refresh_from_db()
    assert p.title["de"] == "Alt"  # не затёрто пустым


def test_promotion_inline_edit_rejects_unknown_field():
    p = PromotionFactory()
    assert _post(p.pk, "status", "active").status_code == 400


def test_promotion_inline_edit_rejects_bad_price():
    p = PromotionFactory()
    assert _post(p.pk, "price_override", "abc").status_code == 400
    assert _post(p.pk, "price_override", "-5").status_code == 400
