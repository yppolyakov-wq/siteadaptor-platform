"""UX-D D1.2: бронь в шторке + три скрытых дефекта, найденных разведкой плана.

1. «Als bezahlt markieren» с полной карточки → 404 (`…/buchung/<pk>/&buchung=`).
2. Формы фрагмента брали `next` с `&box=1` → после POST — голый фрагмент без хрома.
3. Шторка — фрагмент, а не целая страница карточки сделки.
"""

import json

import pytest
from django.urls import resolve

from apps.stays import views
from apps.stays.tests.test_belegungsplan import D0, _book, _req, _unit

pytestmark = pytest.mark.django_db


def _detail(booking, data=None, **kw):
    req = _req(path=f"/dashboard/stays/buchung/{booking.pk}/", data=data)
    req.META.update(kw)
    from apps.tenants.tests.factories import TenantFactory

    req.tenant = TenantFactory.build(business_type="hotel")
    return views.booking_detail(req, pk=booking.pk)


def test_box_fragment_is_the_drawer_not_the_full_card():
    booking = _book(_unit(), 1, 4)
    html = _detail(
        booking, data={"box": "1", "next": "/dashboard/verkaeufe/?tab=stay"}
    ).content.decode()
    assert "<html" not in html and "navpal" not in html
    assert f'data-drawer-title="Buchung {booking.reference_code}"' in html
    assert 'value="update"' in html and "data-drawer-form" in html
    assert f'href="/dashboard/stays/buchung/{booking.pk}/"' in html  # полная карточка
    # формы шторки возвращают на страницу продаж, а не на сам фрагмент
    assert "box=1" not in html.split('name="next"', 1)[1].split(">", 1)[0]
    assert 'name="next" value="/dashboard/verkaeufe/?tab=stay"' in html


def test_drawer_get_by_header_is_a_marked_fragment():
    """Шторка грузит фрагмент заголовком X-Sf-Drawer; ответ помечен X-Sf-Fragment
    (без метки клиент его не вставит) и не кэшируется."""
    booking = _book(_unit(), 1, 4)
    resp = _detail(booking, HTTP_X_SF_DRAWER="1")
    assert resp["X-Sf-Fragment"] == "1" and "no-store" in resp["Cache-Control"]
    assert "<html" not in resp.content.decode()


def test_box_fragment_rejects_foreign_next():
    booking = _book(_unit(), 1, 4)
    html = _detail(booking, data={"box": "1", "next": "//evil.example/x"}).content.decode()
    assert "evil.example" not in html


def test_mark_paid_from_full_card_redirects_to_a_real_url():
    """Дефект 1: next без `?` + `&buchung=` → 404. Замок красный до правки."""
    booking = _book(_unit(), 1, 4)
    detail = f"/dashboard/stays/buchung/{booking.pk}/"
    req = _req(
        method="post",
        path=f"/dashboard/stays/{booking.pk}/aktion/",
        data={"action": "mark_paid", "next": detail},
    )
    resp = views.stay_action(req, pk=booking.pk)
    assert resp.status_code == 302
    assert "&buchung" not in resp.url
    resolve(resp.url.split("?", 1)[0])  # адрес существует


def test_update_respects_next():
    unit = _unit()
    booking = _book(unit, 1, 4)
    req = _req(
        method="post",
        path=f"/dashboard/stays/{booking.pk}/aktion/",
        data={
            "action": "update",
            "next": "/dashboard/verkaeufe/?tab=stay",
            "unit": str(unit.pk),
            "arrival": (D0.replace(day=2)).isoformat(),
            "departure": (D0.replace(day=5)).isoformat(),
            "adults": "2",
        },
    )
    resp = views.stay_action(req, pk=booking.pk)
    assert resp.status_code == 302
    assert resp.url.startswith("/dashboard/verkaeufe/?") and f"buchung={booking.pk}" in resp.url


def test_drawer_post_gets_json_with_messages():
    booking = _book(_unit(), 1, 4)
    req = _req(
        method="post",
        path=f"/dashboard/stays/{booking.pk}/aktion/",
        data={"action": "mark_paid", "next": "/dashboard/verkaeufe/?tab=stay"},
    )
    req.META["HTTP_X_SF_DRAWER"] = "1"
    resp = views.stay_action(req, pk=booking.pk)
    assert resp["Content-Type"].startswith("application/json")
    data = json.loads(resp.content)
    assert data["ok"] is True and data["messages"]
    # без заголовка ответ прежний (редирект) — сайт работает и без JS
    req2 = _req(method="post", path="/x/", data={"action": "mark_paid", "next": "/dashboard/"})
    assert views.stay_action(req2, pk=booking.pk).status_code == 302
