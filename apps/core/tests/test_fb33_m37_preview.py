"""FB-33 M3-7: замки ДО кода «Vorschau» в окне блока (план среза M3-7, развилки 1а/2а/3а).

В окне блока (`<dialog class="ui-bwin">`, его строит `aufbau.js`) — область «Vorschau»: кадр
черновика страницы `?preview=1&aufbau=<код>`, прокрученный к блоку (`data-sf-section`). Сервер
ничего не пишет: экран кладёт адрес и якорь в `<template data-bw-preview>` ПОСЛЕ тега
`aufbau.js` (эталоны без JS — до него — не меняются), кадр строит `aufbau_preview.js`.

L2 — якорь в обе стороны (`window_links.canvas_key` ↔ `_block_of`), L3 — контекст экрана,
L4 — показ черновика ничего не пишет, L5 — черновик не утекает чужим, кадр только свой,
L6 — песочница кадра без скриптов/форм/ухода наверх, L7 — тексты и ровно три новых события.
"""

import copy
import re
import uuid
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlencode, urlsplit

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.db import connection
from django.http import HttpResponse
from django.test import RequestFactory
from django.test.signals import template_rendered
from django.test.utils import CaptureQueriesContext
from django.utils import translation

from apps.core import detail_parts, window_links
from apps.core.middleware import StorefrontFrameOptionsMiddleware
from apps.core.tests.test_fb27_r2_draft import Browser, _tenant
from apps.core.tests.test_fb33_m3_window_before import CASES, CFG

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]
JS = ROOT / "static" / "js"
WOPEN = "openPV"


def _owner_browser():
    tenant = _tenant()
    tenant.site_config = CFG
    tenant.save()
    return Browser(tenant)


def _ctx(b, query):
    seen = []

    def grab(sender, template, context, **kw):
        if getattr(template, "name", "") == "tenant/site_schema.html":
            seen.append(context)

    template_rendered.connect(grab)
    try:
        with translation.override("de"):
            html = b.get(query)
    finally:
        template_rendered.disconnect(grab)
    return html, seen[-1]


def _req(b, path="/dashboard/site/aufbau/", user=None):
    req = RequestFactory().get(path)
    req.session = b.session
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = user or SimpleNamespace(is_authenticated=True)
    b.tenant.refresh_from_db()
    req.tenant = b.tenant
    return req


def _member(role=None):
    from apps.core.models import Membership

    user = get_user_model().objects.create_user(username=f"pv-{uuid.uuid4().hex[:6]}")
    Membership.objects.create(user=user, role=role or Membership.ROLE_OWNER)
    return user


def _home(req):
    from apps.promotions import public_views

    with translation.override("de"):
        return public_views.storefront_home(req).content.decode()


# ───────────── L2: якорь кадра в обе стороны ─────────────


@pytest.mark.parametrize("case", CASES, ids=["|".join(c) for c in CASES])
def test_canvas_key_maps_back_to_the_same_row(case):
    code, ref = case[0], case[1]
    b = _owner_browser()
    b.get(f"?seite={code}")
    req = _req(b)
    key = window_links.canvas_key(req, code, ref)
    host = window_links._host(req.tenant, code)
    if window_links.whole_page(ref):
        # строка самой страницы (★, «Seitentitel», «Kaufen», «Einstellungen der Seite») —
        # кадр показывает страницу целиком: якорь — обёртка страницы, у главной — её начало
        want = "" if code == "home" else detail_parts.shared_host(host)
        assert key == want, (case, key)
        assert key == "" or window_links._is_page_key(code, host, key), (case, key)
    else:
        assert window_links._block_of(req, code, host, key) == ref, (case, key)
    assert key == "" or window_links.REF_RE.fullmatch(key), key


def test_canvas_key_of_a_detail_section_carries_the_page_prefix():
    b = _owner_browser()
    b.get("?seite=product")
    req = _req(b)
    assert window_links.canvas_key(req, "product", "related") == "product_related"
    assert window_links.canvas_key(req, "product", "__kauf") == "product_detail"
    assert window_links.canvas_key(req, "catalog", "main") == "catalog"
    assert window_links.canvas_key(req, "home", "t1") == "t1"
    assert window_links.canvas_key(req, "home", "<x>") == ""  # мусор — начало страницы


def test_frame_src_shows_the_draft_with_the_block_anchor():
    b = _owner_browser()
    b.post(seite="home", ref="t1", op="update", panel_present="1", wopen=WOPEN, f_title="Neu7")
    _html, ctx = _ctx(b, f"?seite=home&block=t1&wopen={WOPEN}")
    pv = ctx["bw_preview"]
    assert pv["anchor"] == "t1"
    req = _req(b, pv["src"], user=_member())
    shown = _home(req)
    assert 'data-sf-section="t1"' in shown and "Neu7" in shown  # черновик и якорь в кадре


# ───────────── L3: контекст экрана ─────────────


#: строки CASES, у которых окна «Vorschau» нет: подтверждение удаления, страница без адреса
#: превью у тестового бизнеса (товара нет), закреплённые строки без окна
NO_PREVIEW = {
    ("home", "t1", "&entfernen=1"),
    ("product", "__kauf"),
    ("product", "related"),
    ("text", "pagetext"),
    ("confirmation", "summary"),
    ("confirmation", "recommend"),
}
WITH_PREVIEW = [c for c in CASES if c not in NO_PREVIEW]


@pytest.mark.parametrize("case", sorted(NO_PREVIEW), ids=["|".join(c) for c in sorted(NO_PREVIEW)])
def test_no_preview_where_the_window_has_no_page_to_show(case):
    code, ref, extra = (*case, "")[:3]
    html, ctx = _ctx(_owner_browser(), f"?seite={code}&block={ref}{extra}")
    assert extra == "&entfernen=1" or not ctx.get("preview_url") or not ctx.get("window")
    assert not ctx.get("bw_preview"), case
    assert "data-bw-preview" not in html and "aufbau_preview.js" not in html


@pytest.mark.parametrize("case", WITH_PREVIEW, ids=["|".join(c) for c in WITH_PREVIEW])
def test_preview_context_for_an_open_block_window(case):
    code, ref, extra = (*case, "")[:3]
    html, ctx = _ctx(_owner_browser(), f"?seite={code}&block={ref}{extra}")
    assert ctx.get("preview_url") and ctx.get("window")
    pv = ctx.get("bw_preview")
    assert pv, case
    src = pv["src"]
    assert src.startswith("/") and not src.startswith("//") and "\\" not in src
    assert not src.startswith(StorefrontFrameOptionsMiddleware._BLOCK_PREFIXES)
    query = dict(parse_qsl(urlsplit(src).query))
    assert query["preview"] == "1" and query["aufbau"] == code
    assert "data-bw-preview" in html


def test_preview_query_is_exactly_preview_and_aufbau():
    b = _owner_browser()
    _html, ctx = _ctx(b, "?seite=home&block=t1")
    assert urlsplit(ctx["bw_preview"]["src"]).query == "preview=1&aufbau=home"


def test_no_preview_without_a_block_or_while_confirming_removal():
    b = _owner_browser()
    for query in ("?seite=home", "?seite=home&block=t1&entfernen=1"):
        html, ctx = _ctx(b, query)
        assert not ctx.get("bw_preview"), query
        assert "data-bw-preview" not in html and "aufbau_preview.js" not in html


def test_template_sits_after_the_aufbau_script_and_escapes_values():
    b = _owner_browser()
    html, _ctx_ = _ctx(b, "?seite=home&block=t1")
    at = html.index("js/aufbau")
    tag = re.search(r"<template data-bw-preview[^>]*>", html)
    assert tag and tag.start() > at
    attrs = dict(re.findall(r'(data-[a-z-]+)="([^"]*)"', tag.group(0)))
    assert attrs["data-src"].startswith("/") and attrs["data-anchor"] == "t1"
    assert attrs["data-label"] == "Vorschau" and attrs["data-missing"]
    assert html.index("aufbau_preview.js") > tag.start()


# ───────────── L4: показ черновика ничего не пишет ─────────────


def test_draft_preview_writes_nothing():
    b = _owner_browser()
    b.post(seite="home", ref="t1", op="update", panel_present="1", wopen=WOPEN, f_title="Neu7")
    before = copy.deepcopy(dict(b.session.items()))
    b.session.modified = False  # запись правки выше — не в счёт
    req = _req(b, "/?preview=1&aufbau=home", user=_member())
    with CaptureQueriesContext(connection) as q:
        shown = _home(req)
    assert "Neu7" in shown
    writes = [
        x["sql"] for x in q.captured_queries if re.match(r"\s*(INSERT|UPDATE|DELETE)", x["sql"])
    ]
    assert writes == []
    assert dict(b.session.items()) == before
    assert not req.session.modified  # черновик только читается


# ───────────── L5: свой тенант и права ─────────────


def test_draft_does_not_leak_to_anonymous_or_member_without_site_rights():
    from django.contrib.auth.models import AnonymousUser

    b = _owner_browser()
    b.post(seite="home", ref="t1", op="update", panel_present="1", wopen=WOPEN, f_title="Neu7")
    anon = _home(_req(b, "/?preview=1&aufbau=home", user=AnonymousUser()))
    assert "Neu7" not in anon
    stranger = get_user_model().objects.create_user(username=f"pv-{uuid.uuid4().hex[:6]}")
    assert "Neu7" not in _home(_req(b, "/?preview=1&aufbau=home", user=stranger))


def test_storefront_frames_only_same_origin_cabinet_never():
    mw = StorefrontFrameOptionsMiddleware(lambda r: HttpResponse())
    rf = RequestFactory()
    assert mw(rf.get("/?preview=1&aufbau=home"))["X-Frame-Options"] == "SAMEORIGIN"
    denied = mw(rf.get("/dashboard/site/aufbau/"))
    assert denied.get("X-Frame-Options") != "SAMEORIGIN"
    from django.conf import settings

    assert "frame-ancestors 'self'" in settings.CSP_REPORT_ONLY


# ───────────── L6/L7: кадр без скриптов, тексты, события ─────────────


def test_frame_sandbox_has_no_scripts_forms_or_top_navigation():
    src = (JS / "aufbau_preview.js").read_text()
    sandbox = re.findall(r'"sandbox",\s*"([^"]*)"', src)
    assert sandbox == ["allow-same-origin"]
    for bad in ("allow-scripts", "allow-forms", "allow-top-navigation", "allow-popups"):
        assert bad not in src
    assert "tabIndex = -1" in src
    assert 'referrerpolicy", "same-origin"' in src


def test_aufbau_js_gets_exactly_three_new_events():
    src = (JS / "aufbau.js").read_text()
    names = set(re.findall(r'new CustomEvent\("([^"]+)"', src))
    assert names == {"aufbau:panel", "aufbau:window-open", "aufbau:window-close", "aufbau:saved"}
    assert src.count("dispatchEvent(new CustomEvent(") == 4


def test_preview_texts_are_translated():
    want = ("Dieser Block ist hier nicht zu sehen – die Vorschau zeigt den Seitenanfang.",)
    for lang in ("de", "en", "ru", "tr", "uk"):
        po = (ROOT / "locale" / lang / "LC_MESSAGES" / "django.po").read_text()
        for msgid in want:
            entry = re.search(r'msgid "' + re.escape(msgid) + r'"\nmsgstr "([^"]*)"', po)
            assert entry and entry.group(1), (lang, msgid)


# ───────────── ревью M3-7 (django + a11y) ─────────────


@pytest.mark.parametrize("code", ["nichtda", "event", "x" * 200, "home@<b>"])
def test_foreign_or_inactive_aufbau_code_does_not_break_the_storefront(code):
    b = _owner_browser()
    b.get("?seite=home")
    shown = _home(_req(b, "/?" + urlencode({"preview": "1", "aufbau": code}), user=_member()))
    assert "<html" in shown


def test_whole_page_is_an_explicit_set_of_service_rows():
    from apps.core import page_title, site_schema
    from apps.tenants import siteconfig

    for ref in (
        siteconfig.MAIN_LIST_KEY,
        site_schema.PAGE_REF,
        page_title.TITLE_REF,
        detail_parts.KAUF_REF,
    ):
        assert window_links.whole_page(ref), ref
    assert not window_links.whole_page("__neu") and not window_links.whole_page("t1")


def test_canvas_key_reuses_the_known_host(monkeypatch):
    from apps.core import site_schema

    b = _owner_browser()
    b.get("?seite=catalog")
    req = _req(b)

    def boom(*a, **kw):
        raise AssertionError("resolve повторно")

    monkeypatch.setattr(site_schema, "resolve", boom)
    assert window_links.canvas_key(req, "catalog", "main", host="catalog") == "catalog"
    got = window_links.canvas_key(req, "product", "related", host="product_detail")
    assert got == "product_related"


def test_frame_area_is_hidden_from_assistive_tech_and_returns_focus():
    src = (JS / "aufbau_preview.js").read_text()
    assert 'stage.setAttribute("aria-hidden", "true")' in src
    assert 'setAttribute("title"' not in src and "data-title" not in src
    # шаблон читается при каждом использовании, не кешируется при загрузке
    assert "\n  var tpl = " not in src  # не на верхнем уровне скрипта
    assert src.count('querySelector("template[data-bw-preview]")') == 1
    # клик в кадр не оставляет фокус в нём: blur окна → фокус на кнопку
    assert 'window.addEventListener("blur"' in src and "document.activeElement === frame" in src
    assert src.count('behavior: "instant"') == 2
    tpl = (ROOT / "templates" / "tenant" / "site_schema.html").read_text()
    assert "data-title=" not in tpl.split("data-bw-preview", 1)[1].split("</template>", 1)[0]


def test_preview_css_respects_reduced_motion_and_short_screens():
    css = (ROOT / "static" / "src" / "app.css").read_text()
    assert ".ui-bwin-pv-toggle svg { transition" not in css.replace(
        "@media (prefers-reduced-motion: no-preference) { .ui-bwin-pv-toggle svg { transition", ""
    )
    assert (
        "@media (prefers-reduced-motion: no-preference) { .ui-bwin-pv-toggle svg { transition"
        in css
    )
    assert re.search(r"max-height: 520px\) \{[^}]*\.ui-bwin-pv-stage \{[^}]*30dvh", css)
    assert "(max-height: 520px)" in (JS / "aufbau_preview.js").read_text()
