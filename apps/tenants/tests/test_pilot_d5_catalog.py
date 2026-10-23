"""KA-D5 (решение владельца 2026-10-23): каждый бизнес всегда в каталоге города.

Владелец выключить сам не может (ни в кабинете, ни в быстрой регистрации, ни в боте);
выключение — флаг оператора в админке платформы по письменному отказу."""

import pytest

from apps.tenants import quickstart
from apps.tenants.admin import TenantAdmin
from apps.tenants.forms import BusinessSettingsForm

pytestmark = pytest.mark.django_db


def test_cabinet_form_has_no_catalog_switch():
    assert "in_city_catalog" not in BusinessSettingsForm.Meta.fields
    assert "in_city_catalog" not in BusinessSettingsForm().fields


def test_quick_start_form_has_no_catalog_checkbox():
    assert "in_city_catalog" not in quickstart.QuickStartForm.base_fields


def test_operator_can_still_set_refusal_in_admin():
    assert "in_city_catalog" in TenantAdmin.VISIBILITY_FIELDS


def test_bot_summary_has_no_catalog_button(monkeypatch):
    from apps.platform_bot import signup

    sent = []
    monkeypatch.setattr(signup, "_send", lambda bot, chat, text, kb=None: sent.append(kb))
    signup._summary(None, 1, {"data": {"title": "X"}})
    buttons = [b["callback_data"] for row in sent[0]["inline_keyboard"] for b in row]
    assert "ps:p" not in buttons
