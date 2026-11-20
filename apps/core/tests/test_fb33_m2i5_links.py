"""FB-33 M2i-5 C4: старый адрес панели «Anfrage-Formular» и ссылки на вкладку «Felder».

Решение владельца (2026-11-20): панель на «Abläufe» сразу заменена ссылкой «In Seitenaufbau
bearbeiten →»; GET старого адреса — 302 на окно (фиксированный путь, без `next`), POST прежний
(замки `test_fb33_m2i5_before`); у полосы заявки главной — ссылка «Felder bearbeiten →».
"""

import pytest

from apps.core import block_window, site_schema
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
WINDOW = "/dashboard/site/aufbau/?seite=anfrage&block=form&tab=felder#schema-panel"


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def test_window_url_is_fixed():
    assert site_schema.form_window_url() == WINDOW


@pytest.mark.parametrize("query", ["", "?next=//evil.com", "?next=/%5Cevil.com&tab=x"])
def test_old_address_get_redirects_to_the_window(query):
    from types import SimpleNamespace

    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.jobs import views

    req = RequestFactory().get("/dashboard/auftraege/anfrage-formular/" + query)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = TenantFactory.build()
    resp = views.anfrage_form_settings(req)
    assert resp.status_code == 302 and resp["Location"] == WINDOW


def _home(jobs=True):
    tenant = TenantFactory(
        business_type="catering",
        disabled_modules=[] if jobs else ["jobs"],
        site_config={"sections": [{"key": "hero"}, {"key": "anfrage", "enabled": True}]},
    )
    return Browser(tenant)


def test_home_band_has_felder_link_to_the_form_window():
    html = _home().get("?seite=home&block=anfrage&tab=felder")
    assert 'data-window-part="formlink"' in html
    assert f'href="{WINDOW.replace("&", "&amp;")}"' in html and "data-form-link" in html
    assert "data-form-felder" not in html  # без дубля вкладки
    assert block_window.PART_TAB["formlink"] == "felder"


def test_no_link_without_jobs():
    html = _home(jobs=False).get("?seite=home&block=anfrage")
    assert "data-form-link" not in html


def test_ablaeufe_hides_the_link_without_website_rights(settings):
    from apps.core.models import Membership
    from apps.core.tests.test_staff_walk import _open, _user

    tenant = TenantFactory(business_type="catering", disabled_modules=[])
    owner = _user(Membership.ROLE_OWNER)
    body = _open("/dashboard/ablaeufe/", tenant, owner).content.decode()
    assert "data-anfrage-form-link" in body
    staff = _user(Membership.ROLE_STAFF)
    Membership.objects.filter(user=staff).update(
        permissions={"add": ["ablaeufe.view"], "remove": ["website.view", "website.edit"]}
    )
    resp = _open("/dashboard/ablaeufe/", tenant, staff)
    assert resp.status_code == 200
    assert "data-anfrage-form-link" not in resp.content.decode()
