"""I18N-7b: документы (PDF) печатаются на языке поверхности/`?lang=`.

Текст из PDF не парсим (reportlab пишет сжатые потоки) — проверяем то, что
реально определяет содержимое: резолвер языка, форматы и то, что генератор под
разными локалями даёт РАЗНЫЕ байты (иначе перевод не доехал бы до холста).
"""

import pytest
from django.test import RequestFactory
from django.utils import translation

from apps.core import documents
from apps.tenants.tests.factories import TenantFactory


def _req(query=""):
    return RequestFactory().get(f"/x/{query}")


def test_allowed_languages_are_tenant_locales_plus_cabinet():
    tenant = TenantFactory.build(enabled_locales=["de", "tr"])
    codes = documents.allowed_languages(tenant)
    assert codes[:2] == ["de", "tr"]  # локали витрины первыми, в порядке тенанта
    assert "en" in codes  # язык кабинета доступен владельцу всегда


def test_explicit_lang_wins_and_garbage_is_ignored():
    tenant = TenantFactory.build(enabled_locales=["de", "tr"])
    assert documents.document_language(_req("?lang=tr"), tenant=tenant) == "tr"
    # чужая/мусорная локаль → активный язык поверхности
    with translation.override("en"):
        assert documents.document_language(_req("?lang=zz"), tenant=tenant) == "en"


def test_active_language_is_used_without_param():
    tenant = TenantFactory.build(enabled_locales=["de", "ru"])
    with translation.override("ru"):
        # кириллица требует TTF; в окружении с DejaVu — ru, без него — латиница
        lang = documents.document_language(_req(), tenant=tenant)
    assert lang == ("ru" if documents.unicode_fonts_available() else "en")


@pytest.mark.parametrize("lang", ["ru", "uk", "tr"])
def test_non_latin_falls_back_when_no_unicode_font(monkeypatch, lang):
    """Ловушка №1 плана: без юникод-шрифта текст выйдет рваным. Кириллица
    очевидна; турецкий тоже — стенд показал, что WinAnsi не знает ı и «Açıklama»
    рассыпается на «A ç n klama». Честнее отдать документ латиницей."""
    monkeypatch.setattr(documents, "unicode_fonts_available", lambda: False)
    tenant = TenantFactory.build(enabled_locales=["de", "ru", "uk", "tr", "en"])
    assert documents.document_language(_req(f"?lang={lang}"), tenant=tenant) == "en"


def test_money_and_date_follow_locale():
    with translation.override("de"):
        assert documents.money("1234.5") == "1234,50 EUR"
        assert documents.qty("3.50") == "3,5"
    with translation.override("en"):
        assert documents.money("1234.5") == "1234.50 EUR"
        assert documents.qty("3.50") == "3.5"


def pdf_text(data: bytes) -> str:
    """Текст из PDF: reportlab жмёт потоки ASCII85+zlib, строки лежат как (…).

    Сравнивать БАЙТЫ бессмысленно — в PDF есть CreationDate/ID, они меняются от
    запуска к запуску, и такой «замок» проходил бы даже без перевода."""
    import base64
    import re
    import zlib

    out = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        try:
            chunk = zlib.decompress(base64.a85decode(m.group(1).strip(), adobe=True))
        except Exception:  # noqa: BLE001 — не текстовый поток (шрифт/картинка)
            continue
        for tok in re.findall(rb"\(((?:[^()\\]|\\.)*)\)", chunk):
            out.append(tok.decode("latin-1", "replace"))
    return " ".join(out)


@pytest.mark.django_db
def test_invoice_pdf_text_is_translated(monkeypatch):
    from apps.finance.pdf import build_invoice_pdf
    from apps.finance.services import issue_invoice
    from apps.finance.tests.test_invoices import _draft

    # Helvetica-режим: строки в потоке читаемы (у subset-TTF они закодированы).
    monkeypatch.setattr(documents, "unicode_fonts_available", lambda: False)
    tenant = TenantFactory.build(small_business=True)
    invoice = issue_invoice(_draft(recipient="Max Mustermann"))
    with translation.override("de"):
        de_text = pdf_text(build_invoice_pdf(invoice, tenant))
    with translation.override("en"):
        en_text = pdf_text(build_invoice_pdf(invoice, tenant))
    assert "Rechnung" in de_text and "Netto" in de_text
    assert "Invoice" in en_text and "Net:" in en_text
    assert "Rechnung" not in en_text  # немецкие подписи не протекают в EN-документ


@pytest.mark.django_db
def test_issued_invoice_keeps_its_language(monkeypatch):
    """I18N-7b/2: язык выставленного счёта зафиксирован — тот же номер обязан
    давать тот же документ (GoBD), независимо от языка кабинета читателя."""
    from django.test import RequestFactory

    from apps.finance import views
    from apps.finance.pdf import build_invoice_pdf
    from apps.finance.services import issue_invoice
    from apps.finance.tests.test_invoices import _draft

    monkeypatch.setattr(documents, "unicode_fonts_available", lambda: False)
    tenant = TenantFactory.build(enabled_locales=["de", "en"], default_locale="de")
    invoice = _draft(recipient="Max Mustermann")
    invoice.language = "en"
    invoice.save(update_fields=["language"])
    invoice = issue_invoice(invoice)

    request = RequestFactory().get("/x/?lang=de")  # владелец кликает «de»
    request.tenant = tenant
    with translation.override("de"):  # и кабинет тоже по-немецки
        lang = documents.document_language(request, explicit=invoice.language, tenant=tenant)
    assert lang == "en"  # выигрывает язык, зафиксированный на счёте
    with translation.override(lang):
        text = pdf_text(build_invoice_pdf(invoice, tenant))
    assert "Invoice" in text and "Rechnung" not in text
    assert views  # вьюха импортируется (регресс-страховка на провод)


@pytest.mark.django_db
def test_draft_language_can_be_changed_but_issued_cannot():
    from apps.finance.services import issue_invoice
    from apps.finance.tests.test_invoices import _draft

    invoice = _draft(recipient="X")
    assert invoice.is_editable  # черновик — язык ещё можно менять
    invoice.language = "en"
    invoice.save(update_fields=["language"])
    issued = issue_invoice(invoice)
    assert not issued.is_editable and issued.language == "en"


def test_clean_language_accepts_renderable_and_rejects_garbage():
    """Счёт можно выставить на любом языке, который мы умеем печатать (в т.ч. не
    включённом на витрине — язык клиента ≠ язык сайта). Мусор отбрасывается."""
    tenant = TenantFactory.build(enabled_locales=["de"])
    assert documents.clean_language("de", tenant) == "de"
    assert documents.clean_language("ru", tenant) == "ru"  # язык клиента
    assert documents.clean_language("zz", tenant) == ""
    assert documents.clean_language("", tenant) == ""


def test_business_language_is_tenant_default():
    tenant = TenantFactory.build(enabled_locales=["de", "en"], default_locale="en")
    assert documents.business_language(tenant) == "en"
