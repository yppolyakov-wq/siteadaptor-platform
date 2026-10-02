"""LB-2: «Hauptliste» — блоки страницы над и под основным списком.

План — `docs/lb-list-blocks-plan-2026-10-02.md` §11 (решение владельца Р-1(а):
основной список листинга — особый блок, один, двигается, не удаляется). Замки
написаны ДО кода.

Маркер `{"key": "main"}` в `page_blocks[<хост>]` делит блоки страницы на две части:
до него — над списком, после — под ним. Маркер первым = сегодняшний вид («все блоки
под списком»), поэтому в таком положении он НЕ хранится: конфиги живых сайтов, демо и
golden не меняются, хранится только осмысленное «есть блоки над списком».
"""

import itertools
import json
import pathlib
import re
from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.promotions import public_views
from apps.promotions.models import Promotion
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

_N = itertools.count()
MAIN = {"key": "main"}
ABOVE = "LB2-OBERHALB-7f3"
BELOW = "LB2-UNTERHALB-7f3"


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _text(title, bid=None):
    return {
        "key": "text",
        "id": bid or f"t{next(_N)}",
        "enabled": True,
        "data": {"title": title, "body": "x"},
    }


def _tenant(**cfg):
    # Схема НЕ public: context-processor витрины для public-схемы молчит (урок ST-3).
    t = TenantFactory(slug=f"mk{next(_N)}", name="Mk")
    t.site_config = cfg
    t.save(update_fields=["site_config"])
    return t


def _req(method, path, tenant, data=None, **get):
    req = getattr(RequestFactory(), method)(path, data or get or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return req


def _aktionen(tenant, **get):
    Promotion.objects.get_or_create(
        title={"de": "Angebot"},
        defaults={"status": "active", "promo_type": "discount", "discount_percent": 10},
    )
    return public_views.promotion_list(_req("get", "/aktionen/", tenant, **get)).content.decode()


# ───────────────────────────── данные ─────────────────────────────


def test_marker_after_a_block_is_kept_on_a_listing_host():
    out = siteconfig.normalize_page_blocks({"promos": [_text("A"), MAIN, _text("B")]})
    assert [b["key"] for b in out["promos"]] == ["text", "main", "text"]
    assert out["promos"][1] == {"key": "main"}  # у маркера нет данных


def test_marker_first_is_todays_layout_and_is_not_stored():
    out = siteconfig.normalize_page_blocks({"promos": [MAIN, _text("A"), _text("B")]})
    assert [b["key"] for b in out["promos"]] == ["text", "text"]


def test_marker_alone_is_not_a_block():
    assert siteconfig.normalize_page_blocks({"promos": [MAIN]}) == {}


def test_marker_is_dropped_on_a_page_without_a_main_list():
    out = siteconfig.normalize_page_blocks({"info": [_text("A"), MAIN]})
    assert [b["key"] for b in out["info"]] == ["text"]


def test_only_one_marker_per_host():
    out = siteconfig.normalize_page_blocks({"promos": [_text("A"), MAIN, _text("B"), MAIN]})
    assert [b["key"] for b in out["promos"]].count("main") == 1


def test_category_pages_have_a_main_list_too():
    out = siteconfig.normalize_page_blocks({"catalog:kaese": [_text("A"), MAIN]})
    assert [b["key"] for b in out["catalog:kaese"]] == ["text", "main"]


def test_marker_does_not_eat_the_block_cap():
    cap = siteconfig._MAX_CBLOCKS
    items = [_text(f"B{i}") for i in range(cap)]
    out = siteconfig.normalize_page_blocks({"promos": [items[0], MAIN, *items[1:]]})
    assert [b["key"] for b in out["promos"]].count("text") == cap


def test_main_list_hosts_are_page_block_hosts():
    for host in siteconfig.MAIN_LIST_HOSTS:
        assert siteconfig.is_page_block_host(host), host


# ───────────────────────────── рендер ─────────────────────────────


def test_without_marker_all_blocks_stay_below_the_list():
    t = _tenant(page_blocks={"promos": [_text(ABOVE), _text(BELOW)]})
    body = _aktionen(t)
    main = body.index("data-pb-main")
    assert body.index(ABOVE) > main and body.index(BELOW) > main


def test_blocks_before_the_marker_render_above_the_list():
    t = _tenant(page_blocks={"promos": [_text(ABOVE), MAIN, _text(BELOW)]})
    body = _aktionen(t)
    assert body.index(ABOVE) < body.index("data-pb-main") < body.index(BELOW)


def test_preview_anchor_of_an_empty_host_is_drawn_once():
    t = _tenant()
    body = _aktionen(t, preview="1")
    assert body.count('data-sf-section="pbhost:promos"') == 1


def _templates_with(pattern):
    found = {}
    for tpl in pathlib.Path("templates/storefront").rglob("*.html"):
        for m in re.finditer(pattern, tpl.read_text()):
            found.setdefault(m.group(1), set()).add(tpl.name)
    return found


def test_every_listing_host_renders_blocks_above_the_list():
    """Хост листинга обещает «блоки над списком» → его шаблон обязан их выводить."""
    before = _templates_with(r'page_blocks\s+"([a-z_]+)"\s+part="before"')
    missing = sorted(h for h in siteconfig.MAIN_LIST_HOSTS if h not in before)
    assert not missing, f"листинги без блоков над списком: {missing}"


def test_every_listing_marks_its_main_list():
    """Цель перетаскивания на канве — обёртка основного списка `data-pb-main`.

    Метку ставит общий каркас `listing.html`; замок проверяет, что каждый листинг на
    нём стоит — иначе блоки «над списком» выводились бы, а цели на канве не было.
    """
    skeleton = pathlib.Path("templates/storefront/listing.html").read_text()
    assert "data-pb-main" in skeleton
    for host, names in _templates_with(r'page_blocks\s+"([a-z_]+)"\s+part="before"').items():
        for name in names:
            text = (pathlib.Path("templates/storefront") / name).read_text()
            assert 'extends "storefront/listing.html"' in text, (host, name)


# ───────────────────────── Save, черновик, панель ─────────────────────────


def _pb_post(host, rows):
    """POST билдера со строками блоков страницы: rows = [(id, тип, позиция)]."""
    post = {"pb_present": "1", "pb_id": [bid for bid, _t, _o in rows]}
    for bid, btype, order in rows:
        post[f"pb_page_{bid}"] = host
        post[f"cb_type_{bid}"] = btype
        post[f"order_cb_{bid}"] = str(order)
        if btype != "main":
            post[f"enabled_cb_{bid}"] = "on"
            post[f"cb_{bid}_title"] = bid
    return post


def _save(tenant, post):
    from apps.core import views

    resp = views.home_builder_view(_req("post", "/dashboard/site/home/", tenant, post))
    assert resp.status_code == 302
    tenant.refresh_from_db()
    return siteconfig.normalize(tenant.site_config).get("page_blocks", {})


def test_builder_save_keeps_the_marker_where_the_owner_put_it():
    t = _tenant(page_blocks={"promos": [_text("a", "a1"), _text("b", "b1")]})
    saved = _save(
        t, _pb_post("promos", [("a1", "text", 1), ("main-promos", "main", 2), ("b1", "text", 3)])
    )
    assert [b.get("id", b["key"]) for b in saved["promos"]] == ["a1", "main", "b1"]


def test_builder_save_with_the_marker_first_stores_no_marker():
    t = _tenant(page_blocks={"promos": [_text("a", "a1"), MAIN, _text("b", "b1")]})
    saved = _save(
        t, _pb_post("promos", [("main-promos", "main", 1), ("a1", "text", 2), ("b1", "text", 3)])
    )
    assert [b["key"] for b in saved["promos"]] == ["text", "text"]


def test_builder_save_ignores_a_marker_on_a_page_without_a_main_list():
    t = _tenant(page_blocks={"info": [_text("a", "a1")]})
    saved = _save(t, _pb_post("info", [("a1", "text", 1), ("main-info", "main", 2)]))
    assert [b["key"] for b in saved["info"]] == ["text"]


def test_live_draft_moves_a_block_above_the_list():
    from apps.core import views

    t = _tenant(page_blocks={"promos": [_text(BELOW, "b1")]})
    payload = {
        "page_blocks": {
            "promos": [
                {"key": "text", "id": "a1", "enabled": True, "data": {"title": ABOVE}},
                {"key": "main", "id": "main-promos", "enabled": False, "data": {}},
                {"key": "text", "id": "b1", "enabled": True, "data": {"title": BELOW}},
            ]
        }
    }
    req = RequestFactory().post(
        "/dashboard/site/preview-draft/", data=json.dumps(payload), content_type="application/json"
    )
    SessionMiddleware(lambda r: None).process_request(req)
    req.tenant = t
    req.user = SimpleNamespace(is_authenticated=True)
    views.site_preview_draft(req)
    preview = RequestFactory().get("/aktionen/", {"preview": "1"})
    preview.session = req.session
    preview.tenant = t
    Promotion.objects.create(
        title={"de": "Angebot"}, status="active", promo_type="discount", discount_percent=10
    )
    body = public_views.promotion_list(preview).content.decode()
    assert body.index(ABOVE) < body.index("data-pb-main") < body.index(BELOW)


def _builder(tenant):
    from apps.core import views

    return views.home_builder_view(_req("get", "/dashboard/site/home/", tenant)).content.decode()


def _orders(body, host):
    """{id: позиция} строк блоков хоста в панели (в порядке разметки)."""
    out = {}
    for m in re.finditer(r'data-cb-id="([^"]+)" data-pb-page="' + re.escape(host) + r'"', body):
        bid = m.group(1)
        pos = re.search(r'name="order_cb_' + re.escape(bid) + r'" value="(\d+)"', body)
        out[bid] = int(pos.group(1))
    return out


def test_panel_lists_the_main_list_among_the_blocks():
    t = _tenant(page_blocks={"promos": [_text("a", "a1"), _text("b", "b1")]})
    body = _builder(t)
    orders = _orders(body, "promos")
    main_id = next(bid for bid in orders if bid.startswith("main"))
    # неявный маркер — первым: блоки под списком, как сегодня
    assert orders[main_id] == 1 and orders["a1"] == 2 and orders["b1"] == 3
    assert f'name="cb_type_{main_id}" value="main"' in body


def test_panel_numbers_a_stored_marker_in_place():
    t = _tenant(page_blocks={"promos": [_text("a", "a1"), MAIN, _text("b", "b1")]})
    orders = _orders(_builder(t), "promos")
    main_id = next(bid for bid in orders if bid.startswith("main"))
    assert orders["a1"] == 1 and orders[main_id] == 2 and orders["b1"] == 3


def test_page_without_a_main_list_has_no_main_row():
    t = _tenant(page_blocks={"info": [_text("a", "a1")]})
    orders = _orders(_builder(t), "info")
    assert all(not bid.startswith("main") for bid in orders)


def test_inserted_row_is_numbered_with_the_marker():
    """Вставка без перезагрузки нумерует так же, как форма: неявный маркер — первый."""
    from apps.core import views

    t = _tenant(page_blocks={"promos": [_text("a", "a1"), _text("b", "b1")]})
    resp = views._add_block_fetch_response(_req("post", "/x/", t), "b1", "promos")
    row = json.loads(resp.content)["row_html"]
    assert 'name="order_cb_b1" value="3"' in row
