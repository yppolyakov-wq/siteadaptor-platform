"""LB-3d-3: блок «Liste» — отзывы и блог (план lb-list-blocks §13.5/§13.11).

Замки написаны ДО кода. Отзывы — проверенные отзывы о сущностях (`reviews.Review`):
фильтры вид сущности · «ab N ★» · «nur mit Text», сортировка «новые/лучшие», ссылка на
сущность только у живой сущности включённого модуля, «Alle N →» нет (страницы таких
отзывов не существует). Блог — опубликованные статьи по дате, «Alle N →» → `/blog/`;
общая карточка `_blog_card` рисует и `/blog/`, и секцию главной — на языке витрины.
"""

import itertools
import re
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone, translation

from apps.booking.models import Service
from apps.catalog.models import Category, Product
from apps.core import list_blocks
from apps.core.tests.test_list_block_sources import (
    _all_link,
    _block,
    _builder_html,
    _clean,
    _home,
    _row,
    _section,
    _tenant,
)
from apps.events.models import BlogPost
from apps.reviews.models import Review
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db

_N = itertools.count()


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _product(name="Bauernbrot", **kw):
    cat = Category.objects.create(name={"de": "Brot"}, slug=f"brot-{next(_N)}")
    kw.setdefault("is_active", True)
    return Product.objects.create(name={"de": name}, base_price=Decimal("4.90"), category=cat, **kw)


def _review(entity, kind, rating=5, comment="Super", days=0, **kw):
    r = Review.objects.create(
        entity_kind=kind,
        entity_id=entity.pk if hasattr(entity, "pk") else entity,
        rating=rating,
        author_name=kw.pop("author_name", "Anna"),
        email=f"r{next(_N)}@example.de",
        comment=comment,
        **kw,
    )
    if days:
        Review.objects.filter(pk=r.pk).update(created_at=timezone.now() - timedelta(days=days))
    return r


def _post(title, days=0, published=True, **kw):
    return BlogPost.objects.create(
        title=title,
        slug=f"post-{next(_N)}",
        is_published=published,
        published_at=(timezone.now() - timedelta(days=days)) if days is not None else None,
        **kw,
    )


# ───────────────────────────── данные блока ─────────────────────────────


def test_review_block_keeps_only_its_own_filters():
    data = _clean(
        source="reviews",
        entity="product",
        stars=4,
        only="text",
        sort="best",
        category="kaese",  # фильтр каталога
        card="overlay",  # у отзывов форм карточки нет
    )
    assert data == {
        "source": "reviews",
        "entity": "product",
        "stars": 4,
        "only": "text",
        "sort": "best",
    }
    assert _clean(source="reviews", entity="auto", stars=9, only="video") == {"source": "reviews"}


def test_blog_block_keeps_no_filters():
    data = _clean(source="blog", category="x", only="text", sort="best", card="overlay", limit=3)
    assert data == {"source": "blog", "limit": 3}


def test_review_fields_never_travel_into_a_translation():
    for field in ("entity", "stars"):
        assert field in siteconfig.NON_TRANSLATABLE_FIELDS, field


# ───────────────────────────── отзывы ─────────────────────────────


def test_review_block_filters_by_kind_stars_and_text():
    bread = _product()
    cut = Service.objects.create(name="Schnitt", duration_minutes=30, price_cents=3000)
    _review(bread, "product", rating=5, comment="Kruste top")
    _review(bread, "product", rating=3, comment="Okay")
    _review(bread, "product", rating=5, comment="")
    _review(cut, "service", rating=5, comment="Toller Schnitt")
    _review(bread, "product", rating=5, comment="Versteckt", is_published=False)
    cfg = siteconfig.normalize({})

    def comments(**data):
        items = list_blocks.resolve(cfg, {"source": "reviews", **data})["items"]
        return sorted(r.comment for r in items)

    assert comments() == ["", "Kruste top", "Okay", "Toller Schnitt"]
    assert comments(entity="product") == ["", "Kruste top", "Okay"]
    assert comments(entity="product", stars=4) == ["", "Kruste top"]
    assert comments(entity="product", stars=4, only="text") == ["Kruste top"]


def test_review_block_sorts_newest_or_best():
    bread = _product()
    _review(bread, "product", rating=3, comment="alt gut", days=5)
    _review(bread, "product", rating=5, comment="alt top", days=4)
    _review(bread, "product", rating=4, comment="neu", days=1)
    cfg = siteconfig.normalize({})
    newest = list_blocks.resolve(cfg, {"source": "reviews"})["items"]
    assert [r.comment for r in newest] == ["neu", "alt top", "alt gut"]
    best = list_blocks.resolve(cfg, {"source": "reviews", "sort": "best"})["items"]
    assert [r.comment for r in best] == ["alt top", "neu", "alt gut"]


def test_review_cards_link_to_live_entities_only():
    bread = _product("Bauernbrot")
    gone = _product("Altbrot", is_active=False)
    _review(bread, "product", comment="Kruste top", days=2)
    _review(gone, "product", comment="Gab es mal", days=1)
    _review(uuid.uuid4(), "product", comment="Ohne Ware")  # сущность удалена
    t = _tenant([_block(source="reviews")])
    sec = _section(_home(t), "reviews")
    assert f'href="{bread.get_absolute_url()}"' in sec
    assert "Bauernbrot" in sec
    assert "Altbrot" in sec  # имя есть…
    assert f'href="{gone.get_absolute_url()}"' not in sec  # …а ссылки на снятую — нет
    assert "Ohne Ware" in sec  # отзыв виден и без сущности


def test_review_entity_links_do_not_grow_queries_with_cards():
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    counts = []
    for n in (2, 6):
        Review.objects.all().delete()
        for i in range(n):
            _review(_product(f"Brot {n}-{i}"), "product", comment=f"Text {i}")
        t = _tenant([_block(source="reviews")])
        with CaptureQueriesContext(connection) as ctx:
            _home(t)
        counts.append(len(ctx.captured_queries))
    assert counts[0] == counts[1]


def test_review_block_has_no_show_all_link():
    bread = _product()
    for i in range(4):
        _review(bread, "product", comment=f"Text {i}")
    sec = _section(_home(_tenant([_block(source="reviews", limit=2)])), "reviews")
    assert sec.count("data-review-card") == 2
    assert _all_link(sec) is None  # страницы проверенных отзывов нет — ссылке вести некуда


def test_review_block_needs_the_reviews_module():
    _review(_product(), "product", comment="Text")
    assert 'data-sf-list="reviews"' in _home(_tenant([_block(source="reviews")]))
    body = _home(_tenant([_block(source="reviews")], disabled=["reviews"]))
    assert 'data-sf-list="reviews"' not in body


def test_review_comment_is_shown_in_the_visitors_language():
    _review(_product(), "product", comment="Sehr gut", comment_i18n={"ru": "Очень хорошо"})
    t = _tenant([_block(source="reviews")])
    t.enabled_locales = ["de", "ru"]
    t.save(update_fields=["enabled_locales"])
    with translation.override("ru"):
        sec = _section(_home(t), "reviews")
    assert "Очень хорошо" in sec


# ───────────────────────────── блог ─────────────────────────────


def test_blog_block_shows_published_posts_newest_first():
    _post("Alt", days=10)
    _post("Neu", days=1)
    _post("Ohne Datum", days=None)
    _post("Entwurf", days=0, published=False)
    items = list_blocks.resolve(siteconfig.normalize({}), {"source": "blog"})["items"]
    assert [p.title for p in items] == ["Neu", "Alt", "Ohne Datum"]


def test_blog_block_links_to_the_blog():
    for i in range(3):
        _post(f"Post {i}", days=i + 1)
    sec = _section(_home(_tenant([_block(source="blog", limit=2)])), "blog")
    assert sec.count("data-blog-card") == 2
    assert _all_link(sec) == "/blog/"


def test_blog_block_needs_the_blog_module():
    _post("Post", days=1)
    t = _tenant([_block(source="blog")])
    assert 'data-sf-list="blog"' in _home(t)
    body = _home(_tenant([_block(source="blog")], disabled=["blog"]))
    assert 'data-sf-list="blog"' not in body


def _blog_index(tenant):
    from apps.events import public_views

    req = RequestFactory().get("/blog/")
    SessionMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    return public_views.blog_index(req).content.decode()


def test_blog_page_and_home_section_use_the_shared_card_in_the_visitors_language():
    """Класс C I18N-11: `/blog/` печатал сырые title/excerpt, секция главной — сырой
    excerpt; переводы статей не показывались. Одна карточка на три места."""
    _post(
        "Herbstpflege",
        days=1,
        excerpt="Tipps für den Herbst",
        title_i18n={"ru": "Уход осенью"},
        excerpt_i18n={"ru": "Советы на осень"},
    )
    t = _tenant([])
    cfg = dict(t.site_config)
    for row in cfg["sections"]:
        if row.get("key") == "blog":
            row["enabled"] = True  # секция «News» главной
    t.site_config = cfg
    t.enabled_locales = ["de", "ru"]
    t.save(update_fields=["site_config", "enabled_locales"])
    with translation.override("ru"):
        page = _blog_index(t)
        home = _home(t)
    assert "data-blog-card" in page and "Уход осенью" in page and "Советы на осень" in page
    assert "Herbstpflege" not in page
    assert "data-blog-card" in home and "Советы на осень" in home


# ───────────────────────────── редактор ─────────────────────────────


def test_editor_offers_review_kinds_of_active_modules():
    block = _block(source="reviews", entity="stay")  # модуль номеров выключен
    t = _tenant([block], disabled=["stays"])
    row = _row(_builder_html(t), block["id"])
    i = row.index(f'name="cb_{block["id"]}_entity"')
    select = row[i : row.index("</select>", i)]
    assert 'value="product"' in select and 'value="service"' in select
    assert re.search(r'value="stay"[^>]*selected', select)  # свой вид блока (W0)
    assert select.count('value="stay"') == 1
    i = row.index(f'name="cb_{block["id"]}_stars"')
    assert 'value="4"' in row[i : row.index("</select>", i)]


def test_editor_hides_rows_the_new_sources_do_not_have():
    block = _block(source="blog")
    row = _row(_builder_html(_tenant([block])), block["id"])
    bid = block["id"]

    def box_of(name):
        i = row.index(f'name="cb_{bid}_{name}"')
        start = row.rindex("data-lb-src=", 0, i)
        return row[start : row.index(">", start)]

    assert "blog" not in box_of("sort") and "reviews" in box_of("sort")
    assert "blog" not in box_of("card") and "reviews" not in box_of("card")
    sorts: dict = {}
    for key, _label, srcs in list_blocks.sort_options():
        sorts.setdefault(key, set()).update(srcs.split())
    assert "reviews" in sorts["best"] and "reviews" in sorts[""]
    assert "blog" not in set().union(*sorts.values())
