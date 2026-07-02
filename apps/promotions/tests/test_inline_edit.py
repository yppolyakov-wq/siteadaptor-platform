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


# --- UE3-1: расширение вайтлиста (compare_at_price / discount_percent / ends_at) ---


def test_inline_edit_compare_at_price_comma_decimal():
    p = PromotionFactory()
    assert _post(p.pk, "compare_at_price", "12,90").status_code == 204
    p.refresh_from_db()
    assert str(p.compare_at_price) == "12.90"


def test_inline_edit_discount_percent_valid_and_zero_clears():
    p = PromotionFactory(discount_percent=None)
    assert _post(p.pk, "discount_percent", "30").status_code == 204
    p.refresh_from_db()
    assert p.discount_percent == 30
    assert _post(p.pk, "discount_percent", "0").status_code == 204  # 0 → очистить
    p.refresh_from_db()
    assert p.discount_percent is None


def test_inline_edit_discount_percent_rejects_invalid():
    p = PromotionFactory(discount_percent=15)
    for bad in ("150", "-5", "30.5", "abc", ""):
        assert _post(p.pk, "discount_percent", bad).status_code == 400
    p.refresh_from_db()
    assert p.discount_percent == 15  # не тронуто


def test_inline_edit_ends_at_iso_naive_becomes_aware():
    from django.utils import timezone

    p = PromotionFactory()
    assert _post(p.pk, "ends_at", "2026-08-01T18:30").status_code == 204
    p.refresh_from_db()
    assert timezone.is_aware(p.ends_at)
    local = timezone.localtime(p.ends_at)
    assert (local.year, local.month, local.day, local.hour, local.minute) == (2026, 8, 1, 18, 30)


def test_inline_edit_ends_at_rejects_garbage():
    p = PromotionFactory()
    before = p.ends_at
    assert _post(p.pk, "ends_at", "не дата").status_code == 400
    p.refresh_from_db()
    assert p.ends_at == before


def test_inline_edit_engine_fields_stay_closed():
    """Анти-оверселл-гейт: поля движка в инлайн НЕ правятся (только форма/SM)."""
    p = PromotionFactory(available_quantity=5)
    assert _post(p.pk, "available_quantity", "999").status_code == 400
    assert _post(p.pk, "status", "ended").status_code == 400
    p.refresh_from_db()
    assert p.available_quantity == 5
