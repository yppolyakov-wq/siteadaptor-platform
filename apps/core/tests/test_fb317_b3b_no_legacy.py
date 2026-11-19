"""FB-31.7 B3b: по умолчанию старые коды шаблонов НЕ читаются — вид держат строки «Seitenaufbau»;
`PAGE_LEGACY_READ=1` возвращает чтение без деплоя (откат). Перенос и сверка видят коды всегда."""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.catalog import catalog_parts
from apps.core import listing_parts
from apps.core import page_axes_migration as pam
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db

CODES = {
    "catalog_page_style": "regale",
    "promo_page_style": "magazin",
    "page_styles": {"services": "kompakt"},
    "site_defaults": {"category_page_style": "kopfbild", "promo_detail_style": "plakat"},
}


def test_old_codes_are_ignored_by_default():
    norm = siteconfig.normalize(CODES)
    assert not pam.legacy_reads()
    assert siteconfig.page_template_code(norm, "catalog_page_style") == ""
    assert siteconfig.page_template_code(norm, "promo_page_style") == ""
    assert listing_parts.code_for(norm, "services") == ""
    from types import SimpleNamespace

    cat = SimpleNamespace(slug="brot", page_style="tabs")
    assert catalog_parts.legacy_code(catalog_parts.category_parts(norm, cat)) == ""


def test_setting_brings_old_codes_back_without_deploy(settings):
    settings.PAGE_LEGACY_READ = True
    norm = siteconfig.normalize(CODES)
    assert siteconfig.page_template_code(norm, "catalog_page_style") == "regale"
    assert listing_parts.code_for(norm, "services") == "kompakt"


def test_migrated_config_looks_the_same_without_codes():
    new, report = pam.migrate(CODES)
    assert report.changed
    norm = siteconfig.normalize(new)
    assert siteconfig.page_template_code(norm, "catalog_page_style") == "regale"
    assert listing_parts.code_for(norm, "services") == "kompakt"


def test_undo_refuses_after_b3b_with_a_hint():
    with pytest.raises(CommandError, match="PAGE_LEGACY_READ"):
        call_command("materialize_page_axes", "--undo")


@pytest.mark.parametrize("kit", ["aktionsmarkt", "clothing", "outlet", "pranasy"])
def test_demo_kit_pages_render_the_same_with_and_without_old_codes(settings, kit):
    """Главный замок B3b: витрина кита без чтения кодов — байт-в-байт та же, что с кодами
    (каталог, обзор акций, все категории, группы акций)."""
    from django.urls import reverse
    from django_tenants.utils import schema_context

    from apps.core import page_axes_objects as pao
    from apps.tenants import demo_kits
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(schema_name="public", slug=f"b3b{kit[:8]}", name="K")
    assert demo_kits.apply_kit(tenant, kit) is True
    tenant.refresh_from_db()
    cfg = tenant.site_config
    render = pam.renderer(tenant)
    with schema_context(tenant.schema_name):
        idx = pao.build_index()
    paths = [
        reverse("storefront-products", urlconf="config.urls_tenant"),
        reverse("storefront-aktionen", urlconf="config.urls_tenant"),
        *(pao.page_url("categories", r.slug) for r in idx.categories),
        *(pao.page_url("promo_groups", g) for g in idx.groups),
    ]
    for path in paths:
        with pam.legacy_view(True):
            before = render.at(cfg, path)
        with pam.legacy_view(False):
            after = render.at(cfg, path)
        assert after == before, (kit, path)


def test_same_template_choice_drops_the_stale_old_key():
    """Ревью B3b (M4): вид уже держат строки — повторный выбор того же шаблона снимает старый
    ключ, чтобы откат `PAGE_LEGACY_READ=1` не оживил его поверх правок после B3b."""
    from apps.core import page_settings

    new, _report = pam.migrate({"catalog_page_style": "regale"})
    assert new.get("catalog_page_style") == "regale", "перенос оставляет ключ (решение 4)"
    out = page_settings.apply_override(new, "catalog_page_style", "regale")
    assert "catalog_page_style" not in out
    assert siteconfig.page_template_code(siteconfig.normalize(out), "catalog_page_style") == (
        "regale"
    )


def test_own_category_code_without_rows_no_longer_changes_the_storefront(settings):
    """M6: свой код категории без строк — витрина его не видит (B3b); с откатом — видит."""
    from types import SimpleNamespace

    cat = SimpleNamespace(slug="brot", page_style="tabs")
    norm = siteconfig.normalize({})
    assert catalog_parts.legacy_code(catalog_parts.category_parts(norm, cat)) == ""
    settings.PAGE_LEGACY_READ = True
    assert catalog_parts.legacy_code(catalog_parts.category_parts(norm, cat)) == "tabs"


def test_own_promo_code_without_rows_is_ignored():
    from apps.promotions import promo_parts

    default = promo_parts.detail_parts({}, "", "", "")
    assert promo_parts.detail_parts({}, "plakat", "", "") == default
