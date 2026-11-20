"""FB-33 M3-5b: писатели вопросов FAQ — только `faq_content` (Студия, превью, канва).

Замки: Студия переставляет переводы по номеру поля и снимает перевод исправленного поля;
форма без отпечатка или из устаревшей вкладки — по тексту; режим перевода `put` не зовёт;
живой черновик превью не стирает вопросы; канва снимает перевод только своего поля; grep
«один писатель».
"""

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import faq_content, views
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

BASE = [
    {"q": "Parkplatz?", "a": "Ja."},
    {"q": "Lieferung?", "a": "Ab 30 €."},
    {"q": "Karte?", "a": "Online."},
]
RU = [
    {"q": "Парковка?", "a": "Да."},
    {"q": "Доставка?", "a": "От 30 €."},
    {"q": "Меню?", "a": "Онлайн."},
]


def _tenant(faq=BASE, ru=RU):
    tenant = TenantFactory(schema_name="public", slug="m35b", name="M35B")
    tenant.site_config = siteconfig.normalize({"faq": faq, "i18n": {"ru": {"faq": ru}}})
    tenant.enabled_locales = ["de", "ru"]
    tenant.save()
    return tenant


def _req(tenant, method, path, data=None, **extra):
    req = getattr(RequestFactory(), method)(path, data or {}, **extra)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return req


def _studio_save(tenant, pairs, base=None, **extra):
    data = {"content_sections_present": "1", "faq_present": "1", **extra}
    if base is not None:
        data["faq_base"] = base
    for i, (q, a) in pairs.items():
        data[f"faq_q_{i}"] = q
        data[f"faq_a_{i}"] = a
    assert (
        views.home_builder_view(_req(tenant, "post", "/dashboard/site/home/", data)).status_code
        == 302
    )
    return siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)


def test_studio_delete_first_question_keeps_the_rest():
    tenant = _tenant()
    cfg = _studio_save(
        tenant,
        {0: ("", ""), 1: BASE[1].values(), 2: BASE[2].values()},
        faq_content.fingerprint(BASE),
    )
    assert [f["q"] for f in cfg["faq"]] == ["Lieferung?", "Karte?"]
    assert cfg["i18n"]["ru"]["faq"] == RU[1:]


def test_studio_german_edit_drops_only_that_field():
    tenant = _tenant()
    cfg = _studio_save(
        tenant,
        {0: BASE[0].values(), 1: ("Lieferung?", "Ab 25 €."), 2: BASE[2].values(), 3: ("Neu?", "x")},
        faq_content.fingerprint(BASE),
    )
    assert cfg["i18n"]["ru"]["faq"] == [RU[0], {"q": "Доставка?"}, RU[2]]
    assert cfg["faq"][3] == {"q": "Neu?", "a": "x"}


def test_studio_equal_questions_do_not_duplicate_a_translation():
    """Прежний путь (`realign_list_overlays`, первое вхождение) дал бы обоим «Цена?»."""
    base = [{"q": "Preis?", "a": "1"}, {"q": "Preis?", "a": "2"}]
    ru = [{"q": "Цена?", "a": "1"}, {"q": "Цена 2?", "a": "2"}]
    tenant = _tenant(base, ru)
    cfg = _studio_save(
        tenant, {0: ("Preis?", "1"), 1: ("Preis?", "2")}, faq_content.fingerprint(base)
    )
    assert cfg["i18n"]["ru"]["faq"] == ru


def test_studio_from_a_stale_tab_matches_by_text():
    """Отпечаток не совпал (вопросы успели изменить) — номера полей ничего не значат."""
    tenant = _tenant()
    cfg = _studio_save(tenant, {0: BASE[2].values(), 1: BASE[0].values()}, "deadbeefdeadbeef")
    assert cfg["i18n"]["ru"]["faq"] == [RU[2], RU[0]]


def test_studio_translation_mode_does_not_call_put(monkeypatch):
    tenant = _tenant()
    monkeypatch.setattr(faq_content, "put", lambda *a, **k: pytest.fail("put в режиме перевода"))
    data = {"content_sections_present": "1", "faq_present": "1", "content_lang": "ru"}
    for i, f in enumerate(RU):
        data[f"faq_q_{i}"], data[f"faq_a_{i}"] = f["q"], f["a"]
    data["faq_a_1"] = "От 25 €."
    req = _req(tenant, "post", "/dashboard/site/home/", data)
    assert views.home_builder_view(req).status_code == 302
    cfg = siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)
    assert cfg["faq"] == BASE and cfg["i18n"]["ru"]["faq"][1]["a"] == "От 25 €."


def test_studio_renders_the_fingerprint_of_the_shown_list():
    tenant = _tenant()
    html = views.home_builder_view(_req(tenant, "get", "/dashboard/site/home/")).content.decode()
    assert f'name="faq_base" value="{faq_content.fingerprint(BASE)}"' in html


def test_live_preview_keeps_the_questions():
    tenant = _tenant()
    body = json.dumps({"cta_title": "Hallo", "hero_title": "X"})
    req = _req(tenant, "post", "/dashboard/site/preview/", body, content_type="application/json")
    req._body = body.encode()
    views.site_preview_draft(req)
    draft = Tenant.objects.get(pk=tenant.pk).site_config["_draft"]
    assert [f["q"] for f in draft["faq"]] == [f["q"] for f in BASE]


def _inline(tenant, field, value, locale=""):
    body = json.dumps({"field": field, "value": value, "locale": locale})
    req = _req(tenant, "post", "/x/", body, content_type="application/json")
    req._body = body.encode()
    return views.site_inline_edit(req)


def test_canvas_german_edit_drops_only_that_field():
    tenant = _tenant()
    assert _inline(tenant, "faq.1.a", "Ab 25 €.").status_code == 204
    cfg = Tenant.objects.get(pk=tenant.pk).site_config
    assert cfg["faq"][1]["a"] == "Ab 25 €."
    assert cfg["i18n"]["ru"]["faq"] == [RU[0], {"q": "Доставка?"}, RU[2]]


def test_canvas_translation_and_bad_index():
    tenant = _tenant()
    assert _inline(tenant, "faq.0.q", "Парковка есть?", locale="ru").status_code == 204
    cfg = Tenant.objects.get(pk=tenant.pk).site_config
    assert cfg["faq"] == BASE and cfg["i18n"]["ru"]["faq"][0]["q"] == "Парковка есть?"
    assert _inline(tenant, "faq.7.q", "x").status_code == 400
    assert _inline(tenant, "faq.0.q", "").status_code == 400
    assert _inline(tenant, "faq.0.z", "x").status_code == 400


#: пишут `site_config["faq"]` целиком сами (сборка конфига) — исключения замка
WRITER_ALLOWED = {
    "apps/core/faq_content.py",  # единственный писатель
    "apps/tenants/siteconfig.py",  # normalize и пути set_value/set_overlay_value
    "apps/tenants/demo_kits.py",  # демо-киты собирают конфиг целиком (~25508)
    "apps/tenants/demo_i18n.py",  # переводы демо (overlay_config)
    "apps/core/aufbau_draft.py",  # `draft["faq"]` — состояние черновика (запись — `put`)
    # FB-33 M2b-2b: свои вопросы ОБЪЕКТА (`details["faq"]` события/тура), не `site_config["faq"]`
    "apps/core/object_faq.py",
}
_WRITE = re.compile(
    r"""\[\s*["']faq["']\s*\]\s*=(?!=)|\(\s*["']faq["']\s*,\s*\w+\s*,\s*(?:parts\[|field|["'][qa]["'])"""
)


def test_one_writer_of_site_faq():
    root = Path(__file__).resolve().parents[3]
    found = sorted(
        str(p.relative_to(root))
        for p in (root / "apps").rglob("*.py")
        if "/tests/" not in str(p)
        and "/migrations/" not in str(p)
        and _WRITE.search(p.read_text(encoding="utf-8"))
    )
    assert set(found) <= WRITER_ALLOWED, set(found) - WRITER_ALLOWED
    views_src = (root / "apps/core/views.py").read_text(encoding="utf-8")
    assert "faq_content.put(" in views_src and "faq_content.set_text(" in views_src
