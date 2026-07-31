"""G10 / G10a: услуги (Service) — слоты по длительности, бронь со снимком цены,
подбор ресурса бизнес-уровня, выручка за выполненную услугу."""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.booking import availability, public_views, services, views
from apps.booking.models import AvailabilityRule, Booking, Resource, Service
from apps.booking.state_machine import BookingSM
from apps.finance.models import RevenueEntry
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _resource(**kwargs):
    return Resource.objects.create(name=f"Platz {uuid.uuid4().hex[:6]}", **kwargs)


def _service(**kwargs):
    kwargs.setdefault("name", "Ölwechsel")
    kwargs.setdefault("duration_minutes", 60)
    kwargs.setdefault("price_cents", 4900)
    return Service.objects.create(**kwargs)


def _future_day(days=7):
    return timezone.localdate() + timedelta(days=days)


def _rule(resource, day, start="09:00", end="12:00", slot=30):
    return AvailabilityRule.objects.create(
        resource=resource, weekday=day.weekday(), start_time=start, end_time=end, slot_minutes=slot
    )


def _aware(day, hour, minute=0):
    return timezone.make_aware(datetime(day.year, day.month, day.day, hour, minute))


# --- A3: фото услуги (богатая карточка) -------------------------------------------
def test_service_image_url_property():
    svc = _service(image={"url": "https://img.example/cut.jpg", "alt": {"de": "Schnitt"}})
    assert svc.image_url == "https://img.example/cut.jpg"
    # не-dict/пусто → '' (без падений)
    assert _service(image={}).image_url == ""
    assert Service(name="x", image=None).image_url == ""


def test_service_slots_page_shows_photo(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r = _resource(type="staff")
    _rule(r, day)
    svc = _service(image={"url": "https://img.example/color.jpg"}, description="Schöne Farbe.")
    request = RequestFactory().get(f"/t/{svc.pk}/?tag={day:%Y-%m-%d}")
    SessionMiddleware(lambda rq: None).process_request(request)
    MessageMiddleware(lambda rq: None).process_request(request)
    request.tenant = TenantFactory.build(name="Salon")
    body = public_views.service_slots(request, pk=svc.pk).content.decode()
    assert "https://img.example/color.jpg" in body
    assert "Schöne Farbe." in body


def test_resource_photo_url_property():
    r = _resource(photo={"url": "https://img.example/lea.jpg"})
    assert r.photo_url == "https://img.example/lea.jpg"
    assert _resource(photo={}).photo_url == ""
    assert Resource(name="x", photo=None).photo_url == ""


# --- R3 «Nächster freier Termin» (empty-state конверсия) ---------------------
def test_next_free_slot_scans_forward_to_available_day():
    r = _resource(type="staff")
    target = _future_day(4)
    _rule(r, target)  # слоты каждую неделю в этот weekday
    svc = _service()
    nf = availability.next_free_slot(svc, from_day=timezone.localdate())
    assert nf is not None
    assert nf.date().weekday() == target.weekday()  # ближайший день с правилом


def test_next_free_slot_none_without_rules():
    assert availability.next_free_slot(_service(), from_day=timezone.localdate()) is None


def test_service_slots_empty_state_offers_next_free(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    r = _resource(type="staff")
    target = _future_day(5)
    _rule(r, target)
    svc = _service()
    empty_day = target + timedelta(days=1)  # другой weekday → без слотов
    request = RequestFactory().get(f"/t/{svc.pk}/?tag={empty_day:%Y-%m-%d}")
    SessionMiddleware(lambda rq: None).process_request(request)
    MessageMiddleware(lambda rq: None).process_request(request)
    request.tenant = TenantFactory.build(name="Salon")
    body = public_views.service_slots(request, pk=svc.pk).content.decode()
    assert "An diesem Tag sind keine Termine frei" in body
    # R3: перехват уходящего клиента. Строка теперь переведена (I18N-9) — витрина
    # рендерится по-немецки, поэтому замок сверяется с немецким текстом.
    assert "Nächster freier Termin" in body
    assert f"tag={target:%Y-%m-%d}" in body  # ссылка ведёт на ближайший свободный день


def test_service_slots_picker_shows_master_profile(settings):
    """A3: пикер специалиста показывает фото+должность; био выбранного мастера."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r1 = _resource(
        type="staff",
        title="Stylistin",
        bio="Balayage-Expertin.",
        photo={"url": "https://img.example/lea.jpg"},
    )
    r2 = _resource(type="staff", title="Barbier")
    _rule(r1, day)
    _rule(r2, day)
    svc = _service(duration_minutes=30)
    request = RequestFactory().get(f"/t/{svc.pk}/?tag={day:%Y-%m-%d}&resource={r1.pk}")
    SessionMiddleware(lambda rq: None).process_request(request)
    MessageMiddleware(lambda rq: None).process_request(request)
    request.tenant = TenantFactory.build(name="Salon")
    body = public_views.service_slots(request, pk=svc.pk).content.decode()
    assert "https://img.example/lea.jpg" in body  # фото в пикере
    assert "Stylistin" in body and "Barbier" in body  # должности
    assert "Balayage-Expertin." in body  # био выбранного мастера


# --- слоты по длительности услуги -------------------------------------------------


def test_free_slots_uses_service_duration():
    resource = _resource()
    day = _future_day()
    _rule(resource, day, "09:00", "12:00", slot=30)
    slots = availability.free_slots(resource, day, duration_minutes=60)
    # длина слота = 60 мин; старты каждые 30: 9:00, 9:30, 10:00, 10:30, 11:00
    assert slots[0][1] - slots[0][0] == timedelta(minutes=60)
    assert len(slots) == 5


def test_service_slots_and_assign_resource():
    r1, r2 = _resource(), _resource()
    day = _future_day()
    _rule(r1, day)
    _rule(r2, day)
    service = _service(duration_minutes=30)
    starts = availability.service_slots(service, day)
    assert starts and starts == sorted(starts)
    # ресурс назначается на свободный старт
    assert availability.assign_resource(service, starts[0]) in (r1, r2)


def test_assign_resource_none_when_full():
    resource = _resource()  # capacity 1
    day = _future_day()
    _rule(resource, day)
    service = _service(duration_minutes=30)
    start = availability.service_slots(service, day)[0]
    end = start + timedelta(minutes=30)
    services.book(resource, start=start, end=end, name="Gast")  # занял единственный ресурс
    assert availability.assign_resource(service, start) is None


def test_choose_specific_resource_scopes_slots_and_booking():
    """#4: выбор конкретного мастера — слоты и бронь только по нему."""
    r1, r2 = _resource(), _resource()
    day = _future_day()
    _rule(r1, day)
    _rule(r2, day)
    service = _service(duration_minutes=30)
    start = availability.service_slots(service, day, resource=r1)[0]
    # занят r1 на этот старт → его слот пропадает, но общий (r2) остаётся
    services.book(r1, start=start, end=start + timedelta(minutes=30), name="X")
    assert start not in availability.service_slots(service, day, resource=r1)
    assert start in availability.service_slots(service, day)  # r2 ещё свободен
    # назначение ограничено выбранным ресурсом
    assert availability.assign_resource(service, start, resource=r1) is None
    assert availability.assign_resource(service, start, resource=r2) == r2


# --- бронь со снимком цены + выручка ----------------------------------------------


def test_book_snapshots_service_and_price():
    resource = _resource()
    day = _future_day()
    service = _service(price_cents=4900)
    start = _aware(day, 9)
    booking = services.book(
        resource,
        start=start,
        end=start + timedelta(minutes=60),
        name="Gast",
        service=service,
        price_cents=service.price_cents,
    )
    assert booking.service == service and booking.price_cents == 4900


def test_fulfilled_service_records_revenue():
    resource = _resource()
    day = _future_day()
    service = _service(price_cents=4900)
    start = _aware(day, 9)
    booking = services.book(
        resource,
        start=start,
        end=start + timedelta(minutes=60),
        name="Gast",
        service=service,
        price_cents=service.price_cents,
    )
    sm = BookingSM()
    booking = sm.apply(booking, "confirmed")
    sm.apply(booking, "fulfilled")
    entry = RevenueEntry.objects.get(source="booking", source_ref=str(booking.id))
    assert entry.amount == Decimal("49.00") and entry.vat_rate == Decimal("19.00")


def test_fulfilled_without_price_no_revenue():
    resource = _resource()
    start = _aware(_future_day(), 9)
    booking = services.book(resource, start=start, end=start + timedelta(hours=1), name="Tisch")
    sm = BookingSM()
    sm.apply(sm.apply(booking, "confirmed"), "fulfilled")
    assert not RevenueEntry.objects.filter(source="booking").exists()


# --- G10b: кабинет + витрина ------------------------------------------------------


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _cab_req(method="get", data=None):
    request = getattr(RequestFactory(), method)("/dashboard/booking/leistungen/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    return request


def _pub_req(method="get", path="/termin/", data=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.7"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(disabled_modules=[])  # booking активен
    return request


def test_cabinet_creates_and_updates_service():
    resp = views.services_view(
        _cab_req(
            "post",
            {"action": "create", "name": "Haarschnitt", "duration": "45", "price_eur": "25,00"},
        )
    )
    assert resp.status_code == 302
    svc = Service.objects.get(name="Haarschnitt")
    assert svc.duration_minutes == 45 and svc.price_cents == 2500
    views.services_view(
        _cab_req(
            "post",
            {"action": "update", "service": str(svc.pk), "duration": "60", "price_eur": "30"},
        )
    )
    svc.refresh_from_db()
    assert svc.duration_minutes == 60 and svc.price_cents == 3000


def _png(name="cut.png"):
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (12, 12), "blue").save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def test_cabinet_service_photo_upload_and_remove():
    """A3: владелец загружает фото услуги в кабинете и может его удалить."""
    create = views.services_view(
        _cab_req(
            "post", {"action": "create", "name": "Färben", "duration": "90", "price_eur": "69"}
        )
    )
    assert create.status_code == 302
    svc = Service.objects.get(name="Färben")
    # загрузка фото на update
    req = _cab_req(
        "post", {"action": "update", "service": str(svc.pk), "duration": "90", "price_eur": "69"}
    )
    req.FILES["image"] = _png()
    views.services_view(req)
    svc.refresh_from_db()
    assert svc.image_url  # фото сохранено
    # удаление фото
    views.services_view(
        _cab_req(
            "post",
            {
                "action": "update",
                "service": str(svc.pk),
                "duration": "90",
                "price_eur": "69",
                "remove_image": "1",
            },
        )
    )
    svc.refresh_from_db()
    assert not svc.image_url


def test_termin_index_shows_services():
    Service.objects.create(name="Ölwechsel", duration_minutes=30, price_cents=4900)
    body = public_views.termin_index(_pub_req()).content.decode()
    assert "Ölwechsel" in body


def test_service_book_assigns_resource_and_snapshots_price():
    resource = _resource()
    day = _future_day()
    _rule(resource, day)
    service = _service(duration_minutes=30, price_cents=2500)
    start = availability.service_slots(service, day)[0]
    resp = public_views.service_book(
        _pub_req(
            "post",
            f"/termin/leistung/{service.pk}/buchen/",
            {"start": start.isoformat(), "name": "Gast"},
        ),
        pk=service.pk,
    )
    booking = Booking.objects.get(service=service)
    assert booking.resource == resource and booking.price_cents == 2500
    assert resp.url == f"/t/{booking.reference_code}/"


def test_service_book_rejects_unavailable_time():
    resource = _resource()
    day = _future_day()
    _rule(resource, day, "09:00", "12:00")
    service = _service(duration_minutes=30)
    bad = _aware(day, 3)  # вне окна правил
    public_views.service_book(
        _pub_req(
            "post",
            f"/termin/leistung/{service.pk}/buchen/",
            {"start": bad.isoformat(), "name": "Gast"},
        ),
        pk=service.pk,
    )
    assert not Booking.objects.filter(service=service).exists()


# --- A3: инлайн-правка услуги на канве витрины ------------------------------------
def _inline_req(payload):
    import json

    request = RequestFactory().post(
        "/dashboard/booking/services/inline-edit/",
        data=json.dumps(payload),
        content_type="application/json",
    )
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    return request


def test_service_inline_edit_name_and_price():
    svc = _service(name="Schnitt", price_cents=2500)
    assert (
        views.service_inline_edit(
            _inline_req({"pk": str(svc.pk), "field": "name", "value": "Föhnen"})
        ).status_code
        == 204
    )
    assert (
        views.service_inline_edit(
            _inline_req({"pk": str(svc.pk), "field": "price_eur", "value": "33,50"})
        ).status_code
        == 204
    )
    svc.refresh_from_db()
    assert svc.name == "Föhnen" and svc.price_cents == 3350


def test_service_inline_edit_rejects_empty_name_and_bad_field():
    svc = _service(name="Schnitt")
    assert (
        views.service_inline_edit(
            _inline_req({"pk": str(svc.pk), "field": "name", "value": "  "})
        ).status_code
        == 400
    )
    assert (
        views.service_inline_edit(
            _inline_req({"pk": str(svc.pk), "field": "duration", "value": "9"})
        ).status_code
        == 400
    )
    svc.refresh_from_db()
    assert svc.name == "Schnitt"


def test_service_photo_edit_replaces_image():
    svc = _service(name="Färben", image={"url": "https://old.example/x.jpg"})
    req = RequestFactory().post("/dashboard/booking/services/photo-edit/", {"pk": str(svc.pk)})
    req.FILES["image"] = _png()
    owner = uuid.uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    assert views.service_photo_edit(req).status_code == 204
    svc.refresh_from_db()
    assert svc.image_url and "old.example" not in svc.image_url  # перезаписано


def test_service_index_has_inline_edit_markers():
    Service.objects.create(name="Ölwechsel", duration_minutes=30, price_cents=4900)
    body = public_views.termin_index(_pub_req()).content.decode()
    assert 'data-edit-model="service"' in body  # имя/описание правятся на канве
    assert "data-price-edit" in body and 'data-price-field="price_eur"' in body
    assert "data-photo-edit" in body  # замена фото услуги


def test_service_images_shim_dict_list_garbage():
    """UC4-3 (D4a): шим Service.images — легаси dict → [dict], список как есть
    (мусор-элементы отфильтрованы), не-JSON-мусор → []; image_url primary-aware."""
    legacy = _service(name="ShimA", image={"url": "/a.jpg"})
    assert legacy.images == [{"url": "/a.jpg"}] and legacy.image_url == "/a.jpg"
    listed = _service(
        name="ShimB",
        image=[
            {"id": "1", "url": "/b.jpg", "is_primary": False},
            {"id": "2", "url": "/c.jpg", "is_primary": True},
            "мусор",
        ],
    )
    assert [i["id"] for i in listed.images] == ["1", "2"]
    assert listed.image_url == "/c.jpg"  # primary, не первый
    assert _service(name="ShimC", image=[]).images == []
    assert _service(name="ShimD", image={}).image_url == ""


def _photo_req(pk, *, op=None, image_id=None, with_file=True):
    data = {"pk": str(pk)}
    if op:
        data["op"] = op
    if image_id is not None:
        data["image_id"] = image_id
    req = RequestFactory().post("/dashboard/booking/services/photo-edit/", data)
    if with_file:
        req.FILES["image"] = _png()
    owner = uuid.uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    return req


def test_service_photo_edit_add_over_legacy_dict(tmp_path, settings):
    """UC4-3: op=add поверх легаси-dict — шим конвертит в список, primary цел."""
    settings.MEDIA_ROOT = str(tmp_path)
    svc = _service(name="GalA", image={"id": "x", "url": "/old.jpg", "is_primary": True})
    assert views.service_photo_edit(_photo_req(svc.pk, op="add")).status_code == 204
    svc.refresh_from_db()
    assert isinstance(svc.image, list) and len(svc.images) == 2
    assert svc.images[0]["is_primary"] and not svc.images[1]["is_primary"]
    assert svc.image_url == "/old.jpg"  # главное не сменилось


def test_service_photo_edit_remove_by_id(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    svc = _service(
        name="GalB",
        image=[
            {"id": "x", "url": "/a.jpg", "is_primary": True},
            {"id": "y", "url": "/b.jpg", "is_primary": False},
        ],
    )
    req = _photo_req(svc.pk, op="remove", image_id="x", with_file=False)
    assert views.service_photo_edit(req).status_code == 204
    svc.refresh_from_db()
    assert [i["id"] for i in svc.images] == ["y"]
    assert svc.image_url == "/b.jpg"  # primary переназначен gallery_remove


def test_service_detail_renders_media_gallery():
    """UC4-3: деталь услуги с фото — единая _media_gallery (лайтбокс)."""
    svc = _service(name="GalC", image={"id": "x", "url": "/a.jpg", "is_primary": True})
    body = public_views.service_detail(_pub_req(), pk=svc.pk).content.decode()
    assert "js-media-gallery" in body


def test_service_slots_page_uses_product_layout(settings):
    """HF-3 (#11): страница услуги — карточка товара, а не голая форма.

    Контракт: единый каркас детали (галерея слева / блок покупки справа), выбор
    времени внутри блока покупки, описание и прочие секции из реестра — ниже.
    Раньше это была узкая колонка с баннером, и владелец не узнавал в ней
    «страницу услуги»."""
    day = _future_day()
    r = _resource(type="staff")
    _rule(r, day)
    svc = _service(image={"url": "https://img.example/color.jpg"}, description="Schöne Farbe.")
    request = RequestFactory().get(f"/termin/leistung/{svc.pk}/?tag={day:%Y-%m-%d}")
    SessionMiddleware(lambda rq: None).process_request(request)
    MessageMiddleware(lambda rq: None).process_request(request)
    request.tenant = TenantFactory.build(name="Salon")
    body = public_views.service_slots(request, pk=svc.pk).content.decode()
    assert 'id="buchen"' in body  # блок покупки каркаса (и якорь мобильного buybar)
    assert 'id="svc-box"' in body  # выбор времени — внутри него
    assert body.find("https://img.example/color.jpg") < body.find('id="buchen"')  # фото слева
    assert 'data-sf-section="service_detail"' in body  # секции описания/FAQ/отзывов
    assert "Schöne Farbe." in body


def _staff_user():
    """HF-4: владелец кабинета для вьюх под @login_required."""
    tag = uuid.uuid4().hex[:8]
    return get_user_model().objects.create_user(
        username=f"o-{tag}", email=f"o-{tag}@test.de", password="pw12345678"
    )


def test_availability_calendar_shows_month_and_toggles_closed_day(settings):
    """HF-4 (#1): визуальный календарь доступности + закрытие продаж кликом.

    Движок (ClosedDate) был давно, но управлялся списком дат — владелец его не
    находил. Замок держит и картину месяца, и обратимость: повторный клик по
    закрытому дню снова открывает продажи."""
    from apps.booking.models import ClosedDate

    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r = _resource(type="staff")
    _rule(r, day)

    def _view(method="get", data=None):
        request = getattr(RequestFactory(), method)(
            "/dashboard/booking/verfuegbarkeit/", data or {}
        )
        SessionMiddleware(lambda rq: None).process_request(request)
        MessageMiddleware(lambda rq: None).process_request(request)
        request.tenant = TenantFactory.build()
        request.user = _staff_user()
        return views.availability_calendar(request)

    body = _view(data={"year": day.year, "month": day.month}).content.decode()
    assert str(day.day) in body and 'name="date"' in body  # сетка месяца с кликом

    resp = _view("post", {"date": day.isoformat()})
    assert resp.status_code == 302
    assert ClosedDate.objects.filter(date=day, resource=None).exists()  # продажи закрыты
    _view("post", {"date": day.isoformat()})
    assert not ClosedDate.objects.filter(date=day).exists()  # тот же клик открывает


def test_availability_calendar_warns_when_no_opening_hours(settings):
    """HF-4: причина витринного «keine freien Termine» называется словами."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    _resource(type="staff")  # ресурс есть, недельных правил нет
    request = RequestFactory().get("/dashboard/booking/verfuegbarkeit/")
    SessionMiddleware(lambda rq: None).process_request(request)
    MessageMiddleware(lambda rq: None).process_request(request)
    request.tenant = TenantFactory.build()
    request.user = _staff_user()
    body = views.availability_calendar(request).content.decode()
    assert "No opening hours yet" in body or "Öffnungszeiten" in body


def test_service_season_price_wins_over_base_price():
    """HF-5 (#2): цена услуги на диапазон дат перебивает базовую.

    Зеркало сезонных тарифов номера — у услуг такой возможности не было вовсе."""
    from datetime import date as _date

    from apps.booking import pricing
    from apps.booking.models import ServiceSeasonRate

    svc = _service(price_cents=4900)
    ServiceSeasonRate.objects.create(
        service=svc,
        label="Feiertage",
        start_date=_date(2026, 12, 24),
        end_date=_date(2026, 12, 26),
        price_cents=6900,
    )
    assert pricing.price_cents_for(svc, _date(2026, 12, 25)) == 6900
    assert pricing.season_label_for(svc, _date(2026, 12, 25)) == "Feiertage"
    assert pricing.price_cents_for(svc, _date(2026, 12, 27)) == 4900  # вне окна — базовая
    assert pricing.price_cents_for(svc, None) == 4900  # без даты — базовая


def test_booking_charges_the_seasonal_price(settings):
    """HF-5: сезонная цена доезжает до БРОНИ, а не только до показа.

    Это и есть смысл фичи: в праздники списывается праздничная цена."""
    from apps.booking.models import ServiceSeasonRate

    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r = _resource(type="staff")
    _rule(r, day)
    svc = _service(price_cents=4900)
    ServiceSeasonRate.objects.create(service=svc, start_date=day, end_date=day, price_cents=7900)
    starts = availability.service_slots(svc, day)
    assert starts, "нужен свободный старт для брони"
    request = RequestFactory().post(
        f"/termin/leistung/{svc.pk}/buchen/",
        {"start": starts[0].isoformat(), "name": "Gast", "email": "g@test.de"},
        REMOTE_ADDR=f"10.9.{day.day}.{day.month}",  # свой IP: rate-limit не мешает
    )
    SessionMiddleware(lambda rq: None).process_request(request)
    MessageMiddleware(lambda rq: None).process_request(request)
    request.tenant = TenantFactory.build()
    public_views.service_book(request, pk=svc.pk)
    booking = Booking.objects.filter(service=svc).order_by("-created_at").first()
    assert booking is not None and booking.price_cents == 7900


def _slot_tuple(svc, day, nth=0):
    """HF-6: (resource, start, end, price) для book_many из реальной сетки слотов.

    `nth` — номер НЕПЕРЕСЕКАЮЩЕГОСЯ периода: сетка идёт шагом 30 мин, а услуга
    длится 60 → соседние старты накладываются друг на друга и как набор
    невозможны. Берём каждый второй."""
    from apps.booking import pricing

    starts = availability.service_slots(svc, day)
    step = max(1, svc.duration_minutes // 30)
    start = starts[nth * step]
    resource = availability.assign_resource(svc, start)
    return (
        resource,
        start,
        start + timedelta(minutes=svc.duration_minutes),
        pricing.price_cents_for(svc, start.date()),
    )


def test_book_many_single_slot_is_byte_for_byte_the_old_behaviour():
    """HF-6a: один период через book_many = обычная одиночная бронь.

    Паритет-замок: группа не должна менять обычный сценарий (99 % случаев)."""
    day = _future_day()
    r = _resource(type="staff")
    _rule(r, day)
    svc = _service(price_cents=4900)
    created = services.book_many([_slot_tuple(svc, day)], name="Gast", email="g@test.de")
    assert len(created) == 1
    assert created[0].group_code == ""  # код группы не материализуется
    assert created[0].price_cents == 4900


def test_book_many_creates_group_and_is_all_or_nothing():
    """HF-6b: N периодов — одна группа; занятый период откатывает ВСЮ бронь.

    Гость не должен получать половину заказа: либо все выбранные периоды, либо
    честный отказ."""
    day = _future_day()
    r = _resource(type="staff", capacity=1)
    _rule(r, day, end="18:00")  # длинный день: хватает и на группу, и на конкурента
    svc = _service(price_cents=4900)
    slots = [_slot_tuple(svc, day, 0), _slot_tuple(svc, day, 1)]
    created = services.book_many(slots, name="Gast", email="g@test.de")
    assert len(created) == 2
    assert created[0].group_code and created[0].group_code == created[1].group_code
    before = Booking.objects.count()

    # Тот же первый период вторым гостем — занят, вся его группа откатывается.
    day2_slots = [_slot_tuple(svc, day, 2), slots[0]]  # свободный + уже занятый
    with pytest.raises(services.SlotTaken):
        services.book_many(day2_slots, name="Zweiter", email="z@test.de")
    assert Booking.objects.count() == before  # ни одной новой брони


def test_book_many_rejects_empty_and_oversized_selection():
    """HF-6b: кап на число периодов — защита от «забронировать весь день»."""
    day = _future_day()
    r = _resource(type="staff")
    _rule(r, day)
    svc = _service(price_cents=1000)
    with pytest.raises(ValueError):
        services.book_many([], name="Gast", email="g@test.de")
    one = _slot_tuple(svc, day)
    with pytest.raises(ValueError):
        services.book_many([one] * (services.MAX_GROUP_SLOTS + 1), name="G", email="g@test.de")


def test_storefront_shows_the_price_it_will_charge(settings):
    """HF-5 (доводка по ревью): показанная цена = списываемая цена.

    Дефект, найденный адверсариальным ревью: страница услуги печатала базовую
    цену, а бронь списывала сезонную. Для §1 PAngV и просто доверия это
    недопустимо — замок держит равенство."""
    from apps.booking.models import ServiceSeasonRate

    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r = _resource(type="staff")
    _rule(r, day)
    svc = _service(price_cents=4900)
    ServiceSeasonRate.objects.create(
        service=svc, label="Feiertage", start_date=day, end_date=day, price_cents=7900
    )
    request = RequestFactory().get(f"/termin/leistung/{svc.pk}/?tag={day:%Y-%m-%d}")
    SessionMiddleware(lambda rq: None).process_request(request)
    MessageMiddleware(lambda rq: None).process_request(request)
    request.tenant = TenantFactory.build(name="Salon")
    body = views_module_service_slots(request, svc)
    assert ">79,00 €<" in body or ">79.00 €<" in body  # ВИДИМАЯ цена = цена дня
    assert "Feiertage" in body  # и причина, чтобы разница не выглядела ошибкой
    # Базовая цена остаётся в data-price инлайн-редактора канвы (он правит именно
    # базовое поле услуги) — но НЕ печатается гостю как цена визита.
    assert ">49,00 €<" not in body and ">49.00 €<" not in body


def views_module_service_slots(request, svc):
    return public_views.service_slots(request, pk=svc.pk).content.decode()


def test_globally_closed_day_is_not_clickable_under_a_resource(settings):
    """Ревью HF-4: день, закрытый для всего бизнеса, нельзя «открыть» из вида
    ресурса — иначе клик плодил вторую запись, а день оставался закрытым."""
    from apps.booking.models import ClosedDate

    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    anna = _resource(type="staff")
    _rule(anna, day)
    ClosedDate.objects.create(date=day, reason="")  # глобальная блокировка

    request = RequestFactory().get(
        "/dashboard/booking/verfuegbarkeit/",
        {"year": day.year, "month": day.month, "resource": str(anna.pk)},
    )
    SessionMiddleware(lambda rq: None).process_request(request)
    MessageMiddleware(lambda rq: None).process_request(request)
    request.tenant = TenantFactory.build()
    request.user = _staff_user()
    body = views.availability_calendar(request).content.decode()
    assert f'value="{day.isoformat()}"' not in body  # кнопки нет
    assert "cursor-not-allowed" in body  # и видно, что клик не поможет


def test_seasonal_price_requires_a_price(settings):
    """Ревью HF-5: пустая цена делала услугу в эти даты бесплатной.

    Денежный дефект: `_eur_to_cents("")` → 0, ноль доезжал до брони."""
    from apps.booking.models import ServiceSeasonRate

    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    svc = _service(price_cents=4900)
    request = RequestFactory().post(
        "/dashboard/booking/leistungen/",
        {
            "action": "season_add",
            "service": str(svc.pk),
            "start_date": day.isoformat(),
            "end_date": day.isoformat(),
            "label": "Sommer",  # цену владелец оставил пустой
        },
    )
    SessionMiddleware(lambda rq: None).process_request(request)
    MessageMiddleware(lambda rq: None).process_request(request)
    request.tenant = TenantFactory.build()
    request.user = _staff_user()
    views.services_view(request)
    assert not ServiceSeasonRate.objects.filter(service=svc).exists()

    from apps.booking import pricing

    assert pricing.price_cents_for(svc, day) == 4900  # цена осталась базовой


# --- HF-6c/6d: мультивыбор времён на витрине -------------------------------------
def _slots_get(svc, day, picked=(), tag=None):
    """GET страницы слотов услуги с уже отмеченными временами (?slot=…)."""
    from urllib.parse import urlencode

    qs = urlencode([("tag", (tag or day).isoformat())] + [("slot", s.isoformat()) for s in picked])
    request = RequestFactory().get(f"/termin/leistung/{svc.pk}/?{qs}")
    SessionMiddleware(lambda rq: None).process_request(request)
    MessageMiddleware(lambda rq: None).process_request(request)
    request.tenant = TenantFactory.build()
    return public_views.service_slots(request, pk=svc.pk)


def test_slot_grid_blocks_times_that_overlap_the_picked_one(settings):
    """HF-6c: услуга длиннее шага сетки — соседние старты вместе НЕ бронируются.

    Раньше их можно было отметить, а отправка ловила отказ «время занято».
    Теперь пересекающиеся времена показаны, но не кликабельны."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r = _resource(type="staff")
    _rule(r, day, end="18:00")
    svc = _service(duration_minutes=60)  # шаг сетки 30 мин → сосед пересекается
    starts = availability.service_slots(svc, day)
    html = _slots_get(svc, day, picked=[starts[0]]).content.decode()
    assert 'data-slot="picked"' in html
    assert 'data-slot="blocked"' in html
    # соседний старт (+30 мин) в сетке есть, но кликнуть его нельзя
    neighbour = starts[1].strftime("%H:%M")
    assert 'data-slot="blocked" title=' in html and neighbour in html


def test_multi_slot_selection_posts_every_picked_time(settings):
    """HF-6c: два непересекающихся времени → две hidden-строки формы и одна группа."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r = _resource(type="staff")
    _rule(r, day, end="18:00")
    svc = _service(duration_minutes=60)
    starts = availability.service_slots(svc, day)
    picked = [starts[0], starts[2]]  # каждый второй — без пересечения
    html = _slots_get(svc, day, picked=picked).content.decode()
    assert html.count('name="start"') == 2

    request = RequestFactory().post(
        f"/termin/leistung/{svc.pk}/buchen/",
        {"start": [s.isoformat() for s in picked], "name": "Gast", "email": "g@test.de"},
        REMOTE_ADDR="10.6.1.1",
    )
    SessionMiddleware(lambda rq: None).process_request(request)
    MessageMiddleware(lambda rq: None).process_request(request)
    request.tenant = TenantFactory.build()
    public_views.service_book(request, pk=svc.pk)
    made = list(Booking.objects.filter(service=svc).order_by("start"))
    assert len(made) == 2
    assert made[0].group_code and made[0].group_code == made[1].group_code


def test_selection_survives_navigation_to_another_day(settings):
    """HF-6c: гость добирает времена на соседнем дне — набор и форма не теряются.

    Без этого выбор жил только на «своём» дне, а форма исчезала при переходе."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    other = day + timedelta(days=1)
    r = _resource(type="staff")
    _rule(r, day, end="18:00")
    _rule(r, other, end="18:00")
    svc = _service(duration_minutes=60)
    first = availability.service_slots(svc, day)[0]
    html = _slots_get(svc, other, picked=[first], tag=other).content.decode()
    assert f'value="{first.isoformat()}"' in html  # выбор дня 1 доезжает до POST
    assert 'name="start"' in html  # форма доступна, хотя на этом дне ничего не выбрано


def test_stale_and_garbage_slot_params_are_dropped(settings):
    """Мусор в ?slot= не должен ронять страницу и не должен уходить в POST."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r = _resource(type="staff")
    _rule(r, day)
    svc = _service(duration_minutes=60)
    request = RequestFactory().get(f"/termin/leistung/{svc.pk}/?tag={day}&slot=nonsense")
    SessionMiddleware(lambda rq: None).process_request(request)
    MessageMiddleware(lambda rq: None).process_request(request)
    request.tenant = TenantFactory.build()
    html = public_views.service_slots(request, pk=svc.pk).content.decode()
    assert 'data-slot="free"' in html  # страница жива
    assert 'data-slot="picked"' not in html  # мусор ничего не «выбрал»
    assert 'name="start"' not in html  # и не доехал до POST-формы


def test_confirmation_lists_every_time_of_the_group(settings):
    """HF-6d: подтверждение называет ВСЕ периоды группы, не только первый."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r = _resource(type="staff")
    _rule(r, day, end="18:00")
    svc = _service(duration_minutes=60)
    created = services.book_many(
        [_slot_tuple(svc, day, 0), _slot_tuple(svc, day, 1)], name="Gast", email="g@test.de"
    )
    request = RequestFactory().get(f"/t/{created[0].reference_code}/", REMOTE_ADDR="10.6.2.2")
    request.tenant = TenantFactory.build()
    html = public_views.termin_confirmation(
        request, code=created[0].reference_code
    ).content.decode()
    for b in created:
        assert b.start.strftime("%H:%M") in html


# --- ревью HF-6c: деньги и карта в мультислот-брони ------------------------------
def _post_group(svc, day, picked, **extra):
    """POST брони услуги на несколько времён (как шлёт форма витрины).

    IP уникален на вызов: rate-limit живёт в Redis и переживает прогоны."""
    request = RequestFactory().post(
        f"/termin/leistung/{svc.pk}/buchen/",
        {
            "start": [s.isoformat() for s in picked],
            "name": "Gast",
            "email": "g@test.de",
            **extra,
        },
        REMOTE_ADDR=f"10.7.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}",
    )
    SessionMiddleware(lambda rq: None).process_request(request)
    MessageMiddleware(lambda rq: None).process_request(request)
    request.tenant = TenantFactory.build()
    return public_views.service_book(request, pk=svc.pk)


def _two_free_starts(svc, day):
    starts = availability.service_slots(svc, day)
    step = max(1, svc.duration_minutes // 30)
    return [starts[0], starts[step]]


def test_voucher_is_spent_once_per_group_not_per_slot(settings):
    """Ревью: промокод уезжал в КАЖДЫЙ период через **kwargs.

    Одноразовый код гасился первой бронью, вторая падала PromoInvalid и откатывала
    ВСЮ транзакцию — гость видел «код недействителен» при валидном коде."""
    from apps.loyalty.models import Voucher

    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r = _resource(type="staff")
    _rule(r, day, end="18:00")
    svc = _service(price_cents=5000)
    voucher = Voucher.objects.create(code="EINMAL", label="1×", discount_cents=1000, max_uses=1)
    _post_group(svc, day, _two_free_starts(svc, day), voucher_code="EINMAL")

    made = list(Booking.objects.filter(service=svc).order_by("start"))
    assert len(made) == 2, "одноразовый код не должен ронять групповую бронь"
    voucher.refresh_from_db()
    assert voucher.used_count == 1  # гашение ровно одно
    assert [b.discount_cents for b in made] == [1000, 0]  # скидка на заказ, не на период


def test_extras_are_charged_once_per_group(settings):
    """Ревью: Extras тем же splat'ом попадали в каждую бронь и в выручку N раз."""
    from apps.core.models import Extra

    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r = _resource(type="staff")
    _rule(r, day, end="18:00")
    svc = _service(price_cents=5000)
    extra = Extra.objects.create(label="Handtuch", price_cents=300, scope="booking", is_active=True)
    _post_group(svc, day, _two_free_starts(svc, day), extra=[str(extra.pk)])

    made = list(Booking.objects.filter(service=svc).order_by("start"))
    assert len(made) == 2
    assert sum(b.extras_cents for b in made) == 300  # один раз на заказ


def test_pass_redeems_one_visit_per_period(settings):
    """Ревью: карта гасила ОДИН визит за N периодов (до 6 слотов за один визит),
    и подтверждалась только первая бронь."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r = _resource(type="staff")
    _rule(r, day, end="18:00")
    svc = _service(price_cents=5000)
    card = services.issue_pass(name="Yogi", email="y@t.de", credits=10)
    _post_group(svc, day, _two_free_starts(svc, day), pass_code=card.code)

    made = list(Booking.objects.filter(service=svc).order_by("start"))
    card.refresh_from_db()
    assert len(made) == 2
    assert card.credits_used == 2  # по визиту на период
    assert all(b.card_id == card.id for b in made)
    assert {b.status for b in made} == {"confirmed"}  # подтверждены обе


def test_naive_slot_param_does_not_crash_the_page(settings):
    """Ревью: ISO без смещения давал naive datetime → sorted() с aware-стартами
    ронял страницу в 500 вместо того, чтобы отбросить мусор."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    other = day + timedelta(days=1)
    r = _resource(type="staff")
    _rule(r, day, end="18:00")
    svc = _service(duration_minutes=60)
    good = availability.service_slots(svc, day)[0]
    from urllib.parse import urlencode

    qs = urlencode(
        [("tag", day.isoformat()), ("slot", good.isoformat()), ("slot", f"{other}T10:00:00")]
    )
    request = RequestFactory().get(f"/termin/leistung/{svc.pk}/?{qs}")
    SessionMiddleware(lambda rq: None).process_request(request)
    MessageMiddleware(lambda rq: None).process_request(request)
    request.tenant = TenantFactory.build()
    resp = public_views.service_slots(request, pk=svc.pk)
    assert resp.status_code == 200
    assert resp.content.decode().count('name="start"') == 1  # naive-мусор отброшен


def test_confirmation_shows_the_total_of_the_whole_group(settings):
    """Ревью: страница перечисляла N времён, а цену показывала за один период."""
    import re

    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r = _resource(type="staff")
    _rule(r, day, end="18:00")
    svc = _service(price_cents=5000)
    created = services.book_many(
        [_slot_tuple(svc, day, 0), _slot_tuple(svc, day, 1)],
        name="Gast",
        email="g@test.de",
        service=svc,
    )
    request = RequestFactory().get(f"/t/{created[0].reference_code}/", REMOTE_ADDR="10.7.9.9")
    request.tenant = TenantFactory.build()
    html = public_views.termin_confirmation(
        request, code=created[0].reference_code
    ).content.decode()
    prices = re.findall(r"[0-9]+[.,][0-9]{2} €", html)
    assert prices and prices[0] in ("100,00 €", "100.00 €"), prices  # 2 × 50 €


def test_confirmed_email_lists_only_confirmed_periods(settings):
    """Ревью: письмо «Reservierung bestätigt» перечисляло и неподтверждённые периоды."""
    from apps.booking.notifications import enqueue_booking_email
    from apps.notifications.models import Notification

    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r = _resource(type="staff")
    _rule(r, day, end="18:00")
    svc = _service(price_cents=5000)
    created = services.book_many(
        [_slot_tuple(svc, day, 0), _slot_tuple(svc, day, 1)], name="Gast", email="g@test.de"
    )
    BookingSM().apply(created[0], "confirmed")  # владелец подтвердил только первый
    enqueue_booking_email(created[0], "confirmed")
    note = Notification.objects.filter(type="booking_confirmed").order_by("-id").first()
    assert note is not None
    # Сверяем именно блок «Alle Termine dieser Buchung» — в теле письма время
    # второго периода могло бы совпасть с временем ОКОНЧАНИЯ первого.
    listed = [ln for ln in note.payload.get("body", "").split("\n") if ln.startswith("- ")]
    assert len(listed) == 1
    assert created[0].start.strftime("%H:%M") in listed[0]


# --- HF-7: услуга на несколько единиц времени подряд («с 8:30 до 12:30») ----------
def test_units_book_one_continuous_block(settings):
    """Фидбэк владельца: «не удаётся забронировать услугу на несколько единиц
    времени». ?dauer=4 → ОДНА бронь длиной 4×услуга и цена ×4."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r = _resource(type="staff")
    _rule(r, day, start="08:30", end="18:00")
    svc = _service(duration_minutes=60, price_cents=2500)
    starts = availability.service_slots(svc, day, duration_minutes=240)
    assert starts, "нужен старт, куда влезает 4 часа"
    request = RequestFactory().post(
        f"/termin/leistung/{svc.pk}/buchen/",
        {"start": starts[0].isoformat(), "dauer": "4", "name": "Gast", "email": "g@test.de"},
        REMOTE_ADDR=f"10.8.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}",
    )
    SessionMiddleware(lambda rq: None).process_request(request)
    MessageMiddleware(lambda rq: None).process_request(request)
    request.tenant = TenantFactory.build()
    public_views.service_book(request, pk=svc.pk)
    made = list(Booking.objects.filter(service=svc))
    assert len(made) == 1
    assert made[0].end - made[0].start == timedelta(minutes=240)
    assert made[0].price_cents == 2500 * 4


def test_units_grid_only_offers_starts_where_the_whole_block_fits(settings):
    """Сетка при ?dauer=N считается на ВЕСЬ отрезок: старт без места под него
    не предлагается (иначе гость упёрся бы в отказ на отправке)."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r = _resource(type="staff")
    _rule(r, day, start="09:00", end="12:00")  # окно 3 часа
    svc = _service(duration_minutes=60)
    assert len(availability.service_slots(svc, day, duration_minutes=60)) > 0
    assert availability.service_slots(svc, day, duration_minutes=240) == []  # 4 ч не влезают

    html = _slots_get(svc, day).content.decode()
    assert 'href="?tag=' in html and "dauer=2" in html  # чип 2× доступен
    assert "dauer=4" not in html  # недостижимая длительность не предлагается


def test_units_parse_is_capped_and_garbage_safe(settings):
    """Мусор/вне капа в ?dauer= → 1 (прежнее поведение байт-в-байт)."""
    assert public_views._parse_units("3") == 3
    assert public_views._parse_units("0") == 1
    assert public_views._parse_units("999") == public_views.MAX_UNITS
    assert public_views._parse_units("abc") == 1
    assert public_views._parse_units(None) == 1


def test_detail_page_carries_the_picker(settings):
    """HF-7: /leistung/<pk>/ показывает календарь и времена сразу — без второй
    страницы и без перезагрузки по кнопке."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r = _resource(type="staff")
    _rule(r, day, end="18:00")
    svc = _service()
    request = RequestFactory().get(f"/leistung/{svc.pk}/?tag={day}")
    SessionMiddleware(lambda rq: None).process_request(request)
    MessageMiddleware(lambda rq: None).process_request(request)
    request.tenant = TenantFactory.build()
    html = public_views.service_detail(request, pk=svc.pk).content.decode()
    assert 'id="svc-box"' in html
    assert 'data-slot="free"' in html
