"""Track D / D3b: публичная запись /termin/ — сетка слотов, выбор, бронь,
валидация слота по расписанию, гейтинг модуля."""

import uuid
from datetime import date, datetime, time, timedelta

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory
from django.utils import timezone

from apps.booking import availability, public_views, services
from apps.booking.models import AvailabilityRule, Booking, ClosedDate, Resource, Service
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

DAY = timezone.localdate() + timedelta(days=7)  # заведомо в будущем, чтобы утренние
# слоты не отсеивались фильтром «прошедшего времени сегодня» (availability.free_slots)
# при прогоне после 10:00. Раньше был жёстко date(2026,7,1) — «сегодня» его догнало.


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _resource(slot_minutes=60, capacity=1):
    resource = Resource.objects.create(name=f"Tisch {uuid.uuid4().hex[:6]}", capacity=capacity)
    AvailabilityRule.objects.create(
        resource=resource,
        weekday=DAY.weekday(),
        start_time=time(10, 0),
        end_time=time(13, 0),
        slot_minutes=slot_minutes,
    )
    return resource


def _req(method="get", path="/termin/", data=None, tenant=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.9"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant if tenant is not None else TenantFactory.build(business_type="cafe")
    return request


# --- сетка слотов ------------------------------------------------------------------


def _customer():
    from apps.promotions.models import Customer

    return Customer.objects.create(name="Gast")


def test_free_slots_grid_and_occupancy():
    resource = _resource()
    slots = availability.free_slots(resource, DAY)
    assert [(s.hour, e.hour) for s, e in slots] == [(10, 11), (11, 12), (12, 13)]

    # занять середину — слот пропадает из сетки
    start, end = slots[1]
    Booking.objects.create(
        resource=resource,
        customer=_customer(),
        reference_code="T-TEST01",
        start=start,
        end=end,
    )
    remaining = availability.free_slots(resource, DAY)
    assert [(s.hour, e.hour) for s, e in remaining] == [(10, 11), (12, 13)]


def test_free_slots_closed_date_and_other_weekday():
    resource = _resource()
    assert availability.free_slots(resource, DAY + timedelta(days=1)) == []  # нет правила
    ClosedDate.objects.create(resource=None, date=DAY, reason="Feiertag")
    assert availability.free_slots(resource, DAY) == []


# --- A3: визуальный календарь слотов ----------------------------------------------
def test_slot_month_helper_marks_days_by_check():
    """A3: `_slot_month` зовёт check только в окне [today, max_day]; помечает has_slots."""
    today = date(2026, 6, 30)
    max_day = today + timedelta(days=30)
    ctx = public_views._slot_month(lambda d: d.weekday() == 2, date(2026, 7, 1), today, max_day)
    by_day = {c["day"]: c for c in ctx["cal_days"]}
    assert by_day[date(2026, 7, 1)]["has_slots"] is True  # среда — check вернул True
    assert by_day[date(2026, 7, 2)]["has_slots"] is False  # четверг
    assert ctx["cal_first"] == date(2026, 7, 1)
    assert ctx["cal_show_prev"] is True and ctx["cal_show_next"] is False  # окно ≤ 30 дн.


def test_slot_calendar_renders_available_day_clickable():
    """A3: в календаре день со свободным слотом — ссылка ?tag=; месяц виден."""
    resource = _resource()  # правило только на DAY.weekday() (среда)
    today = timezone.localdate()
    target = today + timedelta(days=8)  # не примыкает к today (не путать с prev/next day)
    while target.weekday() != DAY.weekday():
        target += timedelta(days=1)
    cal = f"{target.year}-{target.month:02d}"
    body = public_views.termin_slots(_req(data={"cal": cal}), pk=resource.pk).content.decode()
    assert f"?tag={target.isoformat()}" in body  # доступный день кликабелен
    assert "grid-cols-7" in body  # календарь-сетка отрендерилась


# --- A4: iframe-виджет (embed-режим) ----------------------------------------------
def test_slots_embed_sets_xframe_exempt_and_carries_embed():
    resource = _resource()
    resp = public_views.termin_slots(_req(data={"embed": "1"}), pk=resource.pk)
    assert getattr(resp, "xframe_options_exempt", False) is True
    assert "embed=1" in resp.content.decode()  # ссылки/форма несут embed
    plain = public_views.termin_slots(_req(), pk=resource.pk)
    assert getattr(plain, "xframe_options_exempt", False) is False
    assert "embed=1" not in plain.content.decode()  # без embed — чисто


def test_index_single_resource_redirect_keeps_embed():
    _resource()  # один ресурс, без услуг/абонементов → redirect к слотам
    resp = public_views.termin_index(_req(data={"embed": "1"}))
    assert resp.status_code == 302 and "embed=1" in resp.url


def test_book_honeypot_redirect_keeps_embed():
    resource = _resource()
    resp = public_views.termin_book(
        _req("post", data={"embed": "1", "website": "bot"}), pk=resource.pk
    )
    assert resp.status_code == 302 and "embed=1" in resp.url


def test_book_success_redirects_to_confirmation_with_embed():
    resource = _resource()
    start, end = availability.free_slots(resource, DAY)[0]
    resp = public_views.termin_book(
        _req(
            "post",
            data={
                "embed": "1",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "name": "Gast",
                "party_size": "2",
            },
        ),
        pk=resource.pk,
    )
    assert resp.status_code == 302 and "embed=1" in resp.url  # → подтверждение в iframe


# --- публичный флоу ----------------------------------------------------------------


def test_index_redirects_with_single_resource():
    resource = _resource()
    response = public_views.termin_index(_req())
    assert response.status_code == 302 and str(resource.pk) in response.url


def test_slots_page_renders_and_selects():
    resource = _resource()
    start_iso = availability.free_slots(resource, DAY)[0][0].isoformat()
    body = public_views.termin_slots(
        _req(path=f"/termin/{resource.pk}/", data={"tag": DAY.isoformat()}), pk=resource.pk
    ).content.decode()
    assert "10:00" in body and "12:00" in body

    body = public_views.termin_slots(
        _req(
            path=f"/termin/{resource.pk}/",
            data={"tag": DAY.isoformat(), "slot": start_iso},
        ),
        pk=resource.pk,
    ).content.decode()
    assert 'name="start"' in body and "Book now" in body


# --- G9: групповые курсы (видимая вместимость) ------------------------------------


def test_free_slots_with_spots_counts_remaining():
    resource = _resource(capacity=3)
    slots = availability.free_slots_with_spots(resource, DAY)
    assert slots and all(spots == 3 for _s, _e, spots in slots)
    start, end, _ = slots[0]
    Booking.objects.create(
        resource=resource, customer=_customer(), reference_code="T-GRP001", start=start, end=end
    )
    after = availability.free_slots_with_spots(resource, DAY)
    assert next(sp for s, _e, sp in after if s == start) == 2  # одно место занято


def test_group_slots_page_shows_spots():
    resource = _resource(capacity=3)
    body = public_views.termin_slots(
        _req(path=f"/termin/{resource.pk}/", data={"tag": DAY.isoformat()}), pk=resource.pk
    ).content.decode()
    assert "Group course" in body and "3 spots" in body  # int-счётчик локаль-стабилен


def test_party_size_counts_as_spots_when_flag_on():
    resource = _resource(capacity=5)
    resource.counts_party_size = True
    resource.save()
    start, end, _ = availability.free_slots_with_spots(resource, DAY)[0]
    services.book(resource, start=start, end=end, name="A", party_size=3)
    spots = next(
        sp for s, _e, sp in availability.free_slots_with_spots(resource, DAY) if s == start
    )
    assert spots == 2  # 5 − 3 занятых
    with pytest.raises(services.SlotTaken):  # ещё 3 не влезут (3+3 > 5)
        services.book(resource, start=start, end=end, name="B", party_size=3)


def test_party_size_ignored_when_flag_off():
    resource = _resource(capacity=2)  # counts_party_size False — бронь = 1 единица
    start, end, _ = availability.free_slots_with_spots(resource, DAY)[0]
    services.book(resource, start=start, end=end, name="A", party_size=9)
    services.book(resource, start=start, end=end, name="B", party_size=9)  # 2-я ок
    with pytest.raises(services.SlotTaken):  # capacity 2 исчерпана по числу броней
        services.book(resource, start=start, end=end, name="C", party_size=1)


def test_book_flow_creates_booking():
    resource = _resource()
    start, end = availability.free_slots(resource, DAY)[0]
    request = _req(
        "post",
        f"/termin/{resource.pk}/buchen/",
        {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "name": "Karla",
            "email": "karla@test.de",
            "party_size": "3",
        },
    )
    response = public_views.termin_book(request, pk=resource.pk)
    assert response.status_code == 302
    booking = Booking.objects.get(customer__email="karla@test.de")
    assert response.url.endswith(f"/t/{booking.reference_code}/")
    assert booking.party_size == 3 and booking.start == start

    body = public_views.termin_confirmation(_req(), code=booking.reference_code).content.decode()
    assert booking.reference_code in body

    # слот исчез из сетки; повторная попытка отбрасывается валидацией
    response = public_views.termin_book(request, pk=resource.pk)
    assert response.status_code == 302 and "/termin/" in response.url
    assert Booking.objects.count() == 1


def test_book_rejects_interval_outside_schedule():
    resource = _resource()
    tz = timezone.get_current_timezone()
    start = datetime.combine(DAY, time(22, 0), tzinfo=tz)  # вне рабочего окна
    request = _req(
        "post",
        f"/termin/{resource.pk}/buchen/",
        {
            "start": start.isoformat(),
            "end": (start + timedelta(hours=1)).isoformat(),
            "name": "Hacker",
        },
    )
    response = public_views.termin_book(request, pk=resource.pk)
    assert response.status_code == 302 and Booking.objects.count() == 0


def test_booking_module_gated():
    tenant = TenantFactory.build(disabled_modules=["booking"])
    with pytest.raises(Http404):
        public_views.termin_index(_req(tenant=tenant))
    resource = _resource()
    with pytest.raises(Http404):
        public_views.termin_slots(_req(tenant=tenant), pk=resource.pk)


# --- P2.5b: депозит ----------------------------------------------------------------


def _resource_with_deposit(cents=1000):
    resource = _resource()
    resource.deposit_cents = cents
    resource.save(update_fields=["deposit_cents"])
    return resource


def test_book_with_deposit_redirects_to_stripe(monkeypatch, settings):
    settings.STRIPE_LIVE_MODE = False
    settings.STRIPE_TEST_SECRET_KEY = "sk_test_x"
    settings.STRIPE_CONNECT_CLIENT_ID = "ca_x"
    resource = _resource_with_deposit()
    tenant = TenantFactory.build(
        business_type="cafe", payments_enabled=True, stripe_connect_id="acct_1"
    )
    start, end = availability.free_slots(resource, DAY)[0]
    monkeypatch.setattr(
        public_views.payments, "deposit_checkout_url", lambda b, t, **kw: "https://stripe/checkout"
    )
    request = _req(
        "post",
        f"/termin/{resource.pk}/buchen/",
        {"start": start.isoformat(), "end": end.isoformat(), "name": "Karla", "email": "k@test.de"},
        tenant=tenant,
    )
    response = public_views.termin_book(request, pk=resource.pk)
    assert response.status_code == 302
    assert response.url == "https://stripe/checkout"
    booking = Booking.objects.get(customer__email="k@test.de")
    assert booking.payment_state == "pending"
    assert booking.deposit_cents == 1000


def test_book_with_deposit_but_no_payments_is_normal(monkeypatch):
    resource = _resource_with_deposit()
    tenant = TenantFactory.build(business_type="cafe", payments_enabled=False)
    start, end = availability.free_slots(resource, DAY)[0]
    called = {"stripe": False}
    monkeypatch.setattr(
        public_views.payments,
        "deposit_checkout_url",
        lambda b, t, **kw: called.__setitem__("stripe", True) or "x",
    )
    request = _req(
        "post",
        f"/termin/{resource.pk}/buchen/",
        {"start": start.isoformat(), "end": end.isoformat(), "name": "Ben", "email": "b@test.de"},
        tenant=tenant,
    )
    response = public_views.termin_book(request, pk=resource.pk)
    booking = Booking.objects.get(customer__email="b@test.de")
    assert response.url.endswith(f"/t/{booking.reference_code}/")  # обычная бронь
    assert called["stripe"] is False
    assert booking.payment_state == "none"


# --- UA1-1 (E-1): страница-деталь услуги (сплит: деталь → CTA на слот-пикер) --------


def _service(**kw):
    defaults = dict(
        name="Ölwechsel",
        description="Inkl. Öl und Filter.",
        duration_minutes=30,
        price_cents=4900,
        is_active=True,
    )
    defaults.update(kw)
    return Service.objects.create(**defaults)


def test_service_detail_renders_with_cta_to_slots():
    service = _service()
    body = public_views.service_detail(
        _req(path=f"/leistung/{service.pk}/"), pk=service.pk
    ).content.decode()
    assert "Ölwechsel" in body  # название
    assert "Inkl. Öl und Filter." in body  # описание (богатая карточка)
    # primary-CTA ведёт на слот-пикер брони, а НЕ бронирует прямо на детали
    assert f"/termin/leistung/{service.pk}/" in body
    assert "Jetzt buchen" in body  # подпись действия покупки (booking)


def test_service_detail_shows_anfrage_only_when_jobs_active():
    service = _service()
    # дефолтный тенант: jobs активен → вторичная кнопка «запрос сметы» (A7/A9)
    body_on = public_views.service_detail(
        _req(path=f"/leistung/{service.pk}/"), pk=service.pk
    ).content.decode()
    assert "/anfrage/" in body_on

    tenant_off = TenantFactory.build(business_type="cafe", disabled_modules=["jobs"])
    body_off = public_views.service_detail(
        _req(path=f"/leistung/{service.pk}/", tenant=tenant_off), pk=service.pk
    ).content.decode()
    assert "/anfrage/" not in body_off


def test_service_detail_default_primary_is_booking_slots():
    """UA3-1: без override primary = бронь слота (в aside слот-ссылка раньше Anfrage)."""
    service = _service()
    body = public_views.service_detail(
        _req(path=f"/leistung/{service.pk}/"), pk=service.pk
    ).content.decode()
    aside = body[body.find('id="buchen"') :]  # только колонка действий (не nav)
    idx_slots = aside.find(f"/termin/leistung/{service.pk}/")
    idx_anfrage = aside.find("/anfrage/")
    assert idx_slots != -1 and idx_anfrage != -1
    assert idx_slots < idx_anfrage  # бронь — первичная (выше Anfrage)


def test_service_detail_primary_action_request_override():
    """UA3-1 (реш.2): tenant override 'request' + jobs → primary = Anfrage (выше слота)."""
    service = _service()
    tenant = TenantFactory.build(
        business_type="cafe", site_config={"primary_service_cta": "request"}
    )
    body = public_views.service_detail(
        _req(path=f"/leistung/{service.pk}/", tenant=tenant), pk=service.pk
    ).content.decode()
    aside = body[body.find('id="buchen"') :]
    idx_anfrage = aside.find("/anfrage/")
    idx_slots = aside.find(f"/termin/leistung/{service.pk}/")
    assert idx_anfrage != -1 and idx_slots != -1
    assert idx_anfrage < idx_slots  # Anfrage — первичная (выше брони)


def test_service_detail_buybox_exact_ctas():
    """UA3-1 слайс 2 (шаг 0): точные href обоих CTA внутри #buchen — паритет-замок
    перед сводом buy-box на единый _buybox.html."""
    service = _service()
    body = public_views.service_detail(
        _req(path=f"/leistung/{service.pk}/"), pk=service.pk
    ).content.decode()
    aside = body[body.find('id="buchen"') :]
    assert f'href="/termin/leistung/{service.pk}/"' in aside
    assert 'href="/anfrage/"' in aside


def test_service_detail_renders_attributes_and_faq():
    """UA4-3: богатая карточка — атрибуты + FAQ на детали услуги (секции-хуки)."""
    service = _service(
        attributes=["Kostenlos & unverbindlich", "Meisterbetrieb"],
        faq=[{"q": "Was kostet das?", "a": "Nichts."}],
    )
    body = public_views.service_detail(
        _req(path=f"/leistung/{service.pk}/"), pk=service.pk
    ).content.decode()
    assert "Meisterbetrieb" in body
    assert 'data-sf-section="service_attributes"' in body
    assert "Was kostet das?" in body and "Nichts." in body
    assert 'data-sf-section="service_faq"' in body


def test_service_detail_no_rich_sections_when_empty():
    service = _service()  # без attributes/faq
    body = public_views.service_detail(
        _req(path=f"/leistung/{service.pk}/"), pk=service.pk
    ).content.decode()
    assert 'data-sf-section="service_attributes"' not in body
    assert 'data-sf-section="service_faq"' not in body


def test_service_detail_renders_localized_name_en():
    """L3c: под локалью EN показываем перевод name_i18n; под базой — плоское имя."""
    from django.utils import translation

    service = _service(
        name="Ölwechsel",
        description="Öl + Filter",
        name_i18n={"en": "Oil change"},
        description_i18n={"en": "Oil + filter"},
    )
    with translation.override("en"):
        body_en = public_views.service_detail(
            _req(path=f"/leistung/{service.pk}/"), pk=service.pk
        ).content.decode()
    assert "Oil change" in body_en and "Oil + filter" in body_en

    body_de = public_views.service_detail(
        _req(path=f"/leistung/{service.pk}/"), pk=service.pk
    ).content.decode()
    assert "Ölwechsel" in body_de and "Oil change" not in body_de  # база под дефолтом


def test_service_detail_module_gated():
    service = _service()
    tenant = TenantFactory.build(disabled_modules=["booking"])
    with pytest.raises(Http404):
        public_views.service_detail(_req(tenant=tenant), pk=service.pk)


def test_service_index_card_links_to_detail_not_slots():
    service = _service()
    body = public_views.termin_index(_req()).content.decode()
    # карточка листинга услуг ведёт на деталь (сплит), а не сразу на слоты
    assert f"/leistung/{service.pk}/" in body


def test_service_index_on_listing_skeleton_has_sf_section_marker():
    # UB1-1: листинг услуг на каркасе listing.html; обёртка грида размечена для
    # on-canvas редактора (подсветка/клик секции), CTA абонементов не потерян.
    _service()
    from apps.booking.models import PassPlan

    PassPlan.objects.create(label="10er-Karte", credits=10, price_cents=9000, is_active=True)
    body = public_views.termin_index(_req()).content.decode()
    assert 'data-sf-section="services"' in body
    assert "/karten/" in body  # listing_after: ссылка на Mehrfachkarte


def test_service_index_legacy_grid_without_layout_key():
    # UB1-1: без service_index_layout в конфиге витрина держит прежний хардкод-грид
    # (пиксельная неизменность), движковые классы не подмешиваются.
    _service()
    body = public_views.termin_index(_req()).content.decode()
    assert "grid sm:grid-cols-2 gap-4 max-w-3xl" in body


def test_service_index_layout_from_config():
    # UB1-1: заданный пресет → грид из layout-движка (grid_class_string), легаси уходит.
    _service()
    request = _req()
    request.tenant.site_config = {"service_index_layout": {"preset": "cols3"}}
    body = public_views.termin_index(request).content.decode()
    assert "lg:grid-cols-3" in body
    assert "max-w-3xl" not in body


def test_service_index_layout_from_preview_draft():
    # UB1-1: при ?preview=1 черновик канвы из сессии перекрывает сохранённый конфиг.
    _service()
    request = _req(data={"preview": "1"})
    request.session["site_preview_draft"] = {"service_index_layout": {"preset": "cols4"}}
    body = public_views.termin_index(request).content.decode()
    assert "lg:grid-cols-4" in body


def test_service_detail_inline_edit_anchors_present():
    service = _service()
    body = public_views.service_detail(
        _req(path=f"/leistung/{service.pk}/"), pk=service.pk
    ).content.decode()
    assert 'data-edit-model="service"' in body  # инлайн-правка на канве
    assert 'data-edit-field="name"' in body
    assert 'data-edit-field="description"' in body
    assert "data-price-edit" in body
    assert "data-photo-edit" in body


def test_service_index_search_and_sort():
    """UB2-2: поиск ?q= (i18n icontains) и сортировка на листинге услуг; пустая
    выдача поиска НЕ переключает на листинг ресурсов."""
    _service(name="Ölwechsel", price_cents=9000)  # дефолт-описание тоже с «Öl»
    _service(name="Bremsen prüfen", description="Bremsflüssigkeit neu", price_cents=1000)
    body = public_views.termin_index(_req(data={"q": "öl"})).content.decode()
    assert "Ölwechsel" in body and "Bremsen" not in body
    assert "data-listing-toolbar" in body  # тулбар каркаса отрендерен
    body_none = public_views.termin_index(_req(data={"q": "zzz"})).content.decode()
    assert "Nothing found" in body_none  # empty-state, не booking_index
    body_sorted = public_views.termin_index(_req(data={"sort": "price_asc"})).content.decode()
    assert body_sorted.index("Bremsen") < body_sorted.index("Ölwechsel")
