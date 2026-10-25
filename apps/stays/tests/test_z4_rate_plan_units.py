"""KA-12 Zimmer Z-4 (E4.6c): тарифы по категориям, пересечения сезонов, права.

Замки: «для всех» (applies_to_all, дефолт) ведёт себя как до Z-4; чужой/неактивный/
мусорный тариф — честный отказ без тихой подмены (витрина, стойка, book_stay под
локом); обе реализации применимости (в памяти и Exists) совпадают; удаление категории
не расширяет тариф; сезоны той же категории не пересекаются; цены правят owner/admin."""

import pathlib
import re
import uuid
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core.models import Membership
from apps.core.tests.dates import future_month_start
from apps.stays import public_views, services, views
from apps.stays import rate_plans as rp_mod
from apps.stays.models import RatePlan, SeasonRate, StayBooking, StayUnit
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

D0 = future_month_start()


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _unit(name=None, **kw):
    kw.setdefault("price_cents", 10000)
    kw.setdefault("quantity", 3)
    return StayUnit.objects.create(name=name or f"Z {uuid.uuid4().hex[:6]}", **kw)


def _plan(name="Frühstück", units=None, **kw):
    rp = RatePlan.objects.create(name=name, applies_to_all=units is None, **kw)
    if units:
        rp.units.set(units)
    return rp


def _user(role=Membership.ROLE_OWNER):
    tag = uuid.uuid4().hex[:8]
    user = get_user_model().objects.create_user(
        username=f"u-{tag}", email=f"u-{tag}@test.de", password="pw12345678"
    )
    Membership.objects.get_or_create(user=user, defaults={"role": role})
    return user


def _with_mw(request):
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    return request


def _msgs(request):
    return [str(m) for m in get_messages(request)]


# --- модель и хелпер --------------------------------------------------------------


def test_default_plan_applies_to_every_category():
    a, b = _unit(), _unit()
    rp = _plan(units=None)
    assert rp.applies_to_all and rp.applies_to(a) and rp.applies_to(b)
    assert list(RatePlan.objects.for_unit(a)) == [rp]


@pytest.mark.parametrize(
    "case",
    ["all", "only_a", "a_and_b", "none_selected"],
)
def test_memory_and_query_applicability_agree(case):
    a, b, c = _unit(), _unit(), _unit()
    sets = {"all": None, "only_a": [a], "a_and_b": [a, b], "none_selected": []}
    rp = RatePlan.objects.create(name=case, applies_to_all=case == "all")
    if sets[case]:
        rp.units.set(sets[case])
    plans = rp_mod.active_plans()
    for unit in (a, b, c):
        in_memory = rp in rp_mod.plans_for(unit, plans)
        in_db = RatePlan.objects.for_unit(unit).filter(pk=rp.pk).exists()
        assert in_memory == in_db, (case, unit.name)
    assert (rp in rp_mod.plans_for(c, plans)) == (case == "all")


def test_for_unit_has_no_duplicates_and_keeps_order():
    a, b = _unit(), _unit()
    second = _plan("B", units=[a, b], sort_order=2)
    first = _plan("A", units=[a, b], sort_order=1)
    assert list(RatePlan.objects.for_unit(a)) == [first, second]


def test_active_plans_is_two_queries_and_filtering_is_free(django_assert_num_queries):
    units = [_unit() for _ in range(4)]
    _plan("A", units=units[:2])
    _plan("B")
    with django_assert_num_queries(2):
        plans = rp_mod.active_plans()
    with django_assert_num_queries(0):
        for u in units:
            rp_mod.plans_for(u, plans)


def test_resolve_choice_rules():
    a, b = _unit(), _unit()
    mine = _plan("Mine", units=[a], sort_order=1)
    foreign = _plan("Foreign", units=[b], sort_order=0)
    off = _plan("Off", is_active=False)
    plans = rp_mod.active_plans()
    assert rp_mod.resolve_choice(a, "", plans=plans, empty="first") == mine
    assert rp_mod.resolve_choice(a, [], plans=plans, empty="first") == mine
    assert rp_mod.resolve_choice(a, "", plans=plans, empty="none") is None
    assert rp_mod.resolve_choice(a, [str(mine.pk)], plans=plans) == mine
    bad = [
        str(foreign.pk),
        str(off.pk),
        "abc",
        "1 OR 1",
        "９" * 8,
        "x" * 500,
        str(uuid.uuid4()),
        [str(mine.pk), str(mine.pk)],
    ]
    for raw in bad:
        with pytest.raises(rp_mod.RatePlanInvalid):
            rp_mod.resolve_choice(a, raw, plans=plans)
    other = _unit()
    assert rp_mod.resolve_choice(other, "", plans=rp_mod.active_plans()) is None


def test_deleting_last_category_never_widens_plan():
    a = _unit()
    rp = _plan(units=[a])
    a.delete()
    rp.refresh_from_db()
    fresh = _unit()
    assert not rp.applies_to(fresh)
    assert not RatePlan.objects.for_unit(fresh).filter(pk=rp.pk).exists()


# --- сервис book_stay / move_stay --------------------------------------------------


def _book(unit, **kw):
    kw.setdefault("name", "Gast")
    return services.book_stay(unit, arrival=D0, departure=D0 + timedelta(days=2), adults=2, **kw)


def test_book_stay_refuses_plan_of_other_category():
    a, b = _unit(), _unit()
    foreign = _plan(units=[b])
    with pytest.raises(services.RatePlanInvalid):
        _book(a, rate_plan=foreign)
    assert not StayBooking.objects.exists()


def test_book_stay_refuses_plan_deactivated_after_form_read():
    a = _unit()
    rp = _plan()
    RatePlan.objects.filter(pk=rp.pk).update(is_active=False)  # объект в памяти «активен»
    with pytest.raises(services.RatePlanInvalid):
        _book(a, rate_plan=rp)
    assert not StayBooking.objects.exists()


def test_book_stay_uses_fresh_plan_values():
    a = _unit()
    rp = _plan(surcharge_cents=1000)
    RatePlan.objects.filter(pk=rp.pk).update(surcharge_cents=2000)  # в памяти — 10 €
    booking = _book(a, rate_plan=rp)
    assert booking.total_cents == 2 * (10000 + 2000)


def test_book_stay_plan_for_all_is_unchanged():
    a = _unit()
    rp = _plan(surcharge_cents=1200)
    assert _book(a, rate_plan=rp).total_cents == 2 * 11200


def test_move_to_category_outside_plan_keeps_plan():
    a, b = _unit(), _unit(price_cents=12000)
    rp = _plan(units=[a], surcharge_cents=1000)
    booking = _book(a, rate_plan=rp)
    services.move_stay(
        booking, arrival=booking.arrival, departure=booking.departure, unit=b, reprice=True
    )
    booking.refresh_from_db()
    assert booking.unit_id == b.pk and booking.rate_plan_id == rp.pk
    assert booking.total_cents == 2 * (12000 + 1000)


# --- витрина ------------------------------------------------------------------------


def _store_get(unit):
    request = RequestFactory().get(
        f"/unterkunft/{unit.pk}/",
        {
            "von": (D0 + timedelta(days=1)).isoformat(),
            "bis": (D0 + timedelta(days=3)).isoformat(),
            "erw": "2",
        },
    )
    request.tenant = TenantFactory.build(disabled_modules=[])
    return public_views.unterkunft_unit(request, pk=unit.pk).content.decode()


def _store_post(unit, extra=None):
    data = {
        "von": (D0 + timedelta(days=1)).isoformat(),
        "bis": (D0 + timedelta(days=3)).isoformat(),
        "erw": "2",
        "name": "Gast",
        "email": f"g-{uuid.uuid4().hex[:6]}@test.de",
        **(extra or {}),
    }
    request = _with_mw(RequestFactory().post(f"/unterkunft/{unit.pk}/buchen/", data))
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.7"
    request.tenant = TenantFactory.build(disabled_modules=[])
    return request, public_views.unterkunft_book(request, pk=unit.pk)


def test_storefront_shows_only_plans_of_this_category():
    a, b = _unit(), _unit()
    _plan("Seeblick-Halbpension-Nur-B", units=[b], surcharge_cents=100)
    _plan("Fruehstueck-Fuer-Alle", surcharge_cents=900)
    body = _store_get(a)
    assert "Fruehstueck-Fuer-Alle" in body
    assert "Seeblick-Halbpension-Nur-B" not in body


def test_storefront_ab_price_ignores_cheaper_foreign_plan():
    a, b = _unit(), _unit()
    _plan("Spar", units=[b], percent_adjust=-50)
    von, bis = D0 + timedelta(days=1), D0 + timedelta(days=3)
    assert (
        public_views._unit_from_price_cents(a, von, bis, rp_mod.plans_for(a, rp_mod.active_plans()))
        == 2 * 10000
    )


def test_storefront_post_with_foreign_plan_is_refused():
    a, b = _unit(), _unit()
    foreign = _plan(units=[b])
    for raw in (str(foreign.pk), "abc", str(uuid.uuid4())):
        request, resp = _store_post(a, {"rate_plan": raw})
        assert resp.status_code == 302
        assert any("nicht verfügbar" in m for m in _msgs(request))
    assert not StayBooking.objects.exists()


def test_storefront_post_without_plan_takes_first_applicable():
    a, b = _unit(), _unit()
    _plan("Foreign", units=[b], sort_order=0)
    mine = _plan("Mine", units=[a], sort_order=5)
    _request, resp = _store_post(a)
    assert resp.status_code == 302
    assert StayBooking.objects.get().rate_plan_id == mine.pk


# --- стойка ------------------------------------------------------------------------


def _desk(unit, extra=None, role=Membership.ROLE_OWNER):
    data = {
        "unit": str(unit.pk),
        "arrival": D0.isoformat(),
        "departure": (D0 + timedelta(days=2)).isoformat(),
        "name": "Walk-in",
        "erw": "2",
        **(extra or {}),
    }
    request = _with_mw(RequestFactory().post("/dashboard/stays/new/", data))
    request.user = _user(role)
    return request, views.stay_create(request)


def test_front_desk_defaults_to_no_plan():
    a = _unit()
    _plan(surcharge_cents=1200)
    _desk(a)
    booking = StayBooking.objects.get()
    assert booking.rate_plan_id is None and booking.total_cents == 2 * 10000


def test_front_desk_refuses_foreign_plan():
    a, b = _unit(), _unit()
    foreign = _plan(units=[b])
    request, _resp = _desk(a, {"rate_plan": str(foreign.pk)})
    assert not StayBooking.objects.exists()
    assert any("gilt nicht" in m for m in _msgs(request))


def test_walkin_form_has_no_plan_option_and_unit_hints():
    a, _b = _unit(), _unit()
    _plan("Nur-A", units=[a])
    request = _with_mw(RequestFactory().get("/dashboard/stays/new/"))
    request.user = _user()
    body = views.stay_new(request).content.decode()
    assert re.search(r'<option value="" selected>\s*— ohne Tarif —', body)
    assert f'data-units="{a.pk}"' in body


# --- кабинет тарифов ----------------------------------------------------------------


def _units_post(data, role=Membership.ROLE_OWNER):
    request = _with_mw(RequestFactory().post("/dashboard/stays/units/", data))
    request.user = _user(role)
    request.tenant = TenantFactory.build(disabled_modules=[])
    return request, views.units(request)


def test_create_plan_for_selected_categories():
    a, _b = _unit(), _unit()
    _units_post(
        {
            "action": "rateplan",
            "name": "Nur A",
            "rate_scope": "some",
            "units": [str(a.pk), "garbage", str(uuid.uuid4())],
        }
    )
    rp = RatePlan.objects.get(name="Nur A")
    assert not rp.applies_to_all and set(rp.units.all()) == {a}


def test_create_plan_without_scope_field_is_for_all():
    _units_post({"action": "rateplan", "name": "Alt"})
    assert RatePlan.objects.get(name="Alt").applies_to_all


def test_create_plan_some_without_categories_refused():
    request, _ = _units_post({"action": "rateplan", "name": "Leer", "rate_scope": "some"})
    assert not RatePlan.objects.filter(name="Leer").exists()
    assert _msgs(request)


def test_edit_plan_categories_and_w0():
    a, b = _unit(), _unit()
    rp = _plan(units=[a])
    _units_post({"action": "rateplan_units", "rateplan": str(rp.pk)})  # без поля охвата
    assert set(rp.units.all()) == {a} and not RatePlan.objects.get(pk=rp.pk).applies_to_all
    _units_post(
        {
            "action": "rateplan_units",
            "rateplan": str(rp.pk),
            "rate_scope": "some",
            "units": [str(b.pk)],
        }
    )
    assert set(rp.units.all()) == {b}
    _units_post({"action": "rateplan_units", "rateplan": str(rp.pk), "rate_scope": "all"})
    rp.refresh_from_db()
    assert rp.applies_to_all and not rp.units.exists()


@pytest.mark.parametrize(
    "data",
    [
        {"action": "rateplan", "name": "Staff"},
        {"action": "rateplan_delete", "rateplan": "PK"},
        {"action": "rateplan_toggle", "rateplan": "PK"},
        {"action": "rateplan_units", "rateplan": "PK", "rate_scope": "all"},
        {"action": "rate", "unit": "UNIT", "start_date": "2030-01-01", "end_date": "2030-01-05"},
        {"action": "rate_delete", "rate": "SEASON"},
    ],
)
def test_staff_cannot_change_prices(data):
    a = _unit()
    rp = _plan(units=[a])
    season = SeasonRate.objects.create(
        unit=a, start_date=date(2031, 1, 1), end_date=date(2031, 1, 5), price_cents=1
    )
    data = {
        k: v.replace("PK", str(rp.pk)).replace("UNIT", str(a.pk)).replace("SEASON", str(season.pk))
        for k, v in data.items()
    }
    request, _ = _units_post(data, role=Membership.ROLE_STAFF)
    assert set(RatePlan.objects.values_list("name", "is_active")) == {(rp.name, True)}
    assert not RatePlan.objects.get(pk=rp.pk).applies_to_all
    assert SeasonRate.objects.count() == 1
    assert any("Inhaber" in m for m in _msgs(request))


def test_rate_edit_actions_constant_covers_price_writers():
    """Каждый action диспетчера units(), пишущий RatePlan/SeasonRate, — в RATE_EDIT_ACTIONS."""
    src = pathlib.Path(views.__file__).read_text()
    body = src[src.index("def units(") :]
    body = body[: body.index("        if pk:\n")]  # только POST-диспетчер
    blocks = re.split(r'\n        (?:el)?if action == "', body)[1:]
    writers = {
        b.split('"', 1)[0]
        for b in blocks
        if re.search(r"(RatePlan|SeasonRate)\.objects|add_season_rate|rp\.units|rp\.save", b)
    }
    assert writers and writers <= views.RATE_EDIT_ACTIONS


def test_list_label_without_n_plus_one(django_assert_max_num_queries):
    units = [_unit() for _ in range(3)]
    for i in range(5):
        _plan(f"P{i}", units=units[:2])
    request = _with_mw(RequestFactory().get("/dashboard/stays/units/", {"tab": "einstellungen"}))
    request.user = _user()
    request.tenant = TenantFactory.build(disabled_modules=[])
    with django_assert_max_num_queries(40):
        body = views.units(request).content.decode()
    assert "nur:" in body


def test_move_warns_when_plan_does_not_fit():
    a, b = _unit(), _unit()
    rp = _plan("Nur-A-Tarif", units=[a])
    booking = _book(a, rate_plan=rp)
    request = _with_mw(RequestFactory().post("/x/"))
    services.move_stay(
        booking, arrival=booking.arrival, departure=booking.departure, unit=b, reprice=False
    )
    views._warn_rate_mismatch(request, booking)
    assert any("Nur-A-Tarif" in m for m in _msgs(request))


# --- сезоны -------------------------------------------------------------------------


def _season(unit, start, end, label="Sommer"):
    return services.add_season_rate(
        unit, label=label, start_date=start, end_date=end, price_cents=12000
    )


def test_season_overlap_rules():
    a, b = _unit(), _unit()
    d = date(2031, 7, 1)
    _season(a, d, d + timedelta(days=9))  # 1–10
    for start, end in [
        (d + timedelta(days=9), d + timedelta(days=19)),  # касание по 10-й ночи
        (d + timedelta(days=2), d + timedelta(days=4)),  # вложенный
        (d - timedelta(days=5), d + timedelta(days=30)),  # охватывающий
    ]:
        with pytest.raises(services.SeasonOverlap) as exc:
            _season(a, start, end, label="Neu")
        assert exc.value.conflict.label == "Sommer"
    _season(a, d + timedelta(days=10), d + timedelta(days=19))  # 11–20 — рядом, ок
    _season(b, d, d + timedelta(days=9))  # другая категория — ок
    with pytest.raises(ValueError):
        _season(b, d + timedelta(days=40), d + timedelta(days=30))


def test_season_overlap_message_in_cabinet():
    a = _unit()
    _season(a, date(2031, 7, 1), date(2031, 7, 10))
    request, _ = _units_post(
        {
            "action": "rate",
            "unit": str(a.pk),
            "start_date": "2031-07-05",
            "end_date": "2031-07-12",
            "price_eur": "90",
        }
    )
    assert SeasonRate.objects.count() == 1
    assert any("Sommer" in m and "Überschneidet" in m for m in _msgs(request))


def test_existing_overlap_badge():
    a = _unit()
    SeasonRate.objects.create(
        unit=a, start_date=date(2031, 7, 1), end_date=date(2031, 7, 10), price_cents=1
    )
    SeasonRate.objects.create(
        unit=a, start_date=date(2031, 7, 8), end_date=date(2031, 7, 12), price_cents=2
    )
    request = _with_mw(RequestFactory().get(f"/dashboard/stays/units/{a.pk}/"))
    request.user = _user()
    request.tenant = TenantFactory.build(disabled_modules=[])
    body = views.units(request, pk=a.pk).content.decode()
    assert body.count("data-season-overlap") == 2


def test_demo_kits_have_no_overlapping_seasons():
    from apps.tenants import demo_kits

    checked = 0
    for key, kit in demo_kits.KITS.items():
        for spec in getattr(kit, "stay_units", None) or []:
            if not isinstance(spec, dict):
                continue
            ranges = sorted((s["start"], s["end"]) for s in spec.get("season", []))
            checked += len(ranges)
            for (_s1, e1), (s2, _e2) in zip(ranges, ranges[1:], strict=False):
                assert s2 > e1, (key, spec.get("name"))
    assert checked  # спека сезонов действительно читается


# --- замок класса -------------------------------------------------------------------


def test_active_plans_only_through_helper():
    root = pathlib.Path(__file__).resolve().parents[3] / "apps"
    offenders = []
    for path in root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if "/tests/" in rel or "/migrations/" in rel or rel == "stays/rate_plans.py":
            continue
        if re.search(r"RatePlan\.objects\.filter\(\s*is_active=True", path.read_text()):
            offenders.append(rel)
    assert not offenders, offenders
