"""FB-33 M3-5c C3: переводы вопросов FAQ, своих вопросов объекта и подписей плашек в окне.

L16 общие вопросы: поля перевода у вопроса с источником (у нового — после «Speichern»),
номер поля — позиция в окне, ключ — индекс источника: после ↑↓ перевод едет за вопросом и по
«Speichern» встаёт на своё место. L17 свои вопросы объекта — тем же путём, только с правом на
объект; подпись плашки — поле перевода только при своей немецкой подписи.
"""

import copy
import re

import pytest

from apps.core import faq_content
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m35b_faq_draft import BASE, RU, _drafts, _faq_post, _saved, _tenant

pytestmark = pytest.mark.django_db


def _ml(tenant, locales=("de", "ru")):
    tenant.enabled_locales = list(locales)
    tenant.save()
    return tenant


def _form(html, fid="bw-form-faq"):
    m = re.search(rf'<form[^>]*id="{fid}".*?</form>', html, flags=re.S)
    return m.group(0) if m else ""


def test_faq_window_has_translation_fields_by_question():
    b = Browser(_ml(_tenant()))
    form = _form(b.get("?seite=home&block=faq&tab=texte"))
    assert 'name="faq_0_q_ru" value="А?"' in form and 'name="faq_2_a_ru"' in form
    assert '<span lang="de">„Frage 1“</span> – Übersetzung (Русский)' in form
    assert 'name="f_sprache" value="ru"' in form
    first = re.search(r"<button[^>]*>", form).group(0)
    assert 'name="faq_add"' in first  # Enter — по-прежнему «Übernehmen»


def test_faq_translation_follows_its_question_to_the_site():
    b = Browser(_ml(_tenant()))
    _faq_post(b, faq_1_q_ru="Б-новый?")
    assert _drafts(b)["home"]["btr"]["faq"] == {"ru": {"faq.1.q": "Б-новый?"}}
    _faq_post(b, faq_move="1:up")  # B? встал первым — поле перевода теперь faq_0_q_ru
    form = _form(b.get("?seite=home&block=faq&tab=texte"))
    assert 'name="faq_0_q_ru" value="Б-новый?"' in form
    b.post(seite="home", op="save")
    cfg = _saved(b)
    assert [i["q"] for i in cfg["faq"]] == ["B?", "A?", "C?"]
    assert cfg["i18n"]["ru"]["faq"][0]["q"] == "Б-новый?" and cfg["i18n"]["ru"]["faq"][1] == RU[0]


def test_new_question_has_no_translation_fields_until_saved():
    b = Browser(_ml(_tenant()))
    _faq_post(b, faq_add="1", faq_new_q="D?", faq_new_a="4")
    form = _form(b.get("?seite=home&block=faq&tab=texte"))
    assert 'name="faq_3_q"' in form and 'name="faq_3_q_ru"' not in form


def test_german_faq_edit_drops_the_translation_unless_typed():
    b = Browser(_ml(_tenant()))
    items = copy.deepcopy(BASE)
    items[0]["q"] = "A neu?"
    _resp, msgs = _faq_post(b, faq_0_q="A neu?")
    assert any("Übersetzung entfernt" in m and "Русский" in m for m in msgs)
    b.post(seite="home", op="save")
    assert "q" not in _saved(b)["i18n"]["ru"]["faq"][0]
    del items


def test_object_faq_translation_needs_rights(monkeypatch):
    from apps.core import object_faq, view_perms
    from apps.core.tests.test_fb33_m2b2b_window import _post, _setup, _svc, own_block

    monkeypatch.setattr(view_perms, "allowed", lambda *a, **k: True)
    tenant, svc, code = _setup(blocks=[own_block()])
    b = Browser(tenant)
    from django.test import override_settings

    with override_settings(ROOT_URLCONF="config.urls_tenant"):
        _post(b, code, svc, faq_1_q_ru="Мыть волосы?")
        b.post(seite=code, op="save")
        assert object_faq.overlays(_svc(svc), "service")["ru"][1] == {"q": "Мыть волосы?"}
        monkeypatch.setattr(view_perms, "allowed", lambda *a, **k: False)
        _resp, msgs = _post(b, code, svc, faq_0_q_ru="Нельзя")
    assert object_faq.error_note("ofaq_rights") in msgs
    assert faq_content is not None


def test_tile_translation_only_with_own_label():
    from apps.core import hero_tiles
    from apps.core.tests.test_fb33_m35b_tiles_window import _tenant as tiles_tenant

    keys = hero_tiles.tile_keys("aktionsmarkt")
    tenant = _ml(tiles_tenant({"set": "aktionsmarkt", "labels": {keys[0]: "Meine Deals"}}))
    form = _form(Browser(tenant).get("?seite=home&block=quicklinks"), "bw-form-tiles")
    assert f'name="f_tr_label_{keys[0]}_ru"' in form
    assert f'name="f_tr_label_{keys[1]}_ru"' not in form
    hero_label = str(hero_tiles.QUICK_LINK_TILES["aktionsmarkt"][0][1])  # подпись плашки, не своя
    assert '<span lang="de">„' + hero_label + "“</span> – Übersetzung (Русский)" in form
