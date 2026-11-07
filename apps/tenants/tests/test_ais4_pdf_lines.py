"""AIS-4: PDF Speisekarte/Preisliste → строки шага «Angebot prüfen» (план
docs/ais-4-pdf-lines-plan-2026-11-07.md).

Замки: извлечение текста с лимитами (скан, шифр, страницы, мусор — код, не 500); правила
берут цену из хвоста строки и отбрасывают заголовки/контакты; путь работает БЕЗ ИИ; в
веб-воркере PDF не разбирается (только размер и сигнатура); фото и PDF вместе — отказ;
байты уходят из кэша; в базу ничего до «Übernehmen»; фото-путь прежний.
"""

import io
from types import SimpleNamespace
from unittest import mock

import pypdf
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from apps.catalog.models import Product
from apps.core import offer_batch, offer_pdf, offer_photo, tasks
from apps.tenants.tests.test_wizard_v4_photo import _jpeg
from apps.tenants.tests.test_wizard_v4_pruefen import Owner, _confirm_data, _v4

pytestmark = pytest.mark.django_db

MENU = [
    "Bäckerei Krume — Preisliste",
    "Hauptstraße 1, Tel. 02103 123456",
    "Brot",
    "Roggenbrot ........ 3,50 €",
    "Dinkelbrot 4,20",
    "Butterbrezel € 1,20",
    "Öffnungszeiten Mo–Fr 7–18",
]


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings, isolated_ratelimit):
    settings.ROOT_URLCONF = "config.urls_tenant"
    settings.AI_ENABLED = False


def _pdf(lines=MENU, pages=1) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for _ in range(pages):
        y = 800
        for line in lines:
            c.drawString(60, y, line)
            y -= 20
        c.showPage()
    c.save()
    return buf.getvalue()


def _blank_pdf() -> bytes:
    w = pypdf.PdfWriter()
    w.add_blank_page(width=595, height=842)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def _upload(data: bytes, name="karte.pdf"):
    return SimpleUploadedFile(name, data, content_type="application/pdf")


# --- извлечение и правила ----------------------------------------------------------


def test_extract_text_layer_returns_lines():
    text, code = offer_pdf.extract_text(_pdf())
    assert code == "" and "Roggenbrot" in text


def test_scanned_pdf_without_text_returns_no_text():
    assert offer_pdf.extract_text(_blank_pdf()) == ("", "no_text")


def test_encrypted_pdf_rejected():
    reader = pypdf.PdfReader(io.BytesIO(_pdf()))
    w = pypdf.PdfWriter()
    for page in reader.pages:
        w.add_page(page)
    w.encrypt("geheim")
    buf = io.BytesIO()
    w.write(buf)
    assert offer_pdf.extract_text(buf.getvalue())[1] == "encrypted"


def test_more_than_10_pages_rejected():
    assert offer_pdf.extract_text(_pdf(pages=11))[1] == "too_many_pages"


def test_garbage_bytes_with_pdf_magic_is_an_error_code_not_500():
    assert offer_pdf.extract_text(b"%PDF-1.7\n garbage \x00\x01")[1] in ("pdf_broken", "no_text")


def test_rule_lines_take_tail_price_and_drop_headings_and_contacts():
    text, _ = offer_pdf.extract_text(_pdf())
    lines = offer_pdf.rule_lines(text, "waren")
    names = [x.split(" — ")[0] for x in lines]
    assert names == ["Roggenbrot", "Dinkelbrot", "Butterbrezel"]
    assert "Roggenbrot — 3,50 €" in lines and "Butterbrezel — € 1,20" in lines


def test_rule_lines_termine_duration():
    lines = offer_pdf.rule_lines("Herrenhaarschnitt 30 Min 25 €\nFärben 60,00", "termine")
    assert lines[0] == "Herrenhaarschnitt — 30 Min — 25 €"
    assert lines[1] == "Färben — 60,00"


# --- шаг мастера --------------------------------------------------------------------


def _inline():
    return mock.patch.object(
        tasks.offer_photo_lines, "delay", side_effect=lambda **kw: tasks.offer_photo_lines(**kw)
    )


def _scan(owner, files, kind="waren"):
    return owner(
        "post", {"action": "offer_scan", "kind": kind, "offer_text": "", "menu_photo": files}
    )


def test_rules_path_works_with_ai_disabled_nothing_created_until_confirm():
    owner = Owner(_v4())
    with _inline():
        _scan(owner, [_upload(_pdf())])
    owner("post", {"action": "offer_scan_apply"})
    draft = owner.session[offer_batch.SESSION_KEY]
    assert draft["source"] == "pdf" and "Roggenbrot — 3,50 €" in draft["text"]
    assert Product.objects.count() == 0
    html = owner().content.decode()
    assert "data-pruefen-from-pdf" in html
    rows = [{"on": "1", "name": "Roggenbrot", "price": "3,50"}]
    owner("post", _confirm_data(owner, rows))
    assert list(Product.objects.values_list("name__de", flat=True)) == ["Roggenbrot"]


def test_pdf_bytes_removed_from_cache_after_job():
    from django.core.cache import cache

    owner = Owner(_v4())
    with _inline():
        _scan(owner, [_upload(_pdf())])
    job = owner.session[offer_photo.SESSION_KEY]["job"]
    entry = cache.get(offer_photo._job_key(offer_photo._schema(), owner.user.pk, job))
    assert "pdf" not in entry and entry["state"] == "done"


def test_non_pdf_magic_rejected_in_web_worker_without_job():
    owner = Owner(_v4())
    with mock.patch.object(tasks.offer_photo_lines, "delay") as delay:
        _scan(owner, [_upload(b"MZ not a pdf")])
    assert delay.call_count == 0
    assert any("nicht gelesen" in m for m in owner.messages)


def test_oversize_upload_rejected_before_read():
    owner = Owner(_v4())
    big = _upload(b"%PDF-" + b"0" * offer_pdf.MAX_BYTES)
    with mock.patch.object(tasks.offer_photo_lines, "delay") as delay:
        _scan(owner, [big])
    assert delay.call_count == 0 and any("5 MB" in m for m in owner.messages)


def test_mixed_photo_and_pdf_rejected():
    owner = Owner(_v4())
    with mock.patch.object(tasks.offer_photo_lines, "delay") as delay:
        _scan(owner, [_upload(_pdf()), _jpeg()])
    assert delay.call_count == 0 and any("Entweder" in m for m in owner.messages)


def test_scanned_pdf_gives_honest_message():
    owner = Owner(_v4())
    with _inline():
        _scan(owner, [_upload(_blank_pdf())])
    owner("post", {"action": "offer_scan_apply"})
    assert any("eingescannt" in m for m in owner.messages)
    assert offer_batch.SESSION_KEY not in owner.session


def test_photo_without_ai_still_refused():
    owner = Owner(_v4())
    with mock.patch.object(tasks.offer_photo_lines, "delay") as delay:
        _scan(owner, [_jpeg()])
    assert delay.call_count == 0
    assert any("nicht verfügbar" in m for m in owner.messages)


# --- ИИ поверх правил: дословная проверка по тексту ---------------------------------

TEXT = "Brot\nRoggenbrot ........ 3,50 €\nDinkelbrot 4,20\nKontakt 02103 123456"


def _gen(data):
    return mock.patch.object(offer_pdf, "generate", return_value=SimpleNamespace(data=data))


@pytest.fixture
def pdf_ai_on(settings):
    settings.AI_ENABLED = True
    settings.AI_REQUIRE_EU = False
    settings.AI_ROUTE_FAST = ["fake"]
    settings.AI_TASKS_ENABLED = [*settings.AI_TASKS_ENABLED, offer_pdf.TASK]
    return settings


def test_ai_invented_name_dropped_and_invented_price_becomes_question_mark():
    data = {
        "is_price_list": True,
        "items": [
            {"name": "Roggenbrot", "price_text": "3,50 €"},
            {"name": "Dinkelbrot", "price_text": "9,99 €"},  # цены нет в тексте
            {"name": "Kaviar", "price_text": "3,50 €"},  # имени нет в тексте
        ],
    }
    assert offer_pdf.verify_lines(data, TEXT, "waren") == [
        "Roggenbrot — 3,50 €",
        "Dinkelbrot — ?",
    ]


def test_ai_not_price_list_gives_nothing():
    assert offer_pdf.verify_lines({"is_price_list": False, "items": []}, TEXT, "waren") == []


def test_read_pdf_uses_ai_when_enabled(pdf_ai_on):
    data = {"is_price_list": True, "items": [{"name": "Butterbrezel", "price_text": "€ 1,20"}]}
    with _gen(data) as gen:
        lines, code = offer_pdf.read_pdf(_pdf(), "waren")
    assert gen.call_count == 1 and code == ""
    assert lines == ["Butterbrezel — € 1,20"]
    prompt = gen.call_args.args[1]
    assert "Roggenbrot" in prompt and "images" not in gen.call_args.kwargs


def test_ai_error_or_empty_falls_back_to_rules(pdf_ai_on):
    from apps.ai.errors import AIError

    with mock.patch.object(offer_pdf, "generate", side_effect=AIError("down")):
        lines, code = offer_pdf.read_pdf(_pdf(), "waren")
    assert code == "" and "Roggenbrot — 3,50 €" in lines
    with _gen({"is_price_list": True, "items": [{"name": "Erfunden", "price_text": "1 €"}]}):
        lines, _ = offer_pdf.read_pdf(_pdf(), "waren")
    assert "Roggenbrot — 3,50 €" in lines


def test_ai_disabled_does_not_call_model():
    with mock.patch.object(offer_pdf, "generate") as gen:
        offer_pdf.read_pdf(_pdf(), "waren")
    assert gen.call_count == 0
