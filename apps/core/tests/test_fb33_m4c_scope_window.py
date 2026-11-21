"""FB-33 M4c: «Ansicht gilt für» — из Студии в окно блока (вкладка «Wie anordnen»).

Охват вида блока «Liste» («Nur diesen Block» / «Den ganzen Typ», `list_blocks.apply_type_scope`)
выбирают в окне блока — только у «Liste» с источником акций и заданным типом. Выбор живёт в
черновике страницы: предпросмотр показывает вид типа, «Speichern» переносит вид блока в
`promo_groups[тип]` и снимает оси у блока, «Abbrechen» возвращает всё как было, правка типа в
другом месте — конфликт. В Студии селекта больше нет. Замки написаны ДО кода.
"""

import copy
import itertools
import re

import pytest

from apps.core import aufbau_draft
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

_N = itertools.count()
TYPE = "Räumung"


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _block(bid, **data):
    return {"key": "list", "id": bid, "enabled": True, "data": data}


def _shop(*blocks, **cfg):
    t = TenantFactory(slug=f"m4c{next(_N)}", name="M4c")
    t.site_config = {"sections": list(blocks), **cfg}
    t.save(update_fields=["site_config"])
    return t


def _promo_block(bid="a1", **data):
    return _block(bid, **{"source": "promotions", "type": TYPE, **data})


def _saved(tenant) -> dict:
    return siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)


def _row(cfg, bid):
    return next(s for s in cfg["sections"] if s.get("id") == bid)


def _window(browser, ref, extra=""):
    return browser.get(f"?seite=home&block={ref}&tab=wie{extra}")


def _scope(browser, ref, value="type", **extra):
    return browser.post(
        seite="home", op="update", ref=ref, panel_present="1", f_scope=value, **extra
    )


def _draft(browser):
    return aufbau_draft.get(browser._request("get"), "home")


# 1 — поле есть только у «Liste» с типом акции
@pytest.mark.xfail(strict=True, reason="FB-33 M4c: до кода")
def test_field_only_for_a_liste_with_a_promo_type():
    b = Browser(
        _shop(
            _promo_block("a1"),
            _block("a2", source="promotions"),
            _block("a3", source="products"),
        )
    )
    html = _window(b, "a1")
    form = re.search(r"<form[^>]*data-schema-listview.*?</form>", html, re.S).group(0)
    select = re.search(r'<select[^>]*name="f_scope"[^>]*>.*?</select>', form, re.S).group(0)
    assert 'id="schema-l-scope"' in select and 'aria-describedby="schema-l-scope-hint"' in select
    assert re.search(r'<option value=""[^>]*selected', select)
    assert '<option value="type">' in select
    assert re.search(r'<label[^>]*for="schema-l-scope"[^>]*>\s*Ansicht gilt für', form)
    hint = re.search(r'<p id="schema-l-scope-hint"[^>]*>(.*?)</p>', form, re.S).group(1)
    assert TYPE in hint
    assert 'name="f_scope"' not in _window(b, "a2")
    assert 'name="f_scope"' not in _window(b, "a3")
    assert 'name="f_scope"' not in _window(b, "promotions")  # встроенный список главной


# 2 — «Den ganzen Typ» → «Speichern»: вид у типа, оси у блока сняты, scope в конфиге нет
@pytest.mark.xfail(strict=True, reason="FB-33 M4c: до кода")
def test_save_moves_the_view_to_the_type():
    b = Browser(
        _shop(
            _promo_block("a1", out="slider", card="coupon"),
            _promo_block("a2", title="Zweiter"),
            promo_groups={TYPE: "countdown"},
        )
    )
    before = copy.deepcopy(Tenant.objects.get(pk=b.tenant.pk).site_config)
    resp, _msgs = _scope(b, "a1")
    assert resp.status_code == 302
    assert Tenant.objects.get(pk=b.tenant.pk).site_config == before  # пока только черновик
    assert "data-schema-draft" in b.get("?seite=home")
    _resp, msgs = b.post(seite="home", op="save")
    assert any("Gespeichert" in m for m in msgs)
    cfg = _saved(b.tenant)
    entry = cfg["promo_groups"][TYPE]
    assert entry["card"] == "coupon" and entry["layout"]["scroll"] is True
    assert entry["style"] == "countdown"  # шаблон страницы типа не тронут
    data = _row(cfg, "a1")["data"]
    assert not {"out", "card", "scope"} & set(data)
    assert "scope" not in str(Tenant.objects.get(pk=b.tenant.pk).site_config)
    assert _draft(b) is None


# 3 — предпросмотр показывает вид типа; окно — выбранный охват и свои оси блока
@pytest.mark.xfail(strict=True, reason="FB-33 M4c: до кода")
def test_preview_shows_the_type_view_and_the_window_keeps_the_choice():
    b = Browser(_shop(_promo_block("a1", out="slider", card="coupon"), _promo_block("a2")))
    _scope(b, "a1")
    draft = _draft(b)
    shown = siteconfig.normalize(aufbau_draft.overlay(_saved(b.tenant), draft))
    assert shown["promo_groups"][TYPE]["card"] == "coupon"
    assert shown["promo_groups"][TYPE]["layout"]["scroll"] is True
    assert "card" not in _row(shown, "a1")["data"]
    html = _window(b, "a1")
    select = re.search(r'<select[^>]*name="f_scope"[^>]*>.*?</select>', html, re.S).group(0)
    assert re.search(r'<option value="type"[^>]*selected', select)
    # оси блока в окне — как были: «Übernehmen» без правок не стирает вид типа
    assert re.search(r'name="f_out" value="slider"[^>]*checked', html)
    # «Nur diesen Block» — выбор снят, черновика нет
    _scope(b, "a1", "")
    assert _draft(b) is None


# 4 — «Abbrechen» окна: байт-в-байт
@pytest.mark.xfail(strict=True, reason="FB-33 M4c: до кода")
def test_cancel_restores_everything():
    b = Browser(
        _shop(_promo_block("a1", out="slider", card="coupon"), promo_groups={TYPE: "countdown"})
    )
    before = copy.deepcopy(Tenant.objects.get(pk=b.tenant.pk).site_config)
    _scope(b, "a1", wopen="tok12345")
    assert (_draft(b) or {}).get("scope")
    _resp, msgs = b.post(seite="home", op="revert", ref="a1", wopen="tok12345")
    assert any("zurückgenommen" in m for m in msgs)
    assert _draft(b) is None
    assert Tenant.objects.get(pk=b.tenant.pk).site_config == before
    assert not re.search(r'<option value="type"[^>]*selected', _window(b, "a1"))


# 5 — настройки типа изменили в другом месте → конфликт; чужой тип — не конфликт
@pytest.mark.xfail(strict=True, reason="FB-33 M4c: до кода")
def test_type_changed_elsewhere_is_a_conflict():
    b = Browser(_shop(_promo_block("a1", card="coupon"), promo_groups={TYPE: "countdown"}))
    _scope(b, "a1")
    t = Tenant.objects.get(pk=b.tenant.pk)
    t.site_config = {**t.site_config, "promo_groups": {TYPE: "countdown", "Other": "rows"}}
    t.save(update_fields=["site_config"])
    req = b._request("get")
    assert aufbau_draft.info(req, _saved(t), "home")["conflict"] is False
    t.site_config = {
        **t.site_config,
        "promo_groups": {TYPE: {"style": "countdown", "card": "ring"}},
    }
    t.save(update_fields=["site_config"])
    req = b._request("get")
    assert aufbau_draft.info(req, _saved(t), "home")["conflict"] is True
    with pytest.raises(aufbau_draft.DraftConflict):
        aufbau_draft.commit(req, b.tenant, "home")
    assert _saved(t)["promo_groups"][TYPE]["card"] == "ring"
    _resp, msgs = b.post(seite="home", op="save")
    assert any("an anderer Stelle" in m for m in msgs)


# 6 — в Студии селекта нет, поддельное поле формы вид типу не отдаёт
@pytest.mark.xfail(strict=True, reason="FB-33 M4c: до кода")
def test_studio_has_no_scope_control():
    from pathlib import Path

    from django.conf import settings

    from apps.core import views

    b = Browser(_shop(_promo_block("a1", card="coupon")))
    req = b._request("get")
    body = views.home_builder_view(req).content.decode()
    assert "data-lb-scope" not in body and "cb_a1_scope" not in body
    assert "scope" not in views._LIST_BLOCK_FIELDS
    root = Path(settings.BASE_DIR) / "templates" / "tenant"
    for name in ("site_home.html", "_cb_row.html"):
        assert "lb-scope" not in (root / name).read_text(), name
    post = {
        "cb_id": ["a1"],
        "cb_type_a1": "list",
        "enabled_cb_a1": "on",
        "order_cb_a1": "1",
        "cb_a1_scope": "type",
    }
    assert views.home_builder_view(b._request("post", post)).status_code == 302
    cfg = _saved(b.tenant)
    assert TYPE not in (cfg.get("promo_groups") or {})
    assert _row(cfg, "a1")["data"]["card"] == "coupon"


# 7 — без JS: одна форма вкладки шлёт вид и охват; смена типа блока снимает охват
@pytest.mark.xfail(strict=True, reason="FB-33 M4c: до кода")
def test_plain_form_post_and_stale_scope():
    b = Browser(_shop(_promo_block("a1"), promo_groups={TYPE: {"card": "ring"}}))
    _scope(b, "a1", f_out="slider", f_cols="3", f_rows="", f_style="")
    draft = _draft(b)
    assert draft["scope"] == {"a1": "type"}
    assert _row({"sections": draft["items"]}, "a1")["data"]["out"] == "slider"
    assert "scope" not in _row({"sections": draft["items"]}, "a1")["data"]
    # форма без поля охвата (вкладка «Was», «zurücksetzen») выбор не трогает
    b.post(seite="home", op="update", ref="a1", panel_present="1", f_title="Neu")
    assert _draft(b)["scope"] == {"a1": "type"}
    # тип у блока убрали — охват отдавать некому
    b.post(seite="home", op="update", ref="a1", panel_present="1", f_type="")
    assert "scope" not in _draft(b)
    b.post(seite="home", op="save")
    cfg = _saved(b.tenant)
    assert cfg["promo_groups"][TYPE] == {"card": "ring"}
    assert _row(cfg, "a1")["data"]["out"] == "slider"


# 8 — права: настройки типа пишет «Aktionstypen» (marketing.edit)
@pytest.mark.xfail(strict=True, reason="FB-33 M4c: до кода")
def test_scope_needs_the_right_to_edit_promo_types(monkeypatch):
    from apps.core import list_panel

    b = Browser(_shop(_promo_block("a1", card="coupon")))
    _scope(b, "a1")
    assert _draft(b)["scope"] == {"a1": "type"}
    monkeypatch.setattr("apps.core.view_perms.url_allowed", lambda user, url, method="GET": False)
    assert 'name="f_scope"' not in _window(b, "a1")
    # право отозвали до «Speichern»: страница сохраняется, вид типу не уходит — с пометкой
    b.post(seite="home", op="toggle", ref="a1")
    _resp, msgs = b.post(seite="home", op="save")
    assert msgs[0] == "Gespeichert." and list_panel.scope_rights_note() in msgs
    cfg = _saved(b.tenant)
    assert TYPE not in (cfg.get("promo_groups") or {})
    assert _row(cfg, "a1")["data"]["card"] == "coupon"
    # без права поддельный POST охват не ставит
    _scope(b, "a1")
    assert not (_draft(b) or {}).get("scope")
