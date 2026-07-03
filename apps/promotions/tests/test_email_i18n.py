"""L4 — письма в локали получателя: DE = msgid (рендер прежний, без .po),
EN — переводы locale/en (.mo компилируется в CI/deploy, msgfmt --check-format)."""

from types import SimpleNamespace

from apps.promotions import notifications

_CTX = {
    "customer": SimpleNamespace(name="Kim"),
    "promotion": SimpleNamespace(title_text="Brotkorb XL"),
    "reservation": SimpleNamespace(quantity=2, reference_code="R-123", status="pending"),
    "unsubscribe_url": "",
}


def test_render_de_is_legacy_german():
    subject, body, html = notifications._render("reservation_created", _CTX, locale="de")
    assert subject == "Reservierung eingegangen — Brotkorb XL"
    assert "Hallo Kim," in body
    assert "vielen Dank für Ihre Reservierung." in body
    assert "Referenz-Code: R-123" in body
    assert "Status: wird vom Geschäft bestätigt." in body
    assert "Vielen Dank für Ihre Reservierung!" in html  # HTML-альтернатива тоже DE


def test_render_en_uses_translations():
    subject, body, html = notifications._render("reservation_created", _CTX, locale="en")
    assert subject == "Reservation received — Brotkorb XL"
    assert "Hello Kim," in body
    assert "thank you for your reservation." in body
    assert "Reference code: R-123" in body
    assert "Status: awaiting confirmation by the shop." in body
    assert "Thank you for your reservation!" in html


def test_render_defaults_to_tenant_locale(monkeypatch):
    monkeypatch.setattr(notifications, "_email_locale", lambda: "en")
    subject, _body, _html = notifications._render("reservation_created", _CTX)
    assert subject == "Reservation received — Brotkorb XL"
