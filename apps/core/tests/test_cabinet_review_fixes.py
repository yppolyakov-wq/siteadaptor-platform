"""Замки по подтверждённым находкам адверсариального ревью программы
«Кабинет-X» (2026-08-19).

Каждый тест написан ДО правки и падал на её отсутствии:

- главная кабинета показывает тело поверхности продаж, значит обязана
  отдавать и её fetch-фрагменты (`?box=1`), а не целую страницу;
- фильтр в адресе (`?status=`/`?q=`) обязан быть ИСПОЛНЕН: виды board/kalender
  его не принимают, поэтому адрес с фильтром открывает «Liste»;
- главная не считает то, чего не рисует (X3 поглотил полосу «Heute»);
- «Abläufe» не теряет контекст продаж (`?from=board`) при переключении kind;
- вкладка хаба с неизвестной группой не исчезает молча из таб-бара.
"""

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import sales_page
from apps.core import views as core_views
from apps.core.modules import default_disabled_for
from apps.tenants import onboarding
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(business_type="hotel", enable=()):
    off = [m for m in default_disabled_for(business_type) if m not in enable]
    tenant = TenantFactory(
        slug=f"rv-{business_type[:8]}-{uuid4().hex[:4]}",
        name="RV",
        business_type=business_type,
        disabled_modules=off,
    )
    onboarding.mark_complete(tenant)  # иначе главная уводит в мастер (AB5)
    return tenant


def _req(path="/dashboard/", data=None, tenant=None):
    request = RequestFactory().get(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant if tenant is not None else _tenant()
    request.user = get_user_model().objects.create_user(
        username=f"rv-{uuid4().hex[:8]}", email=f"rv-{uuid4().hex[:8]}@t.de", password="pw12345678"
    )
    return request


# --- главная: fetch-фрагмент карточки брони ----------------------------------


def _stay_booking():
    from datetime import date, timedelta

    from apps.stays import services
    from apps.stays.models import StayUnit

    unit = StayUnit.objects.create(name="Doppelzimmer", quantity=2, price_cents=9000)
    today = date.today()
    return services.book_stay(
        unit, arrival=today, departure=today + timedelta(days=2), name="Frau Müller"
    )


def test_dashboard_returns_booking_card_fragment_for_box_request():
    """Belegungsplan шлёт fetch по ТЕКУЩЕМУ пути, а X3 показывает его и на
    главной — значит `?buchung=&box=1` обязан вернуть партиал карточки, а не
    58 КБ кабинета (иначе внутрь панели вставляется вложенный кабинет)."""
    tenant = _tenant("hotel")
    booking = _stay_booking()
    request = _req(data={"buchung": str(booking.pk), "box": "1"}, tenant=tenant)
    response = core_views.dashboard(request)
    body = response.content.decode()

    assert response.status_code == 200
    assert booking.reference_code in body
    # признаки ЦЕЛОЙ страницы кабинета — их во фрагменте быть не может
    assert "navpal" not in body
    assert "<html" not in body.lower()


def test_dashboard_box_request_without_booking_is_404_like_sales_page():
    tenant = _tenant("hotel")
    _stay_booking()
    request = _req(
        data={"buchung": "00000000-0000-0000-0000-000000000000", "box": "1"}, tenant=tenant
    )
    assert core_views.dashboard(request).status_code == 404


# --- главная: не считать то, чего не рисуешь ---------------------------------


def test_dashboard_does_not_compute_heute_columns(monkeypatch):
    """X3 поглотил отдельную полосу «Heute» (её показывает вид `?view=heute`
    на странице продаж). Вычисление осталось в контексте и стоило 5-6 запросов
    на каждый заход — держим удалённым."""
    calls = []
    original = sales_page.heute_columns
    monkeypatch.setattr(
        sales_page, "heute_columns", lambda tenant: calls.append(tenant) or original(tenant)
    )
    core_views.dashboard(_req(tenant=_tenant("hotel")))
    assert calls == []


# --- фильтр в адресе обязан быть исполнен ------------------------------------


@pytest.mark.parametrize(
    "kind,view,params,expected",
    [
        # board не принимает ни ?status=, ни ?q= — фильтр обязан открыть «Liste»
        ("job", "board", {"status": "quoted"}, "liste"),  # легаси-редирект jobs:list
        ("order", "board", {"status": "ready"}, "liste"),  # виджет «Abholbereit»
        ("stay", "kalender", {"status": "confirmed"}, "liste"),
        # …а то, что вид ИСПОЛНЯЕТ сам, не перебиваем: Belegungsplan ищет по ?q=
        ("stay", "kalender", {"q": "Müller"}, "kalender"),
        ("order", "liste", {"status": "ready"}, "liste"),
        ("booking", "kalender", {}, "kalender"),
        # deep-link виджетов на kind-агностичный вид сильнее фильтра
        ("order", "heute", {"status": "ready"}, "heute"),
    ],
)
def test_filter_in_url_forces_view_that_executes_it(kind, view, params, expected):
    """`?status=`/`?q=` board игнорировал молча — владелец видел ВСЕ сделки,
    считая их отфильтрованными. Правило: вид адреса обязан исполнять фильтр."""
    assert sales_page.view_for_filters(kind, view, params) == expected


def test_filtered_deep_link_renders_list_body():
    """Сквозная проверка правила на самой странице продаж (не только резолвер)."""
    tenant = _tenant("handwerker", enable=("jobs",))
    request = _req("/dashboard/verkaeufe/", {"tab": "job", "status": "quoted"}, tenant=tenant)
    body = core_views.verkaeufe(request).content.decode()
    assert 'name="q"' in body and 'value="liste"' in body  # форма фильтра «Liste»


def test_heute_view_is_not_hijacked_by_filter():
    """Вид «Heute» kind-агностичен и живёт по `?view=heute` — фильтр не должен
    перебивать явный вид (иначе deep-link виджетов ломается)."""
    tenant = _tenant("hotel")
    request = _req("/dashboard/verkaeufe/", {"view": "heute", "status": "ready"}, tenant=tenant)
    body = core_views.verkaeufe(request).content.decode()
    assert "data-sales-heute" in body


# --- «Abläufe»: контекст продаж не теряется ----------------------------------


def test_ablaeufe_kind_chips_keep_board_context():
    """Вход «Verkäufe → Abläufe» даёт ?from=board (хлебная крошка + подсветка
    сайдбара). Клик по чипу другого kind не имеет права это терять."""
    tenant = _tenant("hotel", enable=("stays", "booking"))
    request = _req("/dashboard/ablaeufe/", {"from": "board"}, tenant=tenant)
    body = core_views.ablaeufe_view(request).content.decode()

    hrefs = [line for line in body.splitlines() if "?kind=" in line]
    assert hrefs, "чипы выбора kind не отрисованы"
    assert all("from=board" in line for line in hrefs), hrefs


# --- инварианты, удерживающие КЛАСС находок ----------------------------------


def test_no_gettext_aliases_in_sources():
    """Псевдоним (`gettext as _t`, `gettext_lazy as _l/_lazy`) не извлекается
    makemessages, поэтому строка минует ОБА i18n-гейта и молча уезжает в прод
    непереведённой (23 такие строки нашлись ревью 2026-08-19). Канонические
    имена — `_` и полное `gettext_lazy`."""
    import pathlib
    import re

    pat = re.compile(
        r"from django\.utils\.translation import [^\n]*\b(gettext|gettext_lazy|ngettext|"
        r"ngettext_lazy|pgettext|pgettext_lazy)\s+as\s+(?!_\b)(\w+)"
    )
    root = pathlib.Path(__file__).resolve().parents[3]
    bad = []
    for path in list((root / "apps").rglob("*.py")) + list((root / "config").rglob("*.py")):
        for m in pat.finditer(path.read_text()):
            bad.append(f"{path.relative_to(root)}: {m.group(1)} as {m.group(2)}")
    assert bad == [], "псевдонимы gettext минуют i18n-гейты: " + "; ".join(bad)


def test_sidebar_menu_never_drops_an_entry():
    """R7-1 (переписан после сноса таб-баров): состав раздела не имеет права
    ТЕРЯТЬ запись — тот же класс «узел молча выпал». Раньше вкладку роняла
    опечатка в `group`; теперь единственная поверхность — подменю сайдбара,
    и в него обязана попасть каждая гейт-проходимая запись хаба."""
    from apps.core import modules, nav_registry

    tenant = _tenant("hotel", enable=("stays", "booking", "orders"))
    by_anchor = {it["nav_key"]: it["children"] for it in modules.sidebar_nav(tenant)}
    for a in nav_registry.ANCHORS:
        expected = {
            e.url_name
            for e in nav_registry.sidebar_children(a)
            if (not e.module_key or modules.is_module_active(tenant, e.module_key))
            and nav_registry.allowed_for_business(e.url_name, tenant)
        }
        shown = {c["url_name"] for c in by_anchor.get(a.nav_key, [])}
        assert expected <= shown, (a.nav_key, sorted(expected - shown))


def test_registry_groups_are_known():
    """Статический дубль того же инварианта — опечатка ловится до рендера."""
    from apps.core import nav_registry

    known = {""} | {key for key, _label in nav_registry.TAB_GROUPS}
    unknown = {e.group for e in nav_registry.ENTRIES} - known
    assert unknown == set(), f"неизвестные группы вкладок: {unknown}"


def test_promotion_status_labels_come_from_model():
    """Подписи статуса акции — в модели (choices), а не словарём во вьюхе:
    иначе каждый новый экран печатает сырой код (так и вышло с аналитикой)."""
    from apps.promotions.models import Promotion
    from apps.promotions.views import PROMO_STATUS_LABELS

    assert dict(Promotion.STATUSES) == PROMO_STATUS_LABELS
    promo = Promotion(status="draft")
    assert str(promo.get_status_display()) == "Entwurf"


def test_no_raw_status_codes_in_promotion_templates():
    """Скан-замок: печать сырого кода статуса/типа акции в шаблонах кабинета."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[3] / "templates" / "promotions"
    raw = re.compile(r"\{\{\s*[\w.]*\b(?:promo|p)\.(?:status|promo_type)\s*\}\}")
    bad = [
        f"{path.name}:{i}"
        for path in root.glob("*.html")
        for i, line in enumerate(path.read_text().splitlines(), 1)
        if raw.search(line)
    ]
    assert bad == [], "сырой код вместо подписи: " + ", ".join(bad)


def test_form_tabs_reveal_hidden_invalid_field():
    """HIGH: обязательное поле в скрытой вкладке вешало сохранение товара —
    браузер валит валидацию на нефокусируемом контроле молча. Общий скрипт
    обязан открывать панель/локаль проблемного поля (и при серверной ошибке)."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[3]
    js = (root / "templates" / "tenant" / "_i18n_switch.html").read_text()
    assert '"invalid"' in js and "true);" in js, "нет capture-слушателя invalid"
    assert "data-field-error" in js, "серверная ошибка в скрытой панели не раскрывается"
    for partial in ("catalog/_pf_field.html", "tenant/_i18n_group.html"):
        assert "data-field-error" in (root / "templates" / partial).read_text(), partial


def test_next_redirects_reject_foreign_host():
    """`next=` — путь ВНУТРИ кабинета. Протокол-относительный `//host` браузер
    считает чужим origin: на `status_manager_save` он приходил из GET-ссылки,
    то есть был достижим одним кликом по подсунутому адресу."""
    from apps.jobs import views as job_views

    def _post(view, data, **kwargs):
        request = RequestFactory().post("/x/", data)
        SessionMiddleware(lambda r: None).process_request(request)
        MessageMiddleware(lambda r: None).process_request(request)
        request.tenant = _tenant("handwerker", enable=("jobs",))
        request.user = get_user_model().objects.create_user(
            username=f"n-{uuid4().hex[:8]}",
            email=f"n-{uuid4().hex[:8]}@t.de",
            password="pw12345678",
        )
        return view(request, **kwargs)

    good = _post(job_views.anfrage_form_settings, {"next": "/dashboard/ablaeufe/?kind=job"})
    assert good.url == "/dashboard/ablaeufe/?kind=job"
    for hostile in ("//evil.tld/x", "https://evil.tld/x"):
        resp = _post(job_views.anfrage_form_settings, {"next": hostile})
        assert resp.url == "/dashboard/ablaeufe/", hostile
