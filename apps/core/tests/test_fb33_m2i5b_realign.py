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


def test_deploy_runs_realign_after_the_new_web_is_up():
    """Ревью п.1: ПОСЛЕ подъёма нового web (наоборот, чем detach_quick_links): старый web не
    знает `event_types_i18n` и Save на нём стёр бы перенесённое; до переноса новый web читает
    старый оверлей запасным путём."""
    sh = Path("scripts/deploy.sh").read_text()
    step = sh.index("$COMPOSE exec -T web python manage.py form_i18n_realign; then")
    assert sh.index("\n$COMPOSE up -d\n") < step
    assert sh.index("manage.py materialize_page_axes --residue") < step
    assert "run --rm web python manage.py form_i18n_realign" not in sh
    assert "наоборот, чем detach_quick_links" in sh


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


def test_rolled_back_site_is_reported_and_errors_hide_text(capsys, monkeypatch):
    """Ревью п.3: откаченный владельцем сайт — «rolled-back» в строке и итоге; ошибка — только
    тип исключения, без текста."""
    from apps.core.management.commands import form_i18n_realign as cmd

    legacy, _clean = _sites()
    call_command("form_i18n_realign")
    call_command("form_i18n_realign", "--undo")
    capsys.readouterr()
    call_command("form_i18n_realign")
    out = capsys.readouterr().out
    assert f"{legacy.schema_name}: rolled-back" in out and "откачено владельцем 1" in out

    def boom(*_a, **_kw):
        raise ValueError("secret-detail")

    monkeypatch.setattr(cmd, "apply_tenant", boom)
    with pytest.raises(Exception, match="не обработаны"):
        call_command("form_i18n_realign")
    err = capsys.readouterr().err
    assert "ValueError" in err and "secret-detail" not in err


def test_dry_run_lists_doubtful_sites(capsys):
    cfg = {
        "anfrage": {"fields": ["event_type"], "event_types": ["A", "B", "A"]},
        "i18n": {"ru": {"anfrage": {"event_types": ["а", "б"]}}},
    }
    site = TenantFactory(site_config=cfg)
    call_command("form_i18n_realign", "--dry-run")
    assert f"{site.schema_name}: длина перевода" in capsys.readouterr().err


def test_old_panel_rename_reports_dropped_translation(monkeypatch):
    """Ревью п.6: старый POST панели переименовал вариант — перевод выпал, владельцу —
    сообщение с названием варианта."""
    from django.contrib import messages

    said = []
    monkeypatch.setattr(messages, "warning", lambda _req, text, **_kw: said.append(str(text)))
    data = {"af_event_type": "on", "af_event_types": "Trauung\nFirmenfeier"}
    _resp, stored = _old_post(copy.deepcopy(POSITIONAL), data)
    norm = siteconfig.normalize(stored)
    assert norm["form_fields"]["anfrage"]["event_types_i18n"] == {
        "Firmenfeier": {"ru": "Корпоратив"}
    }
    assert any("„Hochzeit“" in m for m in said)
