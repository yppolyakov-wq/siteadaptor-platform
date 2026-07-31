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


@pytest.mark.django_db
def test_invoice_pdf_differs_between_languages():
    from apps.finance.pdf import build_invoice_pdf
    from apps.finance.services import issue_invoice
    from apps.finance.tests.test_invoices import _draft

    tenant = TenantFactory.build(small_business=True)
    invoice = issue_invoice(_draft(recipient="Max Mustermann"))
    with translation.override("de"):
        de_pdf = build_invoice_pdf(invoice, tenant)
    with translation.override("en"):
        en_pdf = build_invoice_pdf(invoice, tenant)
    assert de_pdf.startswith(b"%PDF") and en_pdf.startswith(b"%PDF")
    assert de_pdf != en_pdf  # подписи реально переведены, а не захардкожены
