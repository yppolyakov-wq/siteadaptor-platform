"""FB-31.7 B1b-1: перенос шаблонов уровня сайта в строки схемы — сверка по осям и по
отрисованной странице (`docs/fb31-7-materialize-plan-2026-11-16.md`, «B1b — разведка»)."""

import pytest

from apps.core import page_axes_migration as pam
from apps.core.tests.test_fb317_b1b_writer import OWN, _codes
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _with_code(key, code, rows=()):
    host, path = siteconfig.PAGE_TEMPLATE_HOSTS[key]
    raw = {"page_blocks": {host: list(rows)}} if rows else {}
    if len(path) == 1:
        raw[path[0]] = code
    else:
        raw[path[0]] = {path[1]: code}
    return raw


@pytest.mark.parametrize("key", sorted(siteconfig.PAGE_TEMPLATE_HOSTS))
def test_every_code_moves_to_rows_keeps_the_old_key_and_repeats_as_noop(key):
    for code in _codes(key):
        for rows in ((), (OWN,)):
            raw = _with_code(key, code, rows)
            if not pam._old_code(siteconfig.normalize(raw), key):
                continue  # код этой страницы не принимается нормализацией — переносить нечего
            want = siteconfig.page_template_code(siteconfig.normalize(raw), key)
            new, report = pam.migrate_templates(raw)
            assert report.surfaces.get(key) == pam.DONE, (key, code, report.surfaces)
            norm = siteconfig.normalize(new)
            assert siteconfig.page_template_code(norm, key) == want
            bare = siteconfig.normalize(pam._without_key(new, key))
            assert siteconfig.page_template_code(bare, key) == want, "вид держат строки"
            assert pam._old_code(norm, key) == code, "старый ключ остаётся (решение 4)"
            again, report2 = pam.migrate_templates(new)
            assert not report2.changed and again == new, (key, code, report2.surfaces)


def test_hidden_categories_row_replaced_by_the_code_skips_the_site():
    hidden = {"key": "categories", "enabled": False, "style": "tabs"}
    raw = _with_code("catalog_page_style", "regale", [hidden])
    new, report = pam.migrate_templates(raw)
    assert report.surfaces["catalog_page_style"] == pam.SKIP and new == raw


def test_render_mismatch_leaves_the_site_untouched():
    raw = _with_code("promo_page_style", "regale", [OWN])
    calls = []

    def render(cfg, key):
        calls.append(key)
        return "before" if len(calls) == 1 else "after"

    new, report = pam.migrate_templates(raw, render=render)
    assert report.surfaces["promo_page_style"] == pam.MISMATCH and new == raw


@pytest.fixture
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(cfg):
    return TenantFactory(name="Laden X", business_type="bakery", site_config=cfg)


@pytest.mark.usefixtures("_urlconf")
@pytest.mark.parametrize("head", [None, "titelbild"])
def test_root_sets_template_renders_the_same_page_after_the_move(head):
    """Ловушка разведки: у корня «sets» шапки нет, пока её не включили строкой."""
    from apps.catalog.tests.factories import CategoryFactory, ProductFactory

    cat = CategoryFactory(slug="brot", name={"de": "Brot"})
    ProductFactory(name={"de": "Brot 1"}, category=cat)
    rows = [{"key": "page_head", "style": head}] if head else []
    raw = {**_with_code("catalog_page_style", "sets", rows), "catalog_intro": "Willkommen"}
    tenant = _tenant(raw)
    render = pam.renderer(tenant)
    new, report = pam.migrate_templates(raw, render=render)
    assert report.surfaces["catalog_page_style"] == pam.DONE, report.surfaces
    assert render(new, "catalog_page_style") == render(raw, "catalog_page_style")


@pytest.mark.usefixtures("_urlconf")
@pytest.mark.parametrize("code", ["regale", "magazin", "tabs"])
def test_promo_overview_renders_the_same_after_the_move(code):
    from apps.promotions.tests import test_fb31p3_promo_golden as p3

    p3._seed(True)
    raw = _with_code("promo_page_style", code, [OWN])
    tenant = _tenant(raw)
    render = pam.renderer(tenant)
    new, report = pam.migrate_templates(raw, render=render)
    assert report.surfaces["promo_page_style"] == pam.DONE, report.surfaces


def _seed_all():
    from apps.catalog.tests.factories import CategoryFactory, ProductFactory
    from apps.promotions.tests import test_fb31p3_promo_golden as p3

    root = CategoryFactory(slug="brot", name={"de": "Brot"})
    sub = CategoryFactory(slug="roggen", name={"de": "Roggen"}, parent=root)
    ProductFactory(name={"de": "Brot 1"}, category=root)
    ProductFactory(name={"de": "Roggen 1"}, category=sub)
    p3._seed(True)


@pytest.mark.usefixtures("_urlconf")
@pytest.mark.parametrize("key", sorted(siteconfig.PAGE_TEMPLATE_HOSTS))
def test_every_code_renders_the_same_page_after_the_move(key):
    _seed_all()
    tenant = _tenant({})
    render = pam.renderer(tenant)
    checked = 0
    for code in _codes(key):
        for rows in ((), (OWN,)):
            raw = {**_with_code(key, code, rows), "catalog_intro": "Willkommen"}
            if not pam._old_code(siteconfig.normalize(raw), key):
                continue
            new, report = pam.migrate_templates(raw, render=render)
            assert report.surfaces.get(key) in (pam.DONE, pam.SAME), (key, code, report.surfaces)
            assert render(new, key) == render(raw, key), (key, code)
            checked += 1
    assert checked, key


@pytest.mark.usefixtures("_urlconf")
@pytest.mark.parametrize("key", sorted(siteconfig.PAGE_TEMPLATE_HOSTS))
def test_the_renderer_is_deterministic(key):
    """Сверка имеет смысл, только если одна и та же страница дважды рисуется одинаково."""
    _seed_all()
    render = pam.renderer(_tenant({}))
    assert render({}, key) == render({}, key), key


@pytest.mark.usefixtures("_urlconf")
@pytest.mark.parametrize("kit", ["aktionsmarkt", "clothing", "online_shop", "outlet"])
def test_demo_kits_store_templates_as_rows_without_old_keys(kit):
    """FB-31.7 B2: демо-киты не пишут старые ключи шаблонов — вид тот же, строками."""
    from apps.tenants import demo_kits

    spec = demo_kits.KITS[kit]
    patch = spec.config_patch or {}
    expected = {}
    for key, (_host, path) in siteconfig.PAGE_TEMPLATE_HOSTS.items():
        node = patch
        for part in path:
            node = node.get(part) if isinstance(node, dict) else None
        if isinstance(node, str) and node:
            expected[key] = node
    tenant = TenantFactory(
        schema_name="public", slug=f"k{kit[:8]}", name="K", business_type="bakery"
    )
    assert demo_kits.apply_kit(tenant, kit) is True
    tenant.refresh_from_db()
    raw = tenant.site_config
    norm = siteconfig.normalize(raw)
    for key, code in expected.items():
        assert not pam._old_code(raw, key), (kit, key, "старый ключ не пишется")
        want = siteconfig.page_template_code(siteconfig.normalize(_with_code(key, code)), key)
        assert siteconfig.page_template_code(norm, key) == want, (kit, key)


@pytest.mark.usefixtures("_urlconf")
def test_apply_tenant_moves_site_templates_with_the_real_renderer():
    from apps.promotions.tests import test_fb31p3_promo_golden as p3
    from apps.tenants.models import SiteConfigSnapshot

    p3._seed(True)
    raw = _with_code("promo_page_style", "regale", [OWN])
    tenant = TenantFactory(schema_name="public", slug="b1bcmd", name="B", site_config=raw)
    report = pam.apply_tenant(tenant)
    assert report.surfaces.get("promo_page_style") == pam.DONE, report.surfaces
    tenant.refresh_from_db()
    norm = siteconfig.normalize(tenant.site_config)
    assert siteconfig.page_template_code(norm, "promo_page_style") == "regale"
    assert pam._old_code(norm, "promo_page_style") == "regale", "ключ остаётся до B3"
    assert SiteConfigSnapshot.objects.filter(tenant_id=tenant.pk, reason=pam.REASON).exists()
    again = pam.apply_tenant(tenant)
    assert not again.changed, again.surfaces


def test_render_failure_is_reported_and_the_site_left_untouched():
    raw = _with_code("promo_page_style", "regale", [OWN])

    def render(cfg, key):
        raise RuntimeError("boom")

    new, report = pam.migrate_templates(raw, render=render)
    assert report.surfaces["promo_page_style"] == pam.RENDER_FAILED and new == raw
    assert report.mismatches == ["promo_page_style"]
