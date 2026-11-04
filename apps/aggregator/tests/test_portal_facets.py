"""FLT-1c: счётчики опций фильтров портала (план §3, §13.4).

Главный инвариант: счётчик опции = размер выдачи, которая получится, если её отметить.
Сверяем с тем же `search.apply_filters`, которым строится сама выдача.
"""

import uuid

import pytest

from apps.aggregator import portal_facets, search
from apps.aggregator.models import AggregatorListing

pytestmark = pytest.mark.django_db

WALD, MITTE, OHLIGS = "wald", "mitte", "ohligs-aufderhoehe-merscheid"
DISTRICTS = (WALD, MITTE, OHLIGS)
BROT, CAFE = "brot-backwaren", "cafes"
FOOD = "lebensmittel-getraenke"


def _l(district, cat, tags=()):
    return AggregatorListing.objects.create(
        tenant_schema="t",
        tenant_slug="t",
        business_name="T",
        business_type="bakery",
        city="Solingen",
        district=district,
        city_category=cat,
        city_tags=list(tags),
        promo_uuid=uuid.uuid4(),
        title={"de": "x"},
        detail_url="https://t.siteadaptor.de/p/1/",
        is_active=True,
    )


@pytest.fixture
def pool():
    _l(WALD, BROT, ("vegan", "bio"))
    _l(WALD, BROT, ("bio",))
    _l(WALD, CAFE, ("vegan",))
    _l(MITTE, BROT, ())
    _l(MITTE, CAFE, ("vegan", "bio"))
    _l(OHLIGS, CAFE, ())
    return AggregatorListing.objects.all()


def _expected(base, *, area=(), kats=(), tags=()):
    f = search.SearchFilters(districts=area, kats=kats, tags=tags)
    return search.apply_filters(base, f).count()


def _counts(base, **kw):
    return portal_facets.counts(base, district_options=DISTRICTS, **kw)


@pytest.mark.parametrize(
    "area, kats, tags",
    [
        ((), (), ()),
        ((WALD,), (), ()),
        ((WALD, MITTE), (), ()),
        ((), (BROT,), ()),
        ((WALD,), (FOOD,), ("bio",)),
        ((WALD, MITTE), (BROT, CAFE), ("vegan",)),
    ],
)
def test_total_is_exact_result_size(pool, area, kats, tags):
    assert _counts(pool, area=area, kats=kats, tags=tags).total == _expected(
        pool, area=area, kats=kats, tags=tags
    )


def test_district_count_ignores_own_facet_but_keeps_others(pool):
    c = _counts(pool, area=(WALD,), kats=(BROT,))
    for slug in DISTRICTS:
        assert c.districts[slug] == _expected(pool, area=(slug,), kats=(BROT,))
    assert c.districts[WALD] == c.total  # единственный выбранный район = «N Treffer»


def test_section_and_category_counts_ignore_own_facet(pool):
    c = _counts(pool, area=(WALD,), kats=(BROT,))
    assert c.sections[FOOD] == _expected(pool, area=(WALD,), kats=(FOOD,))
    assert c.categories[BROT] == c.total
    assert CAFE not in c.categories  # кафе — в другом разделе, строки только открытого
    assert "essen-gastronomie" in c.sections


def test_categories_only_for_open_sections(pool):
    assert _counts(pool).categories == {}
    assert BROT in _counts(pool, kats=(FOOD,)).categories


def test_tags_are_and(pool):
    c = _counts(pool, area=(WALD,), tags=("bio",))
    assert c.tags["bio"] == c.total == 2
    assert c.tags["vegan"] == _expected(pool, area=(WALD,), tags=("bio", "vegan")) == 1


def test_one_query(pool, django_assert_num_queries):
    with django_assert_num_queries(1):
        _counts(pool, area=(WALD,), kats=(FOOD,), tags=("bio",))


def test_ranked_pool_works(pool):
    """Пул поиска приходит с аннотациями ранга и сортировкой — агрегат их отбрасывает."""
    ranked = search.execute(pool, "", search.SearchFilters(), surface="portal", track=False).qs
    assert _counts(ranked).total == pool.count()
