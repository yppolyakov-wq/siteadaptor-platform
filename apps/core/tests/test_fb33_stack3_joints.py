"""FB-33 стопка 3: стыки срезов M2b-2b (свои вопросы FAQ объекта) и M3-6 («Seite» окном, SEO
страницы, «Wo zeigen» баннера, закреплённые 🔒) в одном черновике «Seitenaufbau».

Замки: (a) черновик детальной страницы со своими вопросами и местами баннера — «Speichern»
пишет обе части, «Abbrechen» окна откатывает только своё; текстовая страница — общие вопросы,
SEO и места вместе; (b) у окна одна применяющая часть на вкладку (FAQ и SEO — разные строки),
вкладки без скриптов — кнопки формы FAQ; (c) строки FAQ не закреплены, 🔒 — только у pinned.
"""

import copy
import re

import pytest

from apps.core import aufbau_draft, block_window, faq_content, object_faq
from apps.core import object_structure as ost
from apps.core.models import Banner
from apps.core.tests.test_fb27_r2_draft import Browser, _tenant
from apps.core.tests.test_fb33_m3_window_before import _panel
from apps.tenants import siteconfig
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db

OWN = [
    {"q": "Wie lange hält das Brot?", "a": "Drei Tage."},
    {"q": "Ohne Hefe?", "a": "Ja."},
]
SHARED = [{"q": "Parkplatz?", "a": "Ja."}]
WOPEN_FAQ = "stackFaq"
WOPEN_BN = "stackBn"


@pytest.fixture(autouse=True)
def _perms(monkeypatch):
    from apps.core import view_perms

    monkeypatch.setattr(view_perms, "allowed", lambda *a, **k: True)


def _cat(slug="brot"):
    from apps.catalog.models import Category

    return Category.objects.create(name={"de": slug.title()}, slug=slug, is_active=True)


def _drafts(b):
    return copy.deepcopy((b.session or {}).get(aufbau_draft.SESSION_KEY) or {})


def _detail():
    """Товар со своими вопросами, на его странице — блок FAQ (свои вопросы) и баннер."""
    from apps.catalog.tests.factories import ProductFactory

    tenant = _tenant()
    product = ProductFactory(name={"de": "Brot"}, faq=copy.deepcopy(OWN))
    banner = Banner.objects.create(title="Herbst")
    host = ost.object_host("product", product)
    blocks = [
        {"key": "faq_ref", "id": "faqown01", "enabled": True, "data": {"source": "object"}},
        {"key": "banner", "id": "bn1", "enabled": True, "data": {"pick": [str(banner.pk)]}},
    ]
    tenant.site_config = siteconfig.normalize({"faq": SHARED, "page_blocks": {host: blocks}})
    tenant.save()
    return tenant, product, banner, ost.schema_code("product", product)


def _faq_post(b, code, product, **extra):
    draft = _drafts(b).get(code)
    product.refresh_from_db()
    items, src = object_faq.state(product, "product", draft)
    data = {
        "seite": code,
        "ref": "faqown01",
        "op": "update",
        "faq_present": "1",
        "faq_scope": "object",
        "wopen": WOPEN_FAQ,
        "faq_rev": faq_content.revision(items, src),
        "faq_base": object_faq.fingerprint(product, "product"),
    }
    for i, it in enumerate(items):
        data[f"faq_{i}_q"], data[f"faq_{i}_a"] = it["q"], it["a"]
    data.update(extra)
    return b.post(**data)


def _place_post(b, code, value="add", **extra):
    return b.post(seite=code, op="places", ref="bn1", value=value, wopen=WOPEN_BN, **extra)


# ───────────── (a) свои вопросы + «Wo zeigen» в одном черновике ─────────────


def test_detail_draft_with_own_faq_and_places_saves_both():
    tenant, product, banner, code = _detail()
    _cat("brot")
    b = Browser(tenant)
    _faq_post(b, code, product, faq_move="0:down")
    _resp, msgs = _place_post(b, code, wo_add="category:brot")
    assert not [m for m in msgs if "nicht" in m], msgs
    draft = _drafts(b)[code]
    assert draft["ofaq"]["src"] == [1, 0]
    assert draft["show_on"] == {str(banner.pk): ["category:brot"]}
    assert "Änderungen: 2" in b.get(f"?seite={code}")
    product.refresh_from_db()
    banner.refresh_from_db()
    assert product.faq == OWN and banner.show_on == [], "до «Speichern» на сайте ничего"
    _resp, msgs = b.post(seite=code, op="save")
    assert msgs == ["Gespeichert."]
    product.refresh_from_db()
    banner.refresh_from_db()
    assert [f["q"] for f in product.faq] == [OWN[1]["q"], OWN[0]["q"]]
    assert banner.show_on == ["category:brot"]
    assert code not in _drafts(b)


def test_abbrechen_of_one_window_keeps_the_other_part():
    tenant, product, banner, code = _detail()
    _cat("brot")
    b = Browser(tenant)
    b.get(f"?seite={code}&block=faqown01&tab=texte&wopen={WOPEN_FAQ}")
    _faq_post(b, code, product, faq_remove="0")
    b.get(f"?seite={code}&block=bn1&wopen={WOPEN_BN}")
    _place_post(b, code, wo_add="category:brot")
    # «Abbrechen» окна FAQ — места баннера остаются
    _resp, msgs = b.post(seite=code, op="revert", ref="faqown01", wopen=WOPEN_FAQ)
    draft = _drafts(b)[code]
    assert "ofaq" not in draft and "ofaq_base" not in draft
    assert draft["show_on"] == {str(banner.pk): ["category:brot"]}
    # снова правка вопросов, затем «Abbrechen» окна баннера — вопросы остаются
    _faq_post(b, code, product, faq_remove="0")
    b.post(seite=code, op="revert", ref="bn1", wopen=WOPEN_BN)
    draft = _drafts(b)[code]
    assert "show_on" not in draft and "show_on_base" not in draft
    assert draft["ofaq"]["items"] == OWN[1:]
    b.post(seite=code, op="save")
    product.refresh_from_db()
    banner.refresh_from_db()
    assert product.faq == OWN[1:] and banner.show_on == []


def test_text_page_draft_with_shared_faq_seo_and_places_saves_all():
    tenant = _tenant()
    banner = Banner.objects.create(title="Herbst")
    _cat("brot")
    blocks = [
        {"key": "faq_ref", "id": "faq1", "enabled": True, "data": {}},
        {"key": "banner", "id": "bn1", "enabled": True, "data": {"pick": [str(banner.pk)]}},
    ]
    tenant.site_config = siteconfig.normalize({"faq": SHARED, "page_blocks": {"info": blocks}})
    tenant.save()
    b = Browser(tenant)
    b.post(seite="text", op="update", ref="__page", panel_present="1", f_seo_title="Über uns")
    b.post(
        seite="text",
        ref="faq1",
        op="update",
        faq_present="1",
        faq_rev=faq_content.revision(SHARED, [0]),
        faq_0_q="Parkplatz?",
        faq_0_a="Ja, im Hof.",
    )
    _place_post(b, "text", wo_add="category:brot")
    draft = _drafts(b)["text"]
    assert {"seo", "faq", "show_on"} <= set(draft)
    _resp, msgs = b.post(seite="text", op="save")
    assert msgs == ["Gespeichert."]
    cfg = siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)
    assert cfg["seo"]["pages"]["info"]["title"] == "Über uns"
    assert cfg["faq"][0]["a"] == "Ja, im Hof."
    banner.refresh_from_db()
    assert banner.show_on == ["category:brot"]


# ───────────── (b) одна применяющая часть на вкладку ─────────────


def test_detail_faq_window_has_one_apply_part_and_tab_buttons():
    tenant, _product, _banner, code = _detail()
    html = _panel(Browser(tenant).get(f"?seite={code}&block=faqown01&tab=texte"))
    assert 'id="bw-form-faq"' in html and 'id="bw-form-seo"' not in html
    # без скриптов вкладки — кнопки формы FAQ (набранное применяется при переходе)
    assert re.search(r'<button[^>]*form="bw-form-faq"[^>]*name="zu_tab"', html) or re.search(
        r'<button[^>]*name="zu_tab"[^>]*form="bw-form-faq"', html
    )


def test_page_row_on_detail_has_no_seo_part_and_no_faq_part():
    tenant, _product, _banner, code = _detail()
    html = _panel(Browser(tenant).get(f"?seite={code}&block=__page&tab=texte"))
    assert 'id="bw-form-seo"' not in html and 'id="bw-form-faq"' not in html


def test_apply_form_counts_one_part_per_tab():
    window = [
        {"key": "texte", "active": True, "parts": ["faq", "pinned"]},
        {"key": "seite", "active": False, "parts": ["settings"]},
    ]
    assert block_window.apply_form(window)["part"] == "faq"
    both = [{**window[0], "parts": ["faq", "seo"]}, window[1]]
    assert block_window.apply_form(both) is None, "две части — вкладки остаются ссылками"


# ───────────── (c) 🔒 и строки своих вопросов ─────────────


def test_faq_rows_are_not_pinned_and_carry_no_lock():
    tenant, _product, _banner, code = _detail()
    b = Browser(tenant)
    page = b.get(f"?seite={code}")
    m = re.search(r'<li class="min-w-0"[^>]*data-schema-(drag|pinned)="faqown01"', page)
    assert m and m.group(1) == "drag", "строка своих вопросов перетаскивается, без 🔒"
    kauf = re.search(r'<li class="min-w-0"[^>]*data-schema-(drag|pinned)="__kauf"', page)
    assert kauf and kauf.group(1) == "pinned", "«Kaufen» на той же странице — закреплена"
    html = _panel(b.get(f"?seite={code}&block=faqown01&tab=texte"))
    assert "data-schema-lock" not in html
