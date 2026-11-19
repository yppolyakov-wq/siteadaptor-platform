"""FB-33 M2f-0: аудит «Состав / аллергены» у сайтов еды (только чтение)."""

import pytest
from django.core.management import call_command

from apps.catalog.management.commands import lmiv_info_audit
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def test_site_level_hiding_is_found():
    assert lmiv_info_audit.site_hides_info({"product_detail": {"hidden": ["info"]}})
    assert not lmiv_info_audit.site_hides_info({})


def test_command_counts_food_sites_only(capsys):
    TenantFactory(business_type="bakery", site_config={"product_detail": {"hidden": ["info"]}})
    TenantFactory(business_type="clothing", site_config={"product_detail": {"hidden": ["info"]}})
    call_command("lmiv_info_audit")
    out = capsys.readouterr().out
    assert "lmiv hidden: 1 sites, 0 products" in out


def test_command_writes_nothing():
    t = TenantFactory(business_type="cafe", site_config={"product_detail": {"hidden": ["info"]}})
    before = dict(t.site_config)
    call_command("lmiv_info_audit")
    t.refresh_from_db()
    assert t.site_config == before
