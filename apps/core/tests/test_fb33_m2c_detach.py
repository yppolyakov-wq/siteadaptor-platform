"""FB-33 M2c-2: перенос «Быстрых ссылок» из баннера в блок (`detach_quick_links`)."""

import pytest
from django.core.management import call_command

from apps.core import quick_links_migration as qlm
from apps.tenants import siteconfig
from apps.tenants.models import SiteConfigSnapshot, Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _cfg(widget, **extra):
    """Сайт с включённым баннером (по умолчанию баннер главной выключен — тогда плиток
    не видно, и перенос ставит замену скрытой)."""
    extra.setdefault("sections", [{"key": "hero", "enabled": True}])
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
    assert "hero_widget" not in _norm(new)["site_defaults"]  # M2c-4: баннер ключ не читает


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
    call_command("detach_quick_links", "--undo", "--force", "--schema", tenant.schema_name)
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
    from django.core.management.base import CommandError

    _tenant("shop")
    with pytest.raises(CommandError, match="остаток 1"):  # ревью M2c-4: WARN в deploy.sh
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


def test_deploy_runs_it_before_the_new_web_starts():
    """Ревью M2c-4: новый код ключ не читает — Save неперенесённого сайта уронил бы его.
    Перенос идёт после миграций тенантов и ДО `up -d` (пока работает старый web)."""
    import pathlib

    sh = pathlib.Path("scripts/deploy.sh").read_text()
    step = sh.index("$COMPOSE run --rm web python manage.py detach_quick_links; then")
    assert sh.index("migrate_schemas --tenant;") < step < sh.index('step "[7/8] Restart services"')
    assert "$COMPOSE run --rm web python manage.py detach_quick_links --residue" in sh
    assert "exec -T web python manage.py detach_quick_links" not in sh
    assert "tiles are NOT shown until detach_quick_links runs" in sh
    assert "keep the tiles in the banner" not in sh


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
    from django.core.management.base import CommandError

    with pytest.raises(CommandError, match="пропущено сайтов: 1"):  # ревью M2c-4: код ≠ 0
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
    tenant = TenantFactory(site_config={"site_defaults": {"hero_widget": "shop"}})
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


@pytest.mark.parametrize("widget", ("shop", "stays", "services"))
def test_switched_off_banner_gets_hidden_replacements(widget):
    """Стенд M2c: баннер выключен — его плиток не было видно; после переноса тоже не видно."""
    raw = _cfg(widget, sections=[{"key": "hero", "enabled": False}])
    new, res = qlm.detach(raw)
    rows = _norm(new)["sections"]
    keys = [r["key"] for r in rows]
    nxt = rows[keys.index("hero") + 1]
    assert nxt["enabled"] is False, (widget, nxt)
    assert qlm.verify(raw, new, res.action) == ""


# --- M2c-4: `place` — единая точка для писателей (ключ не читает) ---------------------


def test_place_puts_the_set_without_reading_or_writing_the_key():
    cfg = {"sections": [{"key": "hero", "enabled": True}], "site_defaults": {"radius": 8}}
    new, res = qlm.place(cfg, "shop")
    assert res.action == "block" and res.changed
    assert _keys(new)[:2] == ["hero", "quick_links"]
    assert new["site_defaults"] == {"radius": 8}
    assert cfg == {"sections": [{"key": "hero", "enabled": True}], "site_defaults": {"radius": 8}}


def test_place_ignores_a_raw_key_it_is_not_asked_about():
    cfg = _cfg("friseur")
    new, res = qlm.place(cfg, "")
    assert new is cfg and not res.changed
    new, _res = qlm.place(cfg, "shop")
    assert new["site_defaults"]["hero_widget"] == "friseur"  # ключ — дело `detach`


@pytest.mark.parametrize("bad", ("evil", 3, ["shop"]))
def test_place_skips_garbage(bad):
    new, res = qlm.place({}, bad)
    assert new == {} and res.action == "skip:bad-widget"


def test_legacy_widgets_are_link_sets_plus_search_and_services():
    from apps.core import hero_tiles

    assert qlm.LEGACY_WIDGETS == (*hero_tiles.QUICK_LINK_SETS, "stays", "services")


def test_verify_catches_a_key_left_behind():
    before = _cfg("shop")
    new, res = qlm.detach(before)
    assert qlm.verify(before, new, res.action) == ""
    left = {**new, "site_defaults": {**new["site_defaults"], "hero_widget": "shop"}}
    assert qlm.verify(before, left, res.action) == "key-left"


def test_undo_without_force_warns_and_changes_nothing(capsys):
    """M2c-4: витрина ключ не читает — откат без `--force` вернул бы сайт без плиток."""
    from django.core.management.base import CommandError

    tenant = _tenant("shop")
    call_command("detach_quick_links", "--schema", tenant.schema_name)
    moved = Tenant.objects.get(pk=tenant.pk).site_config
    with pytest.raises(CommandError, match="--force"):
        call_command("detach_quick_links", "--undo", "--schema", tenant.schema_name)
    assert "плитки пропадут" in capsys.readouterr().err
    assert Tenant.objects.get(pk=tenant.pk).site_config == moved


def test_undo_with_force_still_warns(capsys):
    tenant = _tenant("shop")
    call_command("detach_quick_links", "--schema", tenant.schema_name)
    call_command("detach_quick_links", "--undo", "--force", "--schema", tenant.schema_name)
    assert "плитки пропадут" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("args", "msg"),
    ((("--force",), "только вместе с --undo"), (("--undo", "--dry-run"), "dry-run")),
)
def test_meaningless_flag_combinations_are_refused(args, msg):
    from django.core.management.base import CommandError

    tenant = _tenant("shop")
    before = Tenant.objects.get(pk=tenant.pk).site_config
    with pytest.raises(CommandError, match=msg):
        call_command("detach_quick_links", *args, "--schema", tenant.schema_name)
    assert Tenant.objects.get(pk=tenant.pk).site_config == before


def test_skip_is_logged_with_the_schema(caplog):
    from django.core.management.base import CommandError

    tenant = _tenant("shop")
    Tenant.objects.filter(pk=tenant.pk).update(
        site_config={"site_defaults": {"hero_widget": "nonsense"}}
    )
    with caplog.at_level("WARNING"), pytest.raises(CommandError):
        call_command("detach_quick_links", "--schema", tenant.schema_name)
    assert any(
        tenant.schema_name in r.getMessage() and "skip:bad-widget" in r.getMessage()
        for r in caplog.records
    )


def test_rolled_back_site_is_not_an_error(capsys):
    tenant = _tenant("shop")
    call_command("detach_quick_links", "--schema", tenant.schema_name)
    call_command("detach_quick_links", "--undo", "--force", "--schema", tenant.schema_name)
    call_command("detach_quick_links", "--schema", tenant.schema_name)  # откатил — без ошибки
    assert "Готово" in capsys.readouterr().out


def test_residue_survives_a_broken_site_and_reports_it(monkeypatch, capsys):
    from django.core.management.base import CommandError

    a, b = _tenant("shop"), TenantFactory(site_config={})

    def boom(t):
        if t.pk == a.pk:
            raise ValueError("bad")
        return False

    monkeypatch.setattr(qlm, "residue", boom)
    with pytest.raises(CommandError, match="не проверено 1"):
        call_command("detach_quick_links", "--residue")
    out = capsys.readouterr()
    assert "quick_links residue: 0" in out.out and f"{a.schema_name}: ОШИБКА" in out.err
    assert b.schema_name not in out.err


def test_bundle_rebuild_gives_the_owners_block_the_bundles_set(monkeypatch):
    """Решение M2c-3 (замок ревью M2c-4): сборка с перестройкой главной меняет НАБОР уже
    стоящего блока владельца — место, id и видимость остаются его; «none» блок владельца
    не снимает (снимаются только автоблоки)."""
    from apps.tenants import sitetemplates

    owner = {"key": "quick_links", "id": "own", "enabled": False, "data": {"set": "shop"}}
    base = {"sections": [{"key": "hero", "enabled": True}, {"key": "about"}, owner]}
    bundle = dict(sitetemplates.get_bundle("fokus_gastro"))
    bundle["config"] = {**bundle["config"], "hero_widget": "gastro"}
    monkeypatch.setitem(sitetemplates._BUNDLE_BY_KEY, "fokus_gastro", bundle)
    tenant = TenantFactory(business_type="restaurant", site_config=base)
    assert sitetemplates.apply_bundle(tenant, "fokus_gastro", rebuild_home=True)
    blocks = [r for r in tenant.site_config["sections"] if r.get("key") == "quick_links"]
    assert len(blocks) == 1
    assert blocks[0]["id"] == "own" and blocks[0]["enabled"] is False
    assert blocks[0]["data"] == {"set": "gastro"}
    monkeypatch.undo()
    assert sitetemplates.apply_bundle(tenant, "fokus_gastro", rebuild_home=True)  # «none»
    blocks = [r for r in tenant.site_config["sections"] if r.get("key") == "quick_links"]
    assert [b["id"] for b in blocks] == ["own"]
