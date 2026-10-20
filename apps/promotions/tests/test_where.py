"""T-8.10h H-7d: «Wo ist meine Aktion?» — отчёт после ✅ и по кнопке 📍.

План — docs/t8-10h-h7-owner-bot-ux-plan-2026-10-20.md §2.
"""

import pytest

from apps.aggregator.models import AggregatorListing, AggregatorPortal
from apps.promotions import telegram_promo as tp
from apps.promotions import where
from apps.promotions.models import Promotion
from apps.promotions.tests.test_telegram_promo import _cb, _draft, tg  # noqa: F401

pytestmark = pytest.mark.django_db


def _published(tg):  # noqa: F811
    token, _p = _draft(tg)
    assert _cb(tg, f"tp:ok:{token}") == "published"
    return token, Promotion.objects.get()


def _text(tenant, promo):
    return "\n".join(where.report(tenant, promo))


def test_after_publish_report_and_where_button(tg):  # noqa: F811
    token, _promo = _published(tg)
    last = tg["sent"][-1]
    assert "Aushang" in last["text"] and "Stadtkatalog" in last["text"]
    datas = [b["callback_data"] for row in last["markup"]["inline_keyboard"] for b in row]
    assert datas == [f"tp:wh:{token}"]


def test_where_button_resends_report(tg):  # noqa: F811
    token, promo = _published(tg)
    assert _cb(tg, f"tp:wh:{token}") == "where"
    assert promo.get_i18n("title") in tg["sent"][-1]["text"]


def test_where_button_unknown_token(tg):  # noqa: F811
    assert _cb(tg, "tp:wh:" + "a" * 16) == "where_missing"


def test_reason_email_pending(tg):  # noqa: F811
    _token, promo = _published(tg)
    tenant = tg["tenant"]
    tenant.email_pending = True
    assert "E-Mail" in _text(tenant, promo)


def test_reason_catalog_switched_off(tg):  # noqa: F811
    _token, promo = _published(tg)
    tenant = tg["tenant"]
    tenant.in_city_catalog = False
    assert "ausgeschaltet" in _text(tenant, promo)


def test_reason_demo(tg):  # noqa: F811
    _token, promo = _published(tg)
    tenant = tg["tenant"]
    tenant.is_demo = True
    assert "Demo" in _text(tenant, promo)


def test_inactive_promo(tg):  # noqa: F811
    _token, promo = _published(tg)
    promo.status = "paused"
    assert "aktiv ist" in _text(tg["tenant"], promo)


def test_listing_link_on_portal_and_hidden(tg):  # noqa: F811
    _token, promo = _published(tg)
    tenant = tg["tenant"]
    listing, _c = AggregatorListing.objects.update_or_create(
        tenant_schema=tenant.schema_name,
        listing_kind=AggregatorListing.KIND_PROMOTION,
        source_ref=str(promo.pk),
        defaults={"title": {"de": "Brötchen"}, "city": "", "is_active": True},
    )
    AggregatorPortal.objects.create(host="stadt.example.com", is_active=True)
    text = _text(tenant, promo)
    assert f"stadt.example.com/angebot/{listing.pk}/" in text
    from django.utils import timezone

    listing.hidden_at = timezone.now()
    listing.save(update_fields=["hidden_at"])
    assert "ausgeblendet" in _text(tenant, promo)


def test_listing_missing_means_queued(tg):  # noqa: F811
    _token, promo = _published(tg)
    AggregatorListing.objects.filter(source_ref=str(promo.pk)).delete()
    assert "aufgenommen" in _text(tg["tenant"], promo)


def test_channels_in_words(tg):  # noqa: F811
    from apps.publishing.models import Channel, Publication

    _token, promo = _published(tg)
    channel = Channel.objects.create(type=Channel.TELEGRAM, is_enabled=True)
    Publication.objects.update_or_create(
        promotion=promo,
        channel=channel,
        defaults={"status": "failed", "dedupe_key": f"publish:{promo.pk}:{channel.pk}"},
    )
    assert "Fehler" in _text(tg["tenant"], promo)


def test_callback_regex_accepts_where():
    assert tp.CALLBACK_RE.match("tp:wh:" + "b" * 16)


def test_expired_listing_is_not_linked(tg):  # noqa: F811
    from datetime import timedelta

    from django.utils import timezone

    _token, promo = _published(tg)
    tenant = tg["tenant"]
    AggregatorListing.objects.update_or_create(
        tenant_schema=tenant.schema_name,
        listing_kind=AggregatorListing.KIND_PROMOTION,
        source_ref=str(promo.pk),
        defaults={
            "title": {"de": "Brötchen"},
            "city": "",
            "is_active": True,
            "ends_at": timezone.now() - timedelta(hours=1),
        },
    )
    text = _text(tenant, promo)
    assert "/angebot/" not in text and "aufgenommen" in text
