"""T-8.20: единый поиск каталога города (портал + /entdecken/).

План — docs/t8-20-unified-search-plan-2026-10-15.md §5.
"""

import re
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.core.cache import cache
from django.db import connection
from django.test import RequestFactory, override_settings
from django.utils import timezone, translation

from apps.aggregator import portal_views, search, search_synonyms, tasks, views
from apps.aggregator.models import AggregatorListing, AggregatorPortal

pytestmark = pytest.mark.django_db

_n = iter(range(100_000))


@pytest.fixture(autouse=True)
def _clear():
    cache.clear()
    yield
    cache.clear()


def _listing(title, *, kind="promotion", schema=None, **kw):
    i = next(_n)
    title = title if isinstance(title, dict) else {"de": title}
    kw.setdefault("business_name", f"Laden {i}")
    return AggregatorListing.objects.create(
        tenant_schema=schema or f"t{i}",
        tenant_slug=f"x{i}",
        city=kw.pop("city", "Solingen"),
        listing_kind=kind,
        source_ref=f"s{i}",
        title=title,
        detail_url="https://x.siteadaptor.de/",
        **kw,
    )


def _found(q, filters=None, **kw):
    base = views.listings_for(city="Solingen")
    out = search.execute(base, q, filters, surface="test", **kw)
    return out, [x.title["de"] for x in out.qs]


def _req(path="/", ip="10.1.1.1", **params):
    return RequestFactory().get(path, params, REMOTE_ADDR=ip)


# --- сопоставление -----------------------------------------------------------------------


def test_german_stemming_finds_inflected_forms():
    _listing("Messer Santoku")
    _listing("Brötchen vom Bäcker")
    assert _found("Messern")[1] == ["Messer Santoku"]
    assert "Brötchen vom Bäcker" in _found("brot")[1]  # префикс последнего слова


def test_typo_falls_back_to_similar_spelling():
    _listing("Messer Santoku")
    out, titles = _found("Mesesr")
    assert out.mode == "trigram" and titles == ["Messer Santoku"]


def test_exact_hit_does_not_drag_in_similar_words():
    """Опечаточный поиск включается только при пустом полнотексте («Boot» ≈ «Brot»)."""
    _listing("Brot vom Bäcker")
    _listing("Boot fahren")
    out, titles = _found("Brot")
    assert out.mode == "fts" and titles == ["Brot vom Bäcker"]


def test_synonyms_work_both_ways():
    _listing("Smartphone-Reparatur in 1 Stunde")
    _listing("Handyhülle")
    assert "Smartphone-Reparatur in 1 Stunde" in _found("Handy")[1]
    _listing("Handy kaufen", schema="h")
    assert "Handy kaufen" in _found("smartphone")[1]


def test_synonym_dictionary_has_each_term_once():
    seen = {}
    for group in search_synonyms.GROUPS:
        assert len(group) >= 2
        for term in group:
            assert term == term.lower() and " " not in term and "-" not in term
            assert term not in seen, f"{term} в двух группах"
            seen[term] = group


def test_title_outranks_teaser_and_weights_are_settings():
    in_teaser = _listing("Küchenhelfer", teaser={"de": "Das beste Messer der Stadt"})
    in_title = _listing("Messer aus Solingen")
    AggregatorListing.objects.filter(pk=in_title.pk).update(
        created_at=timezone.now() - timedelta(days=10)
    )
    assert _found("Messer")[1] == ["Messer aus Solingen", "Küchenhelfer"]
    flipped = {"weights": {"A": 0.01, "B": 0.01, "C": 1.0, "D": 0.01}}
    with override_settings(AGGREGATOR_SEARCH={**_settings(), **flipped}):
        assert _found("Messer")[1][0] == "Küchenhelfer"
    assert in_teaser.pk


def _settings():
    from django.conf import settings

    return dict(settings.AGGREGATOR_SEARCH)


def test_category_label_and_district_and_business_are_searchable():
    _listing("Angebot", business_name="Feinkost Weber", city_category="feinkost")
    _listing("Zweites", district="graefrath")
    assert _found("Weber")[1] == ["Angebot"]
    assert _found("Spezialitäten")[1] == ["Angebot"]  # подпись категории справочника
    assert _found("Gräfrath")[1] == ["Zweites"]


def test_russian_title_with_russian_stemming():
    _listing({"de": "Frisches Brot", "ru": "Свежий хлеб"})
    with translation.override("ru"):
        assert _found("хлеба", lang="ru")[1] == ["Frisches Brot"]
        assert _found("Brot", lang="ru")[1] == ["Frisches Brot"]


# --- платное размещение (UWG §5a) -----------------------------------------------------------


def test_featured_does_not_change_organic_order():
    good = _listing("Messer Messer Messer")
    weak = _listing("Brettchen", teaser={"de": "mit Messer"})
    before = [x.pk for x in _found("Messer")[0].qs]
    AggregatorListing.objects.filter(pk=weak.pk).update(
        featured_until=timezone.now() + timedelta(days=3)
    )
    after = [x.pk for x in _found("Messer")[0].qs]
    assert before == after == [good.pk, weak.pk]


# --- невидимое ----------------------------------------------------------------------------


@pytest.mark.parametrize("q", ["Geheim", "Gehiem"])
def test_invisible_never_found_in_any_mode(q):
    from apps.tenants.tests.factories import TenantFactory

    TenantFactory(schema_name="t_hold", slug="hold", in_city_catalog=False)
    now = timezone.now()
    _listing("Geheim inaktiv", is_active=False)
    _listing("Geheim versteckt", hidden_at=now)
    _listing("Geheim abgelaufen", ends_at=now - timedelta(hours=1))
    _listing("Geheim vorbei", kind="event", starts_at=now - timedelta(days=1))
    _listing("Geheim gesperrt", schema="t_hold")
    demo = _listing("Geheim Demo", is_demo=True)
    base = views.listings_for(city="Solingen", include_demo=False)
    out = search.execute(base, q, surface="test")
    assert list(out.qs) == []
    assert demo.pk


# --- запрос: пустой, мусор, спецсимволы ----------------------------------------------------


@pytest.mark.parametrize("q", ["!!!:*&|", "'; DROP TABLE x; --", "a" * 500, "()<>"])
def test_garbage_query_is_safe(q):
    _listing("Messer")
    out = search.execute(views.listings_for(), q, surface="test")
    list(out.qs)  # без ошибки БД
    assert AggregatorListing.objects.exists()
    assert len(search.tokenize(q)) <= 8


def test_only_symbols_yield_nothing_not_everything():
    _listing("Messer")
    out = search.execute(views.listings_for(), "!!!", surface="test")
    assert out.mode == "empty" and list(out.qs) == []


@pytest.mark.urls("config.urls_portal")
def test_empty_query_keeps_portal_home():
    portal = _portal()
    _listing("Messer")
    req = _req(q="  ")
    req.portal = portal
    assert "data-portal-home" in portal_views.portal_home(req).content.decode()


# --- фильтры ---------------------------------------------------------------------------------


def _filters(**params):
    return search.parse_filters(_req(**params), city="Solingen")


def test_filters_one_by_one():
    now = timezone.now()
    _listing("Pizza", city_category="restaurants", new_price=Decimal("9.50"), district="graefrath")
    _listing("Brot", city_category="brot-backwaren", new_price=Decimal("3"))
    _listing("Jacke", kind="product", city_category="damenmode", availability="sold_out")
    _listing("Vegan Bio", city_tags=["vegan", "bio"])
    _listing("Nur vegan", city_tags=["vegan"])
    # +1 минута, не +1 час: час пересекал бы полночь и ронял тест вечером
    _listing("Konzert heute", kind="event", starts_at=now + timedelta(minutes=1))
    _listing("Konzert später", kind="event", starts_at=now + timedelta(days=30))
    _listing("Zimmer", kind="stay")
    assert set(_found("", _filters(kat=["essen-gastronomie", "brot-backwaren"]))[1]) == {
        "Pizza",
        "Brot",
    }
    assert _found("", _filters(merkmal=["vegan", "bio"]))[1] == ["Vegan Bio"]  # И
    assert _found("", _filters(stadtteil="graefrath"))[1] == ["Pizza"]
    assert set(_found("", _filters(preis_von="4", preis_bis="9,50"))[1]) == {"Pizza"}
    heute = _found("", _filters(datum="heute"))[1]
    assert "Konzert heute" in heute and "Konzert später" not in heute
    assert "Zimmer" in heute  # пересмотр Р-О1 (2026-10-23): номер при дате не отпадает
    assert "Jacke" not in _found("", _filters(verfuegbar="1"))[1]


def test_filters_combined_with_query():
    _listing("Pizza Margherita", city_category="restaurants", district="graefrath")
    _listing("Pizza Salami", city_category="restaurants", district="wald")
    _listing("Pizza Ofen", kind="product", city_category="haushalt", district="graefrath")
    f = _filters(kat="essen-gastronomie", stadtteil="graefrath")
    assert _found("Pizza", f)[1] == ["Pizza Margherita"]


def test_garbage_filter_values_are_ignored():
    f = _filters(kat="zzz", merkmal="zzz", stadtteil="mond", datum="gestern", preis_von="abc")
    assert not f.active


def test_open_now_uses_business_hours():
    from apps.tenants.tests.factories import TenantFactory

    now = timezone.localtime()
    day = str(now.weekday())
    TenantFactory(
        schema_name="t_open", slug="open", opening_hours_structured={day: ["00:00", "23:59"]}
    )
    TenantFactory(schema_name="t_closed", slug="closed", opening_hours_structured={})
    _listing("Offen", schema="t_open")
    _listing("Ohne Zeiten", schema="t_closed")
    assert _found("", _filters(offen="1"))[1] == ["Offen"]


# --- поверхности ------------------------------------------------------------------------------


def _portal():
    return AggregatorPortal.objects.get_or_create(
        host="solingen.siteadaptor.de",
        defaults={
            "kind": "city",
            "city": "Solingen",
            "title": {"de": "Solingen lokal"},
            "is_active": True,
        },
    )[0]


def _titles(html):
    return set(
        re.findall(r'<h2 class="font-semibold leading-tight line-clamp-2">([^<]+)</h2>', html)
    )


@pytest.mark.urls("config.urls_portal")
def test_portal_and_entdecken_find_the_same():
    _listing("Messer Santoku", city_category="kunst")
    _listing("Messerschärfen", kind="service", city_category="handwerk")
    _listing("Brot")
    req = _req(q="Messer", kind="alle")
    req.portal = _portal()
    portal_html = portal_views.portal_home(req).content.decode()
    with override_settings(ROOT_URLCONF="config.urls_public"):
        ent = views.discover_index(_req("/entdecken/", q="Messer", city="Solingen"))
    assert (
        _titles(portal_html)
        == _titles(ent.content.decode())
        == {
            "Messer Santoku",
            "Messerschärfen",
        }
    )


@pytest.mark.urls("config.urls_portal")
def test_portal_typo_note_and_filter_panel():
    _listing("Messer Santoku", kind="product")
    req = _req(q="Mesesr")
    req.portal = _portal()
    html = portal_views.portal_home(req).content.decode()
    assert "Messer Santoku" in html and "data-search-fuzzy" in html
    assert "data-portal-filters" in html


@pytest.mark.urls("config.urls_portal")
def test_filter_pill_removes_only_its_filter():
    _listing("Pizza", city_category="restaurants", district="graefrath")
    req = _req(q="Pizza", stadtteil="graefrath", offen="1")
    req.portal = _portal()
    html = portal_views.portal_home(req).content.decode()
    pills = html.split("data-filter-pills", 1)[1].split("</div>", 1)[0]
    hrefs = [h.replace("&amp;", "&") for h in re.findall(r'href="([^"]+)"', pills)]
    assert len(hrefs) == 2 and all("q=Pizza" in h for h in hrefs)
    assert {("stadtteil=" in h, "offen=" in h) for h in hrefs} == {(False, True), (True, False)}


def test_ranked_pagination_has_no_duplicates():
    from apps.core.pagination import _encode, paginate_ranked

    for i in range(30):
        _listing(f"Messer {i}")
    qs = search.execute(views.listings_for(), "Messer", surface="test").qs
    first = paginate_ranked(qs, limit=24)
    second = paginate_ranked(qs, limit=24, cursor=first.next_cursor)
    pks = [x.pk for x in first.items + second.items]
    assert len(first.items) == 24 and len(second.items) == 6 and len(set(pks)) == 30
    assert not second.has_more
    keyset = _encode({"v": "2026-01-01", "pk": 5})
    assert [x.pk for x in paginate_ranked(qs, limit=24, cursor=keyset).items] == [
        x.pk for x in first.items
    ]


@pytest.mark.urls("config.urls_portal")
def test_record_seam_called_once_per_search():
    _listing("Messer")
    req = _req(q="Messer")
    req.portal = _portal()
    with mock.patch.object(search, "record") as rec:
        portal_views.portal_home(req)
    assert rec.call_count == 1
    assert rec.call_args.kwargs["surface"] == "portal"
    assert rec.call_args.kwargs["portal_host"] == "solingen.siteadaptor.de"
    assert rec.call_args.kwargs["city"] == "Solingen"
    assert rec.call_args.args[0].mode == "fts"


@pytest.mark.urls("config.urls_portal")
def test_filter_without_query_is_rate_limited(isolated_ratelimit):
    from apps.core import ratelimit

    ip = "10.3.3.3"
    for _i in range(views.SEARCH_RATE_LIMIT):
        ratelimit.hit("portal-search", ip, limit=10_000, window=60)
    req = _req(ip=ip, offen="1")
    req.portal = _portal()
    assert portal_views.portal_home(req).status_code == 429


@pytest.mark.urls("config.urls_portal")
@override_settings(PORTAL_DISTRICT_MIN_BUSINESSES=0)  # Г5 выкл.: хвост — свой замок счёта
def test_query_count_does_not_grow(django_assert_max_num_queries):
    portal = _portal()
    for i in range(3):
        _listing(f"Messer {i}", city_category="kunst")
    req = _req(q="Messer", stadtteil="graefrath", sort="neu")
    req.portal = portal
    # T-8.21: +2 на журнал поиска (подсчёт с потолком + UPDATE/INSERT агрегата).
    # Блок Б1: +3 постоянных (районы и отрасли найденного, «N Treffer»); Б5: +1 (фирмы запроса).
    # AI-CFG: +2 постоянных — чтение настроек ИИ из БД (в тесте — с точкой сохранения);
    # в проде кэш 15 с на процесс. Второй замок ниже (уже с тёплым кэшем) держит рост.
    with django_assert_max_num_queries(28) as ctx:
        portal_views.portal_home(req)
    small = len(ctx.captured_queries)
    for i in range(30):
        _listing(f"Messer viel {i}", city_category="kunst")
    req = _req(q="Messer", stadtteil="graefrath", sort="neu", ip="10.1.1.2")
    req.portal = portal
    with django_assert_max_num_queries(small):
        portal_views.portal_home(req)


# --- индекс ------------------------------------------------------------------------------------


def _vector(pk):
    with connection.cursor() as cur:
        cur.execute(
            "SELECT search_vector::text FROM aggregator_aggregatorlisting WHERE id=%s", [pk]
        )
        return cur.fetchone()[0] or ""


def test_tenant_rename_updates_index():
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(schema_name="t_ren", slug="ren", name="Alter Name", city="Solingen")
    listing = _listing("Angebot", schema="t_ren", business_name="Alter Name")
    tenant.name = "Klingenhaus"
    tasks.refresh_tenant_fields(tenant)
    assert "klingenhaus" in _vector(listing.pk)
    assert _found("Klingenhaus")[1] == ["Angebot"]


def test_counter_update_does_not_touch_index_and_save_refreshes():
    listing = _listing("Messer")
    listing.title = {"de": "Schere"}
    listing.save(update_fields=["featured_clicks"])  # не индексируемое — индекс прежний
    assert "messer" in _vector(listing.pk)
    listing.save(update_fields=["title"])
    assert "scher" in _vector(listing.pk) and "messer" not in _vector(listing.pk)


def test_rebuild_command():
    from django.core.management import call_command

    listing = _listing("Messer")
    AggregatorListing.objects.filter(pk=listing.pk).update(search_vector=None, search_text="")
    call_command("rebuild_search_index")
    assert "messer" in _vector(listing.pk)


# --- находки ревью (django-reviewer / security-reviewer) -------------------------------------


@pytest.mark.parametrize("q", ["Brot in Solingen", "brot und", "the Brot", "Haarschnitt bei"])
def test_stopwords_do_not_break_the_query(q):
    """H1: «in», «und», «the», «bei» не требуют буквального слова — точный поиск, не опечатки."""
    _listing("Frisches Brot")
    _listing("Haarschnitt Herren")
    out, titles = _found(q)
    assert out.mode == "fts" and titles


def test_only_stopwords_find_nothing():
    _listing("Frisches Brot des Tages")
    out, titles = _found("der die das")
    assert out.mode == "empty" and titles == []


def test_compound_words_found_by_part():
    """M2: «brot» находит «Roggenbrot» (как раньше подстрокой)."""
    _listing("Roggenbrot")
    _listing("Mischbrot Aktion")
    _listing("Brötchen")
    titles = set(_found("brot")[1])
    assert {"Roggenbrot", "Mischbrot Aktion", "Brötchen"} <= titles
    assert views.listings_for(q="brot").count() == 3


def test_short_typo_tokens_do_not_flood_results():
    _listing("Frisches Brot")
    out, titles = _found("xq")
    assert titles == []


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1e999999", "sNaN", "abc"])
def test_garbage_price_is_ignored_not_500(value):
    """S1: цена из URL — только конечное число в разумных пределах."""
    assert views._money(value) is None
    _listing("Pizza", new_price=Decimal("5"))
    assert _found("", _filters(preis_von=value))[1] == ["Pizza"]


@pytest.mark.parametrize("payload", [{"o": 1e308 * 10}, {"o": "x"}, {"o": [1]}, {"v": 1}])
def test_garbage_cursor_is_first_page(payload):
    """M1/M5: курсор с огромным/чужим содержимым — первая страница, не 500."""
    import base64
    import json

    from apps.core.pagination import paginate, paginate_ranked

    raw = json.dumps(payload).replace("Infinity", "1e999")
    cursor = base64.urlsafe_b64encode(raw.encode()).decode()
    _listing("Messer")
    qs = views.listings_for()
    assert len(paginate_ranked(qs, limit=5, cursor=cursor).items) == 1
    assert len(paginate(qs, order_field="created_at", limit=5, cursor=cursor).items) == 1


def test_query_size_is_bounded():
    """S3: длина запроса, слова и число подзапросов tsquery ограничены."""
    q = " ".join(["handy smartphone fahrrad friseur"] * 20) + " " + "x" * 500
    tokens = search.tokenize(q)
    assert len(tokens) <= 8 and all(len(t) <= search.TOKEN_MAX for t in tokens)
    words = search._words(q, "de")
    sql = str(views.listings_for().filter(search_vector=search.build_query(q)).query)
    assert len(words) <= 8 and sql.count("to_tsquery") <= search.TERMS_MAX + 3 * 8


@pytest.mark.urls("config.urls_public")
def test_entdecken_form_and_chips_keep_filters():
    """M3: на /entdecken/ форма и чипы не теряют фильтры единого поиска."""
    _listing("Pizza", city_category="restaurants", district="graefrath")
    html = views.discover_index(
        _req("/entdecken/", q="Pizza", city="Solingen", stadtteil="graefrath", offen="1")
    ).content.decode()
    form = html.split('action="/entdecken/"', 1)[1].split("</form>", 1)[0]
    assert 'name="stadtteil" value="graefrath"' in form and 'name="offen" value="1"' in form


@pytest.mark.urls("config.urls_portal")
def test_portal_search_form_keeps_neu():
    _listing("Messer", is_new=True, kind="product")
    req = _req(kind="alle", neu="1")
    req.portal = _portal()
    html = portal_views.portal_home(req).content.decode()
    form = html.split("data-portal-search", 1)[1].split("</form>", 1)[0]
    assert 'name="neu" value="1"' in form


def test_save_writes_listing_and_index_together():
    """L1: запись листинга и индекса — одна транзакция (сбой индекса откатывает запись)."""
    listing = _listing("Messer")
    listing.title = {"de": "Schere"}
    with mock.patch("apps.aggregator.search_index.refresh_listing", side_effect=RuntimeError):
        with pytest.raises(RuntimeError):
            listing.save()
    listing.refresh_from_db()
    assert listing.title == {"de": "Messer"}


def test_migration_rollback_keeps_pg_trgm_extension():
    """database-reviewer: откат 0023 не удаляет расширение — оно могло быть чужим."""
    from importlib import import_module

    from django.db import migrations

    mod = import_module("apps.aggregator.migrations.0023_t8_20_search")
    sql_ops = [op for op in mod.Migration.operations if isinstance(op, migrations.RunSQL)]
    assert sql_ops and "pg_trgm" in sql_ops[0].sql
    assert sql_ops[0].reverse_sql == migrations.RunSQL.noop


# --- T-8.26 п.4: фолбэк по значимым словам, топонимы, пометка на /entdecken/ ----------------


def test_fallback_ignores_toponyms_and_needs_the_subject():
    """Аудит §7.3-1: «Friseur in Solingen-Wald» давал 18 мусорных «ähnliche» — длинное
    «solingen» вытягивало склеенную фразу выше порога, хотя предмета в тексте нет."""
    _listing("Fahrrad-Check", business_name="Rad & Tat Solingen")
    _listing("Burg Solingen Tour")
    _listing("Herrenschnitt", business_name="Friseur Kamm")
    out, titles = _found("Friseur in Solingen-Wald", city="Solingen")
    assert out.mode == "trigram" and titles == ["Herrenschnitt"]


def test_toponyms_only_query_finds_nothing_fuzzy():
    _listing("Messer aus Solingen")
    _listing("Burg Solingen Tour")
    out, titles = _found("Solingen-Wald", city="Solingen")
    assert out.mode == "trigram" and titles == []


def test_toponyms_apply_only_to_registry_cities():
    """Ревью: в городе вне реестра «Burg»/«Wald» — обычные слова, фолбэк их не теряет."""
    from apps.core import districts

    assert districts.toponym_tokens("Hilden") == frozenset()
    _listing("Burgführung am Abend", city="Hilden")
    base = views.listings_for(city="Hilden")
    out = search.execute(base, "Burgfuehrung", surface="test", city="Hilden")
    assert [x.title["de"] for x in out.qs] == ["Burgführung am Abend"]


def test_need_boundary_three_terms_one_hit_is_excluded():
    _listing("Messer Santoku")
    _, titles = _found("Mesesr Qqqqq Zzzzz", city="Solingen")  # n=3, совпало 1 < need=2
    assert titles == []


def test_soft_step_runs_only_when_toponym_or_hyphen_changed_the_terms():
    """Опечатка + топоним → мягкий точный поиск по оставшимся словам не поможет
    (слово с опечаткой), дальше триграммы по значимым словам находят предмет."""
    _listing("Herrenschnitt", business_name="Friseur Kamm")
    _listing("Burg Solingen Tour")
    out, titles = _found("Frisur in Solingen-Wald", city="Solingen")
    assert out.mode == "trigram" and titles == ["Herrenschnitt"]
    # цифра не «меняет состав»: «Messer 2000» → фолбэк по «messer», без мягкого шага
    _listing("Messer Santoku")
    assert search._significant(["messer", "2000"]) == {"messer"}


def test_per_word_threshold_with_ballast_word():
    _listing("Messer Santoku")
    _, titles = _found("Mesesr Santoku Zzzz", city="Solingen")  # n=3 → хватит 2 совпавших
    assert titles == ["Messer Santoku"]
    _, titles = _found("Mesesr Zzzz", city="Solingen")  # n=2 → нужны оба
    assert titles == []


def test_hyphen_still_glued_for_exact_search():
    """Регресс-замок tokenize: «E-Bike» ищется точно как «ebike» (синонимы), фолбэк не нужен."""
    _listing("E-Bike Verleih")
    _, titles = _found("E-Bike", city="Solingen")
    assert titles == ["E-Bike Verleih"]


def test_toponym_tokens_registry():
    from apps.core import districts

    toks = districts.toponym_tokens("Solingen")
    assert {
        "solingen",
        "wald",
        "graefrath",
        "grafrath",
        "hoehscheid",
        "hohscheid",
        "ohligs",
    } <= toks
    assert "" not in toks and "friseur" not in toks
    assert toks <= districts.toponym_tokens("")  # без города — объединение по реестру


@override_settings(ROOT_URLCONF="config.urls_public")
def test_entdecken_marks_fuzzy_results(isolated_ratelimit):
    _listing("Messer Santoku")
    html = views.discover_index(_req("/entdecken/", q="Mesesr", city="Solingen")).content.decode()
    assert "data-search-fuzzy" in html and "Messer Santoku" in html
    html = views.discover_index(
        _req("/entdecken/", q="Messer", city="Solingen", ip="10.1.1.2")
    ).content.decode()
    assert "data-search-fuzzy" not in html


# --- T-8.26 п.5a: намерение запроса на обеих поверхностях -------------------------------


def _portal_html(q, isolated=True, **params):
    portal = _portal()
    req = RequestFactory().get("/", {"q": q, **params}, REMOTE_ADDR="10.5.5.5")
    req.portal = portal
    return portal_views.portal_home(req).content.decode()


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_winterjacke_unter_100_filters_price_and_shows_removable_chip(isolated_ratelimit):
    _listing("Jacke Basic", kind="product", new_price=Decimal("80"))
    _listing("Jacke Premium", kind="product", new_price=Decimal("150"))
    html = _portal_html("Jacke unter 100 Euro")
    assert "Jacke Basic" in html and "Jacke Premium" not in html
    assert 'data-intent-chip="preis_bis"' in html
    # выведенное НЕ прилипает к форме: скрытых полей preis_bis нет, q остаётся сырым
    assert 'type="hidden" name="preis_bis"' not in html
    assert 'name="preis_bis" value="100' not in html  # панель фильтров показывает ЯВНЫЕ
    assert 'value="Jacke unter 100 Euro"' in html


# Г5 выкл.: замок точности района (хвост соседей — test_district_threshold).
@override_settings(ROOT_URLCONF="config.urls_portal", PORTAL_DISTRICT_MIN_BUSINESSES=0)
def test_friseur_in_wald_filters_district_and_roh_ort_undoes_it(isolated_ratelimit):
    _listing("Herrenschnitt Wald", business_name="Friseur Wald", district="wald")
    _listing("Herrenschnitt Mitte", business_name="Friseur Mitte", district="mitte")
    html = _portal_html("Friseur in Solingen-Wald")
    assert "Herrenschnitt Wald" in html and "Herrenschnitt Mitte" not in html
    assert 'data-intent-chip="stadtteil"' in html and "roh=ort" in html
    html = _portal_html("Friseur in Solingen-Wald", roh="ort")
    assert "Herrenschnitt Wald" in html and "Herrenschnitt Mitte" in html


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_heute_geoeffnet_equals_offen_param(isolated_ratelimit, monkeypatch):
    a = _listing("Trattoria Sole", business_name="Trattoria")
    _listing("Bistro Luna", business_name="Bistro")
    monkeypatch.setattr(views, "_open_now_schemas", lambda schemas: {a.tenant_schema})
    by_text = _titles(_portal_html("Trattoria heute geöffnet"))
    by_param = _titles(_portal_html("Trattoria", offen="1"))
    assert by_text == by_param == {"Trattoria Sole"}


@override_settings(ROOT_URLCONF="config.urls_public")
def test_entdecken_intent_chips_and_journal_raw_query(isolated_ratelimit):
    from apps.aggregator.models import SearchQueryLog

    _listing("Jacke Basic", kind="product", new_price=Decimal("80"))
    html = views.discover_index(
        _req("/entdecken/", q="Jacke unter 100 euro", city="Solingen", ip="10.5.5.6")
    ).content.decode()
    assert 'data-intent-chip="preis_bis"' in html and "Jacke Basic" in html
    row = SearchQueryLog.objects.get()
    assert row.query_norm == "jacke unter 100 euro"  # сырой запрос жителя
    assert "auto" in row.filters and "preis" in str(row.filters["auto"])


# --- T-8.26 п.5b: составные слова (закрытый словарь голов) + синонимы --------------------


def test_compound_finds_head_and_ranks_exact_first():
    _listing("Jacke Basic", kind="product")
    _listing("Winterjacke Alpin", kind="product")
    out, titles = _found("Winterjacke", city="Solingen")
    assert out.mode == "fts" and titles[0] == "Winterjacke Alpin" and "Jacke Basic" in titles


def test_modifier_prefix_is_an_or_branch_of_the_same_word():
    _listing("Kinder Basteln")
    _listing("Aktivitäten für alle")
    _, titles = _found("Kinderaktivitäten", city="Solingen")
    assert set(titles) == {"Kinder Basteln", "Aktivitäten für alle"}


def test_heads_stoplist_nachtisch_is_not_tisch():
    assert "tisch" not in search_synonyms.HEADS and "haus" not in search_synonyms.HEADS
    _listing("Tisch aus Eiche", kind="product")
    out, titles = _found("Nachtisch", city="Solingen")
    # точного совпадения нет (голова «tisch» не раскрывается); если что-то и находится,
    # то только фолбэком опечаток — и подписано «ähnliche», а не как точный результат
    assert out.mode != "fts"


def test_split_compound_rules():
    sc = search_synonyms.split_compound
    assert sc("winterjacke") == ("winter", "jacke")
    assert sc("kinderaktivitäten") == ("kinder", "aktivitäten")
    assert sc("jacke") == ()  # короткое / само в словаре
    assert sc("zahnbürste") == ()  # неизвестная голова и модификатор
    assert sc("nachtisch") == ()  # стоп-лист
    assert sc("bioladen") == ("bio",)  # только модификатор, остаток ≥ 3


def test_new_synonym_groups():
    _listing("Vegetarische Bowl")
    _, titles = _found("veggie", city="Solingen")
    assert titles == ["Vegetarische Bowl"]
    _listing("Jeans Slim", kind="product")
    _, titles = _found("Hose", city="Solingen")
    assert "Jeans Slim" in titles


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_kinderaktivitaeten_am_wochenende_equals_manual(isolated_ratelimit):
    soon = timezone.now() + timedelta(days=1)
    _listing("Kinder Zirkus", kind="event", starts_at=soon, ends_at=soon + timedelta(hours=2))
    _listing("Kinder Theater", kind="event", starts_at=soon + timedelta(days=30))
    with mock.patch("apps.aggregator.search.timezone.now", return_value=soon - timedelta(days=1)):
        by_text = _titles(_portal_html("Kinderaktivitäten am Wochenende"))
        by_param = _titles(_portal_html("Kinder", datum="wochenende"))
    assert by_text == by_param


def test_cyrillic_fallback_does_not_match_by_shared_suffix():
    """Фидбэк 2026-10-23: «сладости» находило «кости» и «лояльности» (общее «-ости»)."""
    _listing({"de": "Kauknochen", "ru": "Жевательные кости для собак"})
    _listing({"de": "Treuekarte", "ru": "Карта лояльности"})
    _listing({"de": "Sladosti-Box", "ru": "Сладкости ассорти"})
    out, titles = _found("сладости", lang="ru")
    assert "Kauknochen" not in titles and "Treuekarte" not in titles
