"""W10-6: легаси-страницы продаж → 302 на Verkäufe с сохранением GET.

Паритет достигнут ДО схлопывания (аудит-урок): фильтр/поиск заказов — W10-3a,
календарные deep-links — W7c/W10-1, «Heute» с Im Haus — W10-4/W10-6.
events:list / jobs:list / board / stay_new НЕ редиректятся (полные управляющие
экраны и цель «＋»).
"""

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(path, data=None):
    req = RequestFactory().get(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    o = uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(
        username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
    )
    return req


def test_order_list_redirects_with_get_carry():
    from apps.orders import views

    resp = views.order_list(_req("/dashboard/orders/", {"status": "ready", "q": "abc"}))
    assert resp.status_code == 302
    loc = resp["Location"]
    assert loc.startswith("/dashboard/verkaeufe/?")
    assert "tab=order" in loc and "view=liste" in loc
    assert "status=ready" in loc and "q=abc" in loc


def test_booking_calendar_redirects_with_get_carry():
    from apps.booking import views

    resp = views.calendar(_req("/dashboard/booking/", {"tag": "2026-09-01"}))
    assert resp.status_code == 302
    loc = resp["Location"]
    assert "tab=booking" in loc and "view=kalender" in loc and "tag=2026-09-01" in loc


def test_stays_calendar_redirects_with_get_carry():
    from apps.stays import views

    resp = views.calendar(_req("/dashboard/stays/", {"von": "2026-09-01", "q": "Gast"}))
    assert resp.status_code == 302
    loc = resp["Location"]
    assert "tab=stay" in loc and "view=kalender" in loc
    assert "von=2026-09-01" in loc and "q=Gast" in loc


def test_stays_today_redirects_to_heute():
    from apps.stays import views

    resp = views.today_view(_req("/dashboard/stays/heute/"))
    assert resp.status_code == 302
    assert "view=heute" in resp["Location"]


def test_redirect_target_renders_end_to_end():
    """Замок «нет петли»: цель редиректа рендерится 200 с теми же GET."""
    from apps.core import views as core_views
    from apps.core.modules import default_disabled_for
    from apps.stays import views as stays_views
    from apps.tenants.tests.factories import TenantFactory

    resp = stays_views.calendar(_req("/dashboard/stays/", {"von": "2026-09-01"}))
    path, _, qs = resp["Location"].partition("?")
    req = RequestFactory().get(path, dict(p.split("=", 1) for p in qs.split("&")))
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    o = uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(
        username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
    )
    req.tenant = TenantFactory.build(
        business_type="hotel", disabled_modules=list(default_disabled_for("hotel"))
    )
    out = core_views.verkaeufe(req)
    assert out.status_code == 200
    assert "belegungsplan" in out.content.decode()


def test_full_pages_not_redirected():
    """events:list/jobs:list/stay_new остаются страницами (не 302).
    X2b: `board` из списка ВЫШЕЛ — легаси-доска снесена (302 на Verkäufe);
    events/jobs остаются до волны X2c (решение владельца 2026-08-19)."""
    from apps.core import views as core_views
    from apps.core.modules import default_disabled_for
    from apps.tenants.tests.factories import TenantFactory

    req = _req("/dashboard/board/")
    req.tenant = TenantFactory.build(
        business_type="bakery", disabled_modules=list(default_disabled_for("bakery"))
    )
    assert core_views.board(req).status_code == 302  # X2b: снесена

    from apps.stays import views as stays_views

    req = _req("/dashboard/stays/neu/")
    req.tenant = TenantFactory.build(
        business_type="hotel", disabled_modules=list(default_disabled_for("hotel"))
    )
    assert stays_views.stay_new(req).status_code == 200
