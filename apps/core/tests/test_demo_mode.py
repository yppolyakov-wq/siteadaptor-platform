"""В1 (вариант 1 владельца): демо-бизнес на витрине — плашка «это демо», без онлайн-оплаты,
Vorkasse и счетов, без писем и Telegram. План — docs/backlog-portal-direction-2026-10-16.md §9.
Замки написаны ДО кода."""

from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _detail_html(tenant):
    from apps.promotions import public_views
    from apps.promotions.models import Promotion

    promo = Promotion.objects.create(
        title={"de": "Brot"}, status="active", price_override=Decimal("2.00")
    )
    req = RequestFactory().get(f"/p/{promo.pk}/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    return public_views.promotion_detail(req, pk=promo.pk).content.decode()


# --- (a) плашка ------------------------------------------------------------------


def test_demo_storefront_shows_banner():
    html = _detail_html(TenantFactory.build(business_type="bakery", is_demo=True))
    assert "data-demo-banner" in html
    assert "Bestellungen sind nicht echt" in html


def test_real_storefront_has_no_banner():
    html = _detail_html(TenantFactory.build(business_type="bakery", is_demo=False))
    assert "data-demo-banner" not in html


def test_embed_base_includes_banner():
    src = (Path(settings.BASE_DIR) / "templates/storefront/_embed_base.html").read_text()
    assert "_demo_banner.html" in src


# --- (c) оплата -------------------------------------------------------------------


def test_demo_tenant_offers_only_on_site_payment():
    from apps.core import payment_methods

    tenant = TenantFactory.build(
        is_demo=True,
        vorkasse_enabled=True,
        bank_iban="DE02120300000000202051",
        bank_holder="X",
        invoice_b2b_enabled=True,
        payments_enabled=True,
    )
    assert payment_methods.available(tenant) == [payment_methods.ON_SITE]


def test_demo_tenant_never_keeps_online_payments_on():
    tenant = TenantFactory(schema_name="public", slug="demo-pay", is_demo=True)
    tenant.payments_enabled = True
    tenant.save(update_fields=["payments_enabled"])
    tenant.refresh_from_db()
    assert tenant.payments_enabled is False


def test_real_tenant_keeps_its_payment_settings():
    tenant = TenantFactory(schema_name="public", slug="real-pay", is_demo=False)
    tenant.payments_enabled = True
    tenant.save(update_fields=["payments_enabled"])
    tenant.refresh_from_db()
    assert tenant.payments_enabled is True


# --- (d) письма и Telegram ----------------------------------------------------------


def _notification(**kw):
    from apps.notifications.models import Notification

    defaults = {
        "dedupe_key": f"demo-{kw.get('channel', 'email')}",
        "type": "reservation_confirmed",
        "channel": "email",
        "recipient": "kunde@example.de",
        "subject": "Hallo",
        "payload": {"body": "Text"},
    }
    defaults.update(kw)
    return Notification.objects.create(**defaults)


def test_demo_tenant_sends_no_email(mailoutbox):
    from apps.notifications import tasks

    TenantFactory(schema_name="public", slug="demo-mail", is_demo=True)
    n = _notification()
    tasks.deliver(str(n.pk))
    n.refresh_from_db()
    assert mailoutbox == []
    assert n.status == "failed" and "demo" in n.last_error


def test_demo_tenant_sends_no_telegram(monkeypatch):
    from apps.notifications import adapters, tasks

    sent = []
    monkeypatch.setattr(adapters, "send", lambda notification: sent.append(notification))
    TenantFactory(schema_name="public", slug="demo-tg", is_demo=True)
    n = _notification(channel="telegram", recipient="12345", dedupe_key="demo-tg")
    tasks.deliver(str(n.pk))
    assert sent == []


def test_real_tenant_still_sends_email(mailoutbox):
    from apps.notifications import tasks

    TenantFactory(schema_name="public", slug="real-mail", is_demo=False)
    n = _notification(dedupe_key="real-mail")
    tasks.deliver(str(n.pk))
    n.refresh_from_db()
    assert n.status == "sent"


def test_demo_tenant_gets_no_trial_reminder(mailoutbox):
    from apps.billing import tasks

    tenant = TenantFactory(
        schema_name="public", slug="demo-trial", is_demo=True, owner_email="o@example.de"
    )
    res = tasks.send_trial_reminder.run(tenant_id=tenant.id, days_left=1)
    assert res == {"skipped": True} and mailoutbox == []


def test_demo_cabinet_sends_no_team_invite(mailoutbox):
    from apps.core import team

    req = RequestFactory().post("/", {"email": "neu@example.de"})
    req.tenant = TenantFactory.build(is_demo=True)
    team._send_invite_mail(req, "https://x/join/abc/")
    assert mailoutbox == []
