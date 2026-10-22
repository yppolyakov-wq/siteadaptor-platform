"""KA-H2 (2026-10-22): банковские реквизиты Vorkasse меняет только владелец.

На эти реквизиты клиенты переводят деньги (письмо заказа, страница подтверждения,
предложение). Раньше их мог подменить любой сотрудник, а IBAN не проверялся.
Решение владельца: менять — только владелец; IBAN проверяется по mod-97; при каждой
смене владельцу уходит письмо (это и сигнал захвата аккаунта).
"""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import iban
from apps.core import views as core_views
from apps.core.models import Membership
from apps.notifications.models import Notification
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

OLD = "DE89370400440532013000"
NEW = "DE02120300000000202051"


def _member(role):
    o = uuid.uuid4().hex[:8]
    user = get_user_model().objects.create_user(f"b-{o}", f"b-{o}@t.de", "pw12345678")
    Membership.objects.create(user=user, role=role)
    return user


def _req(method, user, tenant, data=None):
    request = getattr(RequestFactory(), method)("/dashboard/settings/payments/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    request.tenant = tenant
    return request


def _tenant(**kw):
    defaults = {
        "disabled_modules": [],
        "vorkasse_enabled": True,
        "bank_holder": "Alt GmbH",
        "bank_iban": OLD,
        "bank_bic": "COBADEFFXXX",
        "owner_email": "inhaber@t.de",
    }
    defaults.update(kw)
    return TenantFactory(**defaults)


def _bank_post(**over):
    data = {
        "sec_vorkasse": "1",
        "sec_prepay": "1",
        "vorkasse_enabled": "on",
        "bank_holder": "Neu GmbH",
        "bank_iban": "de02 1203 0000 0000 2020 51",
        "bank_bic": "BYLADEM1001",
    }
    data.update(over)
    return data


def _bank_mails():
    return Notification.objects.filter(type="bank_details_changed_owner")


# --- валидатор ---------------------------------------------------------------------------


def test_iban_validator():
    assert iban.is_valid_iban(OLD)
    assert iban.is_valid_iban(iban.normalize_iban("de89 3704 0044 0532 0130 00"))
    assert iban.is_valid_iban("AT611904300234573201")
    assert not iban.is_valid_iban("DE89370400440532013001")  # контрольная сумма
    assert not iban.is_valid_iban("DE8937040044053201300")  # длина DE
    assert not iban.is_valid_iban("DE1")
    assert not iban.is_valid_iban("")
    assert iban.mask_iban(OLD).endswith("3000") and "0532" not in iban.mask_iban(OLD)


def test_demo_kit_ibans_are_valid():
    """Демо-киты кладут IBAN в Vorkasse-реквизиты — они обязаны проходить проверку."""
    import re
    from pathlib import Path

    src = (Path(iban.__file__).resolve().parents[1] / "tenants" / "demo_kits.py").read_text()
    found = re.findall(r'"bank_iban":\s*"([^"]+)"', src)
    assert found
    for raw in found:
        assert iban.is_valid_iban(iban.normalize_iban(raw)), raw


# --- права ------------------------------------------------------------------------------


def test_staff_cannot_change_bank_details_but_may_toggle(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = _tenant(vorkasse_enabled=False)
    staff = _member(Membership.ROLE_STAFF)
    core_views.payment_settings(_req("post", staff, tenant, _bank_post()))
    tenant.refresh_from_db()
    assert tenant.bank_iban == OLD and tenant.bank_holder == "Alt GmbH"
    assert tenant.bank_bic == "COBADEFFXXX"
    assert tenant.vorkasse_enabled is True  # тумблер способа оплаты — можно
    assert not _bank_mails().exists()


def test_staff_sees_bank_details_read_only(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = _tenant()
    html = core_views.payment_settings(
        _req("get", _member(Membership.ROLE_STAFF), tenant)
    ).content.decode()
    assert 'name="bank_iban"' not in html
    assert OLD not in html  # полный IBAN сотруднику не показываем
    assert "3000" in html
    owner_html = core_views.payment_settings(
        _req("get", _member(Membership.ROLE_OWNER), tenant)
    ).content.decode()
    assert 'name="bank_iban"' in owner_html


# --- проверка IBAN ----------------------------------------------------------------------


def test_invalid_iban_is_not_saved_other_sections_are(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = _tenant(orders_prepay=False)
    request = _req(
        "post",
        _member(Membership.ROLE_OWNER),
        tenant,
        _bank_post(bank_iban="DE89370400440532013001", orders_prepay="on"),
    )
    core_views.payment_settings(request)
    tenant.refresh_from_db()
    assert tenant.bank_iban == OLD and tenant.bank_holder == "Alt GmbH"
    assert tenant.orders_prepay is True
    levels = [m.level_tag for m in get_messages(request)]
    assert "error" in levels
    assert not _bank_mails().exists()


def test_owner_may_clear_bank_details(settings, django_capture_on_commit_callbacks):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = _tenant()
    with django_capture_on_commit_callbacks(execute=True):
        core_views.payment_settings(
            _req("post", _member(Membership.ROLE_OWNER), tenant, _bank_post(bank_iban=""))
        )
    tenant.refresh_from_db()
    assert tenant.bank_iban == ""
    assert _bank_mails().count() == 1


# --- письмо владельцу -------------------------------------------------------------------


def test_owner_change_sends_one_masked_mail(settings, django_capture_on_commit_callbacks):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = _tenant()
    owner = _member(Membership.ROLE_OWNER)
    with django_capture_on_commit_callbacks(execute=True):
        core_views.payment_settings(_req("post", owner, tenant, _bank_post()))
    tenant.refresh_from_db()
    assert tenant.bank_iban == NEW
    mails = list(_bank_mails())
    assert len(mails) == 1
    mail = mails[0]
    assert mail.recipient == "inhaber@t.de"
    text = mail.subject + mail.payload.get("body", "")
    assert NEW not in text and OLD not in text
    assert "2051" in text and owner.email in text

    # повтор того же сохранения — изменений нет, письма нет
    with django_capture_on_commit_callbacks(execute=True):
        core_views.payment_settings(_req("post", owner, tenant, _bank_post()))
    assert _bank_mails().count() == 1


def test_wizard_slide_keeps_invalid_iban_out(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.core import setup_steps

    tenant = _tenant()
    request = _req("post", _member(Membership.ROLE_OWNER), tenant, _bank_post(bank_iban="DE1"))
    assert setup_steps._post_payment(request) is False
    tenant.refresh_from_db()
    assert tenant.bank_iban == OLD
