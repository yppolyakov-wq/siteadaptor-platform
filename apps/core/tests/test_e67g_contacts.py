"""KA-12 E6.7g: право «Kontaktdaten sehen» (kunden.kontakte) действует везде.

Решение владельца: по умолчанию контакты видит вся команда; владелец снимает право
точечно. Без права e-mail/телефон маскируются в списках и карточках, не ищутся и не
перезаписываются формами (ни видимыми, ни подделанным POST)."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import contact_access, permissions
from apps.core.models import Membership
from apps.crm import views as crm_views
from apps.crm.models import Customer
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

NO_CONTACTS = {"remove": ["kunden.kontakte"]}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _user(role=Membership.ROLE_STAFF, perms=None):
    tag = uuid.uuid4().hex[:8]
    user = get_user_model().objects.create_user(username=f"c-{tag}", password="pw12345678")
    Membership.objects.create(user=user, role=role, permissions=perms or {})
    return user


def _req(method, path, data=None, user=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    request.tenant = TenantFactory.build(disabled_modules=[])
    return request


def _customer():
    return Customer.objects.create(
        name="Frau Geheim", email="geheim@beispiel.de", phone="+49 170 1234567"
    )


@pytest.mark.parametrize("role", [Membership.ROLE_STAFF, Membership.ROLE_ADMIN])
def test_team_sees_contacts_by_default(role):
    user = _user(role)
    assert permissions.has_perm(user, "kunden.kontakte")
    assert contact_access.can_see(user)


def test_owner_can_remove_contacts_per_member():
    assert not contact_access.can_see(_user(perms=NO_CONTACTS))


def test_kept_keeps_old_value_without_right():
    c = _customer()
    assert contact_access.kept(_user(perms=NO_CONTACTS), c, "email", "") == "geheim@beispiel.de"
    assert contact_access.kept(_user(), c, "email", "neu@beispiel.de") == "neu@beispiel.de"


def test_crm_list_masks_contacts_without_right():
    _customer()
    body = crm_views.customer_list(_req("get", "/crm/", user=_user(perms=NO_CONTACTS)))
    text = body.content.decode()
    assert "Frau Geheim" in text and "geheim@beispiel.de" not in text
    full = crm_views.customer_list(_req("get", "/crm/", user=_user())).content.decode()
    assert "geheim@beispiel.de" in full


def test_crm_search_by_email_needs_right():
    _customer()
    blind = crm_views.customer_list(
        _req("get", "/crm/", {"q": "geheim@"}, user=_user(perms=NO_CONTACTS))
    ).content.decode()
    assert "Frau Geheim" not in blind
    seen = crm_views.customer_list(
        _req("get", "/crm/", {"q": "geheim@"}, user=_user())
    ).content.decode()
    assert "Frau Geheim" in seen


def test_customer_detail_post_does_not_wipe_contacts():
    c = _customer()
    request = _req(
        "post",
        f"/crm/{c.pk}/",
        {"name": "Frau Neu", "email": "", "phone": ""},
        user=_user(perms=NO_CONTACTS),
    )
    crm_views.customer_detail(request, c.pk)
    c.refresh_from_db()
    assert c.email == "geheim@beispiel.de" and c.phone == "+49 170 1234567"


def test_customer_detail_hides_contact_fields_without_right():
    c = _customer()
    text = crm_views.customer_detail(
        _req("get", f"/crm/{c.pk}/", user=_user(perms=NO_CONTACTS)), c.pk
    ).content.decode()
    assert "geheim@beispiel.de" not in text and "1234567" not in text
