"""FB-27 R8: граница со Студией — «Speichern» Студии пишет содержимое и вид блоков, а
структуру (порядок, состав, видимость, ширину) правит только «Seitenaufbau»."""

import pytest

from apps.core import site_schema
from apps.core.tests.test_stu12_groups import _post_builder
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _text(bid, title, **extra):
    return {"key": "text", "id": bid, "enabled": True, "data": {"title": title}, **extra}


def _tenant(sections=None, page_blocks=None):
    cfg = {}
    if sections is not None:
        cfg["sections"] = sections
    if page_blocks is not None:
        cfg["page_blocks"] = page_blocks
    return TenantFactory(site_config=cfg)


def _own(cfg):
    return [s for s in cfg["sections"] if s.get("id")]


def _row(bid, title, order, **extra):
    """Строка своего блока, как её шлёт форма Студии."""
    return {
        f"cb_type_{bid}": "text",
        f"enabled_cb_{bid}": "on",
        f"order_cb_{bid}": str(order),
        f"cb_{bid}_title": title,
        **extra,
    }


# ───────────── чистая функция ─────────────


def test_merge_keeps_saved_order_and_takes_posted_content():
    saved = [_text("a", "A", width="w12"), {"key": "main"}, _text("b", "B")]
    posted = [_text("b", "B neu", width="w13", enabled=False), _text("a", "A neu")]
    out = site_schema.merge_structure(saved, posted)
    assert [b.get("id") or b["key"] for b in out] == ["a", "main", "b"]
    assert [b["data"]["title"] for b in out if b.get("id")] == ["A neu", "B neu"]
    assert out[0]["width"] == "w12" and "width" not in out[2] and out[2]["enabled"] is True


def test_merge_drops_unknown_blocks_and_keeps_missing_ones():
    saved = [_text("a", "A"), _text("b", "B")]
    out = site_schema.merge_structure(saved, [_text("zzz", "fremd"), _text("b", "B neu")])
    assert [b["id"] for b in out] == ["a", "b"]
    assert out[0]["data"]["title"] == "A" and out[1]["data"]["title"] == "B neu"


def test_merge_ignores_a_row_of_another_type_under_the_same_id():
    saved = [_text("a", "A")]
    posted = [{"key": "button", "id": "a", "enabled": True, "data": {"label": "x"}}]
    assert site_schema.merge_structure(saved, posted) == saved


def test_merge_pages_keeps_hosts_that_are_not_in_the_form():
    saved = {"info": [_text("a", "A")], "catalog": [_text("b", "B")]}
    out = site_schema.merge_pages(saved, {"info": [_text("a", "A neu")], "cart": [_text("x", "X")]})
    assert sorted(out) == ["catalog", "info"]
    assert out["info"][0]["data"]["title"] == "A neu" and out["catalog"] == saved["catalog"]


# ───────────── «Speichern» Студии ─────────────


def test_save_writes_text_but_not_order_visibility_or_width():
    tenant = _tenant([_text("a", "A", width="w12"), _text("b", "B")])
    before = siteconfig.normalize(tenant.site_config)
    post = {"cb_id": ["a", "b"], **_row("a", "A neu", 9, width_cb_a="w13"), **_row("b", "B neu", 1)}
    del post["enabled_cb_b"]  # галочка «sichtbar» снята
    cfg = _post_builder(tenant, post)
    assert [b["id"] for b in _own(cfg)] == ["a", "b"]
    assert [b["data"]["title"] for b in _own(cfg)] == ["A neu", "B neu"]
    assert _own(cfg)[0]["width"] == "w12" and _own(cfg)[1]["enabled"] is True
    assert site_schema.structure_hash(cfg) == site_schema.structure_hash(before)


def test_fixed_sections_keep_their_order_and_visibility():
    tenant = _tenant()
    before = siteconfig.normalize(tenant.site_config)
    keys = [s["key"] for s in before["sections"]]
    # форма шлёт обратный порядок и ни одной галочки видимости
    post = {f"order_{key}": str(len(keys) - i) for i, key in enumerate(keys)}
    cfg = _post_builder(tenant, post)
    assert [s["key"] for s in cfg["sections"]] == keys
    assert [s["enabled"] for s in cfg["sections"]] == [s["enabled"] for s in before["sections"]]


def test_block_missing_from_the_form_is_not_deleted():
    tenant = _tenant([_text("a", "A"), _text("b", "B")])
    cfg = _post_builder(tenant, {"cb_id": ["a"], **_row("a", "A neu", 1)})
    assert [(b["id"], b["data"]["title"]) for b in _own(cfg)] == [("a", "A neu"), ("b", "B")]


def test_delete_checkbox_of_the_studio_is_ignored():
    tenant = _tenant([_text("a", "A")])
    cfg = _post_builder(tenant, {"cb_id": ["a"], **_row("a", "A", 1), "delete_cb_a": "on"})
    assert [b["id"] for b in _own(cfg)] == ["a"]


def test_stale_tab_cannot_bring_back_a_removed_block():
    tenant = _tenant([_text("a", "A"), _text("b", "B")])
    # «Seitenaufbau» тем временем убрал блок b
    cfg = siteconfig.normalize(tenant.site_config)
    cfg["sections"] = [s for s in cfg["sections"] if s.get("id") != "b"]
    Tenant.objects.filter(pk=tenant.pk).update(site_config=cfg)
    tenant.refresh_from_db()
    post = {"cb_id": ["a", "b"], **_row("a", "A neu", 1), **_row("b", "B neu", 2)}
    assert [b["id"] for b in _own(_post_builder(tenant, post))] == ["a"]


def test_page_blocks_keep_hosts_order_and_blocks_outside_the_form():
    pages = {
        "info": [_text("a", "A"), _text("b", "B")],
        "catalog": [_text("c", "C"), {"key": "main"}, _text("d", "D")],
    }
    tenant = _tenant(page_blocks=pages)
    post = {
        "pb_present": "1",
        "pb_id": ["b", "a", "x"],
        "pb_page_b": "info",
        "pb_page_a": "info",
        "pb_page_x": "cart",
        **_row("b", "B neu", 1),
        **_row("a", "A neu", 2),
        **_row("x", "Fremd", 1),
    }
    out = _post_builder(tenant, post)["page_blocks"]
    assert sorted(out) == ["catalog", "info"]
    assert [(b["id"], b["data"]["title"]) for b in out["info"]] == [("a", "A neu"), ("b", "B neu")]
    assert [b.get("id") or b["key"] for b in out["catalog"]] == ["c", "main", "d"]


def test_partial_form_does_not_erase_content():
    tenant = _tenant([_text("a", "A", visual={"radius": 12})], {"info": [_text("p", "P")]})
    before = siteconfig.normalize(tenant.site_config)
    cfg = _post_builder(tenant, {})
    assert _own(cfg) == _own(before)
    assert cfg["page_blocks"] == before["page_blocks"]


# ───────────── живой черновик ─────────────


def test_live_draft_carries_text_but_cannot_reorder_hide_or_drop():
    import json
    from types import SimpleNamespace

    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.core import views

    tenant = _tenant(
        [_text("a", "A"), _text("b", "B")], {"info": [_text("p", "P"), _text("q", "Q")]}
    )
    payload = {
        "sections": [
            {"key": "text", "id": "b", "enabled": False, "data": {"title": "B neu"}},
            {"key": "text", "id": "zzz", "enabled": True, "data": {"title": "Fremd"}},
        ],
        "page_blocks": {
            "info": [{"key": "text", "id": "q", "enabled": True, "data": {"title": "Q neu"}}],
            "cart": [{"key": "text", "id": "x", "enabled": True, "data": {"title": "X"}}],
        },
    }
    req = RequestFactory().post(
        "/dashboard/site/preview-draft/", data=json.dumps(payload), content_type="application/json"
    )
    SessionMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    req.user = SimpleNamespace(is_authenticated=True)
    assert views.site_preview_draft(req).status_code == 204
    draft = siteconfig.normalize(req.session["site_preview_draft"])
    own = _own(draft)
    assert [(b["id"], b["data"]["title"], b["enabled"]) for b in own] == [
        ("a", "A", True),
        ("b", "B neu", True),
    ]
    assert sorted(draft["page_blocks"]) == ["info"]
    assert [(b["id"], b["data"]["title"]) for b in draft["page_blocks"]["info"]] == [
        ("p", "P"),
        ("q", "Q neu"),
    ]
