"""FB-31.7 B1b-2b: свои шаблоны объектов (категория, акция, группа) → строки своих хостов.
Сверка по осям и по отрисованной странице: до == после == после без кодов (как B3)."""

import pytest

from apps.core import page_axes_migration as pam
from apps.core import page_axes_objects as pao
from apps.core.tests.test_fb317_b1b_writer import OWN
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(cfg):
    return TenantFactory(name="Laden X", business_type="bakery", site_config=cfg)


def _seed_cats(root_style="", sub_style=""):
    from apps.catalog.tests.factories import CategoryFactory, ProductFactory

    root = CategoryFactory(slug="brot", name={"de": "Brot"}, page_style=root_style)
    sub = CategoryFactory(slug="roggen", name={"de": "Roggen"}, parent=root, page_style=sub_style)
    other = CategoryFactory(slug="kuchen", name={"de": "Kuchen"})
    for cat in (root, sub, other):
        ProductFactory(name={"de": f"{cat.slug} 1"}, category=cat)


def _run(raw):
    tenant = _tenant(raw)
    render = pam.renderer(tenant)
    from django_tenants.utils import schema_context

    with schema_context(tenant.schema_name):
        idx = pao.build_index()
    new, report = pam.migrate(raw, render=render, objects=idx)
    return tenant, render, idx, new, report


def _same_pages(render, raw, new, paths):
    for path in paths:
        before = render.at(raw, path)
        assert before is not None, path
        assert render.at(new, path) == before, path
        with pam.objects_blind():
            assert render.at(pam._without_key(new, "category_page_style"), path) == before, path


@pytest.mark.usefixtures("_urlconf")
@pytest.mark.parametrize("default", ["", "kopfbild"])
@pytest.mark.parametrize("own", ["tabs", "kopfbild", ""])
def test_own_category_codes_and_alle_kategorien_move_together(own, default):
    _seed_cats(root_style=own)
    raw = {"site_defaults": {"category_page_style": default}} if default else {}
    raw["catalog_intro"] = "Willkommen"
    _tenant_, render, _idx, new, report = _run(raw)
    if not own and not default:
        assert "categories" not in report.surfaces and new == raw
        return
    assert report.surfaces["categories"] == pam.DONE, (report.surfaces, report.notes)
    paths = [pao.page_url("categories", s) for s in ("brot", "roggen", "kuchen")]
    _same_pages(render, raw, new, paths)
    if own:
        assert siteconfig.category_host("brot") in new["page_blocks"]
    if default:
        assert "categories:detached:category" in report.notes
    again, report2 = pam.migrate(new, render=render, objects=_idx)
    assert not report2.changed and again == new, report2.surfaces


def test_hidden_categories_row_on_own_host_skips_the_site():
    hidden = {"key": "categories", "enabled": False, "style": "tabs"}
    raw = {"page_blocks": {siteconfig.category_host("brot"): [hidden, {"key": "main"}]}}
    idx = pao.ObjectIndex(categories=[pao.CategoryRef("brot", "kopfbild")])
    new, report = pam.migrate_objects(raw, idx)
    assert report.surfaces["categories"] == pam.SKIP and new == raw


def test_full_category_hosts_purge_deleted_ones_first_then_refuse():
    cap = siteconfig._MAX_CATEGORY_HOSTS
    full = {siteconfig.category_host(f"c{i:03d}"): [OWN] for i in range(cap)}
    refs = [pao.CategoryRef("neu", "tabs")]
    ghosts = pao.ObjectIndex(categories=refs, all_category_slugs=frozenset({"neu"}))
    new, report = pam.migrate_objects({"page_blocks": dict(full)}, ghosts)
    assert report.surfaces["categories"] == pam.DONE, report.surfaces
    assert (
        "categories:purged:120" in report.notes
        and siteconfig.category_host("neu") in (new["page_blocks"])
    )
    alive = pao.ObjectIndex(
        categories=refs, all_category_slugs=frozenset({f"c{i:03d}" for i in range(cap)})
    )
    new, report = pam.migrate_objects({"page_blocks": dict(full)}, alive)
    assert report.surfaces["categories"] == pam.HOSTS_FULL and report.mismatches


@pytest.mark.usefixtures("_urlconf")
@pytest.mark.parametrize("code", ["plakat", "kompakt", "magazin"])
def test_own_promo_template_moves_to_its_host(code):
    from apps.promotions.models import Promotion
    from apps.promotions.tests import test_fb31p3_promo_golden as p3

    p3._seed(True)
    promo = Promotion.objects.filter(Promotion.on_sale_q()).order_by("pk").first()
    Promotion.objects.filter(pk=promo.pk).update(page_style=code)
    raw = {"catalog_intro": "Willkommen"}
    _t, render, _idx, new, report = _run(raw)
    assert report.surfaces["promos"] == pam.DONE, (report.surfaces, report.notes)
    assert f"promo:{promo.pk.hex}" in new["page_blocks"]
    _same_pages(render, raw, new, [pao.page_url("promos", promo.pk.hex)])


@pytest.mark.usefixtures("_urlconf")
@pytest.mark.parametrize("code", ["magazin", "prospekt", "countdown"])
@pytest.mark.parametrize("shared", [False, True])
def test_own_group_template_moves_to_a_detached_copy(code, shared):
    from apps.promotions.tests import test_fb31p3_promo_golden as p3

    p3._seed(True)
    raw = {"promo_groups": {"Räumung": {"style": code}, "Weg": {"style": "magazin"}}}
    if shared:
        raw["page_blocks"] = {"promo_group": [OWN, {"key": "main"}]}
    _t, render, _idx, new, report = _run(raw)
    assert report.surfaces["promo_groups"] == pam.DONE, (report.surfaces, report.notes)
    host = siteconfig.promo_group_host("Räumung")
    assert f"promo_groups:detached:{host}" in report.notes
    assert "promo_groups:orphan:Weg" in report.notes, "группа без акций — заметка, не отказ"
    _same_pages(render, raw, new, [pao.page_url("promo_groups", "Räumung")])


@pytest.mark.usefixtures("_urlconf")
def test_apply_tenant_moves_objects_with_a_snapshot_and_undo():
    from apps.tenants.models import SiteConfigSnapshot

    _seed_cats(root_style="tabs")
    tenant = TenantFactory(schema_name="public", slug="b1b2cmd", name="B", site_config={})
    report = pam.apply_tenant(tenant)
    assert report.surfaces.get("categories") == pam.DONE, (report.surfaces, report.notes)
    tenant.refresh_from_db()
    assert siteconfig.category_host("brot") in tenant.site_config["page_blocks"]
    assert SiteConfigSnapshot.objects.filter(tenant_id=tenant.pk, reason=pam.REASON).exists()
    assert not pam.apply_tenant(tenant).changed
    assert pam.undo_tenant(tenant) == "undone"
    tenant.refresh_from_db()
    assert not (tenant.site_config.get("page_blocks") or {})


@pytest.mark.usefixtures("_urlconf")
@pytest.mark.parametrize("kit", ["aktionsmarkt", "clothing", "outlet"])
def test_demo_kits_with_own_templates_move_without_mismatch(kit):
    """Киты со своими шаблонами категорий, «Alle Kategorien» и групп акций: перенос проходит
    сверку по отрисованным страницам (до == после == без кодов) и повторяется вхолостую."""
    from apps.tenants import demo_kits

    tenant = TenantFactory(
        schema_name="public", slug=f"m{kit[:8]}", name="K", business_type="bakery"
    )
    assert demo_kits.apply_kit(tenant, kit) is True
    tenant.refresh_from_db()
    report = pam.apply_tenant(tenant)
    assert not report.mismatches, (kit, report.surfaces, report.notes)
    want = {"aktionsmarkt": {"categories", "promo_groups"}, "clothing": {"categories"}}
    want["outlet"] = {"categories", "promo_groups"}
    done = {k for k, v in report.surfaces.items() if v == pam.DONE}
    assert want[kit] <= done, (kit, report.surfaces, report.notes)
    assert not pam.apply_tenant(tenant).changed
