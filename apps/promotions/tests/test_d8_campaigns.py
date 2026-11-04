"""UX-D D8.2: Kampagnen — «＋ New campaign» шторкой, авто-рассылки в Einstellungen.

План — docs/ux-d8-archetype-parity-plan-2026-11-04.md. На рабочем экране кампаний —
только список и сводка автоматики; формы прежние (W0), старые POST работают."""

import json
import re
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core.models import Membership
from apps.promotions import campaign_pages, views
from apps.promotions.models import CouponCampaign
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(path, method="get", data=None, drawer=False):
    extra = {"HTTP_X_SF_DRAWER": "1"} if drawer else {}
    req = getattr(RequestFactory(), method)(path, data or {}, **extra)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    tag = uuid.uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(username=f"u-{tag}", password="pw12345678")
    Membership.objects.get_or_create(user=req.user, defaults={"role": Membership.ROLE_OWNER})
    req.tenant = TenantFactory.build(disabled_modules=[])
    req.build_absolute_uri = lambda p="/": "http://laden.test" + p
    return req


_VALID = {
    "name": "VIP-Herbst",
    "tag": "VIP",
    "discount_percent": "15",
    "valid_days": "30",
    "subject": "Ihr Gutschein",
    "body": "",
}


def test_list_has_no_open_forms_only_list_and_automation_summary():
    html = views.coupon_campaigns(_req("/promotions/kampagnen/")).content.decode()
    # ни формы создания, ни форм автоматики на рабочем экране
    assert 'name="subject"' not in html and 'name="inactive_days"' not in html
    assert 'value="winback"' not in html and 'value="birthday"' not in html
    assert re.search(r'<a href="/promotions/kampagnen/neu/" data-drawer', html)
    assert "data-campaign-automation" in html
    assert 'href="/promotions/kampagnen/automatisch/"' in html


def test_new_campaign_fragment_and_create():
    resp = campaign_pages.campaign_new(_req("/promotions/kampagnen/neu/", drawer=True))
    html = resp.content.decode()
    assert resp["X-Sf-Fragment"] == "1" and "<script" not in html
    assert "data-drawer-form" in html and 'data-drawer-after="close"' in html
    resp = campaign_pages.campaign_new(
        _req(
            "/promotions/kampagnen/neu/",
            "post",
            {**_VALID, "next": "/promotions/kampagnen/"},
            drawer=True,
        )
    )
    assert json.loads(resp.content)["ok"] is True
    camp = CouponCampaign.objects.get(name="VIP-Herbst")
    assert camp.tag == "vip" and camp.discount_percent == 15
    assert camp.status == CouponCampaign.STATUS_DRAFT


def test_new_campaign_errors_stay_in_the_drawer_with_input():
    data = {**_VALID, "valid_days": "999"}
    resp = campaign_pages.campaign_new(
        _req("/promotions/kampagnen/neu/", "post", data, drawer=True)
    )
    html = resp.content.decode()
    assert resp.status_code == 200 and resp["X-Sf-Fragment"] == "1"
    assert 'id="id_valid_days_errors"' in html
    assert 'value="VIP-Herbst"' in html  # ввод не потерян
    assert not CouponCampaign.objects.exists()


def test_new_campaign_needs_a_discount_shown_as_form_error():
    data = {k: v for k, v in _VALID.items() if k != "discount_percent"}
    resp = campaign_pages.campaign_new(
        _req("/promotions/kampagnen/neu/", "post", data, drawer=True)
    )
    assert 'role="alert"' in resp.content.decode()
    assert not CouponCampaign.objects.exists()


def test_new_campaign_without_js_redirects_to_list():
    resp = campaign_pages.campaign_new(_req("/promotions/kampagnen/neu/", "post", _VALID))
    assert resp.status_code == 302 and resp.url == "/promotions/kampagnen/"


def test_crm_tag_prefills_the_new_campaign():
    html = campaign_pages.campaign_new(
        _req("/promotions/kampagnen/neu/?tag=stammkunde")
    ).content.decode()
    assert 'value="stammkunde"' in html
    old = views.coupon_campaigns(_req("/promotions/kampagnen/?tag=stammkunde"))
    assert old.status_code == 302 and old.url == "/promotions/kampagnen/neu/?tag=stammkunde"


def test_automation_screen_saves_winback_and_birthday():
    campaign_pages.campaign_automation(
        _req(
            "/promotions/kampagnen/automatisch/",
            "post",
            {
                "action": "winback",
                "enabled": "1",
                "inactive_days": "45",
                "discount_percent": "20",
                "valid_days": "21",
                "subject": "Kommen Sie wieder",
            },
        )
    )
    wb = CouponCampaign.objects.get(kind=CouponCampaign.KIND_AUTO_WINBACK)
    assert wb.status == CouponCampaign.STATUS_ACTIVE and wb.inactive_days == 45
    campaign_pages.campaign_automation(
        _req(
            "/promotions/kampagnen/automatisch/",
            "post",
            {"action": "birthday", "discount_percent": "12", "valid_days": "14"},
        )
    )
    bd = CouponCampaign.objects.get(kind=CouponCampaign.KIND_BIRTHDAY)
    assert bd.status == CouponCampaign.STATUS_PAUSED and bd.discount_percent == 12
    html = campaign_pages.campaign_automation(
        _req("/promotions/kampagnen/automatisch/")
    ).content.decode()
    assert 'value="Kommen Sie wieder"' in html and 'value="12"' in html


def test_automation_rejects_garbage_numbers():
    campaign_pages.campaign_automation(
        _req(
            "/promotions/kampagnen/automatisch/",
            "post",
            {"action": "winback", "inactive_days": "abc", "discount_percent": "10"},
        )
    )
    wb = CouponCampaign.objects.get(kind=CouponCampaign.KIND_AUTO_WINBACK)
    assert wb.inactive_days is None or wb.inactive_days != 0  # ничего не записано мусором
    assert wb.status == CouponCampaign.STATUS_PAUSED


def test_automation_lives_in_settings_navigation():
    from apps.core import nav_registry

    entry = next(e for e in nav_registry.ENTRIES if e.url_name == "promotions:campaign-automation")
    assert entry.hub == "settings"


def test_drawer_from_crm_navigates_to_the_draft_list():
    """Шторка, открытая из CRM, после сохранения ведёт к черновику (navigate), а не
    оставляет на CRM с одним тостом. Чужой next не принимается."""
    resp = campaign_pages.campaign_new(
        _req("/promotions/kampagnen/neu/", "post", {**_VALID, "next": "/crm/"}, drawer=True)
    )
    data = json.loads(resp.content)
    assert data["navigate"] is True and data["location"] == "/promotions/kampagnen/"
    resp = campaign_pages.campaign_new(
        _req(
            "/promotions/kampagnen/neu/",
            "post",
            {**_VALID, "name": "Zwei", "next": "//evil.example/"},
            drawer=True,
        )
    )
    data = json.loads(resp.content)
    assert "evil" not in json.dumps(data)  # чужой адрес не попадает никуда
    assert CouponCampaign.objects.filter(name="Zwei").exists()


def test_blank_subject_keeps_the_previous_one():
    campaign_pages.campaign_automation(
        _req(
            "/promotions/kampagnen/automatisch/",
            "post",
            {"action": "winback", "subject": "   ", "discount_percent": "10"},
        )
    )
    wb = CouponCampaign.objects.get(kind=CouponCampaign.KIND_AUTO_WINBACK)
    assert wb.subject == campaign_pages.WINBACK_SUBJECT
