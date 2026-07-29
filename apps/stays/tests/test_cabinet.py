"""Track E / E2: кабинет date-range-броней — календарь загрузки, действия по
FSM, перенос дат, ручная бронь, управление юнитами и блокировками."""

import re
import uuid
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.stays import services, views
from apps.stays.models import StayBooking, StayUnit, UnitBlock
from apps.stays.state_machine import StayBookingSM
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

D0 = date(2026, 9, 1)


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", path="/dashboard/stays/", data=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    return request


def _unit(**kwargs):
    kwargs.setdefault("price_cents", 8000)
    return StayUnit.objects.create(name=f"Zimmer {uuid.uuid4().hex[:6]}", **kwargs)


def _book(unit, arr_off, dep_off, **kwargs):
    kwargs.setdefault("name", "Gast")
    return services.book_stay(
        unit,
        arrival=D0 + timedelta(days=arr_off),
        departure=D0 + timedelta(days=dep_off),
        **kwargs,
    )


# --- календарь --------------------------------------------------------------------


def test_calendar_renders_grid_and_booking():
    unit = _unit()
    booking = _book(unit, 1, 4)
    body = views.calendar(_req(data={"von": D0.isoformat()})).content.decode()
    assert unit.name in body
    assert booking.reference_code in body


def test_calendar_transition_rule_hides_action_button():
    """FB-3: скрытие перехода pending→confirmed убирает КНОПКУ действия в карточке
    брони под календарём (фидбэк 2026-07-28: список броней и панели статусов с
    календаря убраны — дубль доски). FSM не трогаем — apply разрешает переход."""
    unit = _unit()
    b = _book(unit, 1, 4)  # pending → есть кнопка «Bestätigen» (value=confirmed)
    req = _req(data={"von": D0.isoformat(), "buchung": str(b.pk)})
    req.tenant = TenantFactory(site_config={})
    assert 'value="confirmed"' in views.calendar(req).content.decode()  # дефолт: кнопка есть
    req2 = _req(data={"von": D0.isoformat(), "buchung": str(b.pk)})
    req2.tenant = TenantFactory(site_config={"transitions": {"stay": {"pending": []}}})
    body2 = views.calendar(req2).content.decode()
    assert 'value="confirmed"' not in body2  # переход скрыт → кнопки нет
    # панелей статусов/списка броней на календаре больше нет (они на доске)
    assert "Statusübergänge" not in body2
    assert "Bookings in this period" not in body2


def test_calendar_is_lean_but_keeps_walkin_and_booking_panel():
    """Фидбэк 2026-07-28: календарь = шахматка + карточка брони по клику +
    walk-in форма (добавить бронь / заблокировать даты). Списка броней и
    hub-табов нет; «＋ Buchung» — своя страница только с формой."""
    unit = _unit()
    _book(unit, 1, 4)
    body = views.calendar(_req(data={"von": D0.isoformat()})).content.decode()
    assert 'id="walkin-form"' in body and 'value="block"' in body  # бронь + блокировка
    assert 'id="booking-panel"' in body
    assert "Bookings in this period" not in body
    # отдельная страница добавления: только форма
    page = views.stay_new(_req(path="/dashboard/stays/neu/")).content.decode()
    assert 'id="walkin-form"' in page and 'id="belegungsplan"' not in page


# --- действия по FSM + перенос ----------------------------------------------------


def test_action_confirm_then_move_conflict_then_free():
    unit = _unit()
    first = _book(unit, 0, 3, email="x1@t.de")
    second = _book(unit, 5, 7, email="x2@t.de")

    resp = views.stay_action(_req("post", data={"action": "confirmed"}), pk=first.pk)
    assert resp.status_code == 302
    first.refresh_from_db()
    assert first.status == "confirmed"

    # перенос second на занятый диапазон first — даты не меняются
    views.stay_action(
        _req(
            "post",
            data={
                "action": "move",
                "arrival": D0.isoformat(),
                "departure": (D0 + timedelta(days=2)).isoformat(),
            },
        ),
        pk=second.pk,
    )
    second.refresh_from_db()
    assert second.arrival == D0 + timedelta(days=5)

    # перенос на свободный диапазон — ок
    views.stay_action(
        _req(
            "post",
            data={
                "action": "move",
                "arrival": (D0 + timedelta(days=10)).isoformat(),
                "departure": (D0 + timedelta(days=12)).isoformat(),
            },
        ),
        pk=second.pk,
    )
    second.refresh_from_db()
    assert second.arrival == D0 + timedelta(days=10)


# --- ручная бронь -----------------------------------------------------------------


def test_manual_create_is_confirmed():
    unit = _unit()
    resp = views.stay_create(
        _req(
            "post",
            "/dashboard/stays/new/",
            {
                "unit": str(unit.pk),
                "arrival": D0.isoformat(),
                "departure": (D0 + timedelta(days=2)).isoformat(),
                "name": "Telefon-Gast",
                "guests": "2",
            },
        )
    )
    assert resp.status_code == 302
    booking = StayBooking.objects.get(unit=unit)
    assert booking.status == "confirmed"
    assert booking.nights == 2
    assert booking.source_channel == "manual"


def test_manual_create_rejects_occupied():
    unit = _unit()
    _book(unit, 0, 3)
    views.stay_create(
        _req(
            "post",
            "/dashboard/stays/new/",
            {
                "unit": str(unit.pk),
                "arrival": D0.isoformat(),
                "departure": (D0 + timedelta(days=2)).isoformat(),
                "name": "Zweitgast",
            },
        )
    )
    assert StayBooking.objects.filter(unit=unit).count() == 1  # второй не создан


# --- юниты + блокировки -----------------------------------------------------------


def test_units_page_creates_unit_and_block():
    resp = views.units(
        _req(
            "post",
            "/dashboard/stays/units/",
            {
                "action": "unit",
                "name": "Ferienwohnung Süd",
                "type": "apartment",
                "price_eur": "95,50",
                "quantity": "2",
                "min_nights": "3",
                "max_guests": "4",
                "deposit_eur": "50",
            },
        )
    )
    assert resp.status_code == 302
    unit = StayUnit.objects.get(name="Ferienwohnung Süd")
    assert unit.price_cents == 9550
    assert unit.quantity == 2 and unit.min_nights == 3 and unit.max_guests == 4
    assert unit.deposit_cents == 5000

    views.units(
        _req(
            "post",
            "/dashboard/stays/units/",
            {
                "action": "block",
                "unit": str(unit.pk),
                "start_date": D0.isoformat(),
                "end_date": (D0 + timedelta(days=2)).isoformat(),
                "reason": "Renovierung",
            },
        )
    )
    block = UnitBlock.objects.get(unit=unit)
    assert block.reason == "Renovierung"

    body = views.units(_req(path="/dashboard/stays/units/")).content.decode()
    assert "Ferienwohnung Süd" in body  # компактная строка списка
    # блокировки — на странице номера (список компактен)
    page = views.units(_req(), pk=unit.pk).content.decode()
    assert "Renovierung" in page


def test_unit_settings_saves_deposit():
    unit = _unit()
    views.units(
        _req(
            "post",
            "/dashboard/stays/units/",
            {
                "action": "unit_settings",
                "unit": str(unit.pk),
                "price_eur": "120",
                "quantity": "1",
                "min_nights": "2",
                "max_guests": "3",
                "deposit_eur": "30,00",
                "require_manual_confirm": "on",
            },
        )
    )
    unit.refresh_from_db()
    assert unit.price_cents == 12000 and unit.deposit_cents == 3000
    assert unit.min_nights == 2 and unit.require_manual_confirm is True


# --- P2.5b-аналог: отмена оплаченной возвращает депозит (E4 wires Stripe) ----------


def test_cancel_paid_stay_refunds(monkeypatch):
    unit = _unit(deposit_cents=5000)
    booking = _book(unit, 1, 4)
    StayBookingSM().apply(booking, "confirmed")
    booking.payment_state = StayBooking.PAYMENT_PAID
    booking.stripe_payment_intent = "pi_x"
    booking.save(update_fields=["payment_state", "stripe_payment_intent"])
    captured = {}
    monkeypatch.setattr(views.connect, "refund", lambda **kw: captured.update(kw))
    request = _req("post", data={"action": "cancelled"})
    request.tenant = TenantFactory.build(stripe_connect_id="acct_1")
    views.stay_action(request, pk=booking.pk)
    booking.refresh_from_db()
    assert booking.status == "cancelled"
    assert booking.payment_state == StayBooking.PAYMENT_REFUNDED
    assert captured == {"connect_id": "acct_1", "payment_intent": "pi_x"}


def test_invoice_action_creates_draft(monkeypatch):
    unit = _unit(price_cents=10700)
    booking = _book(unit, 1, 2, email="g@test.de")
    StayBookingSM().apply(booking, "confirmed")
    request = _req("post", data={"action": "invoice"})
    request.tenant = TenantFactory.build(small_business=False)
    monkeypatch.setattr(request.tenant, "is_module_active", lambda m: m == "finance")
    resp = views.stay_action(request, pk=booking.pk)
    assert resp.status_code == 302 and "/rechnungen/" in resp.url
    booking.refresh_from_db()
    assert booking.invoice_id is not None


def test_invoice_action_blocked_when_finance_off(monkeypatch):
    from apps.finance.models import Invoice

    unit = _unit()
    booking = _book(unit, 1, 2)
    StayBookingSM().apply(booking, "confirmed")
    request = _req("post", data={"action": "invoice"})
    request.tenant = TenantFactory.build()
    monkeypatch.setattr(request.tenant, "is_module_active", lambda m: False)
    views.stay_action(request, pk=booking.pk)
    assert not Invoice.objects.exists()


def test_reports_view_renders(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    unit = _unit(price_cents=10000, quantity=2)
    _book(unit, 1, 4)  # бронь в текущем окне (book_stay)
    resp = views.reports(_req(path="/dashboard/stays/reports/"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "RevPAR" in body and "%" in body


# --- FB-11: карточка брони (кто/когда/сумма/оплата) --------------------------------


def test_booking_detail_renders_guest_dates_money_actions():
    """FB-11: деталь брони — гость (имя/email), даты/ночи, сумма, статус-действия;
    календарь линкует на неё; manage_url доски ведёт сюда же (UD1)."""
    unit = _unit(price_cents=9000)
    booking = _book(unit, 1, 4, email="gast@test.de", phone="0170 123")
    body = views.booking_detail(_req(), booking.pk).content.decode()
    assert booking.reference_code in body and unit.name in body
    assert "gast@test.de" in body  # контакт гостя
    assert "270" in body  # 3 ночи × 90 € = 270.00 € (сумма на карточке)
    assert 'kind="stay"' not in body  # партиал отрендерен, не сырой тег
    assert "Meldeschein" in body  # секция G6 присутствует
    # календарь линкует код брони на деталь
    cal = views.calendar(_req(data={"von": D0.isoformat()})).content.decode()
    assert f"/dashboard/stays/buchung/{booking.pk}/" in cal
    # доска (UD1): manage_url карточки — деталь брони
    from apps.core.transactions import transaction_for

    tx = transaction_for("stay", booking)
    assert tx.manage_url == f"/dashboard/stays/buchung/{booking.pk}/"


def test_booking_detail_shows_meldeschein_when_filled():
    from apps.stays.models import GuestRegistration

    unit = _unit()
    booking = _book(unit, 2, 5)
    GuestRegistration.objects.create(
        booking=booking, last_name="Muster", first_name="Max", nationality="DE"
    )
    body = views.booking_detail(_req(), booking.pk).content.decode()
    assert "Max Muster" in body


def test_booking_detail_shows_custom_status_label():
    """FB-4b: своё имя статуса брони (site_config['status_labels']['stay']) — в кабинете.
    FSM/дефолт не трогаем: без своего имени показался бы get_status_display()."""
    unit = _unit()
    booking = _book(unit, 1, 4)  # pending
    req = _req()
    req.tenant = TenantFactory(site_config={"status_labels": {"stay": {"pending": "Angefragt ⭐"}}})
    body = views.booking_detail(req, booking.pk).content.decode()
    assert "Angefragt ⭐" in body


# --- FB-10/11: сумма в письмах брони ------------------------------------------------


def test_stay_emails_include_total():
    """Подтверждение/заявка клиенту и письмо владельцу содержат Gesamtpreis."""
    from apps.stays.notifications import _render

    unit = _unit(price_cents=9000)
    booking = _book(unit, 1, 4, email="gast@test.de")
    ctx = {
        "booking": booking,
        "unit": unit,
        "customer": booking.customer,
        "cancel_url": "",
        "unsubscribe_url": "",
    }
    for tpl in ("stay_created", "stay_confirmed", "stay_owner"):
        _subj, body, _html = _render(tpl, ctx)
        assert "270" in body, tpl  # 3 × 90 €


def test_stay_emails_include_checkin_link_until_signed():
    """G6-фикс (PMS-аудит 2026-07-27): подтверждение и pre-arrival напоминание
    несут ссылку на Online-Checkin, пока Meldeschein не подписан."""
    from apps.stays.notifications import _render

    unit = _unit(price_cents=9000)
    booking = _book(unit, 1, 4, email="gast@test.de")
    ctx = {
        "booking": booking,
        "unit": unit,
        "customer": booking.customer,
        "cancel_url": "",
        "unsubscribe_url": "",
        "checkin_url": "https://hotel.example/checkin/tok",
    }
    for tpl in ("stay_confirmed", "stay_reminder"):
        _subj, body, _html = _render(tpl, ctx)
        assert "https://hotel.example/checkin/tok" in body, tpl
    # без ссылки (подписан/нет базы) — строка не рендерится
    _subj, body, _html = _render("stay_confirmed", {**ctx, "checkin_url": ""})
    assert "Online-Check-in" not in body


def test_unit_form_tabs_keep_all_fields_in_dom():
    """Фидбэк 2026-07-28: форма номера — табы Grunddaten/Preise/Regeln (теперь
    на СТРАНИЦЕ номера /units/<pk>/). Инвариант W0: ВСЕ поля в DOM (панели
    скрыты только CSS) — Save с любого таба сохраняет всё."""
    unit = StayUnit.objects.create(name="TabZimmer", price_cents=9000)
    body = views.units(_req(), pk=unit.pk).content.decode()
    assert "data-unit-tabs" in body and 'data-ut-tab="preise"' in body
    for field in (
        'name="description"',
        'name="price_eur"',
        'name="weekend_price_eur"',
        'name="deposit_eur"',
        'name="quantity"',
        'name="min_nights"',
        'name="max_guests"',
        'name="require_manual_confirm"',
        'name="area_sqm"',
        'name="bed_type"',
        'name="amenities"',
        'name="photos"',
    ):
        assert field in body, field
    # скрытие — только классом hidden на панелях, поля не выпадают из формы
    assert 'data-ut-panel="preise" class="hidden' in body


def test_unit_tabs_cover_whole_card_and_settings_are_collapsed():
    """Фидбэк 2026-07-28 (доводка): табы охватывают ВЕСЬ блок номера — Zimmer/
    Sperrzeiten/Saisonpreise/iCal тоже панели, а не хвост «портянки». Глобальные
    настройки (тарифы/скидки/правила/фиды) — свёрнутые <details> под списком.
    Инвариант W0: все поля остаются в DOM."""
    unit = StayUnit.objects.create(name="TabZimmer", price_cents=9000)
    body = views.units(_req(), pk=unit.pk).content.decode()
    for tab in ("basis", "preise", "regeln", "zimmer", "ical"):
        assert f'data-ut-tab="{tab}"' in body, tab
    # форма принадлежит трём табам сразу и прячется на Zimmer/iCal (там свой Save)
    assert 'data-ut-panel="basis preise regeln"' in body
    for panel in ("zimmer", "ical"):
        assert f'data-ut-panel="{panel}" class="hidden' in body, panel
    # глобальные настройки живут на СПИСКЕ — 8 карточек (часть раскрыта в своих
    # под-табах), поля в DOM (W0)
    body_list = views.units(_req()).content.decode()
    assert (
        body_list.count('<details class="bg-white')
        + body_list.count('<details open class="bg-white')
        == 8
    )
    for field in (
        'name="kurtaxe_eur"',  # Kurtaxe
        'name="max_advance_days"',  # Verkaufsregeln
        'name="occupancy"',  # PMS-D
        'name="gap_max_nights"',  # Lücken-Deal
        'name="free_cancel_days"',  # Ratenpläne
        'name="threshold"',  # Automatik-Rabatte
    ):
        assert field in body_list, field
    # порядок: номера ВЫШЕ глобальных настроек (страница открывается номерами)
    assert body_list.index("TabZimmer") < body_list.index('<details class="bg-white')


def test_units_list_page_tabs_and_settings_groups():
    """Фидбэк 2026-07-28 (№2): список разделён табами «Einheiten» (список +
    кнопка «＋ Neue Einheit») / «Einstellungen» (4 группы). W0: обе панели в
    DOM, скрытие только CSS; Save настройки возвращает на таб настроек."""
    StayUnit.objects.create(name="TabZimmer", price_cents=9000)
    body = views.units(_req()).content.decode()
    assert 'data-pt-tab="einheiten"' in body and 'data-pt-tab="einstellungen"' in body
    # дефолт: активен список, настройки скрыты (но в DOM — W0)
    assert 'data-pt-panel="einstellungen" class="hidden"' in body
    assert 'name="kurtaxe_eur"' in body
    # группы настроек — ПОД-ТАБЫ в заданном порядке, все панели в DOM (W0)
    for st in ("preise", "regeln", "kurtaxe", "kanaele"):
        assert f'data-st-tab="{st}"' in body and f'data-st-panel="{st}"' in body, st
    assert body.index("💶") < body.index("📅") < body.index("🏛") < body.index("🔗")
    assert "Preise & Rabatte" in body and "Kanäle & Export" in body
    # дефолт: активна секция «Preise», остальные скрыты только CSS
    assert 'data-st-panel="regeln" class="hidden"' in body
    assert 'name="max_advance_days"' in body  # но поля скрытой секции в DOM
    # ?sec=regeln → активна её панель
    body_sec = views.units(_req(data={"tab": "einstellungen", "sec": "regeln"})).content.decode()
    assert 'data-st-panel="regeln" class="hidden"' not in body_sec
    assert 'data-st-panel="preise" class="hidden"' in body_sec
    # ?tab=einstellungen → активен таб настроек, список скрыт
    body2 = views.units(_req(data={"tab": "einstellungen"})).content.decode()
    assert 'data-pt-panel="einstellungen" class="hidden"' not in body2
    assert 'data-pt-panel="einheiten" class="hidden ' in body2
    # Save настройки редиректит на её таб И под-таб (секцию)
    resp = views.units(_req("post", data={"action": "gap_deal", "gap_discount_percent": "25"}))
    assert resp.status_code == 302 and resp.url.endswith("?tab=einstellungen&sec=preise")
    resp_k = views.units(_req("post", data={"action": "kurtaxe", "kurtaxe_eur": "2,00"}))
    assert resp_k.url.endswith("?tab=einstellungen&sec=kurtaxe")
    resp_r = views.units(_req("post", data={"action": "booking_window", "max_advance_days": "30"}))
    assert resp_r.url.endswith("?tab=einstellungen&sec=regeln")
    # создание юнита — редирект ТОЧНО на страницу нового номера (не на список/таб)
    resp2 = views.units(_req("post", data={"action": "unit", "name": "Neu Z", "type": "room"}))
    neu = StayUnit.objects.get(name="Neu Z")
    assert resp2.url.endswith(f"/units/{neu.pk}/")


def test_units_list_is_compact_and_links_to_unit_page():
    """Фидбэк 2026-07-28: «это же разные номера» — список компактный (строка =
    номер, ссылка «Bearbeiten» на СВОЮ страницу), портянки настроек на нём нет;
    страница номера не содержит глобальных настроек и чужих номеров."""
    a = StayUnit.objects.create(name="ZimmerA", price_cents=9000)
    StayUnit.objects.create(name="ZimmerB", price_cents=8000)
    body = views.units(_req()).content.decode()
    assert f"/dashboard/stays/units/{a.pk}/" in body
    assert "data-unit-tabs" not in body  # полной карточки на списке нет
    page = views.units(_req(), pk=a.pk).content.decode()
    assert "data-unit-tabs" in page and "ZimmerA" in page
    assert "ZimmerB" not in page  # только свой номер
    # ловим ОБЕ формы карточки (после под-табов часть рендерится <details open>)
    assert not re.search(r'<details(?: open)? class="bg-white', page)
    # POST со страницы номера возвращает на неё же
    resp = views.units(
        _req("post", {"action": "unit_settings", "unit": str(a.pk), "price_eur": "95"}),
        pk=a.pk,
    )
    assert resp.status_code == 302 and resp.url.endswith(f"/units/{a.pk}/")
