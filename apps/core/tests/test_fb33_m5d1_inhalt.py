"""FB-33 M5d-1 (D1): часть окна «Inhalt» у неподвижных строк страниц-форм (G2).

План — `docs/fb33-stack11-plan-2026-11-23.md` §2 D1, §4 D1, правки §8.1 H3/M8/M9 и §8.2 B5,
ответы владельца §8.5; макет M5dWindow (вариант A). Восемь строк `hideable=False` одной
строкой (`detail_sections.py`): у каждой — «Dieser Block zeigt …», «🔒 fest», ссылка «Inhalt
bearbeiten: <экран>» (экран — `DetailSection.content_nav`, подпись и доступ — `nav_registry`) и
подсказка про «＋ Block»; без «⋯», «Platz», «Vorschau». У Gutschein-Formular «Inhalt» — на той
же вкладке над частью § 312j (`pinned`), без второй вкладки.
"""

import ast
import dataclasses
import importlib.util
import logging
import re
from pathlib import Path
from types import SimpleNamespace

import polib
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import translation

from apps.core import block_window, detail_sections, nav_registry, site_schema
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m3_window_before import CFG, _capture, _panel
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]

#: G2 плана (`detail_sections.py`): страница → (ref строки, экран содержимого по grep реестра)
G2 = {
    "contact": ("form", "settings"),
    "gift": ("form", "promotions:voucher-list"),
    "loyalty": ("programs", "promotions:loyalty-list"),
    "finder": ("wizard", "finder-settings"),
    "teachers": ("teacherlist", "events:teacher-list"),
    "event_calendar": ("calendar", "events:list"),
    "passes": ("plans", "booking:passes"),
    "booking_slots": ("slots", "booking:resources"),
}
NO_RIGHT = "Nur mit Berechtigung bearbeitbar"
#: ревью D1 (решение владельца): модуль или пакет закрыты — видимая причина без ссылки
MODULE_OFF = "Modul ist nicht aktiv"
NO_PACKAGE = "Nicht in Ihrem Paket enthalten"
#: ревью a11y: подсказка называет кнопку её доступным именем («Block hinzufügen»,
#: `site_schema.html`), без полноширинного «＋» и без мест, которых владелец не видит
HINT = "Eigene Blöcke darüber oder darunter fügen Sie mit „Block hinzufügen“ in der Liste ein."
OLD_HINT = (
    "Eigene Blöcke darüber oder darunter: „＋ Block“ unter dieser Zeile oder unter dem Block davor."
)
MSGIDS = (
    "Inhalt bearbeiten: %(screen)s",
    "Dieser Block zeigt: %(summary)s.",
    "Er gehört fest zur Seite und lässt sich nicht ausblenden oder verschieben.",
    HINT,
    NO_RIGHT,
    MODULE_OFF,
    NO_PACKAGE,
)


@pytest.fixture(autouse=True)
def _env(settings, monkeypatch):
    from apps.core import page_settings

    settings.ROOT_URLCONF = "config.urls_tenant"
    # страницы G2 видны, когда у бизнеса есть их содержимое (тарифы, преподаватели, оплата
    # гутшайнов…) — здесь важен только модуль; гейт модуля `type_active` остаётся
    monkeypatch.setattr(page_settings, "_storefront_shows", lambda tenant, code: True)
    before = getattr(connection, "tenant", None)
    yield
    connection.tenant = before


def _tenant(disabled=()):
    tenant = TenantFactory(business_type="friseur", disabled_modules=list(disabled))
    connection.tenant = tenant
    return tenant


def _open(code, tenant=None, extra=""):
    ref = G2[code][0]
    return _capture(Browser(tenant or _tenant()), f"?seite={code}&block={ref}{extra}")


def _view_ctx(browser, query):
    """Контекст шаблона экрана (весь, не только `_VIEW_KEYS`)."""
    from django.test.signals import template_rendered

    seen = []

    def grab(sender, template, context, **kw):
        if getattr(template, "name", "") == "tenant/site_schema.html":
            seen.append(context)

    template_rendered.connect(grab)
    try:
        browser.get(query)
    finally:
        template_rendered.disconnect(grab)
    return seen[-1]


def _part(html: str, part: str) -> str:
    m = re.search(rf'<div data-window-part="{part}">(.*?)</div>\s*(?:<div data-window-part|</section>)',
                  html, re.S)  # fmt: skip
    assert m, f"нет части {part}"
    return m.group(1)


# --- реестр один -------------------------------------------------------------------------------


def test_content_nav_from_registry():
    """`content_nav` есть ровно у восьми разделов G2, каждый — имя URL записи `nav_registry`
    (однозначной: одна запись или одна без `query`); подпись ссылки — подпись этой записи."""
    with_nav = {
        (module, s.key): s.content_nav
        for module, sections in detail_sections.DETAIL_SECTIONS.items()
        for s in sections
        if getattr(s, "content_nav", "")
    }
    assert with_nav == {(code if code != "contact" else "message", ref): url
                        for code, (ref, url) in G2.items()}  # fmt: skip
    for (module, key), url_name in with_nav.items():
        section = next(s for s in detail_sections.sections_for(module) if s.key == key)
        assert not section.hideable and len(detail_sections.sections_for(module)) == 1
        entries = [e for e in nav_registry.ENTRIES if e.url_name == url_name]
        assert entries, url_name
        assert len([e for e in entries if not e.query]) == 1, url_name  # замок однозначности
        assert nav_registry.entry_by_url(url_name) is next(e for e in entries if not e.query)
    # у «Anfrage-Formular» своё окно («Felder») — экрана содержимого нет
    assert not detail_sections.sections_for("anfrage")[0].content_nav


def test_day_home_uses_the_registry_access_check():
    """M8: проверка «экран открыт» — одна функция `nav_registry.screen_open`; у `day_home`
    своей копии нет."""
    tree = ast.parse((ROOT / "apps/core/day_home.py").read_text(encoding="utf-8"))
    defs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert "_screen_open" not in defs
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Attribute) and n.attr == "screen_open"
        and isinstance(n.value, ast.Name) and n.value.id == "nav_registry"
    ]  # fmt: skip
    assert len(calls) >= 3


def test_screen_open_keeps_the_day_home_answers(monkeypatch):
    """Прежнее поведение `day_home._screen_open`: модуль выключен — закрыт; пакет закрыт —
    закрыт; сотрудник без права — закрыт (с причиной «perm»)."""
    from apps.core import packages, view_perms

    tenant = _tenant(disabled=["inbox"])
    member = SimpleNamespace(is_authenticated=True)
    req = SimpleNamespace(tenant=tenant, user=member)
    assert nav_registry.screen_closed(req, "inbox:list") == "module"
    assert not nav_registry.screen_open(req, "inbox:list")
    assert nav_registry.screen_open(req, "promotions:loyalty-list")
    monkeypatch.setattr(packages, "view_allowed", lambda t, name: name != "stock")
    assert nav_registry.screen_closed(req, "stock") == "package"
    monkeypatch.setattr("apps.core.permissions.is_member", lambda user: True)
    monkeypatch.setattr(view_perms, "allowed_quiet", lambda user, name, method="GET": False)
    assert nav_registry.screen_closed(req, "promotions:loyalty-list") == "perm"


def _inventory():
    spec = importlib.util.spec_from_file_location(
        "fb33_m5d_inventory", ROOT / "scripts" / "fb33_m5d_inventory.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_no_g2_block_without_window(monkeypatch):
    """Логикой `scripts/fb33_m5d_inventory.py` (ответ — разметка вьюхи): у всех строк страниц
    группы G2 окно есть."""
    from apps.core import view_perms
    from apps.core.tests.test_fb33_m5d_inventory import view_fetch
    from apps.tenants import siteconfig

    monkeypatch.setattr(view_perms, "allowed", lambda *a, **k: True)
    tenant = _tenant()
    mod = _inventory()
    saved = siteconfig.normalize(tenant.site_config)
    codes = {
        r.code
        for r in mod.schema_pages(tenant, saved)
        if mod.group_of(r.code, r.host or "") == "G2"
    }
    lines = mod.inventory(tenant, view_fetch(tenant), codes=codes)
    hosts = {ln["host"] for ln in lines if ln.get("key")}
    assert set(G2) - {"contact"} | {"message"} <= hosts, hosts  # фикстура не пустая
    assert not [ln for ln in lines if ln.get("skipped")]
    bare = [(ln["host"], ln["ref"]) for ln in lines if ln.get("key") and not ln["window"]]
    assert not bare, bare


# --- модель части ------------------------------------------------------------------------------


def test_inhalt_summary_is_row_summary(monkeypatch):
    """Сводка — `summary` строки (без своих запросов), пусто — подпись строки."""
    from apps.core import window_parts

    monkeypatch.setattr(nav_registry, "screen_closed", lambda request, url_name: "")
    req = SimpleNamespace(tenant=None, user=SimpleNamespace(is_authenticated=True))
    row = {"ref": "programs", "key": "programs", "label": "Treueprogramm", "summary": "2 Programme"}
    with CaptureQueriesContext(connection) as q:
        window_parts.content_part(row, "loyalty", req)
    assert len(q.captured_queries) == 0
    assert row["content"]["summary"] == "2 Programme"
    bare = {"ref": "programs", "key": "programs", "label": "Treueprogramm"}
    window_parts.content_part(bare, "loyalty", req)
    assert bare["content"]["summary"] == "Treueprogramm"
    # свои блоки и строки других страниц части не получают
    other = {"ref": "description", "key": "description", "label": "Beschreibung"}
    window_parts.content_part(other, "product_detail", req)
    assert "content" not in other
    cb = {"ref": "programs", "key": "programs", "label": "x", "cblock": True}
    window_parts.content_part(cb, "loyalty", req)
    assert "content" not in cb


def test_missing_nav_logged(monkeypatch, caplog):
    """Нет записи реестра — ссылки нет, ошибка конфигурации в журнале (не молча)."""
    from apps.core import window_parts

    broken = tuple(
        dataclasses.replace(s, content_nav="nope:missing")
        for s in detail_sections.DETAIL_SECTIONS["loyalty"]
    )
    monkeypatch.setitem(detail_sections.DETAIL_SECTIONS, "loyalty", broken)
    req = SimpleNamespace(tenant=_tenant(), user=SimpleNamespace(is_authenticated=True))
    row = {"ref": "programs", "key": "programs", "label": "Treueprogramm"}
    with caplog.at_level(logging.WARNING, logger="apps.core.window_parts"):
        window_parts.content_part(row, "loyalty", req)
    assert row["content"]["link"] is None and not row["content"]["reason"]
    assert any(
        "nope:missing" in r.getMessage() and r.levelno >= logging.ERROR for r in caplog.records
    )


def test_every_content_nav_is_configured():
    """Каждый `content_nav`: запись реестра есть, адрес строится, у экрана есть правило
    `view_perms`, `screen_closed` владельца отвечает без исключения (открыт)."""
    from apps.core import view_perms

    tenant = _tenant()
    req = SimpleNamespace(tenant=tenant, user=SimpleNamespace(is_authenticated=True))
    for sections in detail_sections.DETAIL_SECTIONS.values():
        for s in sections:
            if not s.content_nav:
                continue
            entry = nav_registry.entry_by_url(s.content_nav)
            assert entry is not None, s.content_nav
            assert reverse(entry.url_name), s.content_nav
            assert view_perms.rule_for(entry.url_name) is not None, s.content_nav
            assert nav_registry.screen_closed(req, s.content_nav) == "", s.content_nav


def test_screen_closed_without_entry_is_module():
    """Экран без записи реестра закрыт («module»), а не открыт молча."""
    req = SimpleNamespace(tenant=_tenant(), user=SimpleNamespace(is_authenticated=True))
    assert nav_registry.screen_closed(req, "nope:missing") == "module"
    assert not nav_registry.screen_open(req, "nope:missing")


def test_content_part_survives_errors(monkeypatch, caplog):
    """Сбой проверки доступа — экран 200, ссылки и причины нет, исключение в журнале."""

    def boom(request, url_name):
        raise RuntimeError("boom")

    monkeypatch.setattr(nav_registry, "screen_closed", boom)
    with caplog.at_level(logging.ERROR, logger="apps.core.window_parts"):
        html, _view, selected = _open("loyalty")
    assert selected["content"]["link"] is None and selected["content"]["reason"] == ""
    part = _part(_panel(html), "inhalt")
    assert "data-inhalt-link" not in part and "Dieser Block zeigt" in part
    assert any(r.exc_info for r in caplog.records)


def test_message_form_no_felder():
    """Kontaktformular — «Inhalt», без «Felder» (форма `form_spec` только у «Anfrage»)."""
    assert site_schema.form_of("message") == ""
    assert not site_schema.is_form_edit("message", "form", "update")
    html, view, selected = _open("contact")
    tabs = block_window.tabs(selected, view)
    assert [t["key"] for t in tabs] == ["was"] and tabs[0]["parts"] == ["inhalt"]
    assert "data-form-felder" not in html and 'data-window-tab="felder"' not in html


# --- окно ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("code", sorted(G2))
def test_every_g2_row_has_the_inhalt_window(code):
    html, view, selected = _open(code)
    panel = _panel(html)
    assert 'value="window_done"' in panel
    part = _part(panel, "inhalt")
    url = reverse(G2[code][1])
    assert f'href="{url}"' in part and "data-inhalt-link" in part
    assert "Er gehört fest zur Seite" in part and HINT in part and "＋" not in part
    assert "Dieser Block zeigt: " in part
    if code != "gift":
        # одна вкладка — полосы вкладок нет
        assert "data-window-tabs" not in panel
        assert [t["parts"] for t in block_window.tabs(selected, view)] == [["inhalt"]]


def test_inhalt_link_name_matches_visible():
    """Имя ссылки = её видимый текст (без `aria-label`): «Inhalt bearbeiten: Treuepunkte»."""
    html, _view, _selected = _open("loyalty")
    part = _part(_panel(html), "inhalt")
    a = re.search(r"<a\b([^>]*)>(.*?)</a>", part, re.S)
    assert a and "data-inhalt-link" in a.group(1)
    assert "aria-label" not in a.group(1)
    assert re.sub(r"\s+", " ", a.group(2)).strip() == "Inhalt bearbeiten: Treuepunkte"
    assert NO_RIGHT not in part


def test_inhalt_link_and_texts_in_russian():
    with translation.override("ru"):
        html, _view, _selected = _open("loyalty")
    part = _part(_panel(html), "inhalt")
    assert "Изменить содержимое: " in part and "Inhalt bearbeiten" not in part


def test_lock_icon_aria_hidden():
    """Ревью a11y: значок «🔒 fest» целиком `aria-hidden` («fest» уже в заголовке окна и в
    следующей фразе), нефокусируемый; точка `ui-badge` у него спрятана правилом app.css."""
    html, _view, _selected = _open("loyalty")
    part = _part(_panel(html), "inhalt")
    badge = re.search(r"<span\b([^>]*\bdata-inhalt-fixed\b[^>]*)>(.*?)</span>", part, re.S)
    assert badge and 'aria-hidden="true"' in badge.group(1)
    assert "tabindex" not in badge.group(1) and "<a" not in badge.group(2)
    assert re.search(r"🔒\s*fest\b", re.sub(r"<[^>]+>", "", part))  # видно глазами
    assert part.count("🔒") == 1
    css = (ROOT / "static/src/app.css").read_text(encoding="utf-8")
    assert re.search(r"\[data-inhalt-fixed\]::before\s*\{\s*display:\s*none", css)


def test_link_target_44px_in_panel_and_window():
    css = (ROOT / "static/src/app.css").read_text(encoding="utf-8")
    rule = re.search(r"([^{}]*a\[data-inhalt-link\][^{}]*)\{([^}]*)\}", css)
    assert rule and "min-height: 2.75rem" in rule.group(2)
    assert "[data-schema-panel] a[data-inhalt-link]" in rule.group(1)
    assert ".ui-bwin a[data-inhalt-link]" in rule.group(1)


def test_inhalt_no_more_platz_preview():
    """Без «⋯», «Platz» и «Vorschau»: `has_preview` — функция `block_window`, вьюха зовёт её."""
    tenant = _tenant()
    b = Browser(tenant)
    ctx = _view_ctx(b, "?seite=loyalty&block=programs")
    html = b.get("?seite=loyalty&block=programs")
    panel = _panel(html)
    assert ctx["bw_preview"] is None and "data-bw-preview" not in html
    assert 'data-window-part="platz"' not in panel and "data-schema-more" not in panel
    window = ctx["window"]
    assert not block_window.has_preview(window)
    assert not block_window.has_preview([{"key": "texte", "parts": ["inhalt", "pinned"]}])
    assert block_window.has_preview([{"key": "texte", "parts": ["pinned"]}])  # cart — прежнее
    assert not block_window.has_preview([])


def test_inhalt_nojs_column():
    """Без JS — та же часть колонкой в панели: раздел вкладки виден, «Fertig» и «Abbrechen»."""
    html, _view, _selected = _open("finder")
    panel = _panel(html)
    sec = re.search(r'<section id="schema-tab-was"[^>]*>', panel)
    assert sec and " hidden" not in sec.group(0)
    assert 'data-window-part="inhalt"' in panel
    assert 'value="window_done"' in panel and 'value="revert"' in panel


def test_gift_inhalt_above_pinned_on_one_tab():
    """H3 / ответ владельца §8.5 №6: «Inhalt» у Gutschein-Formular — на вкладке части § 312j,
    над ней, второй вкладки нет; «Vorschau» нет."""
    tenant = _tenant()
    b = Browser(tenant)
    ctx = _view_ctx(b, "?seite=gift&block=form")
    window = ctx["window"]
    assert [(t["key"], t["parts"]) for t in window] == [("texte", ["inhalt", "pinned"])]
    assert ctx["bw_preview"] is None
    html = b.get("?seite=gift&block=form")
    panel = _panel(html)
    assert panel.index('data-window-part="inhalt"') < panel.index('data-window-part="pinned"')
    assert "Zahlungspflichtig bestellen" in panel  # подпись § 312j на месте
    assert f'href="{reverse("promotions:voucher-list")}"' in panel


def test_cart_pinned_rows_unchanged():
    """У строк с `pinned` без экрана содержимого (корзина) — ничего не изменилось."""
    from apps.core.tests.test_fb27_r2_draft import _tenant as shop_tenant

    tenant = shop_tenant()
    tenant.site_config = CFG
    tenant.save()
    b = Browser(tenant)
    for ref in ("summary", "items", "form"):
        ctx = _view_ctx(b, f"?seite=cart&block={ref}")
        selected = ctx.get("selected") or {}
        assert "content" not in selected, ref
        assert "inhalt" not in [p for t in ctx["window"] for p in t["parts"]], ref
    ctx = _view_ctx(b, "?seite=cart&block=summary")
    assert [(t["key"], t["parts"]) for t in ctx["window"]] == [
        ("texte", ["pinned"]),
        ("felder", ["noinput"]),
    ]
    assert ctx["bw_preview"] is not None


def test_link_hidden_when_module_off():
    """Модуль экрана выключен (гутшайны без «loyalty») — ссылки нет, видимая причина
    «Modul ist nicht aktiv» (решение владельца, ревью D1)."""
    tenant = _tenant(disabled=["loyalty"])
    html, _view, selected = _open("gift", tenant)
    part = _part(_panel(html), "inhalt")
    assert selected["content"]["link"] is None
    assert "data-inhalt-link" not in part and NO_RIGHT not in part
    assert MODULE_OFF in part and "data-inhalt-reason" in part
    assert "Er gehört fest zur Seite" in part


def test_link_hidden_when_package_closed(monkeypatch):
    """Экрана нет в пакете — ссылки нет, видимая причина «Nicht in Ihrem Paket enthalten»."""
    from apps.core import packages

    monkeypatch.setattr(
        packages, "view_allowed", lambda tenant, name: name != "promotions:loyalty-list"
    )
    html, _view, selected = _open("loyalty")
    part = _part(_panel(html), "inhalt")
    assert selected["content"]["link"] is None
    assert "data-inhalt-link" not in part and NO_PACKAGE in part and MODULE_OFF not in part


def test_employee_without_right_text_without_link():
    """B5 / ответ §8.5 №8: сотрудник без права на экран — текст без ссылки и видимая строка
    «Nur mit Berechtigung bearbeitbar»; с правом — ссылка."""
    from apps.core.models import Membership
    from apps.core.tests.test_staff_walk import _open as walk_open
    from apps.core.tests.test_staff_walk import _user

    tenant = _tenant()
    path = "/dashboard/site/aufbau/?seite=loyalty&block=programs"
    staff = _user(Membership.ROLE_STAFF)
    Membership.objects.filter(user=staff).update(
        permissions={
            "add": ["website.view", "website.edit"],
            "remove": ["marketing.view", "marketing.edit"],
        }
    )
    resp = walk_open(path, tenant, staff)
    assert resp.status_code == 200
    part = _part(_panel(resp.content.decode()), "inhalt")
    assert "data-inhalt-link" not in part and "<a " not in part
    assert NO_RIGHT in part and "data-inhalt-reason" in part
    owner = _user(Membership.ROLE_OWNER)
    part = _part(_panel(walk_open(path, tenant, owner).content.decode()), "inhalt")
    assert "data-inhalt-link" in part and NO_RIGHT not in part


def test_inhalt_window_queries(monkeypatch):
    """Часть «Inhalt» стоит не больше одного запроса поверх окна без неё (№31) — и одинаково
    у всех восьми строк G2."""
    from apps.core import window_parts

    tenant = _tenant()
    b = Browser(tenant)
    real = window_parts.content_part

    def count(query):
        b.get(query)  # прогрев сессии и кэшей
        with CaptureQueriesContext(connection) as q:
            b.get(query)
        return len(q.captured_queries)

    extra = {}
    for code, (ref, _url) in G2.items():
        query = f"?seite={code}&block={ref}"
        monkeypatch.setattr(window_parts, "content_part", real)
        with_part = count(query)
        # FB-33 M5d-2: экран передаёт части ещё код страницы, объект и ссылку на него
        monkeypatch.setattr(window_parts, "content_part", lambda *args, **kwargs: None)
        extra[code] = with_part - count(query)
    assert max(extra.values()) <= 1, extra
    assert len(set(extra.values())) == 1, extra


def test_new_msgids_in_all_po():
    """Строки D1 есть во всех пяти каталогах, плейсхолдеры `%(…)s` совпадают; старая подсказка
    снята."""
    for lang in ("de", "en", "tr", "ru", "uk"):
        po = polib.pofile(str(ROOT / f"locale/{lang}/LC_MESSAGES/django.po"))
        have = {(e.msgctxt, e.msgid): e.msgstr for e in po if not e.obsolete}
        for msgid in MSGIDS:
            assert (None, msgid) in have, (lang, msgid)
            if lang != "de":
                assert have[(None, msgid)], (lang, msgid)
            got = have[(None, msgid)] or msgid
            names = sorted(re.findall(r"%\((\w+)\)s", msgid))
            assert sorted(re.findall(r"%\((\w+)\)s", got)) == names, (lang, msgid)
        assert (None, OLD_HINT) not in have, lang


def test_day_home_staff_without_stock_right_sees_no_low_stock(monkeypatch):
    """Поведение `nav_registry.screen_open` в сводке дня: без права на «stock» счётчик
    «мало на складе» скрыт (у владельца — виден)."""
    from uuid import uuid4

    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.core import day_home
    from apps.core.models import Membership

    tenant = TenantFactory(business_type="bakery", disabled_modules=[])
    monkeypatch.setattr(day_home, "_low_stock", lambda t: 5)

    def req(role, perms=None):
        r = RequestFactory().get("/dashboard/")
        SessionMiddleware(lambda x: None).process_request(r)
        MessageMiddleware(lambda x: None).process_request(r)
        r.tenant = tenant
        r.user = get_user_model().objects.create_user(
            username=f"m5d1-{uuid4().hex[:8]}", password="pw12345678"
        )
        Membership.objects.create(user=r.user, role=role, permissions=perms or {})
        return r

    owner = day_home.summary(req(Membership.ROLE_OWNER), "order")
    assert owner["dh_low_stock"] == 5
    staff = day_home.summary(
        req(Membership.ROLE_STAFF, {"remove": ["lager.view", "lager.edit"]}), "order"
    )
    assert staff["dh_low_stock"] == 0
