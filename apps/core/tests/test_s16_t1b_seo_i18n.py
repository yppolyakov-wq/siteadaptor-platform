"""FB-33 стопка 16 T1b: переводы SEO страницы в окне ★ «Einstellungen der Seite» → «Texte».

План — `docs/fb33-stack16-plan-2026-11-26.md` §2 «T1b», замки §4 «T1b». Хранение —
`i18n.<язык>.seo.pages.<хост>.{title, description}` (`content_pages.seo_tr_path`, по ключу
хоста); в окне — `block_i18n` вид `seo` (поля `seo_title`/`seo_description`); немецкое — один
писатель `content_pages.put_page_seo` (изменённое поле снимает свой перевод); показ —
`content_pages.page_seo(locale=)` через тег `siteui.page_seo` (в превью — из черновика).
Переводы — только в окне; экран «Seiten» — немецкий. Попутно: «Texte» — по общему правилу
языков `i18n_input.window_langs` (T5), полоса доверия без перевода на витрине — `lang="de"`.
"""

import ast
import copy
import logging
import re
import uuid
from collections import Counter
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.db import connection
from django.test import RequestFactory
from django.utils import translation

from apps.core import aufbau_draft, block_i18n, content_pages, page_window
from apps.core.tests.test_fb27_r2_draft import Browser, _tenant
from apps.core.tests.test_fb33_m3_window_before import CFG, _panel
from apps.tenants import siteconfig
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]
WOPEN = "openT1b"
DE = {"title": "Über uns — Teeladen", "description": "Tee aus Solingen seit 1990."}
RU = {"title": "О нас — чайная", "description": "Чай из Золингена с 1990 года."}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture(autouse=True)
def _fresh_cache():
    cache.clear()
    yield
    cache.clear()


def _shop(seo=None, ru=None, locales=("de", "ru", "en"), default="de", host="info"):
    tenant = _tenant()
    cfg = copy.deepcopy(CFG)
    if seo is not None:
        cfg["seo"] = {"pages": {host: dict(seo)}}
    if ru is not None:
        cfg["i18n"] = {"ru": {"seo": {"pages": {host: dict(ru)}}}}
    tenant.site_config = cfg
    tenant.enabled_locales = list(locales)
    tenant.default_locale = default
    tenant.save()
    return tenant


def _cfg(tenant):
    return siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)


def _tr(cfg, loc="ru", host="info"):
    node = (cfg.get("i18n") or {}).get(loc) or {}
    return ((node.get("seo") or {}).get("pages") or {}).get(host)


def _form(b, query="?seite=text&block=__page&tab=texte", lang="de"):
    with translation.override(lang):
        html = b.get(query)
    m = re.search(r'<form[^>]*id="bw-form-seo".*?</form>', html, flags=re.S)
    return html, (m.group(0) if m else "")


def _edit(b, title=None, description=None, **extra):
    """Форма SEO окна: немецкие поля (как показаны) и присланные переводы."""
    shown = page_window.saved_seo(_cfg(b.tenant), "info")
    draft = ((b.session or {}).get(aufbau_draft.SESSION_KEY) or {}).get("text") or {}
    shown = draft.get("seo", shown) if isinstance(draft.get("seo"), dict) else shown
    data = {
        "seite": "text",
        "op": "update",
        "ref": "__page",
        "panel_present": "1",
        "wopen": WOPEN,
        "f_seo_title": shown.get("title", "") if title is None else title,
        "f_seo_description": shown.get("description", "") if description is None else description,
    }
    data.update(extra)
    return b.post(**data)


def _save(b):
    return b.post(seite="text", op="save")


# ───────────── витрина ─────────────


def _sf_req(tenant, path, user=None, session=None):
    req = RequestFactory().get(path)
    req.META["REMOTE_ADDR"] = "10.1.2.3"
    SessionMiddleware(lambda r: None).process_request(req)
    if session is not None:
        req.session = session
    MessageMiddleware(lambda r: None).process_request(req)
    if user is not None:
        req.user = user
    else:
        from django.contrib.auth.models import AnonymousUser

        req.user = AnonymousUser()
    tenant.refresh_from_db()
    req.tenant = tenant
    return req


def _render(tenant, host, lang, user=None, session=None, query=""):
    """Страница хоста на языке посетителя (мимо кэша страниц)."""
    from apps.core import content_page_views
    from apps.orders import public_views as orders_views
    from apps.promotions import public_views

    cache.clear()
    with translation.override(lang):
        if host == "info":
            resp = public_views.about_page(_sf_req(tenant, f"/ueber-uns/{query}", user, session))
        elif host == "versand":
            resp = orders_views.shipping_info(_sf_req(tenant, f"/versand/{query}", user, session))
        else:
            slug = host.removeprefix("seite:")
            resp = content_page_views.storefront_page(
                _sf_req(tenant, f"/{slug}/{query}", user, session), slug
            )
    assert resp.status_code == 200
    return resp.content.decode()


def _title(html):
    return re.search(r"<title>(.*?)</title>", html, flags=re.S).group(1).strip()


def _meta(html):
    return re.search(r'<meta name="description" content="([^"]*)"', html).group(1)


def _host_tenant(host, seo, ru, noindex_ru=False):
    tenant = _shop(locales=("de", "ru", "en"))
    cfg = _cfg(tenant)
    if host.startswith("seite:"):
        from apps.core.models import ContentPage

        ContentPage.objects.get_or_create(
            slug=host.removeprefix("seite:"),
            defaults={"title": "Zahlung", "body": "<p>Karte</p>", "is_published": True},
        )
    over = dict(ru)
    if noindex_ru:
        over["noindex"] = True
    cfg["seo"] = {"pages": {host: dict(seo)}}
    cfg["i18n"] = {"ru": {"seo": {"pages": {host: over}}}}
    Tenant.objects.filter(pk=tenant.pk).update(site_config=cfg)
    tenant.refresh_from_db()
    return tenant


@pytest.mark.parametrize("host", ["info", "versand", "seite:zahlung"])
def test_page_seo_title_in_visitor_language(host):
    tenant = _host_tenant(host, DE, RU, noindex_ru=True)
    ru, de, en = (_render(tenant, host, lang) for lang in ("ru", "de", "en"))
    assert _title(ru) == RU["title"] and _meta(ru) == RU["description"]
    assert _title(de) == DE["title"] and _meta(de) == DE["description"]
    assert _title(en) == DE["title"], "без перевода — немецкое"
    assert 'name="robots" content="noindex' not in ru, "noindex в оверлее не действует"


def test_og_title_follows_seo_translation():
    """seo-specialist: `og:title`/JSON-LD страницы не расходятся с `<title>` языка посетителя
    (у текстовых страниц своих og/LD страницы нет — проверяем, что немецкий SEO туда не
    утёк)."""
    tenant = _host_tenant("info", DE, RU)
    ru = _render(tenant, "info", "ru")
    og = re.search(r'<meta property="og:title" content="([^"]*)"', ru)
    assert og is None or og.group(1) == _title(ru)
    for ld in re.findall(r'<script type="application/ld\+json">(.*?)</script>', ru, flags=re.S):
        assert DE["title"] not in ld and DE["description"] not in ld


# ───────────── битый оверлей ─────────────

BROKEN = {
    "str": "кафе",
    "list": [{"title": "x"}],
    # ревью D2: чужой ключ при валидном `info` перевод не гасит — `test_s16_t1b_review.py`
    "unknown_host": {"pages": {"catalog": {"title": "Чужой"}}},
    "61_hosts": {
        "pages": {
            **{f"seite:p{i}": {"title": f"T{i}"} for i in range(60)},
            "info": {"title": "Слишком много"},
        }
    },
}


@pytest.mark.parametrize("case", sorted(BROKEN))
def test_broken_seo_overlay_storefront_200(case, caplog):
    tenant = _shop(seo=DE)
    cfg = _cfg(tenant)
    cfg["i18n"] = {"ru": {"seo": copy.deepcopy(BROKEN[case])}}
    Tenant.objects.filter(pk=tenant.pk).update(site_config=cfg)
    with caplog.at_level(logging.WARNING, logger="apps.core.content_pages"):
        html = _render(tenant, "info", "ru")
    assert _title(html) == DE["title"]
    if case != "str" and case != "list":
        assert "Чужой" not in html and "Слишком" not in html and "Не тот" not in html
    warned = [r for r in caplog.records if "broken seo overlay" in r.getMessage()]
    assert len(warned) == 1, "одно предупреждение на запрос (ревью D2)"


def test_seo_overlay_orphan_after_host_removed():
    from apps.core.models import ContentPage

    ContentPage.objects.create(slug="zahlung", title="Z", body="<p>x</p>", is_published=True)
    tenant = _shop(seo=DE, ru=RU, host="seite:zahlung")
    connection.tenant, before = tenant, getattr(connection, "tenant", None)
    try:
        assert content_pages.move_page_blocks("zahlung", None) is True
    finally:
        connection.tenant = before
    cfg = _cfg(tenant)
    assert _tr(cfg, host="seite:zahlung") is None, "перевод снятой страницы снят"
    assert content_pages.page_seo(tenant, "seite:zahlung", locale="ru", config=cfg) == {}


# ───────────── окно: поля и запись ─────────────


def test_seo_translation_fields_not_title():
    assert set(block_i18n._SEO_TR) == set(page_window.SEO_FIELDS)
    assert not set(block_i18n._SEO_TR) & set(block_i18n._TITLE_FIELDS)
    page = {"host": "info", "items": [], "seo": {}}
    assert block_i18n.kinds(page, "__page") == ("seo",)
    assert block_i18n._caps(page, "__page", "seo_title") == 70
    assert block_i18n._caps(page, "__page", "seo_description") == 200
    assert block_i18n._empty_text("seo_title", "")[0] != block_i18n._empty_text("title", "")[0]
    cfg = {}
    draft = {"host": "info", "items": [], "btr": {"__page": {"ru": {"seo_title": "Заголовок"}}}}
    block_i18n.apply(cfg, draft, False, "info")
    assert cfg == {"i18n": {"ru": {"seo": {"pages": {"info": {"title": "Заголовок"}}}}}}


def test_window_translation_saved_and_shown():
    b = Browser(_shop(seo=DE))
    _html, form = _form(b)
    assert 'name="f_tr_seo_title_ru"' in form and 'name="f_tr_seo_description_ru"' in form
    assert 'id="bw-seo-title-ru"' in form and 'maxlength="70"' in form
    _edit(b, f_tr_seo_title_ru="О нас", f_tr_seo_description_ru="Чай")
    assert _tr(_cfg(b.tenant)) is None, "до «Speichern» — только черновик"
    _save(b)
    assert _tr(_cfg(b.tenant)) == {"title": "О нас", "description": "Чай"}
    assert _cfg(b.tenant)["seo"]["pages"]["info"] == DE


def _seiten_post(tenant, **data):
    from apps.core import content_page_views as views
    from apps.core.tests.test_m21_6_content_pages import _req, _user

    before = getattr(connection, "tenant", None)
    connection.tenant = tenant
    try:
        req = _req(
            "/x/?tab=suche",
            method="post",
            data={"seo_present": "1", **data},
            user=_user(),
            tenant=tenant,
        )
        resp = views.page_system(req, "ueber-uns")
    finally:
        connection.tenant = before
    assert resp.status_code == 302
    return [str(m) for m in get_messages(req)]


def test_seiten_german_save_drops_changed_translation():
    tenant = _shop(seo=DE, ru=RU)
    msgs = _seiten_post(tenant, seo_title="Neuer Titel", seo_description=DE["description"])
    assert _tr(_cfg(tenant)) == {"description": RU["description"]}, "снят только title"
    assert any("Übersetzung entfernt" in m and "Русский" in m for m in msgs)
    # то же из окна
    b = Browser(_shop(seo=DE, ru=RU))
    _edit(b, description="Neue Beschreibung")
    _save(b)
    assert _tr(_cfg(b.tenant)) == {"title": RU["title"]}


def test_noindex_only_save_keeps_translations():
    tenant = _shop(seo=DE, ru=RU)
    msgs = _seiten_post(
        tenant, seo_title=DE["title"], seo_description=DE["description"], seo_noindex="1"
    )
    cfg = _cfg(tenant)
    assert cfg["seo"]["pages"]["info"] == {**DE, "noindex": True}
    assert _tr(cfg) == RU and not any("Übersetzung entfernt" in m for m in msgs)


def test_put_shown_and_commit_drop_by_field():
    base = {"seo": {"pages": {"info": dict(DE)}}, "i18n": {"ru": {"seo": {"pages": {"info": RU}}}}}
    same = copy.deepcopy(base)
    page_window.put_shown(same, "info", {"seo": dict(DE)})
    assert _tr(same) == RU, "показ без правки немецкого — переводы целы"
    same = copy.deepcopy(base)
    page_window.commit(same, "info", {"seo": dict(DE), "seo_base": dict(DE)})
    assert _tr(same) == RU, "«Speichern» без правки — переводы целы"
    moved = copy.deepcopy(base)
    page_window.commit(moved, "info", {"seo": {**DE, "title": "Anders"}, "seo_base": dict(DE)})
    assert _tr(moved) == {"description": RU["description"]}


def test_commit_order_german_then_translation():
    b = Browser(_shop(seo=DE, ru=RU))
    _edit(b, title="Neu", f_tr_seo_title_ru="Новый")
    _save(b)
    cfg = _cfg(b.tenant)
    assert cfg["seo"]["pages"]["info"]["title"] == "Neu"
    assert _tr(cfg) == {"title": "Новый", "description": RU["description"]}


def test_german_edit_without_translation_drops_it_in_draft_with_note():
    b = Browser(_shop(seo=DE, ru=RU))
    _resp, msgs = _edit(b, title="Neu")
    assert any("Übersetzung entfernt" in m for m in msgs)
    _html, form = _form(b, f"?seite=text&block=__page&tab=texte&wopen={WOPEN}")
    assert re.search(r'id="bw-seo-title-ru"[^>]*value=""', form)


@pytest.mark.parametrize("loc", ["ru", "en"])
def test_page_rename_moves_seo_translations(loc):
    from apps.core.models import ContentPage

    ContentPage.objects.create(slug="zahlung", title="Z", body="<p>x</p>", is_published=True)
    tenant = _shop(seo=DE, host="seite:zahlung")
    cfg = _cfg(tenant)
    cfg["i18n"] = {loc: {"seo": {"pages": {"seite:zahlung": dict(RU)}}}}
    Tenant.objects.filter(pk=tenant.pk).update(site_config=cfg)
    tenant.refresh_from_db()
    before = getattr(connection, "tenant", None)
    connection.tenant = tenant
    try:
        assert content_pages.move_page_blocks("zahlung", "bezahlen") is True
    finally:
        connection.tenant = before
    cfg = _cfg(tenant)
    assert _tr(cfg, loc, "seite:bezahlen") == RU and _tr(cfg, loc, "seite:zahlung") is None


def test_page_rename_moves_translation_without_german():
    """Перевод при пустом немецком (решение владельца) — тоже едет за адресом."""
    tenant = _shop(ru=RU, host="seite:zahlung")
    before = getattr(connection, "tenant", None)
    connection.tenant = tenant
    try:
        assert content_pages.move_page_blocks("zahlung", "bezahlen") is True
    finally:
        connection.tenant = before
    assert _tr(_cfg(tenant), host="seite:bezahlen") == RU


def test_page_delete_drops_seo_translations():
    tenant = _shop(seo=DE, ru=RU, host="seite:zahlung")
    cfg = _cfg(tenant)
    cfg["i18n"]["en"] = {"seo": {"pages": {"seite:zahlung": {"title": "About"}}}}
    Tenant.objects.filter(pk=tenant.pk).update(site_config=cfg)
    before = getattr(connection, "tenant", None)
    connection.tenant = tenant
    try:
        content_pages.move_page_blocks("zahlung", None)
    finally:
        connection.tenant = before
    cfg = _cfg(tenant)
    assert _tr(cfg, "ru", "seite:zahlung") is None and _tr(cfg, "en", "seite:zahlung") is None
    assert "seo" not in (cfg.get("i18n") or {}).get("ru", {})


def test_seo_translation_conflict():
    b = Browser(_shop(seo=DE, ru=RU))
    _edit(b, f_tr_seo_title_ru="Мой")
    cfg = _cfg(b.tenant)
    cfg["i18n"]["ru"]["seo"]["pages"]["info"]["title"] = "Чужой"
    Tenant.objects.filter(pk=b.tenant.pk).update(site_config=cfg)
    _resp, msgs = _save(b)
    assert _tr(_cfg(b.tenant))["title"] == "Чужой", "перевод тем временем изменили — отказ"
    assert any("Übersetzungen" in m for m in msgs)


def test_open_drafts_fingerprint_unchanged():
    """Черновик, открытый до среза (без `btr` у ★, без `seo`), — без ложного конфликта."""
    b = Browser(_shop(seo=DE, ru=RU))
    b.post(seite="text", op="add", type="text")
    raw = (b.session.get(aufbau_draft.SESSION_KEY) or {})["text"]
    raw.pop("seo", None)  # черновик M3-5c до SEO в окне — отпечаток без `seo`
    raw["base"] = aufbau_draft._base_fingerprint(
        aufbau_draft._saved_state(_cfg(b.tenant), False, "info"), _cfg(b.tenant), raw
    )
    b.session.modified = True
    assert "btr" not in raw and "seo" not in raw
    _resp, msgs = _save(b)
    assert any("Gespeichert" in m for m in msgs), msgs
    assert _tr(_cfg(b.tenant)) == RU


def _member():
    from apps.core.models import Membership

    user = get_user_model().objects.create_user(username=f"t1b-{uuid.uuid4().hex[:6]}")
    Membership.objects.create(user=user, role=Membership.ROLE_OWNER)
    return user


def test_window_preview_shows_draft_seo_translation():
    b = Browser(_shop(seo=DE))
    _edit(b, f_tr_seo_title_ru="Черновик")
    html = _render(
        b.tenant, "info", "ru", user=_member(), session=b.session, query="?preview=1&aufbau=text"
    )
    assert _title(html) == "Черновик", "«Vorschau» — перевод из черновика до «Speichern»"
    assert _title(_render(b.tenant, "info", "ru")) == DE["title"], "на сайте — ещё нет"


def test_seo_translation_caps_and_whitespace():
    b = Browser(_shop(seo=DE))
    _html, form = _form(b)
    assert re.search(r'id="bw-seo-title-ru"[^>]*maxlength="70"', form)
    assert re.search(r'id="bw-seo-description-ru"[^>]*maxlength="200"', form)
    assert "Höchstens 70 Zeichen.</p>" in form and "Höchstens 200 Zeichen.</p>" in form
    assert 'aria-describedby="bw-seo-title-ru-src seo-lang-hint bw-seo-title-ru-max"' in form
    desc = "Ж" * 199 + "\r\nX"  # браузер: «\r\n» — один знак (201 > 200); сервер — пробел
    _resp, msgs = _edit(b, f_tr_seo_title_ru="  Ч   ай  " + "я" * 80, f_tr_seo_description_ru=desc)
    _save(b)
    tr = _tr(_cfg(b.tenant))
    assert tr["title"] == ("Ч ай " + "я" * 80)[:70] and len(tr["title"]) == 70
    assert tr["description"] == "Ж" * 199, "«\\r\\n» — пробел, обрезано до 200 без хвоста"
    assert siteconfig.cap_note() in msgs, msgs


def test_seo_empty_text_flagged_ui():
    b = Browser(_shop())
    _html, form = _form(b)
    assert 'name="f_tr_seo_title_ru"' in form, "перевод — и при пустом немецком"
    assert "Ohne Übersetzung: <span" in form and ">automatisch</span>" in form
    page = {"host": "info", "items": [], "seo": {}}
    selected = {"ref": "__page", "seo": {"title": "", "description": ""}}
    with translation.override("ru"):
        block_i18n.decorate(selected, {}, page, {}, False, "info", ["ru"], "", "de")
    t = selected["seo"]["tr_title"][0]
    assert t["empty_ui"] is True and t["empty_lang"] == "ru", "служебная строка — без lang=de"
    selected = {"ref": "__page", "seo": {"title": "Tee", "description": ""}}
    page["seo"] = {"title": "Tee"}
    block_i18n.decorate(selected, {}, page, {}, False, "info", ["ru"], "", "de")
    t = selected["seo"]["tr_title"][0]
    assert t["empty_ui"] is False and t["empty_lang"] == "de" and t["empty"] == "Tee"


def test_one_rule_for_window_languages():
    """«Texte» и «Felder» — одно правило `i18n_input.window_langs`; «Grundtext» нет."""
    from apps.core import i18n_input

    b = Browser(_shop(seo=DE, locales=("de", "en", "ru"), default="ru"))
    _html, form = _form(b)
    assert re.findall(r'name="f_sprache" value="(\w+)"', form) == ["ru", "en"]
    assert "Deutsch (Ausgangstext)" in form and "Ihre Seite zeigt zuerst Русский." in form
    rule = i18n_input.window_langs(["en", "ru"], "ru", "")
    selected = {"ref": "__page", "seo": {"title": "x", "description": ""}}
    page = {"host": "info", "items": [], "seo": {"title": "x"}}
    block_i18n.decorate(selected, {}, page, {}, False, "info", ["en", "ru"], "", "ru")
    fl = selected["field_langs"]
    assert [x["code"] for x in fl["locales"]] == rule["locs"] and fl["lang"] == rule["lang"]
    assert (fl["base_note"], fl["first_note"]) == (rule["base_note"], rule["first_note"])
    src = (ROOT / "apps/core/block_i18n.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    calls = {
        n.args[0].value
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and getattr(n.func, "id", "") == "gettext"
        and n.args
        and isinstance(n.args[0], ast.Constant)
    }
    assert not any("Ihre Seite zeigt zuerst" in c or "Deutsch (" in c for c in calls)
    for path in (ROOT / "apps").rglob("*.py"):
        if "tests" not in path.parts:
            assert "Grundtext" not in path.read_text(encoding="utf-8"), path


def test_usp_and_seo_forms_ids_unique():
    b = Browser(_shop(seo=DE, ru=RU))
    html, form = _form(b)
    assert 'id="seo-lang-title"' in form and 'id="schema-tab-lang-seo-ru"' in form
    assert 'name="lang_ns" value="seo"' in form
    ids = Counter(re.findall(r'\bid="([^"]+)"', _panel(html)))
    assert [i for i, n in ids.items() if n > 1] == []
    assert "seo" in block_i18n.LANG_NAMESPACES and "usp" in block_i18n.LANG_NAMESPACES
    # кнопка языка: после POST фокус — на кнопке своего ns
    resp, _msgs = _edit(b, f_sprache="en", lang_ns="seo")
    assert resp.url.endswith("#schema-tab-lang-seo-en"), resp.url


def test_default_button_before_language_buttons():
    _html, form = _form(Browser(_shop(seo=DE)))
    first = re.search(r"<button[^>]*>", form).group(0)
    assert 'value="update"' in first and "sr-only" in first and 'tabindex="-1"' in first
    assert "aria-hidden" not in first
    assert form.index(first) < form.index('name="f_sprache"')


def test_storefront_usp_untranslated_lang_de():
    from django.template.loader import render_to_string

    usp = [{"icon": "bio", "label": "Frisch"}, {"icon": "local", "label": "Regional"}]
    tenant = _shop()
    cfg = _cfg(tenant)
    cfg["usp_bar"] = usp
    cfg["i18n"] = {"ru": {"usp_bar": [{"label": "Свежо"}]}}
    Tenant.objects.filter(pk=tenant.pk).update(site_config=cfg)
    req = _sf_req(tenant, "/")
    shown = siteconfig.localize(siteconfig.normalize(cfg), "ru")["usp_bar"]
    with translation.override("ru"):
        html = render_to_string(
            "storefront/sections/_usp_bar.html", {"site": {"usp_bar": shown}}, request=req
        )
    assert '<span class="font-medium">Свежо</span>' in html
    assert '<span class="font-medium" lang="de">Regional</span>' in html
    with translation.override("de"):
        html = render_to_string(
            "storefront/sections/_usp_bar.html", {"site": {"usp_bar": usp}}, request=req
        )
    assert 'lang="de"' not in html


def test_seo_not_in_translatable_keys():
    from apps.tenants import demo_i18n

    assert "seo" not in siteconfig.TRANSLATABLE_KEYS
    assert "seo" in siteconfig._NOT_SHOWN_OVERLAY
    cfg = siteconfig.normalize(
        {"seo": {"pages": {"info": dict(DE)}}, "i18n": {"ru": {"seo": {"pages": {"info": RU}}}}}
    )
    assert siteconfig.localize(cfg, "ru")["seo"]["pages"]["info"] == DE
    # Студия (`split_translation`) перевод `seo` не разбирает и не стирает
    payload = siteconfig.localize(cfg, "ru")
    payload["i18n"] = copy.deepcopy(cfg["i18n"])
    out = siteconfig.split_translation(payload, cfg, "ru")
    assert out["seo"]["pages"]["info"] == DE and _tr(out) == RU
    src = Path(demo_i18n.__file__).read_text(encoding="utf-8")
    assert '"seo"' not in src


def test_studio_ru_save_keeps_german_seo_base():
    from apps.tenants.tests.test_s16_d9_studio_overlay_base import _studio_save
    from apps.tenants.tests.test_s16_d9_studio_overlay_base import _tenant as d9_tenant

    tenant = d9_tenant(
        {"seo": {"pages": {"info": dict(DE)}}, "i18n": {"ru": {"seo": {"pages": {"info": RU}}}}}
    )
    cfg = _studio_save(tenant, {})
    assert cfg["seo"]["pages"]["info"] == DE
    assert _tr(cfg) == RU


def test_seo_and_head_hosts_disjoint():
    from apps.core import page_title

    for host in (*siteconfig.SEO_PAGE_HOSTS, "seite:zahlung"):
        assert siteconfig.is_seo_page_host(host)
        assert not page_title.has_head(host), host
        assert block_i18n.kinds({"host": host, "items": []}, "__page") == ("seo",)
    assert block_i18n.kinds({"host": "services", "items": []}, "__page") == ("title",)


def test_seiten_screen_has_no_translation_fields():
    from apps.core import content_page_views as views
    from apps.core.tests.test_m21_6_content_pages import _req, _user

    tenant = _shop(seo=DE, ru=RU)
    before = getattr(connection, "tenant", None)
    connection.tenant = tenant
    try:
        html = views.page_system(
            _req("/x/?tab=suche", user=_user(), tenant=tenant), "ueber-uns"
        ).content.decode()
    finally:
        connection.tenant = before
    assert DE["title"] in html and RU["title"] not in html and "f_tr_" not in html
