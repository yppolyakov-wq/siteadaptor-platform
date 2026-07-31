"""I18N-7a: письма владельцу и остальные флоу (job/offer/inbox/installment/
gift/waitlist) переводятся, а не остаются немецкими."""

import pytest
from django.template.loader import render_to_string
from django.utils import translation

pytestmark = pytest.mark.django_db


class _Obj(dict):
    """Мини-стаб: доступ и как к атрибуту, и как к ключу (шаблоны письма)."""

    __getattr__ = dict.get


def _render(name, ctx, locale):
    with translation.override(locale):
        return render_to_string(f"emails/{name}", ctx)


def test_owner_emails_translated():
    ctx = {
        "order": _Obj(reference_code="O-1", total="12.00", currency="EUR"),
        "customer": _Obj(name="Kunde"),
        "items": [],
    }
    assert "New order" in _render("order_owner_subject.txt", ctx, "en")
    assert "Новый заказ" in _render("order_owner_subject.txt", ctx, "ru")
    # немецкий остаётся байт-в-байт прежним (msgid = DE)
    assert "Neue Bestellung" in _render("order_owner_subject.txt", ctx, "de")


def test_job_and_offer_emails_translated():
    job = _Obj(reference_code="A-7", title="Bad", gross="100")
    assert "Your quote A-7" in _render("job_quoted_subject.txt", {"job": job}, "en")
    assert "Ваше предложение A-7" in _render("job_quoted_subject.txt", {"job": job}, "ru")
    assert "Teklif kabul edildi" in _render("offer_accepted_subject.txt", {"offer": None}, "tr")


def test_digest_plurals_have_language_specific_forms():
    """Плюралы дайджеста — не «5 запись»: у ru 4 формы, у en 2."""
    d = _Obj(date=None, bookings_today=5, revenue_yesterday=None)
    ru = _render("owner_digest.txt", {"d": d, "tenant": _Obj(name="X")}, "ru")
    en = _render("owner_digest.txt", {"d": d, "tenant": _Obj(name="X")}, "en")
    assert "5 записей" in ru
    assert "5 appointments" in en


def test_gift_and_waitlist_translated():
    gift = _Obj(buyer_name="Anna", amount_eur=50)
    assert "Voucher code" in _render("gift_voucher.txt", {"gift": gift, "code": "G-1"}, "en")
    event = _Obj(title="Yoga", starts_at=None)
    assert "Available again" in _render(
        "event_waitlist_available_subject.txt", {"event": event}, "en"
    )
