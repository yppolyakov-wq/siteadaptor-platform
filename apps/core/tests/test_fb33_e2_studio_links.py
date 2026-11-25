"""FB-33 стопка 14 E2: ссылки Студии «Fenster öffnen» и «Seitenaufbau öffnen» у блоков страниц.

До среза у блока «Liste» страницы ссылки в окно не было, а «Seitenaufbau öffnen» у баннера
страницы вела на голый экран схемы (без страницы и блока). Теперь вьюха Студии кладёт в строку
блока страницы готовый адрес окна (`site_schema.page_code_of_host` → `window_links.
block_window_url`); нет кода страницы — нет и ссылки. У главной — всё как было (охранный замок).

a11y M6: ссылка — обычный `<a href>` под `leaveOk()` (`data-stu-window`), без `target`; её
доступное имя начинается с видимого текста (2.5.3) и различается именем блока.
"""

import copy
import re
from html import unescape
from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils.html import escape

from apps.core import site_schema, views, window_links
from apps.core.modules import default_disabled_for
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


HEX = "0123456789abcdef0123456789abcdef"
#: стопка 15 M5e-3 (S14-E2-ghost, осознанно): ссылка в окно — только у живой страницы; замок
#: держит живые категорию, страницы и группу акций (`_live_pages`)
GROUP = "Sommer"
CATEGORY_HOST = "catalog:brot"


def _liste(ref, title=""):
    return {"key": "list", "id": ref, "enabled": True, "data": {"source": "events", "title": title}}


def _banner(ref):
    return {"key": "banner", "id": ref, "enabled": True, "data": {"pick": []}}


def _tenant(page_blocks=None, sections=None):
    tenant = TenantFactory(
        business_type="online_shop", disabled_modules=list(default_disabled_for("online_shop"))
    )
    tenant.site_config = copy.deepcopy(
        {"sections": sections or [], "page_blocks": page_blocks or {}}
    )
    tenant.save()
    _live_pages()
    return tenant


def _live_pages():
    from apps.catalog.tests.factories import CategoryFactory
    from apps.core.models import ContentPage
    from apps.promotions.tests.factories import PromotionFactory

    CategoryFactory(slug=CATEGORY_HOST.split(":", 1)[1])
    for slug in ("x", "x-2"):
        ContentPage.objects.create(slug=slug, title=slug, body="b", is_published=True)
    PromotionFactory(group=GROUP)


def _studio(tenant) -> str:
    req = RequestFactory().get("/dashboard/site/home/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    tenant.refresh_from_db()
    req.tenant = tenant
    return views.home_builder_view(req).content.decode()


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _page_part(html, host) -> str:
    """Разметка блоков страницы `host` в Студии (контейнер `data-page-key`)."""
    start = html.index(f'data-page-key="{host}"')
    nxt = html.find('class="page-block"', start)
    return html[start : nxt if nxt != -1 else len(html)]


def _anchors(part, text):
    """`<a …>…</a>` части, чей видимый текст начинается с `text`."""
    found = []
    for m in re.finditer(r"<a\b([^>]*)>(.*?)</a>", part, re.S):
        body = unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
        if body.startswith(text):
            found.append((m.group(1), m.group(2), body))
    return found


def _href(attrs) -> str:
    return unescape(re.search(r'href="([^"]*)"', attrs).group(1))


def test_window_url_from_window_links():
    tenant = _tenant({CATEGORY_HOST: [_liste("l2"), _banner("b2")]})
    part = _page_part(_studio(tenant), CATEGORY_HOST)
    code = site_schema.page_code_of_host(CATEGORY_HOST)
    assert code
    assert escape(window_links.block_window_url(code, "l2", "wie")) in part
    assert escape(window_links.block_window_url(code, "b2")) in part
    (fenster,) = _anchors(part, "Fenster öffnen")
    assert _href(fenster[0]) == window_links.block_window_url(code, "l2", "wie")
    (aufbau,) = _anchors(part, "Seitenaufbau öffnen")
    assert _href(aufbau[0]) == window_links.block_window_url(code, "b2")


@pytest.mark.parametrize(
    "host", [CATEGORY_HOST, "seite:x", "seite:x-2", siteconfig.promo_group_host(GROUP)]
)  # fmt: skip
def test_pbhost_key_not_ref(host):
    """Страница окна — код хоста (`page_code_of_host`), а не ключ блока или голый хост."""
    tenant = _tenant({host: [_liste("l2")]})
    part = _page_part(_studio(tenant), host)
    (fenster,) = _anchors(part, "Fenster öffnen")
    href = _href(fenster[0])
    code = site_schema.page_code_of_host(host)
    assert code and code != "l2"
    assert href == window_links.block_window_url(code, "l2", "wie")


def test_host_without_code_no_link():
    host = f"product:{HEX}"
    assert site_schema.page_code_of_host(host) == ""
    tenant = _tenant({host: [_liste("l2"), _banner("b2")]})
    part = _page_part(_studio(tenant), host)
    assert not _anchors(part, "Fenster öffnen")
    assert not _anchors(part, "Seitenaufbau öffnen")


def test_links_plain_named_leaveok():
    tenant = _tenant(
        {
            CATEGORY_HOST: [
                _liste("l2", "Neuheiten"),
                _liste("l3", "Angebote"),
                _banner("b2"),
            ]
        }
    )
    part = _page_part(_studio(tenant), CATEGORY_HOST)
    links = _anchors(part, "Fenster öffnen") + _anchors(part, "Seitenaufbau öffnen")
    assert len(links) == 3
    for attrs, _inner, _body in links:
        assert "data-stu-window" in attrs
        assert "target" not in attrs
        assert re.search(r'href="[^"#][^"]*"', attrs)
    names = [body for _a, _i, body in _anchors(part, "Fenster öffnen")]
    assert len(set(names)) == 2
    assert any("Neuheiten" in n for n in names) and any("Angebote" in n for n in names)
    for _attrs, inner, _body in links:
        # видимый текст первым, имя блока — только для чтения с экрана, после него
        assert inner.lstrip().startswith(("Fenster öffnen", "Seitenaufbau öffnen"))
        assert '<span class="sr-only">' in inner


def test_home_links_unchanged():
    """Охранный: у блоков главной ссылки прежние, байт-в-байт."""
    from django.urls import reverse

    html = _studio(_tenant(sections=[_liste("l1"), _banner("b1")]))
    open_url = reverse("site-schema-open")
    assert (
        f'<a href="{open_url}?page=%2F&amp;block=l1&amp;tab=wie" data-stu-window '
        'class="inline-flex items-center min-h-[24px] font-semibold text-indigo-700 underline">'
        "Fenster öffnen</a>"
    ) in html
    assert (
        f'<a href="{open_url}?page=%2F&amp;block=b1" class="inline-flex min-h-[44px] '
        'items-center font-semibold text-indigo-700 hover:underline">Seitenaufbau öffnen '
        '<span aria-hidden="true">→</span></a>'
    ) in html
