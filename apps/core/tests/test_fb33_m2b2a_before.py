"""FB-33 M2b-2a-0: характеризация FAQ ДО среза «FAQ на детальных: общие вопросы, вид».

Снимки сняты до кода M2b-2a:
- главная: секция FAQ в пяти видах × 2/4 вопроса (с FAQPage) — после среза байт-в-байт;
- прочая страница (каталог кейтеринга) с блоком FAQ — байт-в-байт;
- детальная (услуга, событие) с блоком FAQ — байт-в-байт (без ld+json FAQPage).
Находка разведки: FAQPage стоит под `"faq" not in sample_wrapped`, а `sample_wrapped` кладёт
только главная — вне её условие ложно, и блок FAQ страниц/детальных FAQPage не выводил и до
среза. Срез закрепляет это явно для детальных (`faq_views.emits_ld`).
Детальные без FAQ держит `test_fb31p5_detail_golden` (байт-в-байт).

Обновить (осознанно): FB33M2B2A_GOLDEN=update uv run pytest <этот файл>
"""

import os
from pathlib import Path

import pytest
from django.template import Context, Template
from django.test import RequestFactory

from apps.core.tests import test_fb31p5_detail_golden as _p5

pytestmark = pytest.mark.django_db
GOLDEN = Path(__file__).parent / "golden_fb33m2b2a"
UPDATE = os.environ.get("FB33M2B2A_GOLDEN") == "update"
FAQ4 = [
    {"q": "Wann haben Sie offen?", "a": "Mo–Fr 8–18 Uhr."},
    {"q": "Kann ich vorbestellen?", "a": "Ja, bis 18 Uhr für den nächsten Tag."},
    {"q": "Liefern Sie auch?", "a": "Im Umkreis von 5 km."},
    {"q": "Gibt es Parkplätze?", "a": "Direkt vor dem Haus."},
]
FAQ2 = FAQ4[:2]
STYLES = ("", "list", "twocol", "cards", "numbered")
FAQPAGE = '"@type":"FAQPage"'

frozen_now = _p5.frozen_now


@pytest.fixture(autouse=True)
def _urlconf(settings, frozen_now):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _check(name, got):
    path = GOLDEN / f"{name}.html"
    if UPDATE or not path.exists():
        if not UPDATE:
            pytest.fail(f"нет снимка {path.name}: FB33M2B2A_GOLDEN=update")
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(got)
        return
    assert got == path.read_text(), f"FAQ изменился: {path.name}"


def home_faq_html(style, faq):
    req = RequestFactory().get("/")
    row = {"key": "faq", **({"style": style} if style else {})}
    tpl = Template("{% load siteui %}{% render_block b %}")
    ctx = {"request": req, "site": {"faq": faq}, "b": row, "sample_wrapped": set()}
    return tpl.render(Context(ctx))  # главная кладёт sample_wrapped (промо-витрина)


def blocks_html(host, cfg, business_type="cafe"):
    req = _p5._req("/", cfg)
    req.tenant.business_type = business_type
    tpl = Template("{% load siteui %}{% page_blocks host %}")
    return tpl.render(Context({"request": req, "host": host}))


def faq_block(style="", bid="faq-1"):
    return {"key": "faq_ref", "id": bid, "data": {"style": style} if style else {}}


def detail_html(kind, faq, style=""):
    host = _p5.RENDER[kind][1]
    cfg = {"faq": faq, "page_blocks": {host: [faq_block(style)]}}
    return _p5._normalize(_p5.RENDER[kind][0](cfg).content.decode())


@pytest.mark.parametrize("n", [2, 4])
@pytest.mark.parametrize("style", STYLES)
def test_home_faq_looks_as_before(style, n):
    html = home_faq_html(style, FAQ4[:n])
    assert html.count(FAQPAGE) == 1
    _check(f"home-{style or 'akkordeon'}-{n}", html)


@pytest.mark.parametrize("style", ["", "cards"])
def test_catering_page_faq_block_looks_as_before(style):
    cfg = {"faq": FAQ4, "page_blocks": {"catalog": [faq_block(style)]}}
    html = blocks_html("catalog", cfg, business_type="catering")
    assert html.count(FAQPAGE) == 0  # как до среза: sample_wrapped вне главной нет
    _check(f"catering-{style or 'akkordeon'}", html)


@pytest.mark.parametrize("style", ["", "list", "twocol"])
@pytest.mark.parametrize("kind", ["service", "event"])
def test_detail_faq_block_looks_as_before(kind, style):
    html = detail_html(kind, FAQ2, style)
    assert FAQPAGE not in html and "Kann ich vorbestellen?" in html
    _check(f"{kind}-{style or 'akkordeon'}", html)
