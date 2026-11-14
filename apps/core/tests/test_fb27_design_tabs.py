"""FB-27 «Design», срез D-a: вкладки «Fertige Designs · Farben & Schrift · Karten & Fotos».
Форма на вкладку; нетронутая форма ничего не меняет (W0)."""

from html.parser import HTMLParser
from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import design_page
from apps.tenants import siteconfig, sitetemplates
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _req(method, tenant, data=None, query=""):
    req = getattr(RequestFactory(), method)("/dashboard/design/" + query, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return req


def _html(tenant, query=""):
    return design_page.design_view(_req("get", tenant, query=query)).content.decode()


class _Form(HTMLParser):
    """Поля формы настроек так, как их отправил бы браузер без единой правки."""

    def __init__(self):
        super().__init__()
        self.inside = False
        self.fields: list[tuple[str, str]] = []
        self._select = None
        self._picked = None
        self._first = None
        self._area = None
        self._text = ""

    def handle_data(self, data):
        if self._area is not None:
            self._text += data

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form" and "data-design-form" in a:
            self.inside = True
        if not self.inside:
            return
        if tag == "input" and a.get("name"):
            kind = a.get("type", "text")
            if kind in ("checkbox", "radio"):
                if "checked" in a:
                    self.fields.append((a["name"], a.get("value", "on")))
            elif kind != "submit":
                self.fields.append((a["name"], a.get("value", "")))
        elif tag == "textarea" and a.get("name"):
            self._area, self._text = a["name"], ""
        elif tag == "select":
            self._select, self._picked, self._first = a.get("name"), None, None
        elif tag == "option" and self._select:
            value = a.get("value", "")
            if self._first is None:
                self._first = value
            if "selected" in a:
                self._picked = value

    def handle_endtag(self, tag):
        if tag == "textarea" and self._area is not None:
            # браузер отбрасывает первый перевод строки сразу после <textarea>
            text = self._text[1:] if self._text.startswith("\n") else self._text
            self.fields.append((self._area, text))
            self._area = None
        if tag == "select" and self._select:
            picked = self._picked if self._picked is not None else self._first
            self.fields.append((self._select, picked or ""))
            self._select = None
        if tag == "form":
            self.inside = False


def _untouched_post(tenant, tab):
    form = _Form()
    form.feed(_html(tenant, f"?tab={tab}"))
    assert form.fields, tab
    data = {}
    for name, value in form.fields:
        data[name] = value
    return design_page.design_view(_req("post", tenant, data))


def test_three_tabs_and_the_first_is_ready_designs():
    tenant = TenantFactory(business_type="online_shop")
    body = _html(tenant)
    assert body.count("data-design-tab=") == 3
    assert body.count('aria-current="page"') >= 1
    assert 'data-design-tab="fertig" aria-current="page"' in body
    assert "data-design-card=" in body and 'name="accent"' not in body


def test_each_tab_shows_only_its_own_form():
    tenant = TenantFactory(business_type="online_shop")
    colours = _html(tenant, "?tab=farben")
    assert 'name="accent"' in colours and 'name="theme_present"' in colours
    assert 'name="sd_cards_present"' not in colours and 'name="bundle"' not in colours
    cards = _html(tenant, "?tab=karten")
    assert 'name="sd_cards_present"' in cards and 'name="quick_add_present"' in cards
    assert 'name="accent"' not in cards and 'name="theme_present"' not in cards


def test_unknown_tab_opens_the_first_one():
    tenant = TenantFactory(business_type="online_shop")
    assert 'data-design-tab="fertig" aria-current="page"' in _html(tenant, "?tab=<x>")


def test_save_returns_to_its_tab_and_ignores_rubbish():
    tenant = TenantFactory(business_type="online_shop")
    resp = design_page.design_view(
        _req("post", tenant, {"action": "design_settings", "tab": "karten"})
    )
    assert resp["Location"].endswith("?tab=karten")
    resp = design_page.design_view(
        _req("post", tenant, {"action": "design_settings", "tab": "//evil.example"})
    )
    assert "evil" not in resp["Location"]


@pytest.mark.parametrize("tab", ["farben", "karten"])
@pytest.mark.parametrize(
    "look", ["", *[lk["key"] for lk in sitetemplates.looks_for("online_shop")]]
)
def test_untouched_form_changes_nothing(tab, look):
    tenant = TenantFactory(business_type="online_shop")
    if look:
        assert sitetemplates.apply_look(tenant, look)
    tenant = Tenant.objects.get(pk=tenant.pk)
    before = siteconfig.normalize(tenant.site_config)
    colour = tenant.primary_color
    resp = _untouched_post(tenant, tab)
    assert resp.status_code == 302
    tenant = Tenant.objects.get(pk=tenant.pk)
    assert siteconfig.normalize(tenant.site_config) == before
    assert tenant.primary_color == colour


def test_cards_form_leaves_colours_alone_and_back():
    tenant = TenantFactory(business_type="online_shop")
    assert sitetemplates.apply_look(tenant, "neon")
    tenant = Tenant.objects.get(pk=tenant.pk)
    before = siteconfig.normalize(tenant.site_config)
    design_page.design_view(
        _req(
            "post",
            tenant,
            {"action": "design_settings", "tab": "karten", "sd_cards_present": "1",
             "sd_card_radius": "12"},
        )
    )  # fmt: skip
    after = siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)
    assert after.get("theme") == before.get("theme") and after.get("font") == before.get("font")
    assert after.get("typography") == before.get("typography")
    design_page.design_view(
        _req("post", tenant, {"action": "design_settings", "tab": "farben", "font": "serif"})
    )
    last = siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)
    assert last["site_defaults"] == after["site_defaults"]


def test_screen_speaks_formally_and_names_the_subject():
    tenant = TenantFactory(business_type="online_shop")
    body = _html(tenant)
    assert "So sieht Ihre ganze Website aus" in body
    assert "deine Branche" not in body


def test_way_back_to_the_studio_survives_tabs_and_saving():
    from urllib.parse import parse_qs, urlparse

    tenant = TenantFactory(business_type="online_shop")
    back = design_page.STUDIO_PREFIX
    body = _html(tenant, f"?tab=farben&next={back}")
    assert "Zurück ins Studio" in body and 'name="next"' in body
    assert body.count("&amp;next=") >= 3  # каждая вкладка несёт путь возврата
    resp = design_page.design_view(
        _req("post", tenant, {"action": "design_settings", "tab": "farben", "next": back})
    )
    assert parse_qs(urlparse(resp["Location"]).query) == {"tab": ["farben"], "next": [back]}
    resp = design_page.design_view(
        _req(
            "post", tenant, {"action": "design_settings", "tab": "farben", "next": "//evil.example"}
        )
    )
    assert "evil" not in resp["Location"]


def test_photo_format_is_chosen_with_tiles_not_selects():
    """FB-29.7 (макет B, утверждён 2026-11-13): формат фото по разделам — плитки с рамкой
    нужной пропорции и образцом «zuschneiden / ganz zeigen»; имена полей прежние."""
    from apps.core import media_places

    tenant = TenantFactory(business_type="online_shop")
    body = _html(tenant, "?tab=karten")
    assert body.count("data-photo-place=") == len(media_places.PLACES)
    for code in media_places.PLACES:
        assert f'type="radio" name="mp_{code}_ratio"' in body, code
        assert f'type="radio" name="mp_{code}_fit"' in body, code
        assert f'<select name="mp_{code}_ratio"' not in body
    assert "data-photo-shape" in body and "data-photo-fit" in body


def test_photo_format_tiles_save_like_the_selects_did():
    tenant = TenantFactory(business_type="online_shop")
    design_page.design_view(
        _req(
            "post",
            tenant,
            {"action": "design_settings", "tab": "karten", "sd_cards_present": "1",
             "mp_product_ratio": "1-1", "mp_product_fit": "contain"},
        )
    )  # fmt: skip
    cfg = siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)
    assert cfg["site_defaults"]["media_places"]["product"] == {"ratio": "1-1", "fit": "contain"}
    body = _html(Tenant.objects.get(pk=tenant.pk), "?tab=karten")
    assert "1:1" in body[body.index('data-photo-place="product"') :][:600]
