"""UX-D D6.1: Zusatzleistungen — список строками, «＋» шторкой, страница допа.

Раньше: у каждой строки 4 формы, создание (13 полей) раскрыто, а ПРАВИТЬ доп после
создания было нельзя вовсе."""

import json
import re
import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory

from apps.core import extras_pages as xp
from apps.core import views as core_views
from apps.core.models import Extra, Membership
from apps.core.tests.form_post import form_post
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(path="/dashboard/extras/", method="get", data=None, drawer=False):
    extra = {"HTTP_X_SF_DRAWER": "1"} if drawer else {}
    req = getattr(RequestFactory(), method)(path, data or {}, **extra)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    tag = uuid.uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(username=f"u-{tag}", password="pw12345678")
    Membership.objects.get_or_create(user=req.user, defaults={"role": Membership.ROLE_OWNER})
    req.tenant = TenantFactory.build(business_type="hotel", disabled_modules=[])
    return req


def _page(extra, **kw):
    return xp.extra_edit(_req(f"/dashboard/extras/{extra.pk}/", **kw), pk=extra.pk)


# --- список -------------------------------------------------------------------------


def test_list_rows_have_no_inputs_and_link_to_the_page():
    a = Extra.objects.create(label="Frühstück", price_cents=1200)
    Extra.objects.create(label="Parkplatz", price_cents=800, is_active=False)
    html = core_views.extras_view(_req()).content.decode()
    rows = re.findall(r"<a [^>]*data-extra-row>.*?</a>", html, re.S)
    assert len(rows) == 2
    for row in rows:
        assert "<input" not in row and "<form" not in row and "<select" not in row
    assert f'href="/dashboard/extras/{a.pk}/"' in html
    assert re.search(r'<a href="/dashboard/extras/neu/" data-drawer', html)
    assert 'name="action" value="add"' not in html  # формы создания на списке больше нет


# --- шторка «＋ Zusatzleistung» ------------------------------------------------------


def test_new_fragment_is_marked_and_has_no_scripts():
    resp = xp.extra_new(_req("/dashboard/extras/neu/", drawer=True))
    html = resp.content.decode()
    assert resp["X-Sf-Fragment"] == "1" and "<script" not in html
    assert not re.search(r"\son[a-z]+=", html)
    assert "data-drawer-title=" in html and "data-drawer-form" in html


def test_create_in_drawer_navigates_to_the_page():
    resp = xp.extra_new(
        _req(
            "/dashboard/extras/neu/",
            "post",
            {
                "label": "Frühstück",
                "price": "1.234,50",
                "scope": "stays",
                "per_night": "on",
                "next": "/dashboard/extras/",
            },
            drawer=True,
        )
    )
    x = Extra.objects.get()
    assert (x.price_cents, x.scope, x.per_night) == (123450, "stays", True)
    data = json.loads(resp.content)
    assert data["ok"] is True and data["navigate"] is True
    assert data["location"] == f"/dashboard/extras/{x.pk}/"


@pytest.mark.parametrize(
    "data, field",
    [({"label": " "}, "label"), ({"label": "A", "price": "abc"}, "price")],
)
def test_new_errors_are_at_the_field_and_input_kept(data, field):
    resp = xp.extra_new(_req("/dashboard/extras/neu/", "post", {"scope": "stays", **data}, True))
    html = resp.content.decode()
    assert resp.status_code == 200 and resp["X-Sf-Fragment"] == "1"
    assert f'id="extra-new-{field}-err"' in html and 'value="stays" selected' in html
    assert not Extra.objects.exists()


def test_new_without_js_redirects_to_the_page():
    resp = xp.extra_new(_req("/dashboard/extras/neu/", "post", {"label": "Sauna", "price": "5"}))
    assert resp.status_code == 302 and resp.url == f"/dashboard/extras/{Extra.objects.get().pk}/"


def test_drawer_aware_is_innermost_and_permissions_match_the_list():
    from apps.core import drawer, view_perms

    code = drawer.drawer_aware(lambda r: r).__code__
    chain = [xp.extra_new]
    while hasattr(chain[-1], "__wrapped__"):
        chain.append(chain[-1].__wrapped__)
    assert chain[-2].__code__ is code
    assert view_perms.RULES["extra-new"] == view_perms.RULES["extras"]
    assert view_perms.RULES["extra-edit"] == view_perms.RULES["extras"]


# --- страница допа ------------------------------------------------------------------


def test_page_round_trip_keeps_every_field():
    """W0: Save формы как она нарисована не меняет ни одного поля."""
    x = Extra.objects.create(
        label="Frühstück",
        price_cents=1250,
        scope="stays",
        per_night=True,
        vat_rate=Decimal("19.00"),
        tracker=Extra.TRACKER_POOL,
        pool_size=6,
    )
    html = _page(x).content.decode()
    data = form_post(html, "extra-form")[0]
    _page(x, method="post", data=data)
    x.refresh_from_db()
    assert (x.label, x.price_cents, x.scope, x.per_night) == ("Frühstück", 1250, "stays", True)
    assert (x.vat_rate, x.tracker, x.pool_size) == (Decimal("19.00"), "pool", 6)


def test_page_edits_price_and_tracker():
    x = Extra.objects.create(label="Leihrad", price_cents=1000)
    data = form_post(_page(x).content.decode(), "extra-form")[0]
    data.update({"price": "24,00", "tracker": "pool", "pool_size": "4"})
    resp = _page(x, method="post", data=data)
    x.refresh_from_db()
    assert resp.status_code == 302 and (x.price_cents, x.pool_size) == (2400, 4)


@pytest.mark.parametrize("raw", ["abc", "1,234", "NaN"])
def test_page_garbage_price_is_an_error_without_write(raw):
    x = Extra.objects.create(label="Leihrad", price_cents=1000)
    data = form_post(_page(x).content.decode(), "extra-form")[0]
    data["price"] = raw
    resp = _page(x, method="post", data=data)
    html = resp.content.decode()
    x.refresh_from_db()
    assert resp.status_code == 200 and x.price_cents == 1000
    assert 'id="extra-price-err"' in html and f'value="{raw}"' in html


def test_page_foreign_pk_in_post_is_404():
    x = Extra.objects.create(label="A")
    other = Extra.objects.create(label="B")
    with pytest.raises(Http404):
        _page(x, method="post", data={"action": "delete", "extra": str(other.pk)})
    assert Extra.objects.filter(pk=other.pk).exists()


def test_page_toggle_is_explicit_and_delete_removes():
    x = Extra.objects.create(label="A")
    for _i in range(2):
        _page(x, method="post", data={"action": "toggle", "extra": str(x.pk), "active": "0"})
    x.refresh_from_db()
    assert x.is_active is False
    resp = _page(x, method="post", data={"action": "delete", "extra": str(x.pk)})
    assert resp.status_code == 302 and not Extra.objects.exists()


def test_page_keeps_link_to_an_offer_that_is_no_longer_listed():
    x = Extra.objects.create(label="A", entity_kind="stay", entity_id=str(uuid.uuid4()))
    html = _page(x).content.decode()
    assert f'value="stay:{x.entity_id}" selected' in html


def test_unknown_extra_is_404():
    with pytest.raises(Http404):
        xp.extra_edit(_req(), pk=uuid.uuid4())


def test_delete_button_asks_for_confirmation():
    x = Extra.objects.create(label="A")
    html = _page(x).content.decode()
    form = html.split('value="delete"', 1)[1].split("</form>", 1)[0]
    assert 'data-danger="1"' in form


def test_stock_extra_whose_product_was_deleted_still_saves():
    """W0: товар складского допа удалили (SET_NULL) — правка названия не блокируется."""
    x = Extra.objects.create(label="Wein", tracker=Extra.TRACKER_STOCK)
    data = form_post(_page(x).content.decode(), "extra-form")[0]
    data["label"] = "Wein (Flasche)"
    resp = _page(x, method="post", data=data)
    x.refresh_from_db()
    assert resp.status_code == 302 and x.label == "Wein (Flasche)"


def test_page_error_is_shown_once_at_the_field():
    x = Extra.objects.create(label="Leihrad", price_cents=1000)
    data = form_post(_page(x).content.decode(), "extra-form")[0]
    data["price"] = "abc"
    html = _page(x, method="post", data=data).content.decode()
    assert html.count("Bitte einen Betrag wie 25,00 angeben.") == 1
    assert re.search(r'id="extra-price"[^>]* autofocus aria-invalid="true"', html)
