"""AIS A-1: статьи справки в шторке «✨ Assistent» — реестр, поиск без ИИ, гейты, разметка.

План — docs/ais-a1-help-articles-plan-2026-11-06.md §7."""

import re
import uuid

import polib
import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import translation

from apps.core import assistant, assistant_views, help_articles, packages, tg_login
from apps.core.help_articles import BY_KEY, REGISTRY
from apps.core.models import Membership
from apps.tenants.tests.factories import TenantFactory

LOCALES = ("de", "en", "ru", "tr", "uk")


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture(autouse=True)
def _fresh_index():
    help_articles._index.cache_clear()
    yield
    help_articles._index.cache_clear()


def _user(role=Membership.ROLE_OWNER):
    o = uuid.uuid4().hex[:8]
    user = get_user_model().objects.create_user(
        username=f"h-{o}", email=f"h-{o}@t.de", password="pw12345678"
    )
    Membership.objects.create(user=user, role=role)
    return user


def _req(tenant, data=None, user=None):
    request = RequestFactory().get("/dashboard/assistent/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user or _user()
    request.tenant = tenant
    return request


@pytest.fixture
def bakery(db):
    return TenantFactory(schema_name="public", business_type="bakery")


# --- реестр -------------------------------------------------------------------------------


def test_registry_shape():
    keys = [a.key for a in REGISTRY]
    assert len(keys) == len(set(keys)) and len(keys) >= 20
    for a in REGISTRY:
        assert help_articles.KEY_RE.fullmatch(a.key), a.key
        assert str(a.title) and str(a.summary) and str(a.keywords), a.key
        assert 2 <= len(a.steps) <= 6, a.key
        assert a.links, a.key
        link_keys = [x.key for x in a.links]
        assert len(link_keys) == len(set(link_keys)), a.key


def test_every_link_is_a_known_screen_and_reverses():
    known = assistant.known_screens()
    for a in REGISTRY:
        assert a.all_screens <= known, (a.key, a.all_screens - known)
        for ln in a.links:
            assert ln.url_name in known, (a.key, ln.url_name)
            reverse(ln.url_name)
            assert ln.method in ("GET", "POST")
            if ln.method == "POST":
                assert ln.url_name in assistant.OWNER_ACTIONS, (a.key, ln.url_name)
            assert "?" not in ln.query and "//" not in ln.query and ":" not in ln.query


def _strings(article):
    yield article.title
    yield article.summary
    yield from article.steps
    for ln in article.links:
        yield ln.label


def test_every_string_is_translated_in_all_locales():
    """Каждая строка статьи есть во всех 5 .po и непустая; ключевые слова — с контекстом."""
    for loc in LOCALES:
        po = polib.pofile(f"locale/{loc}/LC_MESSAGES/django.po")
        plain = {e.msgid: e for e in po if not e.msgctxt and not e.obsolete}
        ctx = {e.msgid: e for e in po if e.msgctxt == "help-keywords" and not e.obsolete}
        for a in REGISTRY:
            for s in _strings(a):
                msgid = s._args[0]
                entry = plain.get(msgid)
                assert entry and entry.msgstr and "fuzzy" not in entry.flags, (loc, msgid)
                assert "%" not in msgid, msgid
            kw = a.keywords._args[1]
            assert ctx.get(kw) and ctx[kw].msgstr, (loc, a.key)


# --- поиск --------------------------------------------------------------------------------


def _keys(q):
    return [a.key for a in help_articles.ranked(q)]


def test_search_by_synonym_without_umlaut_and_compound():
    assert _keys("Liefergebiet")[0] == "lieferung_abholung"
    assert _keys("offnungszeiten")[0] == "oeffnungszeiten"
    assert "oeffnungszeiten" in _keys("zeiten")
    assert _keys("Urlaub")[0] == "betriebsferien"


def test_search_all_words_then_any_word():
    assert _keys("Storno Anzahlung")[0] == "buchungsregeln"
    assert _keys("Storno xyzqwv")  # «любое слово», если «все слова» не нашли


def test_short_or_empty_query_finds_nothing():
    assert _keys("") == [] and _keys("ab z") == []


def test_german_word_works_in_russian_interface():
    with translation.override("ru"):
        help_articles._index.cache_clear()
        assert _keys("Lieferung")[0] == "lieferung_abholung"
        assert "lieferung_abholung" in _keys("доставка")


def test_search_caps_results(bakery):
    assert len(help_articles.search(_req(bakery), "Öffnen")) <= help_articles.MAX_RESULTS


# --- гейты --------------------------------------------------------------------------------


def test_disabled_direction_and_module_hide_article(bakery, monkeypatch):
    from apps.core import directions, modules

    request = _req(bakery)
    assert help_articles.opened(request, "zimmer_anlegen") is not None
    monkeypatch.setattr(directions, "is_active", lambda t, key: key != "zimmer")
    assert help_articles.opened(request, "zimmer_anlegen") is None
    assert "zimmer_anlegen" not in [x["key"] for x in help_articles.search(request, "Zimmer")]
    monkeypatch.setattr(
        modules,
        "is_module_active",
        lambda t, k, **kw: k != "promotions",
    )
    assert help_articles.opened(request, "aktion_erstellen") is None
    assert "aktion_erstellen" not in [x["key"] for x in help_articles.search(request, "Aktion")]


def test_gate_applies_before_cap(bakery, monkeypatch):
    """Скрытые статьи с большим весом не вытесняют видимую из выдачи."""
    hidden = [a for a in REGISTRY if a.key != "oeffnungszeiten"][:8]
    monkeypatch.setattr(
        help_articles,
        "ranked",
        lambda q: [*hidden, BY_KEY["oeffnungszeiten"]],
    )
    monkeypatch.setattr(help_articles, "_gate_ok", lambda request, a: a.key == "oeffnungszeiten")
    assert [x["key"] for x in help_articles.search(_req(bakery), "x y")] == ["oeffnungszeiten"]


def test_staff_does_not_see_owner_article(bakery):
    staff = _req(bakery, user=_user(Membership.ROLE_STAFF))
    assert help_articles.opened(staff, "team_rechte") is None
    assert help_articles.opened(_req(bakery), "team_rechte") is not None


def test_blocked_screen_gives_note_not_link(bakery, monkeypatch):
    monkeypatch.setattr(packages, "view_allowed", lambda t, name: name != "payment-settings")
    item = help_articles.opened(_req(bakery), "bezahlung")
    assert item and item["links"][0]["link"].url == ""
    assert item["links"][0]["link"].blocked == assistant.BLOCK_PACKAGE


def test_mini_app_gets_browser_note(bakery, monkeypatch):
    monkeypatch.setattr(tg_login, "is_tg_session", lambda r: True)
    item = help_articles.opened(_req(bakery), "kategorien")
    assert item and item["links"][0]["link"].blocked == assistant.BLOCK_BROWSER


# --- ?artikel= и «Hilfe zu dieser Seite» ----------------------------------------------------


@pytest.mark.parametrize("bad", ["nope", "../etc", "<script>x</script>", "a" * 60, ""])
def test_unknown_artikel_is_ignored_and_not_reflected(bakery, bad):
    resp = assistant_views.assistant_view(_req(bakery, {"artikel": bad}))
    assert resp.status_code == 200
    body = resp.content.decode()
    if bad:
        assert bad not in body
    assert "data-help=" not in body


def test_known_artikel_opens_first(bakery):
    body = assistant_views.assistant_view(
        _req(bakery, {"artikel": "oeffnungszeiten", "box": "1"})
    ).content.decode()
    assert 'open data-help="oeffnungszeiten"' in body
    assert "data-drawer-autofocus" in body


def test_help_here_by_screen_and_screen_extra(bakery):
    here = help_articles.articles_here(_req(bakery), "payment-settings")
    keys = [x["key"] for x in here]
    assert "bezahlung" in keys and "lieferung_abholung" in keys
    assert len(here) <= help_articles.MAX_HERE
    extra = [x["key"] for x in help_articles.articles_here(_req(bakery), "sellable-manage")]
    assert "erstes_produkt" in extra
    assert help_articles.articles_here(_req(bakery), "") == []


def test_drawer_shows_both_groups_for_query(bakery):
    body = assistant_views.assistant_view(_req(bakery, {"q": "Öffnungszeiten"})).content.decode()
    assert "data-help-results" in body and 'data-help="oeffnungszeiten"' in body


def test_templates_have_no_safe_or_script():
    for name in ("_assistant_article.html", "_assistant_body.html"):
        src = open(f"templates/core/{name}", encoding="utf-8").read()
        assert "|safe" not in src and "<script" not in src
        assert not re.search(r"\son[a-z]+=", src)


def test_drawer_with_articles_is_read_only(bakery):
    request = _req(bakery, {"seite": "payment-settings", "q": "Lieferung", "artikel": "bezahlung"})
    with CaptureQueriesContext(connection) as ctx:
        assistant_views.assistant_view(request)
    writes = [
        q["sql"]
        for q in ctx.captured_queries
        if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        and "django_session" not in q["sql"]
    ]
    assert not writes, writes[:3]


# --- шов A-2 ------------------------------------------------------------------------------


def test_for_prompt_has_no_urls_and_respects_gates(bakery):
    request = _req(bakery, user=_user(Membership.ROLE_STAFF))
    out = help_articles.for_prompt(request, ["bezahlung", "team_rechte", "nope"])
    assert [x["key"] for x in out] == ["bezahlung"]
    flat = repr(out)
    assert "/dashboard/" not in flat and "http" not in flat
    assert out[0]["links"][0] == {"key": "open", "label": "Zahlung & Lieferung"}


def test_failed_settings_search_is_reported_even_with_articles(bakery, monkeypatch):
    """Найденные статьи не прячут сбой поиска настроек (и не пишут «Nichts gefunden»)."""
    monkeypatch.setattr(assistant, "where_search", lambda r, q: 1 / 0)
    body = assistant_views.assistant_view(_req(bakery, {"q": "Öffnungszeiten"})).content.decode()
    assert 'data-help="oeffnungszeiten"' in body
    assert "Die Suche konnte nicht ausgeführt werden" in body
    assert "Nichts gefunden" not in body


def test_nothing_found_only_when_both_empty(bakery):
    body = assistant_views.assistant_view(_req(bakery, {"q": "qqqxyzzz"})).content.decode()
    assert "Nichts gefunden" in body
    assert "data-help-results" not in body
