"""UA3-1 слайс 2 (шаг 0): характеризационные замки buy-box акции ДО свода на единый
`_buybox.html` — reserve-форма и sold-out→waitlist байт-в-байт (план
docs/ua3-1-buybox-plan-2026-07-02.md §4)."""

import re

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.promotions import public_views
from apps.promotions.tests.factories import PromotionFactory

pytestmark = pytest.mark.django_db


def form_block(body, action_attr):
    """Единственный <form>…</form> с этим action= в открывающем теге."""
    forms = re.findall(r"<form[^>]*>.*?</form>", body, flags=re.S)
    hits = [f for f in forms if action_attr in f[: f.index(">")]]
    assert len(hits) == 1, f"{len(hits)} forms with {action_attr}"
    return hits[0]


def field_names(form_html):
    """Точный набор name= полей формы (input/select/textarea, включая hidden)."""
    return set(re.findall(r'name="([^"]+)"', form_html))


def _detail(promo):
    request = RequestFactory().get(f"/p/{promo.pk}/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    return public_views.promotion_detail(request, pk=promo.pk).content.decode()


def test_reserve_form_exact_fields():
    promo = PromotionFactory(status="active", available_quantity=5)
    body = _detail(promo)
    form = form_block(body, f'action="/p/{promo.pk}/reserve/"')
    assert field_names(form) == {
        "csrfmiddlewaretoken",
        "website",  # honeypot (offscreen)
        "form_token",  # идемпотентность сабмита (hidden)
        "channel",  # атрибуция ?ch= (hidden)
        "name",
        "email",
        "phone",
        "quantity",
    }
    assert f"/p/{promo.pk}/waitlist/" not in body  # waitlist только при sold-out


def test_sold_out_swaps_reserve_for_waitlist():
    promo = PromotionFactory(status="active", available_quantity=0)
    body = _detail(promo)
    form = form_block(body, f'action="/p/{promo.pk}/waitlist/"')
    assert field_names(form) == {"csrfmiddlewaretoken", "website", "name", "email"}
    assert f"/p/{promo.pk}/reserve/" not in body  # reserve-формы нет
