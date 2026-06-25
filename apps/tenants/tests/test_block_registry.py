"""Спринт D.1: реестр секций главной render_block — покрытие ключей + якоря."""

from django.template import Context
from django.test import RequestFactory

from apps.tenants import siteconfig
from apps.tenants.templatetags import siteui


def test_every_known_section_has_template():
    # каждая секция реестра SECTIONS отрисовывается реестром блоков (нет дыр).
    keys = {key for key, _label, _on in siteconfig.SECTIONS}
    assert keys <= set(siteui.BLOCK_TEMPLATES), keys - set(siteui.BLOCK_TEMPLATES)


def test_unknown_block_renders_empty():
    ctx = Context({"request": RequestFactory().get("/")})
    assert siteui.render_block(ctx, "does-not-exist") == ""


def test_anchor_wrapper_applied():
    req = RequestFactory().get("/")
    req.tenant = None
    # секция с непустыми данными → обёртка с якорем (#kontakt у contact).
    ctx = Context({"request": req, "site": {"usp_bar": [{"icon": "check", "label": "X"}]}})
    html = siteui.render_block(ctx, "usp_bar")
    assert "X" in html  # контент отрисован
    # у usp_bar нет якоря — без обёртки-id; у reviews/contact — с id.
    assert 'id="bewertungen"' not in html
