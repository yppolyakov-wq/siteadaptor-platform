"""UA3-2 (шаг 0): характеризационные замки двухшагового buy-box номера ДО свода
на контрактный путь `_buybox.html` — точный набор полей POST-формы, action и гейт
«форма только при quote.available» (план docs/ua3-2-two-step-buybox-plan-2026-07-02.md §4)."""

import re
import uuid
from datetime import date, timedelta

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core.models import Extra
from apps.stays import public_views
from apps.stays.models import RatePlan, StayUnit
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

D0 = date(2026, 10, 1)  # в будущем относительно «сегодня» сессии


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def form_block(body, action_attr):
    """Единственный <form>…</form> с этим action= в открывающем теге."""
    forms = re.findall(r"<form[^>]*>.*?</form>", body, flags=re.S)
    hits = [f for f in forms if action_attr in f[: f.index(">")]]
    assert len(hits) == 1, f"{len(hits)} forms with {action_attr}"
    return hits[0]


def field_names(form_html):
    """Точный набор name= полей формы (input/select/textarea, включая hidden)."""
    return set(re.findall(r'name="([^"]+)"', form_html))


def _unit(**kw):
    kw.setdefault("price_cents", 9000)
    return StayUnit.objects.create(name=f"FeWo {uuid.uuid4().hex[:6]}", **kw)


def _dates(nights=3):
    return {"von": D0.isoformat(), "bis": (D0 + timedelta(days=nights)).isoformat()}


def _detail(unit, params=None):
    request = RequestFactory().get(f"/unterkunft/{unit.pk}/", params or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(disabled_modules=[])
    return public_views.unterkunft_unit(request, pk=unit.pk).content.decode()


def test_book_form_base_exact_fields():
    unit = _unit()
    body = _detail(unit, _dates())
    form = form_block(body, f'action="/unterkunft/{unit.pk}/buchen/"')
    assert field_names(form) == {
        "csrfmiddlewaretoken",
        "von",
        "bis",
        "erw",
        "kinder",
        "rooms",
        "voucher_code",
        "website",  # honeypot
        "name",
        "email",
        "phone",
        "note",
    }


def test_book_form_with_rate_extra_embed_fields():
    unit = _unit()
    RatePlan.objects.create(name="Standard")
    Extra.objects.create(label="Frühstück", price_cents=1200, scope="stays", per_night=True)
    body = _detail(unit, {**_dates(), "embed": "1"})
    form = form_block(body, f'action="/unterkunft/{unit.pk}/buchen/"')
    assert field_names(form) == {
        "csrfmiddlewaretoken",
        "rate_plan",  # radio тарифов
        "von",
        "bis",
        "erw",
        "kinder",
        "rooms",
        "embed",  # G10 iframe-carry
        "extra",  # чекбоксы доп-услуг
        "voucher_code",
        "website",
        "name",
        "email",
        "phone",
        "note",
    }


def test_unavailable_range_renders_reason_not_form():
    unit = _unit(min_nights=5)
    body = _detail(unit, _dates(nights=2))  # 2 ночи < min 5
    assert f"/unterkunft/{unit.pk}/buchen/" not in body
    assert "requires at least" in body  # amber-бокс причины min_nights


def test_no_dates_selector_only():
    unit = _unit()
    body = _detail(unit)  # без von/bis — quote нет
    assert f"/unterkunft/{unit.pk}/buchen/" not in body  # POST-формы нет
    assert 'id="buchen"' in body and 'name="von"' in body  # селектор дат на месте
