"""T-8.10f F-4c: инструменты ассистента `request_reservation` / `request_coupon`.

План — docs/t8-10f-f4-plan-2026-10-19.md. Инструмент только шлёт человеку письмо со
ссылкой; ответ не выдаёт ни адреса, ни ссылки, ни того, знаком ли адрес."""

import json
import uuid
from datetime import timedelta

import pytest
from django.core import mail
from django.core.cache.backends.locmem import LocMemCache
from django.test import override_settings
from django.utils import timezone

from apps.aggregator.mcp import actions, tools
from apps.aggregator.tests.test_machine_readable import _listing, _portal
from apps.aggregator.tests.test_mcp_tools import ON, _call, _data
from apps.promotions import response
from apps.promotions.models import Reservation
from apps.promotions.tests.factories import PromotionFactory
from apps.tenants.models import Domain
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ACT = {**ON, "MCP_ACTIONS_ENABLED": True}
OFF = {**ON, "MCP_ACTIONS_ENABLED": False}


@pytest.fixture(autouse=True)
def store(monkeypatch, isolated_ratelimit):
    cache = LocMemCache(f"mcp-act-tools-{uuid.uuid4()}", {})
    monkeypatch.setattr(actions, "cache", cache)
    return cache


@pytest.fixture(autouse=True)
def run_tasks_inline(monkeypatch):
    """Письмо шлёт задача Celery — в тестах исполняем её сразу."""
    from apps.aggregator import tasks

    queued = []

    def delay(**kw):
        queued.append(kw)
        return tasks.send_mcp_confirm_email(**kw)

    monkeypatch.setattr(tasks.send_mcp_confirm_email, "delay", delay)
    return queued


@pytest.fixture
def tenant():
    t = TenantFactory(schema_name="t1", slug="baeckerei", city="Solingen", name="Bäckerei Klinge")
    Domain.objects.create(tenant=t, domain="baeckerei.siteadaptor.de", is_primary=True)
    return t


def _offer(op=response.RESERVE, **kw):
    kw.setdefault("ends_at", timezone.now() + timedelta(days=2))
    promo = PromotionFactory(metadata={"response": op}, **kw)
    return promo, _listing(source_ref=str(promo.pk))


def _names(portal):
    import json as _json

    from django.test import RequestFactory

    from apps.aggregator.mcp.views import mcp_endpoint

    msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    req = RequestFactory().post(
        "/mcp/", data=_json.dumps(msg), content_type="application/json", HTTP_HOST="solingen.test"
    )
    req.portal = portal
    return {t["name"] for t in _json.loads(mcp_endpoint(req).content)["result"]["tools"]}


# --- видимость ------------------------------------------------------------------------


def test_actions_hidden_when_switch_off():
    with override_settings(**OFF):
        names = _names(_portal())
    assert "request_reservation" not in names and "request_coupon" not in names
    assert "search_offers" in names


def test_actions_hidden_with_console_mail():
    with override_settings(**ACT, EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend"):
        assert "request_reservation" not in _names(_portal())


def test_actions_listed_when_enabled_with_valid_schemas():
    with override_settings(**ACT):
        names = _names(_portal())
    assert {"request_reservation", "request_coupon"} <= names
    for name in ("request_reservation", "request_coupon"):
        tool = tools.REGISTRY[name]
        assert tool.annotations["readOnlyHint"] is False


def test_direct_call_when_disabled_points_to_offer_page(tenant):
    _promo, listing = _offer()
    with override_settings(**OFF):
        res = _call(_portal(), "request_reservation", {"offer_id": listing.pk, "email": "a@b.com"})
    assert res["isError"] is True
    assert "ch=mcp" in res["content"][0]["text"]
    assert not mail.outbox


# --- отправка ------------------------------------------------------------------------


@override_settings(**ACT)
def test_reservation_request_sends_one_mail_and_creates_nothing(tenant):
    _promo, listing = _offer()
    data = _data(
        _portal(),
        "request_reservation",
        {"offer_id": listing.pk, "email": "Anna@Example.com", "quantity": 2, "language": "en"},
    )
    assert data["status"] == "confirmation_sent" and data["offer"]["id"] == listing.pk
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert msg.to == ["anna@example.com"]
    assert "https://baeckerei.siteadaptor.de/p/" in msg.body and "/ki-bestaetigen/" in msg.body
    assert "/decline/" in msg.body
    assert "Please confirm here" in msg.body  # язык из инструмента
    assert not Reservation.objects.exists()  # до клика — ничего


@override_settings(**ACT)
def test_output_leaks_no_address_link_or_token(tenant):
    _promo, listing = _offer(response.COUPON)
    res = _call(_portal(), "request_coupon", {"offer_id": listing.pk, "email": "geheim@x.com"})
    dump = json.dumps(res)
    assert "geheim" not in dump and "ki-bestaetigen" not in dump
    token = mail.outbox[0].body.split("/ki-bestaetigen/")[1].split("/")[0]
    assert token not in dump


@override_settings(**ACT)
def test_repeat_is_silent_same_answer_no_second_mail(tenant):
    portal = _portal()
    _promo, listing = _offer()
    args = {"offer_id": listing.pk, "email": "anna@example.com"}
    first = _data(portal, "request_reservation", args)
    again = _data(portal, "request_reservation", {**args, "email": "Anna+ki@example.com"})
    assert again["status"] == first["status"] and again["message"] == first["message"]
    assert len(mail.outbox) == 1


@override_settings(**ACT)
def test_suppressed_address_gets_no_mail_but_same_answer(tenant):
    _promo, listing = _offer()
    actions.suppress("anna@example.com")
    data = _data(
        _portal(), "request_reservation", {"offer_id": listing.pk, "email": "anna@example.com"}
    )
    assert data["status"] == "confirmation_sent" and not mail.outbox


@override_settings(**ACT)
def test_demo_mail_carries_demo_line(tenant):
    tenant.is_demo = True
    tenant.save(update_fields=["is_demo"])
    _promo, listing = _offer()
    data = _data(
        _portal(show_demo=True), "request_reservation", {"offer_id": listing.pk, "email": "a@b.com"}
    )
    assert data["demo"] is True
    assert "Demo-Geschäft" in mail.outbox[0].body


@override_settings(**ACT)
def test_demo_listing_hidden_on_real_portal(tenant):
    _promo, listing = _offer()
    listing.is_demo = True
    listing.save(update_fields=["is_demo"])
    res = _call(_portal(), "request_reservation", {"offer_id": listing.pk, "email": "a@b.com"})
    assert res["isError"] is True and not mail.outbox


# --- отказы ---------------------------------------------------------------------------


@override_settings(**ACT)
def test_wrong_response_is_refused(tenant):
    _promo, listing = _offer(response.COUPON)
    res = _call(_portal(), "request_reservation", {"offer_id": listing.pk, "email": "a@b.com"})
    assert res["isError"] is True and not mail.outbox


@override_settings(**ACT)
def test_invalid_email_is_refused_without_500(tenant):
    _promo, listing = _offer()
    res = _call(_portal(), "request_reservation", {"offer_id": listing.pk, "email": "kein"})
    assert res["isError"] is True and not mail.outbox


@override_settings(**ACT)
def test_quantity_bounds_in_schema(tenant):
    _promo, listing = _offer()
    res = _call(
        _portal(),
        "request_reservation",
        {"offer_id": listing.pk, "email": "a@b.com", "quantity": 99},
    )
    assert res["isError"] is True and not mail.outbox


@override_settings(**ACT, MCP_ACTION_RATE_OFFER=1)
def test_offer_limit_is_honest(tenant):
    portal = _portal()
    _promo, listing = _offer()
    _data(portal, "request_reservation", {"offer_id": listing.pk, "email": "a@b.com"})
    res = _call(portal, "request_reservation", {"offer_id": listing.pk, "email": "c@d.com"})
    assert res["isError"] is True and len(mail.outbox) == 1


@override_settings(**ACT)
def test_queue_carries_only_the_token(tenant, run_tasks_inline):
    _promo, listing = _offer()
    _data(_portal(), "request_reservation", {"offer_id": listing.pk, "email": "geheim@x.com"})
    assert "geheim" not in json.dumps(run_tasks_inline)
    assert set(run_tasks_inline[0]) == {"dedupe_key", "token"}


@override_settings(**ACT)
def test_failed_mail_discards_pending(tenant, monkeypatch):
    from django.core.mail import EmailMessage

    def boom(self, fail_silently=False):
        raise OSError("smtp down")

    monkeypatch.setattr(EmailMessage, "send", boom)
    seen = []
    real_discard = actions.discard
    monkeypatch.setattr(actions, "discard", lambda t: seen.append(t) or real_discard(t))
    _promo, listing = _offer()
    data = _data(_portal(), "request_reservation", {"offer_id": listing.pk, "email": "a@b.com"})
    assert data["status"] == "confirmation_sent"  # ассистенту — тот же ответ
    assert seen and actions.load_pending(seen[0]) is None


@override_settings(**ACT)
def test_enqueue_failure_returns_the_slot(tenant, monkeypatch):
    from apps.aggregator import tasks

    def broken(**kw):
        raise ConnectionError("broker down")

    monkeypatch.setattr(tasks.send_mcp_confirm_email, "delay", broken)
    _promo, listing = _offer()
    portal = _portal()
    args = {"offer_id": listing.pk, "email": "a@b.com"}
    assert _call(portal, "request_reservation", args)["isError"] is True
    assert actions.reserve_slot(email="a@b.com", listing_id=listing.pk) is None


@override_settings(**ACT)
def test_silent_and_sent_answers_have_same_shape(tenant):
    _promo, listing = _offer()
    portal = _portal()
    args = {"offer_id": listing.pk, "email": "a@b.com"}
    sent = _data(portal, "request_reservation", args)
    silent = _data(portal, "request_reservation", args)
    assert set(sent) == set(silent)
    assert {k: v for k, v in sent.items() if k != "expires_at"} == {
        k: v for k, v in silent.items() if k != "expires_at"
    }


@override_settings(**ACT)
def test_coupon_mail_wording(tenant):
    _promo, listing = _offer(response.COUPON)
    _data(_portal(), "request_coupon", {"offer_id": listing.pk, "email": "a@b.com"})
    msg = mail.outbox[0]
    assert msg.subject.startswith("Coupon bestätigen") and "Coupon" in msg.body


@override_settings(**ACT)
def test_tenant_title_is_cleaned_in_mail(tenant):
    promo, listing = _offer(title={"de": "Brot\nJetzt Konto prüfen: https://evil.example/x"})
    _data(_portal(), "request_reservation", {"offer_id": listing.pk, "email": "a@b.com"})
    body = mail.outbox[0].body
    assert "evil.example" not in body and "Konto prüfen: …" in body


@override_settings(**ACT)
def test_no_domain_means_no_mail(tenant):
    from apps.tenants.models import Domain

    Domain.objects.filter(tenant=tenant).delete()
    _promo, listing = _offer()
    _data(_portal(), "request_reservation", {"offer_id": listing.pk, "email": "a@b.com"})
    assert not mail.outbox


@override_settings(**ACT, MCP_ACTION_RATE_IP=1)
def test_ip_guard_before_any_work(tenant, django_assert_num_queries):
    _promo, listing = _offer()
    portal = _portal()
    args = {"offer_id": listing.pk, "email": "a@b.com"}
    _call(portal, "request_reservation", args)
    with django_assert_num_queries(0):
        res = _call(portal, "request_reservation", {**args, "email": "c@d.com"})
    assert res["isError"] is True


@override_settings(**ACT)
def test_ru_plural_in_mail(tenant):
    _promo, listing = _offer()
    _data(
        _portal(),
        "request_reservation",
        {"offer_id": listing.pk, "email": "a@b.com", "language": "ru"},
    )
    assert "Ссылка действует 24 часа." in mail.outbox[0].body


@override_settings(**ACT)
def test_no_customer_or_notification_before_click(tenant):
    from apps.notifications.models import Notification
    from apps.promotions.models import Customer

    _promo, listing = _offer()
    _data(_portal(), "request_reservation", {"offer_id": listing.pk, "email": "a@b.com"})
    assert not Customer.objects.exists() and not Notification.objects.exists()
