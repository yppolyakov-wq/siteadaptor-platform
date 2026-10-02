"""LB-2 §11.7: переводы C-блоков едут за своим блоком, а не за позицией.

Оверлей перевода `i18n[<локаль>]["sections"]` / `[…]["page_blocks"][<хост>]` мёржится
ПОЗИЦИОННО (i-й перевод поверх i-го блока). Save в базовом языке пересобирал список в
новом порядке и оверлеи не трогал — перестановка, удаление или вставка блока в
середину сдвигали переводы на чужие блоки: у посетителя на ru заголовок «Бета»
оказывался над блоком «Альфа». Маркер основного списка (LB-2) — тоже элемент списка, и
каждое его перемещение делало бы то же самое. Замки написаны ДО кода.
"""

import itertools
from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

_N = itertools.count()


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _text(title, bid):
    return {"key": "text", "id": bid, "enabled": True, "data": {"title": title, "body": "x"}}


def _tr(title):
    return {"data": {"title": title}}


def _tenant(locales=("de", "ru"), **cfg):
    t = TenantFactory(slug=f"ra{next(_N)}", name="Ra")
    t.site_config = cfg
    t.enabled_locales = list(locales)
    t.save(update_fields=["site_config", "enabled_locales"])
    return t


def _req(method, path, tenant, data=None):
    req = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return req


def _save(tenant, post):
    from apps.core import views

    resp = views.home_builder_view(_req("post", "/dashboard/site/home/", tenant, post))
    assert resp.status_code == 302
    tenant.refresh_from_db()


def _pb_post(host, rows, **extra):
    """POST билдера со строками блоков страницы: rows = [(id, заголовок, позиция)]."""
    post = {"pb_present": "1", "pb_id": [bid for bid, _t, _o in rows], **extra}
    for bid, title, order in rows:
        post[f"pb_page_{bid}"] = host
        post[f"cb_type_{bid}"] = "text"
        post[f"order_cb_{bid}"] = str(order)
        post[f"enabled_cb_{bid}"] = "on"
        post[f"cb_{bid}_title"] = title
        post[f"cb_{bid}_body"] = "x"
    return post


def _shown(tenant, locale, host=None):
    """[(id, заголовок)] блоков так, как их увидит посетитель на `locale`."""
    cfg = siteconfig.localize(siteconfig.normalize(tenant.site_config), locale)
    rows = cfg["page_blocks"][host] if host else cfg["sections"]
    return [(b["id"], b["data"]["title"]) for b in rows if b.get("id")]


def test_reordering_page_blocks_keeps_each_translation_on_its_block():
    t = _tenant(
        page_blocks={"info": [_text("Alpha", "a1"), _text("Beta", "b1")]},
        i18n={"ru": {"page_blocks": {"info": [_tr("Альфа"), _tr("Бета")]}}},
    )
    _save(t, _pb_post("info", [("b1", "Beta", 1), ("a1", "Alpha", 2)]))
    assert _shown(t, "ru", "info") == [("b1", "Бета"), ("a1", "Альфа")]


def test_deleting_a_page_block_takes_its_translation_away():
    t = _tenant(
        page_blocks={"info": [_text("Alpha", "a1"), _text("Beta", "b1")]},
        i18n={"ru": {"page_blocks": {"info": [_tr("Альфа"), _tr("Бета")]}}},
    )
    _save(t, _pb_post("info", [("a1", "Alpha", 1), ("b1", "Beta", 2)], delete_cb_a1="on"))
    assert _shown(t, "ru", "info") == [("b1", "Бета")]


def test_reordering_home_blocks_keeps_each_translation_on_its_block():
    t = _tenant(
        sections=[_text("Eins", "c1"), _text("Zwei", "c2")],
        i18n={"ru": {"sections": [_tr("Один"), _tr("Два")]}},
    )
    post = {
        "cb_id": ["c1", "c2"],
        "cb_type_c1": "text",
        "cb_type_c2": "text",
        "enabled_cb_c1": "on",
        "enabled_cb_c2": "on",
        "order_cb_c1": "2",
        "order_cb_c2": "1",
        "cb_c1_title": "Eins",
        "cb_c2_title": "Zwei",
    }
    _save(t, post)
    assert _shown(t, "ru")[:2] == [("c2", "Два"), ("c1", "Один")]


def test_inserting_a_block_in_the_middle_keeps_translations_in_place():
    from apps.core import views

    t = _tenant(
        page_blocks={"info": [_text("Alpha", "a1"), _text("Beta", "b1")]},
        i18n={"ru": {"page_blocks": {"info": [_tr("Альфа"), _tr("Бета")]}}},
    )
    req = _req(
        "post",
        "/dashboard/site/home/",
        t,
        {"action": "add_block", "block_type": "text", "page_key": "info", "add_after": "a1"},
    )
    views.home_builder_view(req)
    t.refresh_from_db()
    shown = dict(_shown(t, "ru", "info"))
    assert shown["a1"] == "Альфа" and shown["b1"] == "Бета"


def test_saving_in_a_translation_realigns_the_other_locales_too():
    """Save на ru выравнивает ru сам (`split_translation`), но и en не должен съехать."""
    t = _tenant(
        locales=("de", "ru", "en"),
        page_blocks={"info": [_text("Alpha", "a1"), _text("Beta", "b1")]},
        i18n={
            "ru": {"page_blocks": {"info": [_tr("Альфа"), _tr("Бета")]}},
            "en": {"page_blocks": {"info": [_tr("Alpha EN"), _tr("Beta EN")]}},
        },
    )
    _save(t, _pb_post("info", [("b1", "Бета", 1), ("a1", "Альфа", 2)], content_lang="ru"))
    assert _shown(t, "en", "info") == [("b1", "Beta EN"), ("a1", "Alpha EN")]
    assert _shown(t, "ru", "info") == [("b1", "Бета"), ("a1", "Альфа")]
    assert _shown(t, "de", "info") == [("b1", "Beta"), ("a1", "Alpha")]
