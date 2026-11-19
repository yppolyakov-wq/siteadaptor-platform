"""FB-31.7 B3a: остаток перед снятием чтения старых кодов (`materialize_page_axes --residue`)."""

import pytest
from django.core.management import call_command

from apps.core import page_axes_migration as pam
from apps.core import page_axes_residue as par
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _tenant(cfg, slug="b3a"):
    return TenantFactory(schema_name="public", slug=slug, name="R", site_config=cfg)


def test_code_without_rows_is_residue_and_migrated_site_is_clean():
    from apps.tenants import siteconfig

    raw = {"catalog_page_style": "regale", "page_styles": {"services": "kompakt"}}
    tenant = _tenant(raw)
    reasons = par.tenant_residue(tenant)
    assert "view:site:catalog_page_style" in reasons
    assert "view:listing:services" in reasons
    new, report = pam.migrate(raw)
    assert report.changed
    tenant.site_config = new
    assert par.tenant_residue(tenant) == [], "после переноса строки держат вид без кодов"
    assert siteconfig.page_template_code(siteconfig.normalize(new), "catalog_page_style") == (
        "regale"
    )


def test_own_category_code_without_rows_is_residue():
    from apps.catalog.tests.factories import CategoryFactory

    CategoryFactory(slug="brot", name={"de": "Brot"}, page_style="tabs")
    assert "view:category:brot" in par.tenant_residue(_tenant({}))


def test_old_history_version_without_rows_counts_and_rolled_back_counts():
    from apps.tenants.models import SiteConfigSnapshot

    raw = {"history": [{"config": {"catalog_page_style": "regale"}}]}
    tenant = _tenant(raw)
    assert "history:1" in par.tenant_residue(tenant)
    SiteConfigSnapshot.objects.create(
        tenant=tenant, reason=pam.REASON, before={}, after_hash="x", undone_at="2026-11-19T00:00Z"
    )
    assert "rolled_back" in par.tenant_residue(tenant)


@pytest.mark.parametrize("kit", ["aktionsmarkt", "clothing", "outlet", "pranasy"])
def test_demo_kits_have_no_residue(settings, kit):
    from apps.tenants import demo_kits

    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(schema_name="public", slug=f"r{kit[:8]}", name="K")
    assert demo_kits.apply_kit(tenant, kit) is True
    tenant.refresh_from_db()
    assert par.tenant_residue(tenant) == [], kit


def test_command_prints_the_residue_total(capsys):
    _tenant({"catalog_page_style": "regale"}, slug="b3acmd")
    from io import StringIO

    out, err = StringIO(), StringIO()
    call_command("materialize_page_axes", "--residue", stdout=out, stderr=err)
    assert "residue: " in out.getvalue()
