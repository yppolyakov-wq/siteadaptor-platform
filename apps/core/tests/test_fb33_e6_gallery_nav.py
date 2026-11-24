"""FB-33 стопка 14 E6 (M5d-6): «Inhalt bearbeiten: Galerie» у блока «Beispiele unserer Arbeit»
(детальная Kombi) и запись палитры «Galerie».

План — `docs/fb33-stack14-plan-2026-11-24.md` §0.1 и §11 (решение владельца 2026-11-24: цель —
Студия на ГЛАВНОЙ у блока галереи, `site-home?page=%2F&block=gallery`; там фото загружаются при
любом состоянии, а `/galerie/` при пустой галерее — 404), §2 «E6», §4 «E6», §10 (H5, L2, L3,
a11y M6 и L1). Запись реестра — `palette_only`: якоря сайдбара заморожены
(`test_x0_x7_locks.py`). Ссылка строится прежним путём `setting` (§9 №5, вариант (a)): адрес —
`entry.query`, доступ — `nav_registry.screen_closed(request, name, target_url=…)`.
"""

import re
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import polib
import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.test import RequestFactory
from django.urls import resolve, reverse
from django.utils import translation

from apps.core import detail_sections, nav_registry
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m3_window_before import _capture, _panel
from apps.core.tests.test_fb33_m5d1_inhalt import _part
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]
QUERY = "?page=%2F&block=gallery"
WOHER = "Die ersten Fotos der Galerie Ihrer Website."


@pytest.fixture(autouse=True)
def _env(settings, monkeypatch):
    from apps.core import page_settings

    settings.ROOT_URLCONF = "config.urls_tenant"
    monkeypatch.setattr(page_settings, "_storefront_shows", lambda tenant, code: True)
    before = getattr(connection, "tenant", None)
    yield
    connection.tenant = before


def _tenant(**site_config):
    tenant = TenantFactory(business_type="friseur", disabled_modules=[], site_config=site_config)
    connection.tenant = tenant
    return tenant


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html)).strip()


def _inhalt(tenant):
    html, _view, selected = _capture(Browser(tenant), "?seite=combo&block=examples")
    assert selected and "content" in selected
    return _part(_panel(html), "inhalt"), selected["content"]


def _examples():
    return next(s for s in detail_sections.sections_for("combo") if s.key == "examples")


def _studio(tenant, url):
    """GET Студии по адресу ссылки — RequestFactory, как `test_dl19_studio`."""
    from apps.core import views

    split = urlsplit(url)
    request = RequestFactory().get(split.path, {k: v[0] for k, v in parse_qs(split.query).items()})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = SimpleNamespace(is_authenticated=True)
    request.tenant = tenant
    assert resolve(split.path).func is views.home_builder_view
    return views.home_builder_view(request)


def _galerie_entries():
    return [e for e in nav_registry.ENTRIES if e.url_name == "site-home"]


# --- красные: решение владельца и правки ревью ------------------------------------------------


def test_gallery_link_from_registry():
    """№2: ссылка — из записи реестра (подпись и адрес), путь `setting`; «Woher» — новой фразой
    без «automatisch»; presence-гейт витрины прежний (`only_if`)."""
    section = _examples()
    assert (section.source.kind, section.content_nav) == ("setting", "site-home")
    assert section.source.only_if and not section.source.query
    part, ct = _inhalt(_tenant())
    assert ct["link"] == {
        "label": nav_registry.entry_by_url("site-home").label,
        "url": reverse("site-home") + QUERY,
        "only_here": False,
    }
    assert str(ct["link"]["label"]) == "Galerie" and not ct["reason"]
    assert WOHER in ct["woher"] and "automatisch" not in ct["woher"]
    # a11y M6: имя ссылки = видимый текст с именем экрана; без `target` и `aria-label`
    link = re.search(r"<a [^>]*data-inhalt-link[^>]*>(.*?)</a>", part, re.S)
    assert link and _text(link.group(1)) == "Inhalt bearbeiten: Galerie"
    assert "target=" not in link.group(0) and "aria-label" not in link.group(0)


def test_gallery_link_target_200_when_empty():
    """Решение владельца: у бизнеса без фото цель ссылки отвечает 200 и открывает блок
    `gallery` — форма загрузки фото на месте (не `/galerie/`, там 404)."""
    tenant = _tenant()
    assert not siteconfig.normalize(tenant.site_config).get("gallery")
    _part_html, ct = _inhalt(tenant)
    assert ct["link"] and "/galerie/" not in ct["link"]["url"]
    resp = _studio(tenant, ct["link"]["url"])
    assert resp.status_code == 200
    html = resp.content.decode()
    assert 'var BLD_OPEN_BLOCK = "gallery";' in html
    assert 'name="action" value="upload_gallery"' in html


def test_gallery_palette_card_target_exists():
    """Карточка палитры «Galerie»: адрес разбирается в Студию, страница — главная, блок есть в
    секциях главной."""
    tenant = _tenant()
    req = SimpleNamespace(tenant=tenant, user=SimpleNamespace(is_authenticated=True))
    with translation.override("de"):
        cards = [c for c in nav_registry.palette_entries_for(req) if str(c["label"]) == "Galerie"]
    assert len(cards) == 1
    card = cards[0]
    assert card["url_name"] == "site-home" and card["query"] == QUERY
    assert "galerie" in card["haystack"] and "fotos" in card["haystack"]
    assert resolve(reverse(card["url_name"])).view_name == "site-home"
    params = parse_qs(card["query"].lstrip("?"))
    assert params == {"page": ["/"], "block": ["gallery"]}
    keys = {s["key"] for s in siteconfig.normalize(tenant.site_config)["sections"]}
    assert "gallery" in keys


def test_site_home_single_entry():
    """№5 и ревью L3: запись `site-home` в `ENTRIES` одна (с query), `entry_by_url` отдаёт её;
    докстрока `entry_by_url` говорит, что у `site-home` записи без query нет."""
    entries = _galerie_entries()
    assert len(entries) == 1 and entries[0].query == QUERY
    assert nav_registry.entry_by_url("site-home") is entries[0]
    assert "site-home" in (nav_registry.entry_by_url.__doc__ or "")


def test_gallery_entry_palette_only():
    """Мораторий: запись только в палитре, хаб и подсветка — «Website»; в сайдбаре её нет."""
    (entry,) = _galerie_entries()
    assert entry.palette_only and entry.hub == "site" and entry.nav_key == "site"
    assert entry.module_key is None and nav_registry.entry_gate(entry)
    site = next(a for a in nav_registry.ANCHORS if a.nav_key == "site")
    assert entry not in nav_registry.sidebar_children(site)


@pytest.mark.parametrize("closed", ["perm", "package", "rule"])
def test_gallery_link_closed(monkeypatch, closed):
    """№28: закрытая цель — причина абзацем, без `<a>` и без `aria-hidden` (a11y L1). Доступ —
    `screen_closed(..., target_url=)`: цель без правила `view_perms` — закрыто ("module")."""
    from apps.core import packages, view_perms

    target = reverse("site-home")
    if closed == "perm":
        real = view_perms.url_allowed
        monkeypatch.setattr(
            view_perms,
            "url_allowed",
            lambda user, url: False if url.startswith(target) else real(user, url),
        )
        reason = "Nur mit Berechtigung bearbeitbar"
    elif closed == "package":
        real_pkg = packages.view_allowed
        monkeypatch.setattr(
            packages,
            "view_allowed",
            lambda tenant, name: name != "site-home" and real_pkg(tenant, name),
        )
        reason = "Nicht in Ihrem Paket enthalten"
    else:
        real_rule = view_perms.rule_for
        monkeypatch.setattr(
            view_perms,
            "rule_for",
            lambda name: None if name == "site-home" else real_rule(name),
        )
        reason = "Modul ist nicht aktiv"
    part, ct = _inhalt(_tenant())
    assert ct["link"] is None and ct["reason"] == reason
    assert "<a " not in part and "data-inhalt-link" not in part
    para = re.search(r"<p [^>]*data-inhalt-reason[^>]*>.*?</p>", part, re.S)
    assert para and "aria-hidden" not in para.group(0)
    assert _text(para.group(0)) == f"Inhalt bearbeiten: Galerie — {reason}"


def test_e6_msgids_in_all_po():
    """№16: «Woher» блока — дословно строка P0b; она есть во всех пяти каталогах и переведена
    (кроме de)."""
    with translation.override(None):
        assert str(_examples().source.woher) == WOHER
    for lang in ("de", "en", "tr", "ru", "uk"):
        path = ROOT / f"locale/{lang}/LC_MESSAGES/django.po"
        have = {e.msgid: e.msgstr for e in polib.pofile(str(path)) if not e.obsolete}
        assert WOHER in have and "Galerie" in have, lang
        if lang != "de":
            assert have[WOHER] and have[WOHER] != WOHER, lang


# --- охранные: зелёные на базе и после кода ----------------------------------------------------


def test_studio_nav_highlight_unchanged():
    """Подсветка «Website» и адрес раздела — прежние: якорь ведёт в «Design», `nav="site"`
    подсвечивает якорь «Website»."""
    site = next(a for a in nav_registry.ANCHORS if a.nav_key == "site")
    assert site.url_name == "site-home" and site.targets == ("design",)
    assert nav_registry.anchor_for("site") == "site"
    assert nav_registry.ANCHOR_BY_NAV["site"] == "site"
    children = [(e.url_name, e.query) for e in nav_registry.sidebar_children(site)]
    assert ("site-home", QUERY) not in children
