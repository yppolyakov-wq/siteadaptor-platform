"""T-8.13a: категория каталога города и признаки — в формах акции (полная, ассистент, старт).

План — docs/t8-13a-city-categories-plan-2026-10-10.md §2.
"""

import pytest
from django.test import RequestFactory

from apps.promotions import quick, views
from apps.promotions.forms import PromotionForm
from apps.promotions.models import Promotion
from apps.promotions.tests.factories import PromotionFactory
from apps.promotions.tests.test_quick_assistant import _attach, _post, _tenant, user  # noqa: F401
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

_BASE = {"title_de": "Deal", "promo_type": "discount", "max_per_customer": 1}


def test_full_form_preselects_suggestion_for_new_promotion():
    tenant = TenantFactory(schema_name="public", slug="cf-new", business_type="friseur")
    form = PromotionForm(tenant=tenant)
    assert form.fields["city_category"].initial == "friseur"
    assert "city_tags" in form.fields


def test_full_form_saves_category_and_tags_and_drops_unknown():
    tenant = TenantFactory(schema_name="public", slug="cf-save")
    form = PromotionForm(
        {**_BASE, "reservation_ttl_hours": 24, "city_category": "cafes", "city_tags": ["vegan"]},
        tenant=tenant,
    )
    assert form.is_valid(), form.errors
    promo = form.save(commit=False)
    assert (promo.city_category, promo.city_tags) == ("cafes", ["vegan"])
    bad = PromotionForm({**_BASE, "reservation_ttl_hours": 24, "city_category": "zzz"})
    assert not bad.is_valid() and "city_category" in bad.errors


def test_full_form_without_field_keeps_stored_choice():
    promo = Promotion(title={"de": "x"}, city_category="schuhe", city_tags=["regional"])
    form = PromotionForm({**_BASE, "reservation_ttl_hours": 24}, instance=promo)
    assert form.is_valid(), form.errors
    saved = form.save(commit=False)
    assert (saved.city_category, saved.city_tags) == ("schuhe", ["regional"])


def test_assistant_stores_category_and_tags(user):  # noqa: F811
    tenant = _tenant("t813-a")
    _post(
        {"title": "Mantel", "city_category": "damenmode", "city_tags": ["regional"]},
        user,
        tenant,
    )
    promo = Promotion.objects.get()
    assert (promo.city_category, promo.city_tags) == ("damenmode", ["regional"])


def test_assistant_page_shows_select_with_suggestion(user):  # noqa: F811
    tenant = _tenant("t813-b")
    tenant.business_type = "cafe"
    tenant.save()
    body = views.promotion_quick(
        _attach(RequestFactory().get("/promotions/schnell/"), user, tenant)
    ).content.decode()
    assert "data-city-category-select" in body
    assert '<option value="cafes" selected' in body
    assert 'data-city-tag="vegan"' in body


def test_repeat_carries_category_and_tags():
    old = PromotionFactory(status="ended", city_category="getraenke", city_tags=["bio"])
    initial = quick.initial_from(old)
    assert initial["city_category"] == "getraenke" and initial["city_tags"] == ["bio"]
