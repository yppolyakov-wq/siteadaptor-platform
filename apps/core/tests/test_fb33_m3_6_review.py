"""FB-33 M3-6: ревью ECC (security-reviewer, silent-failure-hunter, a11y-architect) — замок на пункт."""

import re

import pytest
from django.db import DatabaseError

from apps.core import aufbau_draft, banners, content_pages, site_schema, window_banner
from apps.core.models import Banner
from apps.core.tests.test_fb27_r2_draft import Browser, _tenant
from apps.core.tests.test_fb33_m3_window_before import CFG, _panel
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db


def _shop(config):
    tenant = _tenant()
    tenant.site_config = config
    tenant.save()
    return tenant


def _banner_shop(pick, extra_blocks=None):
    blocks = {"info": [{"key": "banner", "id": "bn1", "enabled": True, "data": {"pick": pick}}]}
    blocks.update(extra_blocks or {})
    return _shop({"sections": [{"key": "hero"}], "page_blocks": blocks})


def _cat(slug, active=True):
    from apps.catalog.models import Category

    return Category.objects.create(name={"de": slug.title()}, slug=slug, is_active=active)


def _raw(b, code="text"):
    return (b.session.get(aufbau_draft.SESSION_KEY) or {}).get(code)


def _token(html):
    return re.search(r'name="wopen" value="([A-Za-z0-9_-]+)"', _panel(html)).group(1)


class _Req:
    def __init__(self, session):
        self.session = session


# 1 (security): «places» без ref — отказ, а не 500
def test_places_without_ref_is_refused_not_500():
    a = Banner.objects.create(title="A")
    _cat("brot")
    b = Browser(_banner_shop([str(a.pk)]))
    resp, msgs = b.post(seite="text", op="places", value="add", wo_add="category:brot")
    assert resp.status_code == 302 and msgs == ["Diese Änderung ist hier nicht möglich."]
    assert _raw(b) is None


# 2 (silent): «Trotzdem speichern» пишет только поля, изменённые в окне
def test_force_save_keeps_seo_changed_elsewhere():
    tenant = _shop({**CFG, "seo": {"pages": {"info": {"title": "Alt"}}}})
    b = Browser(tenant)
    b.post(seite="text", op="update", ref="__page", panel_present="1", f_seo_description="Mein")
    content_pages.save_page_seo(tenant, "info", {"title": "Anders", "noindex": True})
    b.post(seite="text", op="save", force="1")
    tenant.refresh_from_db()
    assert tenant.site_config["seo"]["pages"]["info"] == {
        "title": "Anders",
        "description": "Mein",
        "noindex": True,
    }


def test_force_save_without_seo_edit_does_not_touch_seo():
    tenant = _shop({**CFG, "seo": {"pages": {"info": {"title": "Alt"}}}})
    b = Browser(tenant)
    b.post(seite="text", op="toggle", ref="tp1")
    content_pages.save_page_seo(tenant, "info", {"title": "Anders"})
    b.post(seite="text", op="save", force="1")
    tenant.refresh_from_db()
    assert tenant.site_config["seo"]["pages"]["info"] == {"title": "Anders"}


# 3 (silent): библиотека недоступна — не «изменено в библиотеке» и не «страницы нет»
def test_library_unavailable_is_not_a_conflict_and_the_window_says_so(monkeypatch):
    a = Banner.objects.create(title="A")
    b = Browser(_banner_shop([str(a.pk)]))
    monkeypatch.setattr(window_banner, "_library", lambda pks: None)
    assert window_banner.conflict({"show_on": {"x": []}, "show_on_base": {"x": []}}) is False
    html = _panel(b.get("?seite=text&block=bn1"))
    assert "data-schema-places-unavailable" in html and 'role="alert"' in html


def test_place_check_failing_in_the_database_has_its_own_message(monkeypatch):
    a = Banner.objects.create(title="A")
    _cat("brot")
    b = Browser(_banner_shop([str(a.pk)]))

    def broken(values, strict=False):
        if strict:
            raise DatabaseError("down")
        return {}

    monkeypatch.setattr(banners, "place_labels", broken)
    _resp, msgs = b.post(seite="text", op="places", ref="bn1", value="add", wo_add="category:brot")
    assert msgs == [window_banner.unavailable_note()]
    assert _raw(b) is None


# 4 (silent): потолок мест после слияния — с сообщением
def test_cut_to_the_ceiling_after_merge_is_reported(monkeypatch):
    for slug in ("a1", "a2", "a3"):
        _cat(slug)
    a = Banner.objects.create(title="A")
    b = Browser(_banner_shop([str(a.pk)]))
    monkeypatch.setattr(banners, "SHOW_ON_MAX", 2)
    b.post(seite="text", op="places", ref="bn1", value="add", wo_add=["category:a1", "category:a2"])
    a.show_on = ["category:a3"]
    a.save()
    _resp, msgs = b.post(seite="text", op="save", force="1")
    assert window_banner.cut_note() % {"n": 2} in msgs
    a.refresh_from_db()
    assert len(a.show_on) == 2


# 5 (silent): «N Seiten» — без исчезнувших страниц и без двойного счёта
def test_page_count_skips_gone_pages_and_counts_a_page_once():
    _cat("brot")
    a = Banner.objects.create(title="A", show_on=["category:brot", "category:weg"])
    tenant = _banner_shop(
        [str(a.pk)],
        {
            "catalog:brot": [
                {"key": "banner", "id": "bc", "enabled": True, "data": {"pick": [str(a.pk)]}}
            ]
        },
    )
    html = _panel(Browser(tenant).get("?seite=text&block=bn1"))
    caps = re.findall(r"data-schema-banner-caption>([^<]*)<", html)
    assert caps == ["immer · 2 Seiten"], caps  # «Über uns» + «Brot» (выбор и show_on — одна)


# 6 (silent): черновик до среза — SEO в окне и «Abbrechen» без ложного конфликта
def test_old_draft_seo_edit_and_abbrechen_restore_the_base():
    tenant = _shop({**CFG, "seo": {"pages": {"info": {"title": "Alt"}}}})
    b = Browser(tenant)
    b.post(seite="text", op="toggle", ref="tp1")
    draft = _raw(b)
    draft.pop("seo")
    config = siteconfig.normalize(tenant.site_config)
    saved = aufbau_draft._saved_state(config, False, "info")
    draft["base"] = aufbau_draft._base_fingerprint(saved, config, draft)
    old_base = draft["base"]
    b.session[aufbau_draft.SESSION_KEY] = {"text": draft}
    token = _token(b.get("?seite=text&block=__page"))
    b.post(seite="text", op="update", ref="__page", panel_present="1", f_seo_title="X", wopen=token)
    _resp, msgs = b.post(seite="text", op="revert", ref="__page", wopen=token)
    assert msgs == ["Änderungen an diesem Block zurückgenommen."]
    after = _raw(b)
    assert "seo" not in after and after["base"] == old_base
    assert aufbau_draft.info(_Req(b.session), config, "text")["conflict"] is False
    _resp, msgs = b.post(seite="text", op="save")
    assert msgs == ["Gespeichert."]


# 7 (low): бросок на «Kaufen» первого экрана — только «после»; закреплённые строки корзины
def test_kauf_first_drop_target_is_after_only():
    html = Browser(_shop(CFG)).get("?seite=product")
    li = re.search(r'<li[^>]*data-schema-pinned="__kauf"[^>]*>', html).group(0)
    assert 'data-schema-drop-only="after"' in li
    js = open("static/js/aufbau.js").read()
    assert 'li.getAttribute("data-schema-drop-only")' in js


@pytest.mark.parametrize("value", ["before:summary", "after:items", "before:form", "after:form"])
def test_drops_onto_pinned_cart_rows_keep_the_pinned_order(value):
    from apps.core import detail_parts

    cfg = siteconfig.normalize({})
    items = detail_parts.edit_rows(
        cfg, "cart", [{"key": "text", "id": "b1", "enabled": True, "data": {}}]
    )
    try:
        site_schema.mutate(items, "cart", "move", "b1", value=value)
    except site_schema.SchemaError:
        return
    keys = [i.get("id") or i["key"] for i in items]
    assert keys[:3] == ["items", "form", "summary"] or not (
        keys.index("form") < keys.index("b1") < keys.index("summary")
    ), keys
    assert site_schema._pinned_order_ok(items, "cart")


# 9 (security): короткий поиск мест — без поиска; отозванное право — страница сохраняется
def test_short_place_search_does_not_query(monkeypatch):
    a = Banner.objects.create(title="A")
    b = Browser(_banner_shop([str(a.pk)]))
    called = []
    monkeypatch.setattr(banners, "place_search", lambda *a, **k: called.append(1) or [])
    html = _panel(b.get("?seite=text&block=bn1&wo=ab"))
    assert not called and "mindestens 3 Zeichen" in html


def test_revoked_banner_right_skips_places_but_saves_the_page(monkeypatch):
    a = Banner.objects.create(title="A")
    _cat("brot")
    b = Browser(_banner_shop([str(a.pk)]))
    b.post(seite="text", op="places", ref="bn1", value="add", wo_add="category:brot")
    b.post(seite="text", op="toggle", ref="bn1")
    monkeypatch.setattr("apps.core.view_perms.url_allowed", lambda user, url, method="GET": False)
    _resp, msgs = b.post(seite="text", op="save")
    assert msgs[0] == "Gespeichert." and window_banner.rights_note() in msgs
    a.refresh_from_db()
    assert a.show_on == []


# 10–12 (a11y)
def test_legal_label_wraps_and_has_no_name():
    html = _panel(Browser(_shop(CFG)).get("?seite=cart&block=summary"))
    field = re.search(r'<textarea[^>]*id="schema-legal-label"[^>]*>([^<]*)</textarea>', html)
    assert field and field.group(1) == "Zahlungspflichtig bestellen"
    assert "readonly" in field.group(0) and "name=" not in field.group(0)


def test_places_announce_the_result_and_focus_the_heading():
    a = Banner.objects.create(title="A")
    _cat("brot")
    b = Browser(_banner_shop([str(a.pk)]))
    resp, _m = b.post(seite="text", op="places", ref="bn1", value="add", wo_add="category:brot")
    assert resp["Location"].endswith("#schema-tab-places")
    html = _panel(b.get("?seite=text&block=bn1"))
    assert re.search(r'role="status"[^>]*data-schema-places-said>1 Seite hinzugefügt\.<', html)
    assert 'aria-label="Kategorien: Brot entfernen"' in html
    assert 'id="schema-tab-places" tabindex="-1"' in html
    html = _panel(b.get("?seite=text&block=bn1"))
    assert "data-schema-places-said></p>" in html, "сообщение — один раз"


def test_category_links_have_full_names_and_shared_rows_say_so():
    from apps.catalog.models import Category

    Category.objects.create(name={"de": "Brot"}, slug="brot")
    b = Browser(_shop(CFG))
    html = _panel(b.get("?seite=category@catalog:brot&block=main"))
    assert 'für alle ändern<span class="sr-only"> – Ansicht aller Kategorie-Seiten</span>' in html
    # FB-33 M5b-2 W1 (A-H2): ссылка на форму категории — у ★-строки страницы, у окна ★ её нет
    # (ревью M5b-2 №8: якорь позиции снят вместе с переездом — отрицательная проверка вместо него)
    assert "data-schema-seo-link" not in html and "In der Kategorie bearbeiten" not in html
    page = _panel(b.get("?seite=category@catalog:brot&block=__page"))
    assert "data-schema-seo-link" in page
    assert re.search(r"</p>\s*<p class=\"text-sm\"><a [^>]*>In der Kategorie bearbeiten →", page)
    src = open("templates/tenant/site_schema.html").read()
    assert "feste Position" in src and "gilt für alle Seiten" in src
