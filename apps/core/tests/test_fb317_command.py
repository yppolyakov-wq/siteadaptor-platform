"""FB-31.7: команда `materialize_page_axes` — шаг deploy.sh (решение владельца): снимок до
правки, повтор без изменений, откат, пропуск при расхождении, сбой сайта не роняет остальных."""

from io import StringIO

import pytest
from django.core.management import call_command

from apps.core import page_axes_migration as pam
from apps.tenants.models import SiteConfigSnapshot
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _run(*args):
    out, err = StringIO(), StringIO()
    call_command("materialize_page_axes", *args, stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


def _tenant(cfg):
    return TenantFactory(site_config=cfg)


def test_moves_codes_keeps_a_snapshot_and_rerun_does_nothing():
    t = _tenant({"page_styles": {"services": "kopfbild"}})
    out, _ = _run("--schema", t.schema_name)
    t.refresh_from_db()
    assert "services=done" in out
    assert t.site_config["page_blocks"]["services"], "оси — строками"
    assert t.site_config["page_styles"] == {"services": "kopfbild"}, "старый ключ — до релиза"
    snap = SiteConfigSnapshot.objects.get(tenant=t)
    assert snap.before == {"page_styles": {"services": "kopfbild"}}
    out, _ = _run("--schema", t.schema_name)
    assert SiteConfigSnapshot.objects.filter(tenant=t).count() == 1, "повтор — 0 изменений"


def test_dry_run_writes_nothing():
    t = _tenant({"page_styles": {"events": "tabs"}})
    out, _ = _run("--schema", t.schema_name, "--dry-run")
    t.refresh_from_db()
    assert "events=done" in out and "page_blocks" not in t.site_config
    assert not SiteConfigSnapshot.objects.filter(tenant=t).exists()


def test_undo_restores_and_the_next_deploy_leaves_the_site_alone():
    cfg = {"page_styles": {"services": "kopfbild"}}
    t = _tenant(cfg)
    _run("--schema", t.schema_name)
    out, _ = _run("--schema", t.schema_name, "--undo")
    t.refresh_from_db()
    assert "undone" in out and t.site_config == cfg
    _run("--schema", t.schema_name)  # следующий деплой
    t.refresh_from_db()
    assert t.site_config == cfg, "откат владельца не перекрывается"


def test_undo_refuses_when_settings_changed_since():
    t = _tenant({"page_styles": {"services": "kopfbild"}})
    _run("--schema", t.schema_name)
    t.refresh_from_db()
    t.site_config = {**t.site_config, "hero_title": "neu"}
    t.save(update_fields=["site_config"])
    out, _ = _run("--schema", t.schema_name, "--undo")
    t.refresh_from_db()
    assert "changed" in out and t.site_config["hero_title"] == "neu"


def test_one_failing_site_does_not_stop_the_others(monkeypatch):
    bad = _tenant({"page_styles": {"services": "kopfbild"}})
    good = _tenant({"page_styles": {"events": "tabs"}})
    real = pam.apply_tenant

    def flaky(tenant, **kw):
        if tenant.pk == bad.pk:
            raise RuntimeError("boom")
        return real(tenant, **kw)

    monkeypatch.setattr(pam, "apply_tenant", flaky)
    with pytest.raises(Exception, match=bad.schema_name):
        _run()
    good.refresh_from_db()
    assert good.site_config.get("page_blocks", {}).get("events")


def test_deploy_runs_the_step_and_does_not_stop_on_failure():
    import pathlib

    src = pathlib.Path("scripts/deploy.sh").read_text()
    assert "if ! $COMPOSE exec -T web python manage.py materialize_page_axes; then" in src
