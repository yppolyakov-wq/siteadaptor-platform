"""FLT-1b: несколько районов в фильтре портала + canonical/noindex query-вариаций.

План — docs/flt-portal-filters-plan-2026-11-04.md §2, §12, §13.
"""

import uuid

import pytest
from django.core.cache import cache
from django.test import RequestFactory

from apps.aggregator import follow_query, portal_views, search
from apps.aggregator.models import AggregatorListing, AggregatorPortal, SearchQueryLog

pytestmark = pytest.mark.django_db

WALD = "wald"
MITTE = "mitte"
OHLIGS = "ohligs-aufderhoehe-merscheid"


@pytest.fixture(autouse=True)
def _clear(settings):
    settings.ROOT_URLCONF = "config.urls_portal"
    settings.PORTAL_DISTRICT_MIN_BUSINESSES = 0  # без хвоста соседей Г5 — чистая выдача
    cache.clear()
    yield
    cache.clear()


def _portal():
    return AggregatorPortal.objects.create(
        host="solingen.siteadaptor.de",
        kind="city",
        city="Solingen",
        title={"de": "Angebote in Solingen"},
        is_active=True,
    )


def _listing(title, district, schema):
    return AggregatorListing.objects.create(
        tenant_schema=schema,
        tenant_slug=schema,
        business_name=schema.upper(),
        business_type="bakery",
        city="Solingen",
        district=district,
        promo_uuid=uuid.uuid4(),
        title={"de": title},
        detail_url=f"https://{schema}.siteadaptor.de/p/1/",
        is_active=True,
    )


def _seed():
    _listing("Brot aus Wald", WALD, "w1")
    _listing("Brot aus Mitte", MITTE, "m1")
    _listing("Brot aus Ohligs", OHLIGS, "o1")


def _html(portal, path, district=None, facet=None):
    req = RequestFactory().get(path, HTTP_HOST=portal.host)
    req.portal = portal
    return portal_views.portal_home(req, facet=facet, district=district).content.decode()


def _filters(**get):
    from django.http import QueryDict

    qd = QueryDict(mutable=True)
    for k, v in get.items():
        qd.setlist(k, v if isinstance(v, list) else [v])
    return search.parse_filters(type("R", (), {"GET": qd})(), city="Solingen")


# --- движок ------------------------------------------------------------------------------


def test_parse_filters_takes_every_district_once_in_order_and_drops_junk():
    f = _filters(stadtteil=["Wald", "mitte", "wald", "atlantis", ""])
    assert f.districts == (WALD, MITTE)
    assert f.district == ""  # одиночный район — только когда он ровно один
    assert _filters(stadtteil="Wald").district == WALD


def test_district_list_is_capped():
    many = ["wald"] * 500 + ["mitte"]
    f = _filters(stadtteil=many)
    assert f.districts == (WALD,)  # сырой ввод режется до нормализации
    assert len(search.parse_districts([f"x{i}" for i in range(100)], city="")) == 0


def test_single_district_carry_is_unchanged():
    assert search.carry("", _filters(stadtteil="wald")) == [("stadtteil", WALD)]
    assert search.carry("", _filters(stadtteil=["wald", "mitte"])) == [
        ("stadtteil", WALD),
        ("stadtteil", MITTE),
    ]


def test_apply_filters_is_or_over_districts():
    _seed()
    qs = search.apply_filters(
        AggregatorListing.objects.all(), _filters(stadtteil=["wald", "mitte"])
    )
    assert set(qs.values_list("district", flat=True)) == {WALD, MITTE}


# --- страница портала --------------------------------------------------------------------


def test_two_districts_show_both_and_page_is_noindex_with_self_canonical():
    _seed()
    p = _portal()
    html = _html(p, "/?stadtteil=wald&stadtteil=mitte")
    assert "Brot aus Wald" in html and "Brot aus Mitte" in html
    assert "Brot aus Ohligs" not in html
    assert '<meta name="robots" content="noindex,follow">' in html
    assert 'rel="canonical" href="http://solingen.siteadaptor.de/?stadtteil=wald' in html


def test_single_district_param_on_root_canonicalizes_to_district_path():
    _seed()
    p = _portal()
    html = _html(p, "/?stadtteil=wald")
    assert 'rel="canonical" href="http://solingen.siteadaptor.de/stadtteil/wald/"' in html
    assert 'name="robots"' not in html


def test_district_path_page_is_indexable_and_unchanged():
    _seed()
    p = _portal()
    html = _html(p, "/stadtteil/wald/", district=WALD)
    assert "Brot aus Wald" in html and "Brot aus Mitte" not in html
    assert 'rel="canonical" href="http://solingen.siteadaptor.de/stadtteil/wald/"' in html
    assert 'name="robots"' not in html


def test_path_plus_param_district_is_union_not_override():
    """Раньше путь молча выкидывал ?stadtteil= (W0-потеря): теперь — объединение."""
    _seed()
    p = _portal()
    html = _html(p, "/stadtteil/wald/?stadtteil=mitte", district=WALD)
    assert "Brot aus Wald" in html and "Brot aus Mitte" in html
    assert "Brot aus Ohligs" not in html
    assert '<meta name="robots" content="noindex,follow">' in html


def test_search_query_page_is_noindex():
    _seed()
    p = _portal()
    assert '<meta name="robots" content="noindex,follow">' in _html(p, "/?q=Brot")


def test_district_path_without_query_writes_no_search_log():
    _seed()
    p = _portal()
    _html(p, "/stadtteil/wald/", district=WALD)
    assert not SearchQueryLog.objects.exists()


def test_each_district_has_its_own_removable_pill():
    _seed()
    p = _portal()
    html = _html(p, "/?stadtteil=wald&stadtteil=mitte")
    assert "?stadtteil=mitte" in html  # ✕ у «Wald» оставляет Mitte
    assert "?stadtteil=wald" in html


# --- подписка ----------------------------------------------------------------------------


def test_follow_set_keeps_both_districts_sorted():
    pairs = follow_query.canonical(
        [("stadtteil", "wald"), ("stadtteil", "mitte"), ("q", "Brot")], city="Solingen"
    )
    assert ("stadtteil", MITTE) in pairs and ("stadtteil", WALD) in pairs
    assert [v for k, v in pairs if k == "stadtteil"] == sorted([MITTE, WALD])


def test_follow_single_district_hash_unchanged():
    one = follow_query.canonical([("stadtteil", "wald"), ("q", "Brot")], city="Solingen")
    assert one == (("q", "Brot"), ("stadtteil", WALD))


def test_follow_refuses_more_districts_than_cap_instead_of_truncating():
    many = [("stadtteil", d) for d in ("wald", "mitte", "graefrath", "burg-hoehscheid")]
    assert follow_query.canonical(many + [("q", "Brot")], city="Solingen") is None


# --- ревью FLT-1b ------------------------------------------------------------------------


def test_filter_form_keeps_param_district_on_district_path_page():
    """«Anwenden» на /stadtteil/wald/?stadtteil=mitte не теряет ни один район: форма шлёт
    на корень, район пути — отмеченной галочкой (FLT-1d, план §13.3)."""
    _seed()
    p = _portal()
    html = _html(p, "/stadtteil/wald/?stadtteil=mitte", district=WALD)
    # PH-11b: шторка теперь стоит ПЕРЕД выдачей (колонка слева) — режем строго до </dialog>
    drawer = html.split('id="flt-drawer"', 1)[1].split("</dialog>", 1)[0]
    assert 'action="/"' in drawer
    assert 'name="stadtteil" value="wald" class="w-5 h-5" checked' in drawer
    assert 'name="stadtteil" value="mitte" class="w-5 h-5" checked' in drawer
    assert '<input type="hidden" name="stadtteil"' not in drawer  # районы — галочками


def test_facet_with_single_district_param_stays_self_canonical_noindex():
    _seed()
    p = _portal()
    html = _html(p, "/bakery/?stadtteil=wald", facet="bakery")
    assert "/stadtteil/wald/" not in html.split('rel="canonical"')[1][:120]


def test_open_feed_takes_every_district():
    from django.http import QueryDict

    from apps.aggregator import open_feed

    qd = QueryDict("stadtteil=wald&stadtteil=mitte")
    params = open_feed.parse_params(type("R", (), {"GET": qd})(), city="Solingen")
    assert params.districts == (WALD, MITTE)


def test_search_log_key_dedupes_path_and_param_district():
    from apps.aggregator import search_log

    _key, shown = search_log.filters_key(_filters(stadtteil="wald"), extra={"stadtteil": WALD})
    assert shown["stadtteil"] == [WALD]


# --- FLT-1d: шторка -----------------------------------------------------------------------


def test_drawer_submit_keeps_every_state_param():
    """W0 (план §1/§4): «Treffer anzeigen» не теряет марку, компанию, карту, «roh=ort»…"""
    import re

    _seed()
    p = _portal()
    path = (
        "/?q=Brot&kind=alle&neu=1&roh=ort&ansicht=karte&marke=Bosch&unternehmen=w1"
        "&groesse=M&sort=endet&preis_von=1&preis_bis=9&datum=heute&verfuegbar=1&offen=1"
        "&stadtteil=wald&kat=lebensmittel-getraenke&merkmal=bio&lat=51.17&lng=7.08&umkreis=5"
    )
    html = _html(p, path)
    drawer = html.split('id="flt-drawer"', 1)[1].split("</dialog>", 1)[0]
    names = set(re.findall(r'name="([a-z_]+)"', drawer))
    sent = {k for k in re.findall(r"[?&]([a-z_]+)=", path)}
    assert sent <= names, sent - names


def test_filter_forms_have_no_csrf_token():
    """Страница портала приходит из кэша публичных страниц — формы фильтров только GET."""
    _seed()
    p = _portal()
    html = _html(p, "/?q=Brot")
    bar = html.split("data-flt", 1)[1].split("</dialog>", 1)[0]
    assert "csrfmiddlewaretoken" not in bar and 'method="post"' not in bar.lower()


# --- ревью FLT-1d ------------------------------------------------------------------------


def test_brand_and_business_filters_can_be_removed_and_reset():
    """F1: «Alle von Bosch» вела на /?marke=Bosch без ✕ — снять фильтр было нельзя."""
    _seed()
    p = _portal()
    html = _html(p, "/?q=Brot&marke=Bosch&unternehmen=w1")
    pills = [h.replace("&amp;", "&") for h in _pill_hrefs(html)]
    assert "/?q=Brot&unternehmen=w1" in pills and "/?q=Brot&marke=Bosch" in pills
    reset = html.split("flt-drawer", 1)[1].split("Zurücksetzen", 1)[0].rsplit('href="', 1)[1]
    assert reset.split('"', 1)[0].replace("&amp;", "&") == "/?q=Brot"


def test_hotel_dates_survive_filter_links():
    """F2: поиск отеля по датам не сбрасывается фильтром района/сортировкой."""
    from apps.aggregator import portal_filter_ui

    req = RequestFactory().get("/?von=2030-05-01&bis=2030-05-03&gaeste=3&x=1")
    assert portal_filter_ui.hotel_params(req) == [
        ("von", "2030-05-01"),
        ("bis", "2030-05-03"),
        ("gaeste", "3"),
    ]
    bad = RequestFactory().get("/?von=2030-05-03&bis=2030-05-01")
    assert portal_filter_ui.hotel_params(bad) == []


def test_default_near_sort_is_not_written_into_links():
    """F4: «рядом» по умолчанию при точке — не параметр ссылок."""
    _seed()
    p = _portal()
    html = _html(p, "/?lat=51.17&lng=7.08&stadtteil=wald")
    assert "sort=naehe" not in html.split("data-flt-bar", 1)[1].split("</dialog>", 1)[0]


def _pill_hrefs(html):
    import re

    return re.findall(r'<a href="([^"]+)" rel="nofollow" data-flt-pill', html)
