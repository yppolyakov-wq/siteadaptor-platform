"""KA-H11 (аудит KA-9 №11, №13).

§312j(3) BGB: кнопка, которой клиент берёт на себя ОБЯЗАННОСТЬ ПЛАТИТЬ, должна
прямо это говорить — «Jetzt buchen» / «Weiter zur Zahlung» не достаточно (EuGH
C-249/21: и при оплате на месте). Бесплатная бронь сохраняет прежний текст.

ODR-платформа ЕС закрыта 20.07.2025 — ссылка на неё в Impressum платформы
вводила бы в заблуждение."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.utils import translation

TEMPLATES = Path(__file__).resolve().parents[3] / "templates"


def _render(name, **ctx):
    with translation.override("de"):
        return render_to_string(name, ctx, request=RequestFactory().get("/"))


@pytest.mark.django_db
@pytest.mark.parametrize(
    "ctx,binding",
    [
        ({"deposit_required": True}, True),
        ({"service": SimpleNamespace(price_cents=2500)}, True),
        ({}, False),  # Tisch ohne Preis — unverbindlich, Text bleibt
    ],
)
def test_slots_box_button(ctx, binding, settings):
    import uuid
    from datetime import datetime, timedelta

    settings.ROOT_URLCONF = "config.urls_tenant"
    start = datetime(2026, 11, 2, 12, 0)
    body = _render(
        "storefront/_booking_slots_box.html",
        resource=SimpleNamespace(pk=uuid.uuid4()),
        selected=(start, start + timedelta(hours=1)),
        **ctx,
    )
    assert "<button" in body
    assert ("Zahlungspflichtig buchen" in body) is binding


def test_binding_wording_in_paid_flows():
    for name in (
        "storefront/_buybox_stay_form.html",
        "storefront/_buybox_service_form.html",
        "storefront/_booking_slots_box.html",
        "storefront/event_detail.html",
    ):
        src = (TEMPLATES / name).read_text()
        assert "Zahlungspflichtig buchen" in src, name
        assert "Continue to payment" not in src and "Book & pay" not in src, name
    assert "Zahlungspflichtig bestellen" in (TEMPLATES / "storefront/gift_voucher.html").read_text()


def test_german_wording_is_literal():
    with translation.override("de"):
        assert translation.gettext("Zahlungspflichtig buchen") == "Zahlungspflichtig buchen"


def test_no_odr_link_anywhere():
    hits = [str(p) for p in TEMPLATES.rglob("*.html") if "consumers/odr" in p.read_text()]
    assert hits == []
    impressum = (TEMPLATES / "tenants/legal_impressum.html").read_text()
    assert "Verbraucherschlichtungsstelle" in impressum
