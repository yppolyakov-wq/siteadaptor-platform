"""T-8.10h H-7f: «/profil» — телефон, WhatsApp и каталог города из чата общего бота.

План — docs/t8-10h-h7-owner-bot-ux-plan-2026-10-20.md §2.
"""

import pytest

from apps.platform_bot import handler, links, profile
from apps.platform_bot.tests.test_h5b_second_business_email import (  # noqa: F401
    USER,
    _cb,
    _msg,
    bot,
)
from apps.platform_bot.tests.test_h7_menu import _owner
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db


@pytest.fixture
def store(monkeypatch):
    import uuid

    from django.core.cache.backends.locmem import LocMemCache

    cache = LocMemCache(f"prof-{uuid.uuid4()}", {})
    monkeypatch.setattr(profile, "cache", cache)
    return cache


def test_profile_shows_business_data(bot, store):  # noqa: F811
    tenant = _owner()
    Tenant.objects.filter(pk=tenant.pk).update(contact_phone="+49 212 1")
    assert handler.handle(_msg("/profil")) == "profile"
    assert "+49 212 1" in bot["sent"][-1]["text"]


def test_edit_phone_then_clear(bot, store):  # noqa: F811
    tenant = _owner()
    assert handler.handle(_cb("pp:p")) == "profile_wait"
    assert handler.handle(_msg("+49 212 777", update_id=2)) == "profile"
    tenant.refresh_from_db()
    assert tenant.contact_phone == "+49 212 777"
    handler.handle(_cb("pp:w"))
    handler.handle(_msg("-", update_id=3))
    tenant.refresh_from_db()
    assert tenant.whatsapp_number == ""


def test_command_cancels_edit_and_is_routed(bot, store):  # noqa: F811
    _owner()
    handler.handle(_cb("pp:p"))
    assert handler.handle(_msg("/hilfe", update_id=2)) == "help"
    assert not profile.pending(USER)


def test_edit_denied_after_unlink(bot, store):  # noqa: F811
    tenant = _owner()
    handler.handle(_cb("pp:p"))
    links.unbind(tenant)
    assert handler.handle(_msg("+49 1", update_id=2)) != "profile"
    tenant.refresh_from_db()
    assert tenant.contact_phone != "+49 1"


def test_catalog_cannot_be_switched_off_from_bot(bot, store, monkeypatch):  # noqa: F811
    """KA-D5 (решение владельца 2026-10-23): каталог города — всегда; выключает только
    оператор по письменному отказу. Старые кнопки бота ничего не меняют."""
    tenant = _owner()
    calls = []
    monkeypatch.setattr("apps.aggregator.visibility.apply_visibility", lambda t: calls.append(t.pk))
    assert handler.handle(_cb("pp:c")) == "catalog_info"
    assert handler.handle(_cb(f"pp:C:{tenant.pk}:0")) == "catalog_info"
    assert Tenant.objects.get(pk=tenant.pk).in_city_catalog is True
    assert calls == []


def test_catalog_confirm_for_other_business_denied(bot, store):  # noqa: F811
    tenant = _owner()
    # KA-D5: переключателя больше нет — любая старая кнопка только объясняет
    assert handler.handle(_cb(f"pp:C:{tenant.pk + 999}:0")) == "catalog_info"


def test_non_text_does_not_clear_number(bot, store):  # noqa: F811
    tenant = _owner()
    Tenant.objects.filter(pk=tenant.pk).update(contact_phone="+49 1")
    handler.handle(_cb("pp:p"))
    assert handler.handle(_msg("", update_id=2)) == "profile_wait"
    tenant.refresh_from_db()
    assert tenant.contact_phone == "+49 1"


def test_too_long_value_rejected(bot, store):  # noqa: F811
    tenant = _owner()
    handler.handle(_cb("pp:p"))
    assert handler.handle(_msg("9" * 500, update_id=2)) == "profile_invalid"
    tenant.refresh_from_db()
    assert len(tenant.contact_phone or "") < 500


def test_profile_without_business(bot, store):  # noqa: F811
    assert handler.handle(_msg("/profil")) == "onboarding"
