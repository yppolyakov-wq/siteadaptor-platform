"""FB-30.16 R0: характеризация страницы каталога и категории ДО разбивки шаблонов на блоки.

Снимок HTML (нормализованный: токены, UUID, ссылки на статику с хешем) для каждого шаблона
(`catalog_page_style` / `category_page_style`) в нескольких состояниях данных. Следующие шаги
(шаблон → блоки страницы) обязаны оставить сайт байт-в-байт таким же — сверка с этими файлами.

Обновить снимки (только осознанно, с объяснением в коммите):
    FB3016_GOLDEN=update uv run pytest apps/catalog/tests/test_fb3016_catalog_golden.py
"""

import os
import re
from datetime import timedelta
from pathlib import Path

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.catalog.tests.factories import CategoryFactory, ProductFactory
from apps.core import compositions
from apps.promotions import public_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
GOLDEN = Path(__file__).parent / "golden_fb3016"
UPDATE = os.environ.get("FB3016_GOLDEN") == "update"

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_HEX32 = re.compile(r"\b[0-9a-f]{32}\b")
_CSRF = re.compile(r'(name="csrfmiddlewaretoken" value=")[^"]+')
_NONCE = re.compile(r'(nonce=")[^"]+')


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _normalize(html: str) -> str:
    # только область страницы: шапка, подвал и скрипты общие и к шаблону каталога не относятся
    start, end = html.find("<main"), html.rfind("</main>")
    if start != -1 and end != -1:
        html = html[start : end + len("</main>")]
    html = _CSRF.sub(r"\1X", html)
    html = _NONCE.sub(r"\1X", html)
    html = _UUID.sub("UUID", html)
    html = _HEX32.sub("HEX", html)
    return "\n".join(line.rstrip() for line in html.splitlines() if line.strip()) + "\n"


def _data(*, subcats: bool, photos: bool):
    """Каталог: корень «Brot» (с подкатегориями или без) и «Kuchen»; товары с явным
    временем создания — порядок карточек не зависит от случайных pk."""
    base = timezone.now() - timedelta(days=30)
    img = [{"url": "/media/categories/c.png", "is_primary": True}] if photos else []
    brot = CategoryFactory(slug="brot", name={"de": "Brot"}, images=img)
    kuchen = CategoryFactory(slug="kuchen", name={"de": "Kuchen"}, images=img)
    n = 0
    targets = [brot, kuchen]
    if subcats:
        for slug, label in (("weizen", "Weizen"), ("roggen", "Roggen")):
            targets.append(
                CategoryFactory(slug=f"brot-{slug}", name={"de": label}, parent=brot, images=img)
            )
    for cat in targets:
        for i in range(3):
            n += 1
            p = ProductFactory(name={"de": f"{cat.slug} {i}"}, category=cat)
            type(p).objects.filter(pk=p.pk).update(created_at=base + timedelta(hours=n))
    return brot


def _request(path, tenant):
    request = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    return request


def _check(name: str, html: str):
    path = GOLDEN / f"{name}.html"
    got = _normalize(html)
    if UPDATE or not path.exists():
        if not UPDATE:
            pytest.fail(f"нет снимка {path.name}: FB3016_GOLDEN=update")
        path.write_text(got)
        return
    assert got == path.read_text(), f"вид каталога изменился: {path.name}"


CATALOG = sorted(code for code, _l, _h in compositions.styles_for("catalog"))
CATEGORY = sorted(code for code, _l, _h in compositions.styles_for("category"))
STATES = [("sub-photo", True, True), ("sub-plain", True, False), ("flat", False, False)]


@pytest.mark.parametrize("state,subcats,photos", STATES)
@pytest.mark.parametrize("code", CATALOG)
def test_catalog_root_looks_as_before(code, state, subcats, photos):
    _data(subcats=subcats, photos=photos)
    tenant = TenantFactory.build(
        name="Bäckerei X", site_config={"catalog_page_style": code} if code else {}
    )
    html = public_views.product_list(_request("/sortiment/", tenant)).content.decode()
    _check(f"root-{code or 'standard'}-{state}", html)


@pytest.mark.parametrize("state,subcats,photos", STATES)
@pytest.mark.parametrize("code", CATEGORY)
def test_category_page_looks_as_before(code, state, subcats, photos):
    brot = _data(subcats=subcats, photos=photos)
    type(brot).objects.filter(pk=brot.pk).update(page_style=code)
    tenant = TenantFactory.build(name="Bäckerei X")
    html = public_views.product_list(_request("/sortiment/brot/", tenant), slug="brot")
    _check(f"cat-{code or 'standard'}-{state}", html.content.decode())


@pytest.mark.parametrize("code", ["", "regale", "mosaik"])
def test_filtered_catalog_looks_as_before(code):
    _data(subcats=True, photos=True)
    tenant = TenantFactory.build(
        name="Bäckerei X", site_config={"catalog_page_style": code} if code else {}
    )
    html = public_views.product_list(_request("/sortiment/?q=brot", tenant)).content.decode()
    _check(f"root-{code or 'standard'}-search", html)


def test_stored_part_rows_do_not_change_the_page_yet():
    """FB-31 P0: строка «Kategorien» и поля ★ уже хранятся, но витрина рисует как раньше
    (рендер по блокам — шаг R2)."""
    _data(subcats=True, photos=True)
    rows = [{"key": "categories", "enabled": True}, {"key": "main", "style": "mosaik"}]
    tenant = TenantFactory.build(name="Bäckerei X", site_config={"page_blocks": {"catalog": rows}})
    html = public_views.product_list(_request("/sortiment/", tenant)).content.decode()
    _check("root-standard-sub-photo", html)


# ── R1: случаи, которых не было в R0 (план §7) ──

_TEXT_ABOVE = {"key": "text", "id": "t-above", "data": {"title": "Über der Liste", "body": "Oben"}}
_TEXT_BELOW = {
    "key": "text",
    "id": "t-below",
    "data": {"title": "Unter der Liste", "body": "Unten"},
}


@pytest.mark.parametrize("code", ["", "regale", "sets", "wegweiser", "navigator", "kopfbild"])
def test_own_blocks_above_and_below_the_list_look_as_before(code):
    _data(subcats=True, photos=True)
    cfg = {"page_blocks": {"catalog": [_TEXT_ABOVE, {"key": "main"}, _TEXT_BELOW]}}
    if code:
        cfg["catalog_page_style"] = code
    tenant = TenantFactory.build(name="Bäckerei X", site_config=cfg)
    html = public_views.product_list(_request("/sortiment/", tenant)).content.decode()
    _check(f"root-{code or 'standard'}-blocks", html)


def test_child_of_a_tabs_parent_looks_as_before():
    brot = _data(subcats=True, photos=False)
    type(brot).objects.filter(pk=brot.pk).update(page_style="tabs")
    tenant = TenantFactory.build(name="Bäckerei X")
    html = public_views.product_list(
        _request("/sortiment/brot-weizen/", tenant), slug="brot-weizen"
    )
    _check("cat-tabs-child", html.content.decode())


@pytest.mark.parametrize("code", ["mosaik", "magazin", "kompakt"])
def test_owner_grid_beats_the_template_hint_as_before(code):
    _data(subcats=True, photos=True)
    cfg = {"catalog_page_style": code, "catalog_layout": {"preset": "cols5"}}
    tenant = TenantFactory.build(name="Bäckerei X", site_config=cfg)
    html = public_views.product_list(_request("/sortiment/", tenant)).content.decode()
    _check(f"root-{code}-owner-grid", html)


def test_category_style_over_the_site_default_looks_as_before():
    brot = _data(subcats=True, photos=True)
    type(brot).objects.filter(pk=brot.pk).update(page_style="regale")
    cfg = {"site_defaults": {"category_page_style": "mosaik"}}
    tenant = TenantFactory.build(name="Bäckerei X", site_config=cfg)
    html = public_views.product_list(_request("/sortiment/brot/", tenant), slug="brot")
    _check("cat-own-over-site", html.content.decode())
    kuchen = public_views.product_list(_request("/sortiment/kuchen/", tenant), slug="kuchen")
    _check("cat-site-default", kuchen.content.decode())
