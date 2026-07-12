"""FB-4a/FB-4b: свои имена статусов (кабинет-отображение) — generic по kind.

Ключевой инвариант: кастом-имена показываем ТОЛЬКО на доске/экранах кабинета
(transaction_for с labels), а клиентский аккаунт (без labels) — дефолт get_status_display.
FSM/переходы/письма/витрину не трогаем; хранение presence-minimal (golden-паритет).
"""

import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory
from django.utils import timezone

from apps.core import status_labels, transactions
from apps.core.views import status_labels_save
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _post(path, data, tenant, user=None):
    req = RequestFactory().post(path, data)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    req.user = user or get_user_model()(is_active=True)
    return req


def _make_stay():
    from apps.stays import services
    from apps.stays.models import StayUnit

    unit = StayUnit.objects.create(name=f"Zimmer {uuid.uuid4().hex[:6]}", price_cents=8000)
    arrival = timezone.localdate() + timedelta(days=10)
    return services.book_stay(
        unit, arrival=arrival, departure=arrival + timedelta(days=2), name="Gast"
    )


# --- generic helper ----------------------------------------------------------


def test_custom_labels_and_rows_defaults():
    t = TenantFactory(site_config={})
    assert status_labels.custom_labels(t, "booking") == {}
    rows = status_labels.label_rows(t, "booking", [("pending", "Pending"), ("confirmed", "Ok")])
    assert rows == [("pending", "Pending", ""), ("confirmed", "Ok", "")]


def test_save_labels_targeted_and_presence_minimal():
    t = TenantFactory(site_config={"foo": 1})
    status_labels.save_labels(
        t, "booking", ["pending", "confirmed"], _post("/x", {"label_pending": "Angefragt"}, t)
    )
    t.refresh_from_db()
    assert t.site_config["status_labels"]["booking"] == {"pending": "Angefragt"}
    assert t.site_config["foo"] == 1  # прочие ключи целы
    # reset (пусто) снимает kind и весь ключ status_labels (presence-minimal)
    status_labels.save_labels(t, "booking", ["pending", "confirmed"], _post("/x", {}, t))
    t.refresh_from_db()
    assert "status_labels" not in t.site_config


def test_save_labels_keeps_other_kind():
    t = TenantFactory(site_config={})
    status_labels.save_labels(t, "order", ["new"], _post("/x", {"label_new": "Neu!"}, t))
    status_labels.save_labels(
        t, "booking", ["pending"], _post("/x", {"label_pending": "Angefragt"}, t)
    )
    t.refresh_from_db()
    assert t.site_config["status_labels"]["order"] == {"new": "Neu!"}
    assert t.site_config["status_labels"]["booking"] == {"pending": "Angefragt"}


# --- board (кабинет) vs клиентский аккаунт -----------------------------------


def test_transaction_for_applies_labels_only_when_passed():
    stay = _make_stay()
    labels = {stay.status: "Reserviert ⭐"}
    assert transactions.transaction_for("stay", stay, labels).status_label == "Reserviert ⭐"
    # без labels (клиентский аккаунт) — дефолт get_status_display, кастом не течёт
    assert transactions.transaction_for("stay", stay).status_label == stay.get_status_display()


# --- normalize + публичный аксессор ------------------------------------------


def test_normalize_status_labels_booking_stay_and_junk():
    out = siteconfig.normalize_status_labels(
        {
            "booking": {"pending": "X", "bogus": "Y"},
            "stay": {"confirmed": "Z"},
            "nope": {"a": "b"},
        }
    )
    assert out == {"booking": {"pending": "X"}, "stay": {"confirmed": "Z"}}


def test_status_label_statuses_public():
    assert siteconfig.status_label_statuses("booking") == (
        "pending",
        "confirmed",
        "fulfilled",
        "cancelled",
        "no_show",
    )
    assert siteconfig.status_label_statuses("nope") is None


# --- generic view ------------------------------------------------------------


def test_status_labels_save_view_saves_and_redirects():
    t = TenantFactory(site_config={})
    req = _post(
        "/dashboard/status-labels/stay/",
        {"label_pending": "Angefragt", "next": "/dashboard/stays/"},
        t,
    )
    resp = status_labels_save(req, "stay")
    assert resp.status_code == 302 and resp.url == "/dashboard/stays/"
    t.refresh_from_db()
    assert t.site_config["status_labels"]["stay"] == {"pending": "Angefragt"}


def test_status_labels_save_view_unknown_kind_404():
    t = TenantFactory(site_config={})
    with pytest.raises(Http404):
        status_labels_save(_post("/x", {}, t), "nope")


def test_status_labels_save_view_bad_next_falls_back_to_board():
    t = TenantFactory(site_config={})
    req = _post("/x", {"label_new": "Neu", "next": "https://evil.example/"}, t)
    resp = status_labels_save(req, "order")
    assert resp.status_code == 302 and resp.url.startswith("/")  # не открытый редирект
