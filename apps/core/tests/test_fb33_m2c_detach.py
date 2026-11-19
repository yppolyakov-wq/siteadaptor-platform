"""FB-33 M2c-2: перенос «Быстрых ссылок» из баннера в блок (`detach_quick_links`)."""

import pytest
from django.core.management import call_command

from apps.core import quick_links_migration as qlm
from apps.tenants import siteconfig
from apps.tenants.models import SiteConfigSnapshot, Tenant
from apps.tenants.templatetags.siteui import banner_tiles
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _cfg(widget, **extra):
    return {"site_defaults": {"hero_widget": widget, "radius": 8}, **extra}


def _keys(cfg):
    return [r.get("key") for r in siteconfig.normalize(cfg)["sections"]]


def _norm(cfg):
    return siteconfig.normalize(cfg)


def test_link_set_becomes_a_block_right_after_the_banner():
    new, res = qlm.detach(_cfg("friseur"))
    assert res.changed and res.action == "block"
    keys = _keys(new)
    assert keys[keys.index("hero") + 1] == "quick_links"
    block = next(r for r in _norm(new)["sections"] if r["key"] == "quick_links")
    assert block["data"] == {"set": "friseur"} and block["enabled"]
    assert "hero_widget" not in new["site_defaults"] and new["site_defaults"]["radius"] == 8
    assert banner_tiles(_norm(new)) == ""


def test_bento_gets_a_hidden_block_so_the_site_looks_the_same():
    new, res = qlm.detach(_cfg("shop", hero_style="bento"))
    block = next(r for r in _norm(new)["sections"] if r["key"] == "quick_links")
    assert res.action == "block-hidden" and not block["enabled"]


def test_date_search_becomes_the_search_section_after_the_banner():
    new, res = qlm.detach(_cfg("stays"))
    rows = _norm(new)["sections"]
    keys = [r["key"] for r in rows]
    assert res.action == "stay_search" and keys[keys.index("hero") + 1] == "stay_search"
    assert next(r for r in rows if r["key"] == "stay_search")["enabled"]


def test_services_section_moves_up_when_it_is_on():
    raw = _cfg(
        "services",
        sections=[{"key": "hero", "enabled": True}, {"key": "services", "enabled": True}],
    )
    new, res = qlm.detach(_norm(raw) | {"site_defaults": raw["site_defaults"]})
    keys = _keys(new)
    assert res.action == "services" and keys[keys.index("hero") + 1] == "services"


def test_services_off_becomes_a_list_of_three():
    new, res = qlm.detach(_cfg("services"))
    keys = _keys(new)
    assert res.action == "services-list" and keys[keys.index("hero") + 1] == "list"
    block = next(r for r in _norm(new)["sections"] if r["key"] == "list")
    assert block["data"]["source"] == "services" and block["data"]["limit"] == 3


def test_existing_block_is_not_doubled():
    raw = _cfg("shop", sections=[{"key": "quick_links", "id": "q1", "data": {"set": "mode"}}])
    new, res = qlm.detach(raw)
    assert res.action == "block-exists"
    assert [r for r in _norm(new)["sections"] if r["key"] == "quick_links"][0]["data"] == {
        "set": "mode"
    }


def test_no_widget_no_change():
    cfg = {"site_defaults": {"radius": 4}}
    new, res = qlm.detach(cfg)
    assert new is cfg and not res.changed


def test_detach_is_pure():
    cfg = _cfg("shop")
    qlm.detach(cfg)
    assert cfg == _cfg("shop")


def _tenant(widget, **extra):
    return TenantFactory(site_config=_cfg(widget, **extra))


def test_command_moves_once_dry_run_writes_nothing_and_undo_restores():
    tenant = _tenant("handwerker")
    before = Tenant.objects.get(pk=tenant.pk).site_config
    call_command("detach_quick_links", "--dry-run", "--schema", tenant.schema_name)
    assert Tenant.objects.get(pk=tenant.pk).site_config == before
    call_command("detach_quick_links", "--schema", tenant.schema_name)
    after = Tenant.objects.get(pk=tenant.pk).site_config
    assert "hero_widget" not in after["site_defaults"]
    assert SiteConfigSnapshot.objects.filter(tenant=tenant, reason=qlm.REASON).count() == 1
    call_command("detach_quick_links", "--schema", tenant.schema_name)  # повтор — 0 изменений
    assert SiteConfigSnapshot.objects.filter(tenant=tenant, reason=qlm.REASON).count() == 1
    call_command("detach_quick_links", "--undo", "--schema", tenant.schema_name)
    assert Tenant.objects.get(pk=tenant.pk).site_config == before
    call_command("detach_quick_links", "--schema", tenant.schema_name)  # откатил — не повторяем
    assert Tenant.objects.get(pk=tenant.pk).site_config == before


def test_undo_refuses_when_the_owner_changed_things():
    tenant = _tenant("shop")
    call_command("detach_quick_links", "--schema", tenant.schema_name)
    t = Tenant.objects.get(pk=tenant.pk)
    t.site_config = {**t.site_config, "hero_title": "Neu"}
    t.save(update_fields=["site_config"])
    assert qlm.undo_tenant(t) == "changed"


def test_residue_counts_sites_with_the_old_key(capsys):
    _tenant("shop")
    call_command("detach_quick_links", "--residue")
    assert "quick_links residue: 1" in capsys.readouterr().out
    call_command("detach_quick_links")
    call_command("detach_quick_links", "--residue")
    assert "quick_links residue: 0" in capsys.readouterr().out


def test_busy_row_is_retried_next_deploy(monkeypatch):
    from django.db import OperationalError

    from apps.core import config_migration as cm

    tenant = _tenant("shop")

    class _Lock(Exception):
        pgcode = "55P03"

    def boom(*a, **kw):
        err = OperationalError("lock timeout")
        err.__cause__ = _Lock()
        raise err

    monkeypatch.setattr(cm, "lock", boom)
    assert qlm.apply_tenant(tenant).action == qlm.BUSY
    assert "hero_widget" in Tenant.objects.get(pk=tenant.pk).site_config["site_defaults"]


def test_deploy_runs_it_after_the_page_axes_step():
    import pathlib

    sh = pathlib.Path("scripts/deploy.sh").read_text()
    assert sh.index("detach_quick_links") > sh.index("materialize_page_axes --residue")
    assert "detach_quick_links --residue" in sh


def test_other_db_errors_are_not_reported_as_busy(monkeypatch):
    from django.db import OperationalError

    from apps.core import config_migration as cm

    tenant = _tenant("shop")

    def boom(*a, **kw):
        raise OperationalError("connection lost")

    monkeypatch.setattr(cm, "lock", boom)
    with pytest.raises(OperationalError):
        qlm.apply_tenant(tenant)


@pytest.mark.parametrize("bad", (["shop"], {"x": 1}, "nonsense"))
def test_garbage_widget_is_skipped_not_erased(bad):
    cfg = {"site_defaults": {"hero_widget": bad}}
    new, res = qlm.detach(cfg)
    assert new is cfg and not res.changed and res.action == "skip:bad-widget"


def test_command_reports_a_skip_and_keeps_the_site(capsys):
    tenant = _tenant("shop")
    t = Tenant.objects.get(pk=tenant.pk)
    t.site_config = {"site_defaults": {"hero_widget": "nonsense"}}
    t.save(update_fields=["site_config"])
    call_command("detach_quick_links", "--schema", tenant.schema_name)
    assert "ПРОПУЩЕНО (bad-widget)" in capsys.readouterr().err
    assert (
        Tenant.objects.get(pk=tenant.pk).site_config["site_defaults"]["hero_widget"] == "nonsense"
    )


@pytest.mark.parametrize(
    ("widget", "extra"),
    (("shop", {}), ("stays", {}), ("services", {}), ("shop", {"hero_style": "bento"})),
)
def test_verify_passes_for_every_action(widget, extra):
    before = _cfg(widget, **extra)
    new, res = qlm.detach(before)
    assert qlm.verify(before, new, res.action) == ""


def test_verify_catches_a_block_that_normalize_drops(monkeypatch):
    before = _cfg("shop")
    new, res = qlm.detach(before)
    real = siteconfig.normalize
    monkeypatch.setattr(
        siteconfig,
        "normalize",
        lambda raw: {
            **real(raw),
            "sections": [r for r in real(raw)["sections"] if r["key"] != "quick_links"],
        },
    )
    assert qlm.verify(before, new, res.action) == "block-missing"


def test_undo_of_a_site_without_saved_sections_drops_them_again():
    tenant = _tenant("shop")
    assert "sections" not in Tenant.objects.get(pk=tenant.pk).site_config
    call_command("detach_quick_links", "--schema", tenant.schema_name)
    assert "sections" in Tenant.objects.get(pk=tenant.pk).site_config
    assert qlm.undo_tenant(Tenant.objects.get(pk=tenant.pk)) == "undone"
    assert "sections" not in Tenant.objects.get(pk=tenant.pk).site_config


def test_race_with_the_cabinet_retries_then_reports_busy(monkeypatch):
    from apps.core import config_migration as cm

    tenant = _tenant("shop")
    monkeypatch.setattr(cm, "write_with_snapshot", lambda *a, **kw: None)  # всегда «менялись»
    assert qlm.apply_tenant(tenant).action == qlm.BUSY


# ───────── ревью M2c-3: писатели и блок владельца ─────────


def test_writer_changes_only_the_set_of_the_owners_block():
    """Блок владельца (свой id, скрыт, стоит ниже) — сборка меняет только набор."""
    own = {"key": "quick_links", "id": "mine", "enabled": False, "data": {"set": "mode"}}
    raw = _cfg("shop", sections=[{"key": "hero"}, {"key": "products"}, own])
    new, res = qlm.detach(raw, replace=True)
    rows = [r for r in new["sections"] if r.get("key") == "quick_links"]
    assert res.action == "block-updated" and len(rows) == 1
    assert rows[0]["id"] == "mine" and rows[0]["enabled"] is False
    assert rows[0]["data"] == {"set": "shop"}


def test_none_drops_only_auto_blocks():
    own = {"key": "quick_links", "id": "mine", "data": {"set": "mode"}}
    auto = {"key": "quick_links", "id": qlm.QUICK_LINKS_ID, "data": {"set": "shop"}}
    svc = {"key": "list", "id": qlm.SERVICES_LIST_ID, "data": {"source": "services"}}
    cfg = {"sections": [{"key": "hero"}, auto, svc, own]}
    qlm.drop_auto_blocks(cfg)
    assert [r.get("id") for r in cfg["sections"]] == [None, "mine"]


def test_services_list_is_not_doubled_on_reapply():
    once, _r = qlm.detach(_cfg("services"))
    again, res = qlm.detach({**once, "site_defaults": {"hero_widget": "services"}}, replace=True)
    ids = [r.get("id") for r in again["sections"] if r.get("id") == qlm.SERVICES_LIST_ID]
    assert ids == [qlm.SERVICES_LIST_ID] and res.action == "services-list-exists"


def test_bundle_without_tiles_drops_the_old_auto_block():
    """Шаблон «gastro» ставит автоблок плиток; сборка «без плиток» его снимает."""
    from apps.tenants import sitetemplates

    tenant = TenantFactory(business_type="restaurant")
    assert sitetemplates.apply_template(tenant, "gastro")
    tenant.refresh_from_db()
    assert any(r.get("id") == qlm.QUICK_LINKS_ID for r in tenant.site_config["sections"])
    assert sitetemplates.get_bundle("fokus_gastro")["config"]["hero_widget"] == "none"
    assert sitetemplates.apply_bundle(tenant, "fokus_gastro")
    tenant.refresh_from_db()
    assert not any(r.get("id") == qlm.QUICK_LINKS_ID for r in tenant.site_config["sections"])


def test_preview_of_a_bundle_matches_applying_it():
    from apps.tenants import sitetemplates

    cfg = sitetemplates.apply_preview_bundle(siteconfig.normalize({}), "fokus_hotel")
    assert not cfg["site_defaults"].get("hero_widget")
    keys = [r["key"] for r in cfg["sections"]]
    assert keys[keys.index("hero") + 1] == "stay_search"
