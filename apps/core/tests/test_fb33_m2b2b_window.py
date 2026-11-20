"""FB-33 M2b-2b C4: окно блока FAQ на детальной — свои вопросы объекта (макет M0-12).

Замки: выбор источника «Fragen nur für <объект>» / «Allgemeine FAQ»; окно раздела «faq»
услуги — тот же редактор; правка — в черновик (`ofaq`, вне `_saved_state`), на сайт по
«Speichern» единственным писателем `object_faq.put` под блокировкой объекта; общий хост —
подсказка и ссылки; «Abbrechen» байт-в-байт; конфликт; право; блок убрали — не публикуем;
новый блок на детальной — свои вопросы; превью черновика.
"""

import copy

import pytest

from apps.core import aufbau_draft, faq_content, object_faq
from apps.core import object_structure as ost
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

OWN = [
    {"q": "Wie lange dauert Balayage?", "a": "2,5 bis 3,5 Stunden."},
    {"q": "Gewaschene Haare?", "a": "Nein."},
    {"q": "Nachfärben?", "a": "Ab 40 €."},
]
RU = [{"q": "Сколько?"}, {"q": "Мыть?"}, {"q": "Подкрасить?"}]
SHARED = [{"q": "Parkplatz?", "a": "Ja."}]
WOPEN = "openM2"


@pytest.fixture(autouse=True)
def _urlconf(settings, monkeypatch):
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.core import view_perms

    # владелец (у заглушки пользователя `Browser` членства нет); отказ — свой тест
    monkeypatch.setattr(view_perms, "allowed", lambda *a, **k: True)


def _setup(blocks=None, shared_blocks=None):
    from apps.booking.models import Service

    tenant = TenantFactory(business_type="salon", disabled_modules=[], enabled_locales=["de", "ru"])
    svc = Service.objects.create(
        name="Balayage", duration_minutes=150, is_active=True, faq=OWN, faq_i18n={"ru": RU}
    )
    host = ost.object_host("service", svc)
    page_blocks = {}
    if blocks is not None:
        page_blocks[host] = blocks
    if shared_blocks is not None:
        page_blocks["service_detail"] = shared_blocks
    tenant.site_config = siteconfig.normalize({"faq": SHARED, "page_blocks": page_blocks})
    tenant.save()
    return tenant, svc, ost.schema_code("service", svc)


def own_block(bid="faqown01"):
    return {"key": "faq_ref", "id": bid, "enabled": True, "data": {"source": "object"}}


def _drafts(b):
    return copy.deepcopy((b.session or {}).get(aufbau_draft.SESSION_KEY) or {})


def _svc(svc):
    svc.refresh_from_db()
    return svc


def _post(b, code, svc, ref="faqown01", items=None, src=None, **extra):
    draft = _drafts(b).get(code)
    if items is None:
        items, src = object_faq.state(_svc(svc), "service", draft)
    data = {
        "seite": code,
        "ref": ref,
        "op": "update",
        "faq_present": "1",
        "faq_scope": "object",
        "wopen": WOPEN,
        "faq_rev": faq_content.revision(items, src),
        "faq_base": object_faq.fingerprint(_svc(svc), "service"),
    }
    for i, it in enumerate(items):
        data[f"faq_{i}_q"], data[f"faq_{i}_a"] = it["q"], it["a"]
    data.update(extra)
    return b.post(**data)


def _shared(b):
    return siteconfig.normalize(Tenant.objects.get(pk=b.tenant.pk).site_config)["faq"]


def test_window_of_the_own_block_shows_source_choice_and_own_questions():
    tenant, svc, code = _setup([own_block()])
    html = Browser(tenant).get(f"?seite={code}&block=faqown01&tab=texte")
    assert "Fragen nur für Balayage" in html and "eigene Liste dieser Leistung" in html
    assert "Allgemeine FAQ" in html and "dieselben Fragen wie auf „FAQ“" in html
    assert 'name="faq_scope" value="object"' in html
    assert 'value="Wie lange dauert Balayage?"' in html and 'value="Parkplatz?"' not in html


def test_edit_goes_to_the_draft_and_save_writes_the_object():
    tenant, svc, code = _setup([own_block()])
    b = Browser(tenant)
    _post(b, code, svc, faq_move="0:down")
    assert _svc(svc).faq == OWN  # на сайте ничего
    draft = _drafts(b)[code]
    assert draft["ofaq"]["src"] == [1, 0, 2] and "faq" not in draft
    assert (
        aufbau_draft.info(b._request("get"), siteconfig.normalize(tenant.site_config), code)[
            "count"
        ]
        == 1
    )
    _resp, msgs = b.post(seite=code, op="save")
    assert "Gespeichert." in msgs
    svc = _svc(svc)
    assert [f["q"] for f in svc.faq] == [OWN[1]["q"], OWN[0]["q"], OWN[2]["q"]]
    assert svc.faq_i18n == {"ru": [RU[1], RU[0], RU[2]]}
    assert _shared(b) == SHARED and code not in _drafts(b)


def test_section_faq_row_opens_the_same_editor():
    tenant, svc, code = _setup([])
    b = Browser(tenant)
    html = b.get(f"?seite={code}&block=faq&tab=texte")
    assert 'value="Wie lange dauert Balayage?"' in html and "data-faq-source" not in html
    _post(b, code, svc, ref="faq", faq_remove="2")
    b.post(seite=code, op="save")
    assert [f["q"] for f in _svc(svc).faq] == [OWN[0]["q"], OWN[1]["q"]]


def test_shared_host_shows_hint_and_links_only():
    tenant, svc, _code = _setup(shared_blocks=[own_block()])
    html = Browser(tenant).get("?seite=service&block=faqown01&tab=texte")
    assert "Jede Leistung zeigt ihre eigenen Fragen." in html
    assert f"/dashboard/booking/services/{svc.pk}/" in html or "data-faq-links" in html
    assert 'name="faq_0_q"' not in html
    assert "Eigene Fragen jeder Seite" in html


def test_switch_source_and_back():
    tenant, svc, code = _setup([own_block()])
    b = Browser(tenant)
    _post(b, code, svc, faq_source="shared")
    row = next(r for r in _drafts(b)[code]["items"] if r.get("id") == "faqown01")
    assert "source" not in (row.get("data") or {})
    html = b.get(f"?seite={code}&block=faqown01&tab=texte")
    assert 'value="Parkplatz?"' in html  # теперь правятся общие вопросы
    b.post(seite=code, op="save")
    blocks = siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)["page_blocks"]
    assert blocks[ost.object_host("service", svc)][0]["data"] == {}
    assert _svc(svc).faq == OWN


def test_cancel_returns_the_draft_byte_for_byte():
    tenant, svc, code = _setup([own_block()])
    b = Browser(tenant)
    before = _drafts(b).get(code)
    _post(b, code, svc, faq_remove="0")
    _post(b, code, svc, faq_source="shared")
    b.post(seite=code, op="revert", ref="faqown01", wopen=WOPEN)
    after = _drafts(b).get(code)
    assert (after or None) is None or after.get(aufbau_draft.IDLE_KEY)
    assert before is None and _svc(svc).faq == OWN


def test_conflict_when_the_object_changed_meanwhile():
    tenant, svc, code = _setup([own_block()])
    b = Browser(tenant)
    _post(b, code, svc, faq_remove="0")
    svc.faq = [{"q": "Anders?", "a": ""}]
    svc.save(update_fields=["faq"])
    _resp, msgs = b.post(seite=code, op="save")
    assert object_faq.error_note("ofaq_conflict") in msgs
    assert _svc(svc).faq == [{"q": "Anders?", "a": ""}] and code in _drafts(b)


def test_without_rights_no_edit(monkeypatch):
    from apps.core import view_perms

    tenant, svc, code = _setup([own_block()])
    monkeypatch.setattr(view_perms, "allowed", lambda *a, **k: False)
    _resp, msgs = _post(Browser(tenant), code, svc, faq_remove="0")
    assert object_faq.error_note("ofaq_rights") in msgs


def test_removed_block_keeps_questions_while_the_section_shows_them():
    """У услуги свои вопросы показывает и раздел «faq» — правка публикуется."""
    tenant, svc, code = _setup([own_block()])
    b = Browser(tenant)
    _post(b, code, svc, faq_remove="0")
    b.post(seite=code, op="delete", ref="faqown01")
    _resp, msgs = b.post(seite=code, op="save")
    assert object_faq.dropped_note() not in msgs and len(_svc(svc).faq) == 2


def test_removed_block_does_not_publish_the_questions_of_a_product():
    from apps.catalog.tests.factories import ProductFactory

    tenant, _svc_obj, _code = _setup()
    p = ProductFactory(name={"de": "Brot"}, faq=OWN)
    host, code = ost.object_host("product", p), ost.schema_code("product", p)
    cfg = copy.deepcopy(tenant.site_config)
    cfg["page_blocks"] = {host: [own_block()]}
    tenant.site_config = siteconfig.normalize(cfg)
    tenant.save()
    b = Browser(tenant)
    items, src = object_faq.state(p, "product")
    data = {
        "seite": code, "ref": "faqown01", "op": "update", "faq_present": "1", "wopen": WOPEN,
        "faq_rev": faq_content.revision(items, src), "faq_remove": "0",
        "faq_base": object_faq.fingerprint(p, "product"),
    }  # fmt: skip
    for i, it in enumerate(items):
        data[f"faq_{i}_q"], data[f"faq_{i}_a"] = it["q"], it["a"]
    b.post(**data)
    assert _drafts(b)[code]["ofaq"]["items"] == OWN[1:]
    b.post(seite=code, op="delete", ref="faqown01")
    _resp, msgs = b.post(seite=code, op="save")
    p.refresh_from_db()
    assert object_faq.dropped_note() in msgs and p.faq == OWN


def test_new_block_on_a_detail_shows_own_questions():
    tenant, _svc_obj, code = _setup([])
    b = Browser(tenant)
    b.post(seite=code, op="add", type="faq_ref")
    row = next(r for r in _drafts(b)[code]["items"] if r.get("key") == "faq_ref")
    assert row["data"] == {"source": "object"}
    b.post(seite="text", op="add", type="faq_ref")  # не детальная — общий FAQ, как был
    row = next(r for r in _drafts(b)["text"]["items"] if r.get("key") == "faq_ref")
    assert "source" not in (row.get("data") or {})


def test_preview_carries_the_draft_questions():
    tenant, svc, code = _setup([own_block()])
    b = Browser(tenant)
    _post(b, code, svc, faq_move="0:down")
    shown = aufbau_draft.overlay(siteconfig.normalize(tenant.site_config), _drafts(b)[code])
    entry = shown[object_faq.DRAFT_KEY][svc.pk.hex]
    assert entry["items"][0] == OWN[1] and entry["i18n"]["ru"][0] == RU[1]
    assert object_faq.localized(svc, "service", "de", shown)[0] == OWN[1]


def test_double_display_hint():
    tenant, svc, code = _setup([own_block()])
    html = Browser(tenant).get(f"?seite={code}&block=faqown01&tab=texte")
    assert "data-faq-double" in html  # раздел «faq» услуги виден по умолчанию


def test_side_parts_row_matches_the_module():
    assert dict(aufbau_draft.SIDE_PARTS)["ofaq"] == object_faq.DRAFT_KEYS


def test_object_limits_in_the_window():
    """У события — до 30 вопросов (у общих — 12)."""
    rows = [{"q": f"F{i}?", "a": ""} for i in range(20)]
    items, _src = faq_content.apply_ops(
        rows,
        list(range(20)),
        {},
        None,
        None,
        clean=lambda r, n: object_faq.clean_input(r, "event", n),
    )
    assert len(items) == 20
    assert len(faq_content.apply_ops(rows, list(range(20)), {})[0]) == 12
