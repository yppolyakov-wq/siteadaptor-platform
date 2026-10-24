"""KA-12 E4.4b (S2): вариант услуги на витрине и в брони.

Сетка и бронь считают длину варианта (и вместе с ?dauer), цена = база дня + доплата,
акция + доплата («показано = списано»); подделка варианта → 404 без брони; снимок
имени варианта на каждой брони группы; ссылки страницы несут выбранный вариант."""

import itertools

import pytest
from django.http import Http404

from apps.booking import availability, public_views, services
from apps.booking.models import Booking, ServiceVariant
from apps.booking.tests.test_services import _aware, _future_day, _resource, _rule, _service

pytestmark = pytest.mark.django_db


def _variant(service, name, price=0, minutes=0, order=0):
    return ServiceVariant.objects.create(
        service=service,
        name=name,
        price_delta_cents=price,
        duration_delta_minutes=minutes,
        sort_order=order,
    )


_IPS = itertools.count(1)


def _rf(method, path, data):
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.tenants.tests.factories import TenantFactory

    # Свой IP на запрос: лимит частоты записи не должен отвечать 429 раньше проверки.
    req = getattr(RequestFactory(), method)(path, data, REMOTE_ADDR=f"10.45.{next(_IPS) % 250}.7")
    SessionMiddleware(lambda r: None).process_request(req)
    req._messages = FallbackStorage(req)
    req.tenant = TenantFactory.build(schema_name="public")
    return req


def _setup(day, window=("09:00", "10:20")):
    r = _resource(type="staff")
    _rule(r, day, window[0], window[1], slot=10)
    svc = _service(duration_minutes=60, price_cents=3000)
    std = _variant(svc, "Standard", order=0)
    lang = _variant(svc, "Lang", price=1200, minutes=30, order=1)
    return r, svc, std, lang


def test_variant_length_drives_grid(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r, svc, std, lang = _setup(day)
    body_std = public_views.service_slots(
        _rf("get", "/", {"tag": day.isoformat()}), pk=svc.pk
    ).content.decode()
    body_lang = public_views.service_slots(
        _rf("get", "/", {"tag": day.isoformat(), "variante": str(lang.pk)}), pk=svc.pk
    ).content.decode()
    assert 'data-slot="free"' in body_std
    assert 'data-slot="free"' not in body_lang  # 90 мин не влезают в окно 80 мин


def test_foreign_or_junk_variant_on_slot_page_is_404(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r, svc, std, lang = _setup(day)
    other = _service()
    foreign = _variant(other, "X")
    for raw in (str(foreign.pk), "abc"):
        with pytest.raises(Http404):
            public_views.service_slots(
                _rf("get", "/", {"tag": day.isoformat(), "variante": raw}), pk=svc.pk
            )


def _book_post(svc, start, **extra):
    data = {"start": start.isoformat(), "name": "Gast", "email": "g@t.de", **extra}
    return public_views.service_book(
        _rf("post", f"/termin/leistung/{svc.pk}/buchen/", data), pk=svc.pk
    )


def test_booking_with_variant_has_length_price_and_snapshot(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r, svc, std, lang = _setup(day, window=("09:00", "12:00"))
    _book_post(svc, _aware(day, 9), variante=str(lang.pk))
    b = Booking.objects.get(service=svc)
    assert (b.end - b.start).total_seconds() == 90 * 60
    assert b.price_cents == 4200
    assert b.variant_id == lang.pk and b.variant_label == "Lang"


def test_booking_with_variant_and_units(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r, svc, std, lang = _setup(day, window=("09:00", "13:00"))
    _book_post(svc, _aware(day, 9), variante=str(lang.pk), dauer="2")
    b = Booking.objects.get(service=svc)
    assert (b.end - b.start).total_seconds() == 180 * 60
    assert b.price_cents == 2 * 4200


def test_default_variant_without_param(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r, svc, std, lang = _setup(day, window=("09:00", "12:00"))
    _book_post(svc, _aware(day, 9))
    b = Booking.objects.get(service=svc)
    assert b.variant_id == std.pk and b.price_cents == 3000


def test_forged_variant_on_post_is_404_without_booking(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r, svc, std, lang = _setup(day, window=("09:00", "12:00"))
    foreign = _variant(_service(), "X")
    lang_off = lang
    lang_off.is_active = False
    lang_off.save()
    for raw in (str(foreign.pk), str(lang_off.pk), "abc"):
        with pytest.raises(Http404):
            _book_post(svc, _aware(day, 9), variante=raw)
    assert not Booking.objects.filter(service=svc).exists()


def test_variant_buffer_extends_from_variant_end(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r, svc, std, lang = _setup(day, window=("09:00", "12:00"))
    svc.buffer_after_minutes = 15
    svc.save(update_fields=["buffer_after_minutes"])
    _book_post(svc, _aware(day, 9), variante=str(lang.pk))
    b = Booking.objects.get(service=svc)
    assert b.occupied_until == _aware(day, 10, 45)


def test_group_booking_snapshots_variant_on_each(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r, svc, std, lang = _setup(day, window=("09:00", "14:00"))
    req = _rf(
        "post",
        "/",
        {
            "start": [_aware(day, 9).isoformat(), _aware(day, 11).isoformat()],
            "name": "Gast",
            "email": "g@t.de",
            "variante": str(lang.pk),
        },
    )
    public_views.service_book(req, pk=svc.pk)
    labels = list(Booking.objects.filter(service=svc).values_list("variant_label", flat=True))
    assert labels == ["Lang", "Lang"]


def test_book_service_rejects_variant_of_other_service():
    day = _future_day()
    r = _resource()
    svc, other = _service(), _service()
    foreign = _variant(other, "X")
    with pytest.raises(ValueError):
        services.book(
            r,
            start=_aware(day, 9),
            end=_aware(day, 10),
            name="G",
            service=svc,
            variant=foreign,
        )


def test_variant_survives_rename_and_delete():
    day = _future_day()
    r = _resource()
    svc = _service()
    v = _variant(svc, "Lang")
    b = services.book(
        r,
        start=_aware(day, 9),
        end=_aware(day, 10),
        name="G",
        service=svc,
        variant=v,
        variant_label="Lang",
    )
    v.name = "Langhaar"
    v.save()
    v.delete()
    b.refresh_from_db()
    assert b.variant_id is None and b.variant_label == "Lang"


def test_next_free_slot_respects_variant_length():
    day = _future_day()
    r, svc, std, lang = _setup(day)  # окно 80 мин
    assert availability.next_free_slot(svc, from_day=day, duration_minutes=90) is None
    assert availability.next_free_slot(svc, from_day=day, duration_minutes=60) is not None


def test_slot_links_carry_non_default_variant(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r, svc, std, lang = _setup(day, window=("09:00", "12:00"))
    body = public_views.service_slots(
        _rf("get", "/", {"tag": day.isoformat(), "variante": str(lang.pk)}), pk=svc.pk
    ).content.decode()
    assert f"variante={lang.pk}" in body
    picked = public_views.service_slots(
        _rf(
            "get",
            "/",
            {"tag": day.isoformat(), "variante": str(lang.pk), "slot": _aware(day, 9).isoformat()},
        ),
        pk=svc.pk,
    ).content.decode()
    assert f'name="variante" value="{lang.pk}"' in picked


def test_default_variant_keeps_links_unchanged(settings):
    """Паритет: при дефолтном варианте ссылки страницы — как были (без параметра)."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r, svc, std, lang = _setup(day, window=("09:00", "12:00"))
    body = public_views.service_slots(
        _rf("get", "/", {"tag": day.isoformat()}), pk=svc.pk
    ).content.decode()
    slot_links = [chunk for chunk in body.split('data-slot="free"')[1:]]
    assert slot_links and all("variante=" not in c.split(">")[0] for c in slot_links)


def test_shown_price_equals_booked_price(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r, svc, std, lang = _setup(day, window=("09:00", "12:00"))
    resp = public_views.service_slots(
        _rf("get", "/", {"tag": day.isoformat(), "variante": str(lang.pk)}), pk=svc.pk
    )
    assert "42,00" in resp.content.decode() or "42.00" in resp.content.decode()


def test_variant_label_on_deal_surfaces():
    from apps.core import transactions
    from apps.finance.services import invoice_from_booking

    day = _future_day()
    r = _resource()
    svc = _service(name="Haarschnitt")
    v = _variant(svc, "Lang")
    b = services.book(
        r,
        start=_aware(day, 9),
        end=_aware(day, 10),
        name="G",
        email="g@t.de",
        service=svc,
        variant=v,
        variant_label="Lang",
        price_cents=4200,
    )
    assert b.service_label == "Haarschnitt · Lang"
    assert transactions._booking_fields(b)["title"].startswith("Haarschnitt · Lang")
    inv = invoice_from_booking(b)
    assert inv.lines[0]["text"] == "Haarschnitt · Lang"
