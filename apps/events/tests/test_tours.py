"""MT-1: тур-продукт — кабинет, витрина и ЗАМКИ видимости маршрута.

Главное, что здесь охраняется: закрытая гидом остановка не должна появиться в
HTML витрины ни при каких обстоятельствах. Плюс паритет: обычные события (без
тура) продолжают работать как раньше.
"""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory
from django.utils import timezone

from apps.events import itinerary, public_views, views
from apps.events.models import Event, Tour
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(**kwargs):
    kwargs.setdefault("name", "Himalaya Rides")
    kwargs.setdefault("enabled_modules", ["events"])
    return TenantFactory.build(**kwargs)


def _pub(path="/touren/", method="get", data=None, tenant=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant or _tenant()
    return request


def _cab(path="/dashboard/events/touren/", method="get", data=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = _tenant()
    suffix = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{suffix}", email=f"o-{suffix}@test.de", password="pw12345678"
    )
    return request


ROUTE = [
    {
        "day": 1,
        "title": "Start Manali",
        "visibility": itinerary.PUBLIC,
        "lat": "32.24",
        "lng": "77.18",
    },
    {"day": 2, "title": "Hotel Jispa", "visibility": itinerary.PARTICIPANTS, "km": 140},
    {"day": 3, "title": "Geheimer Pass", "visibility": itinerary.PRIVATE, "km": 90},
]


def _tour(**kwargs):
    kwargs.setdefault("title", "Manali – Leh")
    kwargs.setdefault("slug", f"manali-leh-{uuid.uuid4().hex[:6]}")
    kwargs.setdefault("is_published", True)
    kwargs.setdefault("itinerary", ROUTE)
    return Tour.objects.create(**kwargs)


def _departure(tour, days_ahead=30, **kwargs):
    kwargs.setdefault("title", "Juni-Tour")
    kwargs.setdefault("status", Event.STATUS_PUBLISHED)
    kwargs.setdefault("price_cents", 149000)
    return Event.objects.create(
        tour=tour, starts_at=timezone.now() + timezone.timedelta(days=days_ahead), **kwargs
    )


class TestStorefrontVisibility:
    def test_guest_never_sees_private_or_participant_stops(self):
        tour = _tour()
        response = public_views.tour_detail(_pub(f"/tour/{tour.slug}/"), slug=tour.slug)
        body = response.content.decode()
        assert "Start Manali" in body
        assert "Hotel Jispa" not in body  # только для участников
        assert "Geheimer Pass" not in body  # разработка гида

    def test_guest_sees_honest_hint_about_hidden_stops(self):
        tour = _tour()
        body = public_views.tour_detail(
            _pub(f"/tour/{tour.slug}/"), slug=tour.slug
        ).content.decode()
        assert "🔒" in body

    def test_fully_private_route_renders_nothing_of_it(self):
        """Маршрут целиком закрыт → на витрине ни одной остановки и ни одной точки."""
        tour = _tour(itinerary=[{**s, "visibility": itinerary.PRIVATE} for s in ROUTE])
        body = public_views.tour_detail(
            _pub(f"/tour/{tour.slug}/"), slug=tour.slug
        ).content.decode()
        for title in ("Start Manali", "Hotel Jispa", "Geheimer Pass"):
            assert title not in body
        assert "tour-route-data" not in body  # карты тоже нет

    def test_map_data_contains_only_public_points(self):
        tour = _tour(
            itinerary=[
                {
                    "day": 1,
                    "title": "Offen",
                    "visibility": itinerary.PUBLIC,
                    "lat": "32.2",
                    "lng": "77.1",
                },
                {
                    "day": 2,
                    "title": "Zu",
                    "visibility": itinerary.PRIVATE,
                    "lat": "34.1",
                    "lng": "77.5",
                },
            ]
        )
        body = public_views.tour_detail(
            _pub(f"/tour/{tour.slug}/"), slug=tour.slug
        ).content.decode()
        assert "34.1" not in body
        assert "32.2" in body

    def test_unpublished_tour_is_404(self):
        tour = _tour(is_published=False)
        with pytest.raises(Http404):
            public_views.tour_detail(_pub(f"/tour/{tour.slug}/"), slug=tour.slug)

    def test_module_gate(self):
        tour = _tour()
        request = _pub(f"/tour/{tour.slug}/", tenant=_tenant(disabled_modules=["events"]))
        with pytest.raises(Http404):
            public_views.tour_detail(request, slug=tour.slug)


class TestStorefrontContent:
    def test_index_lists_published_tours_only(self):
        _tour(title="Sichtbar")
        _tour(title="Versteckt", is_published=False)
        body = public_views.touren_index(_pub()).content.decode()
        assert "Sichtbar" in body
        assert "Versteckt" not in body

    def test_detail_lists_upcoming_departures_with_price(self):
        tour = _tour()
        _departure(tour)
        body = public_views.tour_detail(
            _pub(f"/tour/{tour.slug}/"), slug=tour.slug
        ).content.decode()
        assert "1490,00" in body or "1490.00" in body

    def test_past_departures_are_not_offered(self):
        tour = _tour()
        _departure(tour, days_ahead=-5, title="Vergangen")
        body = public_views.tour_detail(
            _pub(f"/tour/{tour.slug}/"), slug=tour.slug
        ).content.decode()
        assert "Vergangen" not in body

    def test_from_price_uses_cheapest_upcoming_departure(self):
        tour = _tour()
        _departure(tour, days_ahead=10, price_cents=199000)
        _departure(tour, days_ahead=40, price_cents=149000)
        assert tour.from_price_cents == 149000

    def test_index_query_count_does_not_grow_with_tours(self):
        """Замок N+1: «ab X €» берётся из prefetch — запросов столько же на 1 и на 5 туров.

        Проверяем именно РОСТ, а не абсолютное число: у страницы есть запросы хрома,
        и их точное количество — не предмет этого замка.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        _departure(_tour(title="Einzeln"))
        with CaptureQueriesContext(connection) as one:
            public_views.touren_index(_pub())
        for i in range(4):
            _departure(_tour(title=f"Weitere {i}"), price_cents=100000 + i)
        with CaptureQueriesContext(connection) as many:
            public_views.touren_index(_pub())
        assert len(many) == len(one), (
            f"на 5 туров запросов {len(many)} против {len(one)} на один — вернулся N+1"
        )


class TestDetailWording:
    """Дефекты, найденные на стенде: страница тура за 1490 € писала «Kostenlos»,
    а строка места печатала страну дважды («Ladakh, Indien · Indien»)."""

    def test_price_block_shows_cheapest_departure_not_free(self):
        tour = _tour(details={"price_includes": ["Motorrad"]})
        _departure(tour, price_cents=149000)
        body = public_views.tour_detail(
            _pub(f"/tour/{tour.slug}/"), slug=tour.slug
        ).content.decode()
        assert "1490" in body
        assert "Kostenlos" not in body and ">Free<" not in body

    def test_place_line_does_not_repeat_country(self):
        tour = _tour(region="Ladakh, Indien", country="Indien")
        body = public_views.tour_detail(
            _pub(f"/tour/{tour.slug}/"), slug=tour.slug
        ).content.decode()
        assert body.count("📍 Ladakh, Indien") == 1
        assert "Ladakh, Indien · Indien" not in body


class TestCountryGrouping:
    """MT-D2: разбивка листинга по странам."""

    def test_tours_are_grouped_by_country_in_order_of_appearance(self):
        tours = [
            _tour(title="Ladakh", country="Indien", sort_order=1),
            _tour(title="Mustang", country="Nepal", sort_order=2),
            _tour(title="Spiti", country="Indien", sort_order=3),
        ]
        groups = public_views.group_tours_by_country(tours)
        assert [g["key"] for g in groups] == ["Indien", "Nepal"]
        assert [t.title for t in groups[0]["tours"]] == ["Ladakh", "Spiti"]

    def test_two_countries_render_section_headings(self):
        _tour(title="Ladakh", country="Indien")
        _tour(title="Mustang", country="Nepal")
        body = public_views.touren_index(_pub()).content.decode()
        assert 'id="land-indien"' in body and 'id="land-nepal"' in body

    def test_single_country_renders_flat_list(self):
        """Заголовок над единственной группой — шум, а не структура."""
        _tour(title="Ladakh", country="Indien")
        _tour(title="Spiti", country="Indien")
        assert 'id="land-indien"' not in public_views.touren_index(_pub()).content.decode()

    def test_group_label_is_localized_but_key_stays_base(self):
        """Группируем по БАЗОВОМУ значению, показываем перевод — иначе на другой
        локали одна страна распалась бы на несколько групп."""
        tours = [
            _tour(title="Ladakh", country="Indien", country_i18n={"en": "India"}),
            _tour(title="Spiti", country="Indien"),  # без перевода
        ]
        from django.utils import translation

        with translation.override("en"):
            groups = public_views.group_tours_by_country(tours)
        assert len(groups) == 1
        assert groups[0]["key"] == "Indien" and groups[0]["label"] == "India"


class TestHomeSection:
    """MT-F1: поездки на главной — секция `tours` (главная тур-оператора была пустой)."""

    def _home(self, tenant):
        from apps.promotions import public_views as promo_views

        request = _pub("/", tenant=tenant)
        return promo_views.storefront_home(request).content.decode()

    def _tenant_with_section(self, **kwargs):
        return _tenant(
            site_config={
                "sections": [{"key": "hero", "enabled": True}, {"key": "tours", "enabled": True}]
            },
            **kwargs,
        )

    def test_enabled_section_shows_tour_cards(self):
        _tour(title="Ladakh-Runde", country="Indien")
        html = self._home(self._tenant_with_section())
        assert "Ladakh-Runde" in html
        assert 'id="reisen"' in html  # якорь для пункта меню

    def test_no_tours_no_section(self):
        """Секция включена, туров нет → пустого блока на главной не появляется."""
        html = self._home(self._tenant_with_section())
        assert 'data-grid="tours"' not in html

    def test_unpublished_tour_stays_off_home(self):
        _tour(title="Versteckt", is_published=False)
        assert "Versteckt" not in self._home(self._tenant_with_section())

    def test_section_off_by_default(self):
        """Легаси-витрины не затронуты: без включения секции туров на главной нет."""
        _tour(title="Ladakh-Runde")
        html = self._home(_tenant(site_config={"sections": [{"key": "hero", "enabled": True}]}))
        assert "Ladakh-Runde" not in html


class TestPrivateTourRequest:
    """MT-D3: заявка на приватный выезд (вне общих дат)."""

    def test_link_appears_when_jobs_module_is_active(self):
        tour = _tour(title="Ladakh")
        response = public_views.tour_detail(_pub(f"/tour/{tour.slug}/"), slug=tour.slug)
        assert "/anfrage/?betreff=Ladakh" in response.content.decode()

    def test_no_link_without_jobs_module(self):
        """Гейт — активность модуля (disabled_modules), а не витринная разметка."""
        tour = _tour(title="Ladakh")
        request = _pub(f"/tour/{tour.slug}/", tenant=_tenant(disabled_modules=["jobs"]))
        body = public_views.tour_detail(request, slug=tour.slug).content.decode()
        assert "/anfrage/?betreff=" not in body

    def test_index_offers_private_tour_when_module_active(self):
        _tour(title="Ladakh")
        body = public_views.touren_index(_pub()).content.decode()
        assert "Individuelle Reise" in body or "private tour" in body.lower()


class TestLocalizedContent:
    """MT-D1: оверлеи региона/страны/лендинга/маршрута."""

    def test_region_and_country_fall_back_to_base(self):
        tour = _tour(region="Ladakh, Indien", country="Indien")
        from django.utils import translation

        with translation.override("en"):
            assert tour.region_text == "Ladakh, Indien"  # перевода нет — база
        tour.region_i18n = {"en": "Ladakh, India"}
        with translation.override("en"):
            assert tour.region_text == "Ladakh, India"

    def test_landing_overlay_translates_only_leaves(self):
        tour = _tour(
            details={"promise": "Fünf Pässe", "price_includes": ["Motorrad", "Hotels"]},
            details_i18n={"en": {"promise": "Five passes", "price_includes": ["Motorcycle", ""]}},
        )
        from django.utils import translation

        with translation.override("en"):
            landing = tour.landing
        assert landing["promise"] == "Five passes"
        assert landing["price_includes"] == ["Motorcycle", "Hotels"]  # пустой → база

    def test_route_is_translated_before_it_is_filtered(self):
        """Оверлей мерджит списки ПОЗИЦИОННО: если переводить после фильтра,
        тексты сядут на чужие остановки, а закрытая — вообще может утечь."""
        tour = _tour(
            itinerary_i18n={
                "en": [
                    {"title": "Start in Manali"},
                    {"title": "Hotel in Jispa"},
                    {"title": "Secret pass"},
                ]
            }
        )
        from django.utils import translation

        with translation.override("en"):
            stops = tour.route(itinerary.GUEST)
            body = public_views.tour_detail(
                _pub(f"/tour/{tour.slug}/"), slug=tour.slug
            ).content.decode()
        assert [s["title"] for s in stops] == ["Start in Manali"]
        assert "Hotel in Jispa" not in body and "Secret pass" not in body

    def test_visibility_is_never_translated(self):
        """`visibility` — управляющее значение: перевод сломал бы фильтр."""
        tour = _tour(itinerary_i18n={"en": [{"visibility": "public"}, {"visibility": "public"}]})
        from django.utils import translation

        with translation.override("en"):
            assert len(tour.route(itinerary.GUEST)) == 1


class TestCabinet:
    def test_create_tour_generates_unique_slug(self):
        views.tour_list(_cab(method="post", data={"title": "Manali – Leh"}))
        views.tour_list(_cab(method="post", data={"title": "Manali – Leh"}))
        slugs = list(Tour.objects.values_list("slug", flat=True))
        assert len(slugs) == 2
        assert len(set(slugs)) == 2

    def test_edit_saves_route_with_visibility(self):
        tour = _tour(itinerary=[])
        data = {
            "title": tour.title,
            "duration_days": "12",
            "distance_km": "2400",
            "sort_order": "0",
            "it_present": "1",
            "it_day_0": "1",
            "it_title_0": "Manali",
            "it_visibility_0": itinerary.PUBLIC,
            "it_day_1": "2",
            "it_title_1": "Sarchu Camp",
            "it_visibility_1": itinerary.PRIVATE,
        }
        views.tour_edit(_cab(method="post", data=data), pk=tour.pk)
        tour.refresh_from_db()
        assert [s["title"] for s in tour.itinerary] == ["Manali", "Sarchu Camp"]
        assert tour.itinerary[1]["visibility"] == itinerary.PRIVATE
        assert tour.duration_days == 12

    def test_partial_post_without_sentinel_keeps_route(self):
        """Инвариант W0: форма без редактора маршрута не стирает маршрут."""
        tour = _tour()
        views.tour_edit(_cab(method="post", data={"title": tour.title}), pk=tour.pk)
        tour.refresh_from_db()
        assert len(tour.itinerary) == 3

    def test_landing_blocks_are_editable(self):
        """Тур получает тот же редактор богатых блоков, что и событие."""
        tour = _tour()
        data = {
            "title": tour.title,
            "faq_text": "Führerschein? | Klasse A erforderlich.",
            "bring_text": "Helm\nHandschuhe",
        }
        views.tour_edit(_cab(method="post", data=data), pk=tour.pk)
        tour.refresh_from_db()
        assert tour.landing["faq"] == [{"q": "Führerschein?", "a": "Klasse A erforderlich."}]
        assert tour.landing["bring"] == ["Helm", "Handschuhe"]


class TestEventParity:
    def test_event_without_tour_still_works(self):
        """Событие без тура — прежнее поведение (аддитивность MT-1)."""
        event = Event.objects.create(
            title="Einzelevent", starts_at=timezone.now() + timezone.timedelta(days=3)
        )
        assert event.tour_id is None
        assert Event.objects.filter(tour__isnull=True).count() == 1

    def test_deleting_tour_keeps_departures(self):
        """SET_NULL: удаление тура не уносит проданные заезды."""
        tour = _tour()
        departure = _departure(tour)
        tour.delete()
        departure.refresh_from_db()
        assert departure.tour_id is None
