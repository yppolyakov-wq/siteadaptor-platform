"""UX-D D1.3: «Neue Buchung» шторкой — предзаполнение, ошибки в шторке, успех → бронь."""

import json
import re
import uuid
from datetime import timedelta

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.stays import views
from apps.stays.models import Room, StayBooking
from apps.stays.tests.test_z5_front_desk import D0, _unit, _user
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _get(data=None, drawer=True):
    extra = {"HTTP_X_SF_DRAWER": "1"} if drawer else {}
    req = RequestFactory().get("/dashboard/stays/neu/", data or {}, **extra)
    req.user = _user()
    req.tenant = TenantFactory.build(disabled_modules=[])
    return views.stay_new(req)


def _post(data, drawer=True):
    extra = {"HTTP_X_SF_DRAWER": "1"} if drawer else {}
    req = RequestFactory().post("/dashboard/stays/new/", data, **extra)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _user()
    req.tenant = TenantFactory.build(disabled_modules=[])
    return views.stay_create(req)


def test_fragment_prefills_unit_dates_and_room():
    unit = _unit()
    room = Room.objects.create(unit=unit, number="101")
    resp = _get({"unit": str(unit.pk), "arrival": D0.isoformat(), "room": str(room.pk)})
    html = resp.content.decode()
    assert resp["X-Sf-Fragment"] == "1" and "<html" not in html
    assert 'data-drawer-title="Neue Buchung"' in html
    assert f'<option value="{unit.pk}" selected>' in html
    assert f'value="{D0.isoformat()}"' in html
    assert f'value="{(D0 + timedelta(days=1)).isoformat()}"' in html  # выезд = заезд + 1
    assert f'value="{room.pk}" data-unit="{unit.pk}" selected' in html
    assert "data-drawer-form" in html and 'data-drawer-after="close"' in html


@pytest.mark.parametrize(
    "junk",
    [{"unit": "<script>"}, {"arrival": "2026-13-45"}, {"room": "1 OR 1=1"}, {"unit": "x" * 500}],
)
def test_junk_prefill_is_ignored(junk):
    _unit()
    resp = _get(junk)
    html = resp.content.decode()
    assert resp.status_code == 200 and "<script>" not in html and "1 OR 1=1" not in html
    assert " selected>" not in html.split('id="walkin-unit"', 1)[1].split("</select>", 1)[0]


def test_fragment_has_no_scripts_or_inline_handlers():
    _unit()
    html = _get().content.decode()
    assert "<script" not in html
    assert not re.search(r"\son[a-z]+=", html)


def test_error_in_drawer_returns_the_form_with_what_was_typed():
    unit = _unit(quantity=1)
    data = {
        "unit": str(unit.pk),
        "arrival": D0.isoformat(),
        "departure": D0.isoformat(),  # 0 Nächte → ошибка
        "name": "Frau Kühn",
        "phone": "+49 170 123",
        "erw": "3",
        "note": "Spät da",
        "auto_rabatt_present": "1",
        "next": "/dashboard/verkaeufe/?tab=stay",
    }
    resp = _post(data)
    html = resp.content.decode()
    assert resp.status_code == 200 and resp["X-Sf-Fragment"] == "1"
    assert json.loads(resp["X-Sf-Messages"])[0]["level"] == "error"
    assert 'value="Frau Kühn"' in html and 'value="+49 170 123"' in html
    assert 'value="3"' in html and "Spät da" in html
    # снятый «Automatische Rabatte» остаётся снятым, «Mehr» раскрыт — видно, что изменено
    assert 'name="auto_rabatt" value="1" checked' not in html
    assert not StayBooking.objects.exists()


def test_error_without_js_keeps_the_old_redirect():
    unit = _unit()
    resp = _post(
        {"unit": str(unit.pk), "arrival": "x", "departure": "y", "next": "/dashboard/"},
        drawer=False,
    )
    assert resp.status_code == 302 and resp.url == "/dashboard/"


def test_success_in_drawer_opens_the_new_booking():
    unit = _unit()
    resp = _post(
        {
            "unit": str(unit.pk),
            "arrival": D0.isoformat(),
            "departure": (D0 + timedelta(days=2)).isoformat(),
            "name": "Gast",
            "next": "/dashboard/verkaeufe/?tab=stay",
        }
    )
    data = json.loads(resp.content)
    booking = StayBooking.objects.get()
    assert data["ok"] is True and data["open"] == f"/dashboard/stays/buchung/{booking.pk}/"
    assert data["navigate"] is False


def test_block_dates_in_drawer_closes_with_message():
    unit = _unit()
    resp = _post(
        {
            "unit": str(unit.pk),
            "arrival": D0.isoformat(),
            "departure": (D0 + timedelta(days=2)).isoformat(),
            "name": "Renovierung",
            "mode": "block",
            "next": "/dashboard/verkaeufe/?tab=stay",
        }
    )
    data = json.loads(resp.content)
    assert data["ok"] is True and data["open"] == "" and data["messages"]


def test_page_without_drawer_is_still_the_full_page():
    _unit()
    html = _get(drawer=False).content.decode()
    assert "<html" in html and 'id="walkin-form"' in html


def test_stay_create_drawer_aware_is_innermost():
    from apps.core import drawer

    code = drawer.drawer_aware(lambda r: r).__code__
    chain = [views.stay_create]
    while hasattr(chain[-1], "__wrapped__"):
        chain.append(chain[-1].__wrapped__)
    assert chain[-2].__code__ is code


def test_unknown_unit_uuid_is_ignored():
    _unit()
    html = _get({"unit": str(uuid.uuid4())}).content.decode()
    select = html.split('id="walkin-unit"', 1)[1].split("</select>", 1)[0]
    assert select.count(" selected>") == 1 and '<option value="" disabled selected>' in select


def test_error_is_tied_to_its_field():
    """ECC a11y D1.3: ошибка сервера подсвечивает поле (aria-invalid + describedby),
    шторка ставит туда фокус; поле из свёрнутого «Mehr» раскрывает блок."""
    unit = _unit()
    room = Room.objects.create(unit=unit, number="7")
    resp = _post(
        {
            "unit": str(unit.pk),
            "room": str(room.pk),
            "rooms": "2",
            "arrival": D0.isoformat(),
            "departure": (D0 + timedelta(days=1)).isoformat(),
        }
    )
    html = resp.content.decode()
    assert 'aria-invalid="true" aria-describedby="walkin-rooms-err"' in html
    assert 'id="walkin-rooms-err"' in html
    assert re.search(r"<details[^>]*\sopen>", html)


def test_stale_unit_in_link_is_not_silently_replaced():
    """ECC django D1.3: неизвестная категория → пусто (браузер иначе выбрал бы первую)."""
    unit = _unit()
    other = _unit()
    other.is_active = False
    other.save(update_fields=["is_active"])
    html = _get({"unit": str(other.pk), "arrival": D0.isoformat()}).content.decode()
    select = html.split('id="walkin-unit"', 1)[1].split("</select>", 1)[0]
    assert '<option value="" disabled selected>' in select and str(unit.pk) in select
    assert f'value="{unit.pk}" selected' not in select


def test_danger_confirm_takes_custom_texts_for_discard():
    from pathlib import Path

    js = (Path(__file__).resolve().parents[3] / "static/js/cabinet.js").read_text()
    assert "window.sfDangerConfirm = function (label, opts)" in js
    assert "data-drawer-discard-yes" in js
