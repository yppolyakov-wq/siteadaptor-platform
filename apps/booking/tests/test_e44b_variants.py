"""KA-12 E4.4b (S1): варианты услуги — модель и кабинет.

Вариант = дельты цены/длительности к услуге («Langhaar +12 € / +20 min»). Кабинет:
добавить/изменить/выключить/удалить отдельными мини-формами (главный Save услуги
варианты не трогает); вариант чужой услуги → 404; дельты с потолком в БД."""

import pytest
from django.db import IntegrityError, transaction
from django.http import Http404

from apps.booking import pricing
from apps.booking.models import ServiceVariant
from apps.booking.tests.test_services import _service

pytestmark = pytest.mark.django_db


def _variant(service, name="Lang", price=0, minutes=0, order=0, active=True):
    return ServiceVariant.objects.create(
        service=service,
        name=name,
        price_delta_cents=price,
        duration_delta_minutes=minutes,
        sort_order=order,
        is_active=active,
    )


def test_resolve_default_is_first_active_by_order():
    svc = _service()
    _variant(svc, "Lang", order=2)
    kurz = _variant(svc, "Kurz", order=1)
    _variant(svc, "Off", order=0, active=False)
    assert pricing.resolve_variant(svc, "") == (kurz, True)


def test_resolve_without_variants_is_none():
    assert pricing.resolve_variant(_service(), "") == (None, True)


def test_resolve_foreign_inactive_or_junk_is_refused():
    svc, other = _service(), _service()
    off = _variant(svc, "Off", active=False)
    foreign = _variant(other, "X")
    for raw in (str(off.pk), str(foreign.pk), "abc", "00000000-0000-0000-0000-000000000000"):
        assert pricing.resolve_variant(svc, raw)[1] is False


def test_effective_minutes_and_price_clamped():
    svc = _service(duration_minutes=30, price_cents=2000)
    short = _variant(svc, "Kurz", price=-5000, minutes=-60)
    assert pricing.effective_minutes(svc, short) == 5
    assert pricing.variant_price_cents(svc, None, short) == 0
    lang = _variant(svc, "Lang", price=1200, minutes=20, order=1)
    assert pricing.effective_minutes(svc, lang) == 50
    assert pricing.variant_price_cents(svc, None, lang) == 3200
    assert pricing.effective_minutes(svc, None) == 30


def test_delta_caps_enforced_by_database():
    svc = _service()
    with pytest.raises(IntegrityError), transaction.atomic():
        _variant(svc, "Huge", minutes=481)
    with pytest.raises(IntegrityError), transaction.atomic():
        _variant(svc, "Huge2", price=1_000_001)


def test_name_unique_per_service():
    svc = _service()
    _variant(svc, "Lang")
    with pytest.raises(IntegrityError), transaction.atomic():
        _variant(svc, "Lang")


def _post(settings, data):
    from apps.booking import views
    from apps.booking.tests.test_cabinet import _req

    settings.ROOT_URLCONF = "config.urls_tenant"
    return views.services_view(_req("post", data=data))


def test_cabinet_add_update_toggle_delete(settings):
    svc = _service(duration_minutes=30)
    _post(
        settings,
        {
            "action": "variant_add",
            "service": str(svc.pk),
            "name": "Lang",
            "price_delta_eur": "12,50",
            "duration_delta": "20",
        },
    )
    v = svc.variants.get()
    assert (v.price_delta_cents, v.duration_delta_minutes) == (1250, 20)
    _post(
        settings,
        {
            "action": "variant_update",
            "service": str(svc.pk),
            "variant": str(v.pk),
            "name": "Langhaar",
            "price_delta_eur": "-2",
            "duration_delta": "-10",
            "sort_order": "3",
        },
    )
    v.refresh_from_db()
    assert (v.name, v.price_delta_cents, v.duration_delta_minutes, v.sort_order) == (
        "Langhaar",
        -200,
        -10,
        3,
    )
    _post(settings, {"action": "variant_toggle", "service": str(svc.pk), "variant": str(v.pk)})
    v.refresh_from_db()
    assert v.is_active is False
    _post(settings, {"action": "variant_delete", "service": str(svc.pk), "variant": str(v.pk)})
    assert not svc.variants.exists()


def test_cabinet_rejects_foreign_variant(settings):
    svc, other = _service(), _service()
    foreign = _variant(other, "X")
    with pytest.raises(Http404):
        _post(
            settings,
            {
                "action": "variant_update",
                "service": str(svc.pk),
                "variant": str(foreign.pk),
                "name": "Hack",
            },
        )
    foreign.refresh_from_db()
    assert foreign.name == "X"


def test_cabinet_junk_and_too_short_refused(settings):
    svc = _service(duration_minutes=30)
    _post(
        settings,
        {
            "action": "variant_add",
            "service": str(svc.pk),
            "name": "Kurz",
            "price_delta_eur": "abc",
            "duration_delta": "0",
        },
    )
    _post(
        settings,
        {
            "action": "variant_add",
            "service": str(svc.pk),
            "name": "Zu kurz",
            "price_delta_eur": "0",
            "duration_delta": "-40",
        },
    )
    assert not svc.variants.exists()


def test_main_service_save_leaves_variants(settings):
    svc = _service()
    _variant(svc, "Lang")
    _post(
        settings,
        {"action": "update", "service": str(svc.pk), "duration": "60", "price_eur": "10"},
    )
    assert svc.variants.count() == 1


def test_junk_inputs_never_500(settings, monkeypatch):
    """Ревью безопасности: мусорная услуга → 404; «²» в порядке, NUL и длинный
    перевод — без падения, перевод обрезан до длины поля."""
    with pytest.raises(Http404):
        _post(settings, {"action": "variant_add", "service": "zzz", "name": "X"})
    svc = _service(duration_minutes=30)
    _post(
        settings,
        {
            "action": "variant_add",
            "service": str(svc.pk),
            "name": "La\x00ng",
            "price_delta_eur": "1",
            "duration_delta": "0",
            "sort_order": "²",
        },
    )
    v = svc.variants.get()
    assert v.name == "Lang"
    v.name_i18n = {}
    v.save()
    from apps.core import i18n_input

    monkeypatch.setattr(i18n_input, "extra_locales", lambda tenant: ["en"])
    for loc in ("en",):
        _post(
            settings,
            {
                "action": "variant_update",
                "service": str(svc.pk),
                "variant": str(v.pk),
                "name": "Lang",
                f"name_{loc}": "y" * 5000,
            },
        )
        v.refresh_from_db()
        assert len(v.name_i18n.get(loc, "")) == 100


def test_duplicate_name_and_limit_are_messages_not_500(settings):
    from apps.booking.models import MAX_VARIANTS_PER_SERVICE

    svc = _service(duration_minutes=30)
    base = {"action": "variant_add", "service": str(svc.pk), "duration_delta": "0"}
    _post(settings, {**base, "name": "Lang"})
    _post(settings, {**base, "name": "Lang"})
    assert svc.variants.count() == 1
    for i in range(MAX_VARIANTS_PER_SERVICE + 2):
        _post(settings, {**base, "name": f"V{i}"})
    assert svc.variants.count() == MAX_VARIANTS_PER_SERVICE


def test_toggle_delete_with_foreign_service_pair_404(settings):
    svc, other = _service(), _service()
    v = _variant(other, "X")
    for action in ("variant_toggle", "variant_delete"):
        with pytest.raises(Http404):
            _post(settings, {"action": action, "service": str(svc.pk), "variant": str(v.pk)})
    assert ServiceVariant.objects.filter(pk=v.pk, is_active=True).exists()
