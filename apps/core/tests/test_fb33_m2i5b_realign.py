"""FB-33 M2i-5b C4: перенос старых позиционных переводов вариантов события и старые писатели.

* команда `form_i18n_realign` (шаг `deploy.sh` после миграций, до подъёма нового web):
  `--dry-run` — отчёт и предупреждение о неточности, без записи; без флага — перенос ключом
  по тексту и чистка `i18n.*.anfrage`; повтор — 0 изменений; `--undo` — откат по снимку;
* после переноса витрина на ru — те же подписи, что с позиционным оверлеем (замок C0);
* старый POST панели «Anfrage-Formular» впитывает позиционные переводы под блокировкой;
* `anfrage` — вне `TRANSLATABLE_KEYS` (редактор языка не пишет оверлей вариантов).
"""

import copy
import json
from pathlib import Path

import pytest
from django.core.management import call_command
from django.utils import translation

from apps.core.tests.test_fb33_m2i5_before import _old_post
from apps.core.tests.test_fb33_m2i5b_before import GOLDEN, POSITIONAL, anfrage_html
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _sites():
    legacy = TenantFactory(site_config=copy.deepcopy(POSITIONAL))
    clean = TenantFactory(site_config={"hero_title": "Hallo"})
    return legacy, clean


def _cfg(tenant):
    return Tenant.objects.get(pk=tenant.pk).site_config


def test_dry_run_reports_and_warns_without_writing(capsys):
    legacy, clean = _sites()
    before = json.dumps(_cfg(legacy), sort_keys=True)
    call_command("form_i18n_realign", "--dry-run")
    out = capsys.readouterr()
    assert f"{legacy.schema_name}: would-move" in out.out
    assert clean.schema_name not in out.out
    assert "сайтов с позиционным переводом 1" in out.out and "схем " in out.out
    assert "перенос по позиции неточен" in out.err
    assert json.dumps(_cfg(legacy), sort_keys=True) == before


def test_realign_moves_cleans_and_is_idempotent(capsys):
    legacy, clean = _sites()
    with translation.override("ru"):
        shown_before = anfrage_html(_cfg(legacy))
    call_command("form_i18n_realign")
    cfg = _cfg(legacy)
    assert "i18n" not in cfg
    assert cfg["form_fields"]["anfrage"]["event_types_i18n"] == {
        "Hochzeit": {"ru": "Свадьба"},
        "Firmenfeier": {"ru": "Корпоратив"},
    }
    assert _cfg(clean) == {"hero_title": "Hallo"}
    with translation.override("ru"):
        assert anfrage_html(cfg) == shown_before
        assert anfrage_html(cfg) == (GOLDEN / "anfrage-positional-ru.html").read_text()
    capsys.readouterr()
    call_command("form_i18n_realign")
    assert "сайтов изменено 0" in capsys.readouterr().out


def test_realign_undo_restores_snapshot():
    legacy, _clean = _sites()
    call_command("form_i18n_realign")
    call_command("form_i18n_realign", "--undo")
    assert _cfg(legacy)["i18n"] == POSITIONAL["i18n"]
    assert "event_types_i18n" not in _cfg(legacy)["form_fields"]["anfrage"]
    call_command("form_i18n_realign")  # откатил владелец — не повторяем
    assert _cfg(legacy)["i18n"] == POSITIONAL["i18n"]


def test_deploy_runs_realign_after_migrations_before_new_web():
    sh = Path("scripts/deploy.sh").read_text()
    step = sh.index("$COMPOSE run --rm web python manage.py form_i18n_realign; then")
    assert sh.index("migrate_schemas --tenant;") < step < sh.index('step "[7/8] Restart services"')
    assert sh.index("manage.py detach_quick_links --residue") < step


def test_old_panel_post_absorbs_positional_translations():
    data = {"af_event_type": "on", "af_event_types": "Firmenfeier\nHochzeit\nTaufe"}
    _resp, stored = _old_post(POSITIONAL, data)
    assert "i18n" not in stored
    norm = siteconfig.normalize(stored)
    assert norm["anfrage"]["event_types"] == ["Firmenfeier", "Hochzeit", "Taufe"]
    assert norm["form_fields"]["anfrage"]["event_types_i18n"] == {
        "Firmenfeier": {"ru": "Корпоратив"},  # перевод едет с вариантом, а не с позицией
        "Hochzeit": {"ru": "Свадьба"},
    }


def test_anfrage_is_not_a_translatable_overlay_key():
    assert "anfrage" not in siteconfig.TRANSLATABLE_KEYS
    payload = {"anfrage": {"event_types": ["Свадьба"]}}
    base = {"anfrage": {"event_types": ["Hochzeit"]}}
    out = siteconfig.split_translation(copy.deepcopy(payload), base, "ru")
    assert "anfrage" not in (out.get("i18n") or {}).get("ru", {})
