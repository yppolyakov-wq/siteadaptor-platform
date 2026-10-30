"""KA-12 E9.1: библиотека деталей кабинета и тон статуса по роли.

План — `docs/ka-12-w5-e9-1-ui-library-plan-2026-10-30.md`.
"""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.conf import settings
from django.template import Context, Template

from apps.core import status_registry
from apps.core.templatetags.cabinet import ROLE_TONES, tone_for

LIBRARY = [
    "ui-canvas", "ui-topbar", "ui-h1", "ui-h2", "ui-h3", "ui-muted",
    "ui-card", "ui-card-row",
    "ui-btn", "ui-btn-primary", "ui-btn-secondary", "ui-btn-ghost", "ui-btn-danger",
    "ui-btn-danger-outline", "ui-btn-sm", "ui-btn-lg",
    "ui-badge", "ui-tone-new", "ui-tone-ok", "ui-tone-run", "ui-tone-done", "ui-tone-bad",
    "ui-tone-off",
    "ui-tabs", "ui-tab", "ui-tab-count", "ui-seg",
    "ui-field", "ui-label", "ui-input", "ui-help", "ui-field-error", "ui-empty",
]  # fmt: skip

ROOT = Path(settings.BASE_DIR)


def _tenant(cfg=None):
    return SimpleNamespace(schema_name="t1", site_config=cfg or {})


def _render(src, tenant, **ctx):
    request = SimpleNamespace(tenant=tenant)
    return Template("{% load cabinet %}" + src).render(Context({"request": request, **ctx}))


def test_every_builtin_status_gets_the_tone_of_its_role():
    for kind, statuses in status_registry.BUILTIN.items():
        for code, d in statuses.items():
            assert tone_for(kind, code, _tenant()) == ROLE_TONES[d.role], (kind, code)


def test_every_role_has_a_tone():
    assert set(ROLE_TONES) == set(status_registry.ROLES)


def test_confirmed_is_one_colour_across_directions():
    tones = {tone_for(k, "confirmed", _tenant()) for k in ("booking", "stay", "order", "ticket")}
    assert tones == {"ok"}


def test_custom_status_takes_tone_of_its_role():
    t = _tenant({"status_defs": {"order": [{"code": "kulanz", "role": "cancelled"}]}})
    assert tone_for("order", "kulanz", t) == "bad"


@pytest.mark.parametrize("kind,code", [("order", "nope"), ("unknown_kind", "new"), ("order", None)])
def test_unknown_is_neutral(kind, code):
    assert tone_for(kind, code, _tenant()) == "off"


def test_broken_site_config_does_not_crash():
    assert tone_for("order", "x", _tenant({"status_defs": "garbage"})) == "off"
    # не-dict запись внутри kind — доходит до ветки except, а не до 500
    assert tone_for("order", "x", _tenant({"status_defs": {"order": ["x"]}})) == "off"


def test_concrete_tones_are_pinned():
    t = _tenant()
    assert tone_for("order", "new", t) == "new"
    assert tone_for("order", "cancelled", t) == "bad"
    assert tone_for("stay", "fulfilled", t) == "done"


def test_badge_without_choices_shows_label_not_code():
    obj = SimpleNamespace(status="pending")
    html = _render('{% status_badge obj "reservation" %}', _tenant(), obj=obj)
    assert "ui-tone-new" in html and ">pending<" not in html


def test_status_tone_tag_returns_class():
    assert _render('{% status_tone "stay" "no_show" %}', _tenant()) == "ui-tone-bad"


def test_status_badge_uses_owner_label_and_escapes():
    t = _tenant({"status_labels": {"order": {"new": "<b>Eingang</b>"}}})
    obj = SimpleNamespace(status="new", get_status_display=lambda: "Neu")
    html = _render('{% status_badge obj "order" %}', t, obj=obj)
    assert 'class="ui-badge ui-tone-new"' in html
    assert "&lt;b&gt;Eingang&lt;/b&gt;" in html


def test_built_css_contains_every_library_class():
    built = (ROOT / "static/css/app.css").read_text(encoding="utf-8")
    missing = [c for c in LIBRARY if not re.search(r"\." + re.escape(c) + r"[\s{:,.\[>]", built)]
    assert not missing, missing


def test_library_does_not_claim_bare_class_names():
    """Файл общий с витриной/Mini App: голые .btn/.card/.badge перекрасили бы чужое."""
    src = (ROOT / "static/src/app.css").read_text(encoding="utf-8")
    for bare in ("btn", "card", "badge", "tab", "input", "label", "empty"):
        assert not re.search(r"(^|[\s,}])\." + bare + r"[\s{:,]", src), bare
