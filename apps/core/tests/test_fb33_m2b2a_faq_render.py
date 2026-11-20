"""FB-33 M2b-2a C3: блок FAQ на детальных — общие вопросы в своём виде, без FAQPage; пустой
FAQ на сайте не рисуется совсем (в превью — заглушка). Главная и прочие страницы — как были
(снимки `test_fb33_m2b2a_before`)."""

import pytest
from django.template import Context, Template
from django.test import RequestFactory

from apps.core.tests import test_fb31p5_detail_golden as _p5
from apps.core.tests.test_fb33_m2b2a_before import FAQ2, FAQ4, FAQPAGE, blocks_html, faq_block

pytestmark = pytest.mark.django_db
frozen_now = _p5.frozen_now
TEXT_HALF = {**_p5.TEXT, "width": "w12"}


@pytest.fixture(autouse=True)
def _urlconf(settings, frozen_now):
    settings.ROOT_URLCONF = "config.urls_tenant"


def ref_html(host, faq=FAQ4, style="", **extra):
    """Блок FAQ через render_block с хостом страницы `host` (без sample_wrapped — как на
    всех страницах, кроме главной)."""
    tpl = Template("{% load siteui %}{% render_block b %}")
    ctx = {"request": RequestFactory().get("/"), "site": {"faq": faq}, "b": faq_block(style)}
    ctx.update({"pb_page_key": host, **extra})
    return tpl.render(Context(ctx))


OWN_HOSTS = [f"{k}:{'a' * 32}" for k in ("product", "service", "stay", "event", "tour")]


@pytest.mark.parametrize(
    "host", ["catalog", "promo_detail", "combo_detail", "blog_post", "service_detail",
             "event_detail", "product_detail", "stay_detail", *OWN_HOSTS],
)  # fmt: skip
def test_faq_block_emits_no_faqpage_on_any_page(host):
    """Фактическое правило: FAQPage выводит только секция FAQ главной; блок faq_ref — нигде
    (условие `"faq" not in sample_wrapped` вне главной ложно — так было и до среза)."""
    cfg = {"faq": FAQ4, "page_blocks": {host: [faq_block()]}}
    html = blocks_html(host, cfg)
    assert "Kann ich vorbestellen?" in html and FAQPAGE not in html


@pytest.mark.parametrize("host", ["service_detail", *OWN_HOSTS])
def test_no_ld_is_an_insurance_on_details(host):
    """Страховка: появись `sample_wrapped` в контексте страницы (как на главной), детальная
    всё равно без FAQPage — его держит `no_ld`, а не только ложное условие."""
    assert FAQPAGE not in ref_html(host, sample_wrapped=set())
    assert ref_html("catalog", sample_wrapped=set()).count(FAQPAGE) == 1  # без страховки — был бы


@pytest.mark.parametrize("style", ["", "list", "twocol"])
def test_detail_views_differ_from_each_other_and_carry_their_own_title(style):
    detail, other = ref_html("service_detail", style=style), ref_html("catalog", style=style)
    assert "Allgemeine Fragen" in detail and "Allgemeine Fragen" not in other
    assert len({ref_html("service_detail", style=s) for s in ("", "list", "twocol")}) == 3


def test_saved_cards_on_a_detail_still_draw_cards():
    """W0: вид вне пунктов детальной рисуется как раньше (сохранён до среза)."""
    html = ref_html("service_detail", style="cards")
    assert "bg-gray-50 rounded-xl p-4" in html


def _page(kind, cfg):
    return _p5.RENDER[kind][0](cfg).content.decode()


@pytest.mark.parametrize("kind", ["service", "event", "product", "stay"])
def test_empty_faq_on_a_detail_draws_nothing(kind):
    host = _p5.RENDER[kind][1]
    html = _page(kind, {"page_blocks": {host: [faq_block()]}})
    assert 'data-sf-section="faq-1"' not in html  # ни обёртки блока
    assert f'data-pb-host="{host}"' not in html  # ни пустого хоста блоков
    if kind in ("service", "event"):  # второй объект товара/номера меняет slug и «Ähnliche»
        assert _p5._normalize(html) == _p5._normalize(_page(kind, {}))


@pytest.mark.parametrize("kind", ["service", "event"])
def test_empty_faq_leaves_no_hole_next_to_a_narrow_neighbour(kind):
    host = _p5.RENDER[kind][1]
    half_faq = {**faq_block(), "width": "w12"}
    html = _page(kind, {"page_blocks": {host: [TEXT_HALF, half_faq]}})
    alone = _page(kind, {"page_blocks": {host: [TEXT_HALF]}})
    assert _p5._normalize(html) == _p5._normalize(alone)
    assert "Gut zu wissen" in html


@pytest.mark.parametrize("kind", ["service", "event", "product", "stay"])
def test_faq_on_a_detail_draws_the_shared_questions(kind):
    host = _p5.RENDER[kind][1]
    html = _page(kind, {"faq": FAQ2, "page_blocks": {host: [faq_block("twocol")]}})
    assert "Kann ich vorbestellen?" in html and "md:grid-cols-2 gap-x-8" in html
    assert FAQPAGE not in html  # на всей странице
    assert "Allgemeine Fragen" in html


def test_faq_of_only_empty_pairs_counts_as_empty():
    from apps.tenants.templatetags.siteui import _drop_empty_faq

    blocks = [faq_block(), dict(_p5.TEXT)]
    empty = {"faq": [{"q": "", "a": ""}, {"q": None}]}
    assert _drop_empty_faq(blocks, "service_detail", empty) == [_p5.TEXT]
    assert _drop_empty_faq(blocks, "service_detail", {"faq": FAQ2}) == blocks
    assert _drop_empty_faq(blocks, "catalog", empty) == blocks  # прочие — как были


def test_own_faq_section_and_shared_block_have_different_titles():
    """Своё FAQ события (раздел) и общий блок — не два одинаковых «Häufige Fragen»."""
    host = _p5.RENDER["event"][1]
    html = _page("event", {"faq": FAQ2, "page_blocks": {host: [faq_block()]}})
    assert "Parkplatz?" in html and "Allgemeine Fragen" in html


def test_empty_faq_on_other_pages_is_unchanged():
    """Прочие страницы — как были: пустой блок оставляет свою обёртку (не детальная)."""
    html = blocks_html("catalog", {"page_blocks": {"catalog": [faq_block()]}})
    assert 'data-sf-section="faq-1"' in html


def test_preview_keeps_an_empty_detail_faq_as_a_placeholder():
    html = ref_html("service_detail", faq=[], is_preview=True)
    assert "data-faq-empty" in html and "Noch keine Fragen" in html
    assert ref_html("service_detail", faq=[]).strip() == ""
    assert "data-faq-empty" not in ref_html("catalog", faq=[], is_preview=True)


def test_preview_page_blocks_keep_the_empty_faq_block():
    req = _p5._req("/", {"page_blocks": {"service_detail": [faq_block()]}})
    tpl = Template("{% load siteui %}{% page_blocks 'service_detail' %}")
    live = tpl.render(Context({"request": req}))
    preview = tpl.render(Context({"request": req, "is_preview": True}))
    assert live.strip() == ""
    assert 'data-sf-section="faq-1"' in preview and "data-faq-empty" in preview
