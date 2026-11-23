"""FB-33 M5c-4 (C3): полосы шапки и подвала в схеме страницы, «Ausgeblendet» с «Einblenden».

План `docs/fb33-stack11-plan-2026-11-23.md` §2 C3, §4 C3 и ответ владельца по C3m: полоса шапки —
«Menü bearbeiten» и «Design», полоса подвала — «Fußzeile bearbeiten» (экран «Menü» на вкладке
«Fußzeile»). Ссылки — только тому, кому экран открыт (`can_open`, права — прежние), адреса —
через `{% url %}`, ссылки подчёркнуты (WCAG 1.4.1), цель 44 px — правилом `static/src/app.css`.
"""

import re
from pathlib import Path

import pytest
from django.urls import reverse

from apps.core import permissions, view_perms
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb29_banner_pick import _tenant
from apps.core.tests.test_fb33_m5c0_insert import _draft_items

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = ROOT / "templates/tenant/site_schema.html"
APP_CSS = ROOT / "static/src/app.css"


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    settings.LANGUAGE_CODE = "de"


def _strip(html: str, name: str) -> str:
    m = re.search(rf"<div\b[^>]*data-schema-strip=\"{name}\"[^>]*>.*?</div>", html, re.S)
    assert m, f"полоса {name} не найдена"
    return m.group(0)


def _links(strip: str) -> list[str]:
    return re.findall(r"<a\b[^>]*>", strip)


def _href(tag: str) -> str:
    return re.search(r'href="([^"]+)"', tag).group(1).replace("&amp;", "&")


@pytest.mark.xfail(strict=True, reason="C3: полосы ещё без ссылок")
def test_strip_links_via_can_open():
    html = Browser(_tenant()).get("?seite=text")
    head = _links(_strip(html, "head"))
    assert [_href(a) for a in head] == [reverse("site-menu"), reverse("design")]
    foot = _links(_strip(html, "foot"))
    assert [_href(a) for a in foot] == [reverse("site-menu") + "?tab=footer"]
    assert "Fußzeile bearbeiten" in _strip(html, "foot")
    assert re.search(r">Menü bearbeiten</a>", _strip(html, "head"))
    assert re.search(r">Design</a>", _strip(html, "head"))


@pytest.mark.xfail(strict=True, reason="C3: полосы ещё без ссылок")
def test_strip_links_via_url_tag():
    """Адреса — через `{% url %}` под `can_open`, без вписанных путей."""
    src = TEMPLATE.read_text()
    assert "{% url 'design' %}" in src
    assert "{% url 'site-menu' %}?tab=footer" in src
    assert "'design'|can_open:request" in src
    assert src.count("'site-menu'|can_open:request") >= 2
    assert "/dashboard/design/" not in src and "/dashboard/site/menu/" not in src


@pytest.mark.xfail(strict=True, reason="C3: полосы ещё без ссылок")
def test_staff_without_right_no_links(monkeypatch):
    """Сотрудник без права на «Menü»/«Design» — подписи полос остаются, ссылок нет."""
    monkeypatch.setattr(permissions, "is_member", lambda user: True)
    real = view_perms.allowed_quiet

    def quiet(user, name, method="GET"):
        if name in ("site-menu", "design"):
            return False
        return real(user, name, method)

    monkeypatch.setattr(view_perms, "allowed_quiet", quiet)
    html = Browser(_tenant()).get("?seite=text")
    head, foot = _strip(html, "head"), _strip(html, "foot")
    assert _links(head) == [] and _links(foot) == []
    assert "Kopfzeile &amp; Menü" in head and "Fußzeile" in foot


@pytest.mark.xfail(strict=True, reason="C3: полосы ещё без ссылок")
def test_strip_links_underlined():
    html = Browser(_tenant()).get("?seite=text")
    tags = _links(_strip(html, "head")) + _links(_strip(html, "foot"))
    assert len(tags) == 3
    for tag in tags:
        assert re.search(r'class="[^"]*\bunderline\b', tag), tag
        assert "min-h-[24px]" not in tag, "высота цели — правилом app.css, не классом 24 px"


@pytest.mark.xfail(strict=True, reason="C3: полосы ещё без ссылок")
def test_strip_targets_44_in_css():
    css = APP_CSS.read_text()
    rule = re.search(r"\[data-schema-strip\] a\s*\{([^}]*)\}", css)
    assert rule and "min-height: 2.75rem" in rule.group(1)


def test_hidden_rows_show_button_without_number():
    """«Ausgeblendet»: у скрытой строки «Einblenden» (тот же `op=toggle`, `zeile=1`), номера нет;
    кнопка одна на строку (C1 уже рисует её — второй не заводим)."""
    b = Browser(_tenant())
    b.post(seite="text", op="add", type="text")
    ref = [i["id"] for i in _draft_items(b, "text") if i.get("id")][-1]
    b.post(seite="text", op="toggle", ref=ref, zeile="1")
    html = b.get("?seite=text")
    hidden = html[
        html.index("data-schema-hidden") : html.index(
            "</details>", html.index("data-schema-hidden")
        )
    ]
    assert hidden.count(f'id="schema-more-{ref}"') == 1
    assert hidden.count("Einblenden") == 1
    form = re.search(r"<form\b.*?</form>", hidden, re.S).group(0)
    assert 'name="zeile" value="1"' in form and 'value="toggle"' in form
    assert "schema-num" not in hidden
