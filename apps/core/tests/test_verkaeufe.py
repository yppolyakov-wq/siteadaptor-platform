"""Единая страница продаж /dashboard/verkaeufe/ (2026-08-03).

Решения владельца: вкладки по kind (primary всегда, прочие при наличии продаж),
виды Kalender/Board/Liste per-kind с persist'ом.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory

from apps.core import sales_page, views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _req(path="/dashboard/verkaeufe/", data=None, method="get", **tenant_kw):
    import uuid

    request = getattr(RequestFactory(), method)(path, data or {})
    request.user = get_user_model().objects.create_user(
        username=f"v-{uuid.uuid4().hex[:10]}", password="pw12345678"
    )
    request.session = {}
    request._messages = FallbackStorage(request)
    request.tenant = TenantFactory.build(**tenant_kw)
    return request


def _hotel(**kw):
    # disabled_modules=[] включил бы ВСЕ модули реестра (fail-open) — у отеля
    # primary стал бы events. Берём честный стартовый набор архетипа.
    from apps.core.modules import default_disabled_for

    return dict(
        business_type="hotel",
        disabled_modules=list(default_disabled_for("hotel")),
        **kw,
    )


def test_hotel_first_tab_is_stay_and_default_view_is_kalender():
    """Требование владельца: у отеля первым — календарь броней номеров, всегда."""
    body = views.verkaeufe(_req(**_hotel())).content.decode()
    assert "data-sales-tabs" in body
    assert "belegungsplan" in body  # таблица шахматки отрендерена
    assert "Übernachtungen" in body


def test_tab_per_active_module_even_without_sales():
    """SM-2 (решение владельца 2026-08-10, осознанная замена правила W10-2):
    вкладка на КАЖДЫЙ активный модуль сразу — верхний уровень продаж = модули
    бизнеса, а не «что уже продавалось». У отеля booking активен → вкладка
    «Termine» видна и без единой записи."""
    body = views.verkaeufe(_req(**_hotel())).content.decode()
    assert "?tab=booking" in body  # модуль активен — вкладка есть, продаж ноль


def test_primary_tab_visible_even_with_zero_sales():
    """Primary-kind виден ВСЕГДА (пустой Belegungsplan — с CTA, не пропажа)."""
    body = views.verkaeufe(_req(**_hotel())).content.decode()
    assert "Übernachtungen" in body


def test_view_switch_persists_choice_per_kind():
    """POST на verkaeufe-view пишет sales_views[kind]; следующий заход
    открывает сохранённый вид без ?view=."""
    from apps.core.modules import default_disabled_for
    from apps.tenants.tests.factories import TenantFactory as TF

    tenant = TF(business_type="hotel", disabled_modules=list(default_disabled_for("hotel")))
    req = _req(method="post", data={"kind": "stay", "view": "board"})
    req.tenant = tenant
    resp = views.verkaeufe_view_set(req)
    assert resp.status_code == 302
    assert tenant.site_config["sales_views"] == {"stay": "board"}
    # мусорный вид молча игнорируется
    req2 = _req(method="post", data={"kind": "stay", "view": "hackerman"})
    req2.tenant = tenant
    views.verkaeufe_view_set(req2)
    assert tenant.site_config["sales_views"] == {"stay": "board"}


def test_saved_view_resolves_and_bad_saved_value_falls_back():
    tenant = TenantFactory.build(
        business_type="hotel", site_config={"sales_views": {"stay": "liste"}}
    )
    assert sales_page.resolve_view(tenant, "stay") == "liste"
    tenant.site_config = {"sales_views": {"stay": "kaputt"}}
    assert sales_page.resolve_view(tenant, "stay") == "kalender"  # архетипный дефолт


def test_normalize_sales_views_is_presence_minimal():
    from apps.tenants import siteconfig

    assert siteconfig.normalize_sales_views(None) == {}
    assert siteconfig.normalize_sales_views({"stay": "kaputt", "x": "board"}) == {}
    assert siteconfig.normalize_sales_views({"stay": "board"}) == {"stay": "board"}
    # normalize целиком: ключ не материализуется пустым
    cfg = siteconfig.normalize({})
    assert "sales_views" not in cfg


def test_reservation_tab_needs_data_not_just_the_module(monkeypatch):
    """VK-8 (фидбэк владельца 2026-08-20, осознанная правка правила SM-2):
    `reservation` — ЕДИНСТВЕННОЕ исключение из «модуль = вкладка». С волны PL
    покупка по акции создаёт обычный заказ, витрина в `Reservation` не пишет
    вовсе — модуль акций держат ради СКИДОК, и вкладка была вечно пустой.
    Показываем её только там, где легаси-резервы реально есть."""
    from apps.core.modules import default_disabled_for

    tenant = TenantFactory.build(
        business_type="bakery", disabled_modules=list(default_disabled_for("bakery"))
    )
    # promotions активен, но резервов нет → вкладки нет
    monkeypatch.setattr(sales_page, "_has_reservations", lambda: False)
    assert "reservation" not in sales_page.visible_kinds(tenant)

    monkeypatch.setattr(sales_page, "_has_reservations", lambda: True)
    assert "reservation" in sales_page.visible_kinds(tenant)

    off = TenantFactory.build(
        business_type="bakery",
        disabled_modules=list(default_disabled_for("bakery")) + ["promotions"],
    )
    assert "reservation" not in sales_page.visible_kinds(off)  # модуль всё ещё гейт


def test_auftragsbuch_groups_orders_by_pickup_day():
    """V3: календарь заказов по дням выдачи; активные без слота — «ohne Termin»."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.orders.models import Customer as OrderCustomer
    from apps.orders.models import Order

    slot = timezone.now() + timedelta(days=2)
    anna = OrderCustomer.objects.create(name="Anna", email="a@t.de")
    bernd = OrderCustomer.objects.create(name="Bernd", email="b@t.de")
    with_slot = Order.objects.create(customer=anna, pickup_slot=slot, reference_code="O-AB0001")
    без = Order.objects.create(customer=bernd, reference_code="O-AB0002")  # без слота
    body = views.verkaeufe(
        _req(
            data={"tab": "order", "view": "kalender"},
            business_type="bakery",
            disabled_modules=[],
        )
    ).content.decode()
    assert "data-auftragsbuch" in body
    assert "Anna" in body
    assert "Ohne Termin" in body and "Bernd" in body
    assert with_slot.reference_code in body and без.reference_code in body


def test_calendar_day_nav_keeps_the_tab():
    """Фидбэк 2026-08-03 «не работает календарь у услуги»: листание дней в
    Tagesplan шло голым ?tag= — на /verkaeufe/ клик сбрасывал вкладку и
    выбрасывал на Belegungsplan. Ссылки обязаны нести tab."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.booking.models import Booking, Customer, Resource

    start = timezone.now() + timedelta(days=1)
    Booking.objects.create(
        resource=Resource.objects.create(name="Spa2"),
        start=start,
        end=start + timedelta(hours=1),
        customer=Customer.objects.create(name="Gast", email="g2@t.de"),
    )
    body = views.verkaeufe(
        _req(data={"tab": "booking", "view": "kalender"}, **_hotel())
    ).content.decode()
    assert "?tab=booking&amp;tag=" in body  # листание не теряет вкладку
    # W10-6: отдельной страницы booking:calendar больше нет (302 на Verkäufe).


def test_order_liste_kds_entries_only_for_food_types():
    """X4: гейт гастро — «Kitchen Display»/«Tisch-QR» появляются у гастро-типа
    и отсутствуют у прочих (проверяем по URL: de.po переводит подписи)."""
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders import services

    services.create_order(
        items=[(ProductFactory(name={"de": "Brot"}), 1)], name="KDS-Kunde", email="k@t.de"
    )
    kw = dict(disabled_modules=["events", "stays", "booking", "jobs"])
    food = views.verkaeufe(_req(business_type="cafe", **kw)).content.decode()
    assert "kitchen/" in food and "tisch-qr/" in food
    other = views.verkaeufe(_req(business_type="clothing", **kw)).content.decode()
    assert "kitchen/" not in other and "tisch-qr/" not in other


def test_order_liste_parity_filter_search_entries():
    """W10-3: вкладка order — фильтр статуса + поиск + входы KDS/QR (паритет
    с /dashboard/orders/; «тонкая обёртка» больше не богаче единой страницы)."""
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders import services

    order = services.create_order(
        items=[(ProductFactory(name={"de": "Brot"}), 1)], name="Suchkunde", email="such@t.de"
    )
    shop = dict(
        business_type="shop",
        disabled_modules=["events", "stays", "booking", "jobs"],
    )
    body = views.verkaeufe(_req(**shop)).content.decode()
    assert 'name="status"' in body and 'name="q"' in body
    # X4 (осознанная переписка §6.A4.5): KDS/Tisch-QR — гастро-инструменты;
    # магазин их больше не видит (раньше «Kitchen Display» показывался всем,
    # у кого включён модуль orders — вплоть до парикмахерской).
    assert "kitchen/" not in body and "tisch-qr/" not in body
    # фильтр статуса: cancelled скрывает новый заказ
    body = views.verkaeufe(
        _req(data={"tab": "order", "status": "cancelled"}, **shop)
    ).content.decode()
    assert order.reference_code not in body
    # поиск по имени клиента находит
    body = views.verkaeufe(_req(data={"tab": "order", "q": "Suchkunde"}, **shop)).content.decode()
    assert order.reference_code in body
    # поиск-промах — пусто
    body = views.verkaeufe(_req(data={"tab": "order", "q": "niemand-xyz"}, **shop)).content.decode()
    assert order.reference_code not in body


def test_create_button_per_kind():
    """W10-3: «＋» из любого вида — stay → stay-new, booking → walk-in-якорь,
    у заказов кнопки нет (owner-create флоу отсутствует)."""
    body = views.verkaeufe(_req(**_hotel())).content.decode()
    assert "/dashboard/stays/neu/" in body or "/stays/neu/" in body

    services_t = dict(
        business_type="hairdresser",
        disabled_modules=["events", "stays"],
    )
    body = views.verkaeufe(_req(**services_t)).content.decode()
    assert "?tab=booking&amp;view=kalender#neu" in body or "?tab=booking&view=kalender#neu" in body

    shop = dict(business_type="shop", disabled_modules=["events", "stays", "booking", "jobs"])
    body = views.verkaeufe(_req(**shop)).content.decode()
    assert "＋" not in body.split("data-sales-tabs")[0]  # в шапке кнопки нет


def test_ready_widget_deep_links_to_verkaeufe():
    """W10-3: «Abholbereit» главной ведёт на единую страницу (?tab=order&status=ready)."""
    from apps.core import dashboard as dash

    shop = TenantFactory.build(
        business_type="shop", disabled_modules=["events", "stays", "booking", "jobs"]
    )
    widgets = dash.home_widgets(shop)
    ready = next((w for w in widgets if w.get("key") == "ready"), None)
    if ready is not None:  # виджет гейтится наличием ready-заказов
        assert ready["url_name"] == "verkaeufe"
        assert ready["url_query"] == "?tab=order&status=ready"


def test_ticket_and_job_tabs_link_to_full_pages():
    """W10-3b: с вкладок ticket/job достижимы полные управляющие экраны
    (аудит: «events:list/jobs:list выпали из новой навигации продаж»)."""
    ev = dict(business_type="events", disabled_modules=["stays", "booking"])
    body = views.verkaeufe(_req(**ev)).content.decode()
    assert "/dashboard/events/" in body

    hw = dict(business_type="handwerker", disabled_modules=["stays", "booking", "events"])
    body = views.verkaeufe(_req(**hw)).content.decode()
    assert "/dashboard/auftraege/" in body


def test_board_hub_bar_not_rendered_in_templates():
    """W10-3b: огрызок hub_tabs "board" (Tickets/Aufträge) снят со всех страниц.
    Реестр board-хаба жив осознанно — питает палитру Ctrl+K и якорь подсветки."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3] / "templates"
    hits = [
        str(p)
        for p in root.rglob("*.html")
        if 'hub_tabs "board"' in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert hits == []


def test_heute_view_columns_by_archetype():
    """W10-4: «Heute» — kind-агностичные колонки по активным модулям; карточки
    ведут на родные детали; пустые колонки — честное «Nichts für heute»."""
    from datetime import timedelta

    from django.utils import timezone

    # Отель: заезд сегодня → колонка Anreisen с именем гостя.
    from apps.stays.models import Customer as StayCustomer
    from apps.stays.models import StayBooking, StayUnit

    today = timezone.localdate()
    unit = StayUnit.objects.create(name="Doppelzimmer")
    stay = StayBooking.objects.create(
        unit=unit,
        arrival=today,
        departure=today + timedelta(days=2),
        customer=StayCustomer.objects.create(name="Frau Ankunft", email="an@t.de"),
        status="confirmed",
    )
    body = views.verkaeufe(_req(data={"view": "heute"}, **_hotel())).content.decode()
    assert "data-sales-heute" in body
    assert "Frau Ankunft" in body
    assert f"/dashboard/stays/buchung/{stay.pk}/" in body
    assert "Nichts für heute." in body  # выезды пусты — честное пустое состояние

    # Магазин: ready-заказ в «Abholbereit».
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders import services as order_services
    from apps.orders.state_machine import OrderSM

    order = order_services.create_order(
        items=[(ProductFactory(name={"de": "Kuchen"}), 1)], name="Abholer", email="ab@t.de"
    )
    OrderSM().apply(order, "confirmed")
    OrderSM().apply(order, "ready")
    shop = dict(business_type="shop", disabled_modules=["events", "stays", "booking", "jobs"])
    body = views.verkaeufe(_req(data={"view": "heute"}, **shop)).content.decode()
    assert order.reference_code in body


def test_stays_today_widget_deep_links_to_stay_tab():
    from apps.core import dashboard as dash

    hotel = TenantFactory.build(**_hotel())
    w = next((x for x in dash.home_widgets(hotel) if x.get("key") == "stays_today"), None)
    if w is not None:
        # SM-2: сводка Heute живёт на самой главной — виджет ведёт во вкладку.
        assert w["url_name"] == "verkaeufe" and w["url_query"] == "?tab=stay"


def test_toolbar_lives_inside_the_tab_not_above():
    """SM-2 (фидбэк владельца 2026-08-10): «кнопки идут как будто над верхним
    уровнем, а должны быть частью каждого внутри» — переключатель видов стоит
    ПОСЛЕ ряда вкладок; «📆 Heute» из ряда видов ушёл (живёт на Übersicht).
    SM-4 (решение владельца 2026-08-11): «⚙️ Abläufe» ушла из тулбара в подпункт
    сайдбара. VK-2 (фидбэк владельца 2026-08-20): вход в настройки РАЗДЕЛА вернулся
    на страницу — владелец их не находил; замок переписан осознанно: кнопка обязана
    нести АКТИВНЫЙ kind (настраиваем именно эту вкладку) и `from=board` (крошка
    вернёт на неё же)."""
    body = views.verkaeufe(_req(**_hotel())).content.decode()
    assert body.index("data-sales-tabs") < body.index("data-sales-view-switch")
    # кнопка настроек — ПОСЛЕ вкладок (часть вкладки, не полоса над всем)
    assert body.index("data-sales-tabs") < body.index("ablaeufe/?kind=stay")
    assert "ablaeufe/?kind=stay&amp;from=board" in body
    assert "view=heute" not in body  # кнопки Heute на странице продаж больше нет


def test_heute_lives_on_the_dashboard():
    """SM-2: сводка дня — часть Übersicht. Deep-link ?view=heute остаётся
    рабочим (виджеты главной ссылаются на колонки)."""
    from apps.core.views import dashboard as dashboard_view

    body = dashboard_view(
        _req(
            "/dashboard/",
            **_hotel(site_config={"onboarding": {"step": 7, "skipped": [], "completed": True}}),
        )
    ).content.decode()
    assert "Heute" in body

    resp = views.verkaeufe(_req(data={"view": "heute"}, **_hotel()))
    assert resp.status_code == 200


def test_status_settings_parity_for_all_six_kinds():
    """SM-2 (решение владельца 2026-08-10): имена статусов и правила переходов
    доступны КАЖДОМУ направлению продаж, не только order/booking/stay.

    Реестр кодов обязан совпадать со status_registry.BUILTIN один-в-один: имя,
    сохранённое для несуществующего кода, молча бы не показывалось."""
    from apps.core import status_registry
    from apps.core.views import _status_choices, _status_kinds_for
    from apps.tenants import siteconfig

    for kind in ("order", "booking", "stay", "job", "ticket", "reservation"):
        codes = siteconfig.status_label_statuses(kind)
        assert codes is not None, f"{kind}: нет в реестре имён статусов"
        assert set(codes) == set(status_registry.BUILTIN[kind]), kind
        # у панели есть дефолт-подпись для каждого кода
        assert {c for c, _l in _status_choices(kind)} >= set(codes), kind

    tenant = TenantFactory.build(business_type="hotel", disabled_modules=[])
    kinds = {k for k, _l in _status_kinds_for(tenant)}
    assert {"order", "booking", "stay", "job", "ticket", "reservation"} <= kinds
