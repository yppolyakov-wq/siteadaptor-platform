"""MT-1: канон маршрута тура + замки видимости.

Главный инвариант: закрытая остановка НЕ доходит до участника и до витрины.
Маршрут — интеллектуальная собственность гида, поэтому фильтрация проверяется
отдельно от рендера и трактует незнакомую аудиторию как постороннего.
"""

from apps.events import itinerary


def _stop(**kwargs):
    base = {"day": 1, "title": "Stopp", "visibility": itinerary.PUBLIC}
    base.update(kwargs)
    return base


class TestNormalize:
    def test_defaults_to_private(self):
        """Остановка без явной видимости закрыта — маршрут не публикуется сам."""
        [stop] = itinerary.normalize([{"title": "Manali"}])
        assert stop["visibility"] == itinerary.PRIVATE

    def test_unknown_visibility_falls_back_to_private(self):
        [stop] = itinerary.normalize([{"title": "X", "visibility": "everyone"}])
        assert stop["visibility"] == itinerary.PRIVATE

    def test_drops_empty_rows(self):
        """Пустые слоты редактора не копятся в JSON."""
        rows = [{"title": "", "text": "", "overnight": ""}, {"title": "Leh"}]
        assert [s["title"] for s in itinerary.normalize(rows)] == ["Leh"]

    def test_keeps_row_with_only_overnight(self):
        assert len(itinerary.normalize([{"overnight": "Camp Sarchu"}])) == 1

    def test_sorted_by_day_then_time(self):
        rows = [
            _stop(day=2, time_from="08:00", title="B"),
            _stop(day=1, time_from="15:00", title="A2"),
            _stop(day=1, time_from="09:00", title="A1"),
        ]
        assert [s["title"] for s in itinerary.normalize(rows)] == ["A1", "A2", "B"]

    def test_survives_garbage(self):
        rows = ["строка", None, 42, {"title": "OK"}]
        assert [s["title"] for s in itinerary.normalize(rows)] == ["OK"]

    def test_caps_number_of_stops(self):
        rows = [_stop(title=f"S{i}") for i in range(200)]
        assert len(itinerary.normalize(rows)) == 80

    def test_time_is_normalized_and_validated(self):
        rows = [_stop(time_from="9:5", time_to="25:00")]
        [stop] = itinerary.normalize(rows)
        assert stop["time_from"] == "09:05"
        assert stop["time_to"] == ""

    def test_coordinates_out_of_range_are_dropped(self):
        [stop] = itinerary.normalize([_stop(lat="95.0", lng="77,5772")])
        assert stop["lat"] == ""
        assert stop["lng"] == "77.5772"

    def test_km_from_garbage_is_zero(self):
        [stop] = itinerary.normalize([_stop(km="abc")])
        assert stop["km"] == 0


class TestVisibility:
    ROUTE = [
        _stop(day=1, title="Start Manali", visibility=itinerary.PUBLIC),
        _stop(day=2, title="Hotelname", visibility=itinerary.PARTICIPANTS),
        _stop(day=3, title="Geheimer Pass", visibility=itinerary.PRIVATE),
    ]

    def test_owner_sees_everything(self):
        assert len(itinerary.visible(self.ROUTE, itinerary.OWNER)) == 3

    def test_participant_sees_participants_and_public_only(self):
        titles = [s["title"] for s in itinerary.visible(self.ROUTE, itinerary.PARTICIPANT)]
        assert titles == ["Start Manali", "Hotelname"]

    def test_public_sees_only_public(self):
        titles = [s["title"] for s in itinerary.visible(self.ROUTE, itinerary.GUEST)]
        assert titles == ["Start Manali"]

    def test_unknown_audience_is_treated_as_stranger(self):
        """Fail-closed: опечатка в аудитории не должна раскрывать маршрут."""
        titles = [s["title"] for s in itinerary.visible(self.ROUTE, "teilnehmer")]
        assert titles == ["Start Manali"]

    def test_hidden_count_is_honest(self):
        assert itinerary.hidden_count(self.ROUTE, itinerary.GUEST) == 2
        assert itinerary.hidden_count(self.ROUTE, itinerary.OWNER) == 0


class TestSlices:
    def test_by_day_groups_and_sums_km(self):
        stops = itinerary.normalize(
            [
                _stop(day=1, title="A", km=120, time_from="09:00"),
                _stop(day=1, title="B", km=30, overnight="Jispa", time_from="17:00"),
                _stop(day=2, title="C", km=200),
            ]
        )
        days = itinerary.by_day(stops)
        assert [d["day"] for d in days] == [1, 2]
        assert days[0]["km"] == 150
        assert days[0]["overnight"] == "Jispa"
        assert len(days[0]["stops"]) == 2

    def test_map_points_skip_stops_without_coordinates(self):
        stops = itinerary.normalize(
            [
                _stop(day=1, title="Mit", lat="32.24", lng="77.19"),
                _stop(day=2, title="Ohne"),
            ]
        )
        points = itinerary.map_points(stops)
        assert len(points) == 1
        assert points[0]["title"] == "Mit"
        assert points[0]["lat"] == 32.24

    def test_totals(self):
        stops = itinerary.normalize(
            [_stop(day=1, title="A", km=100), _stop(day=2, title="B", km=50)]
        )
        assert itinerary.total_km(stops) == 150
        assert itinerary.day_count(stops) == 2


class TestFromPost:
    def test_parses_indexed_rows(self):
        post = {
            "it_day_0": "1",
            "it_title_0": "Manali",
            "it_km_0": "0",
            "it_visibility_0": "public",
            "it_day_1": "2",
            "it_title_1": "Jispa",
            "it_km_1": "140",
            "it_visibility_1": "participants",
            "it_title_2": "",  # пустой слот запаса
            "fremd_title_3": "ignoriert",
        }
        stops = itinerary.from_post(post)
        assert [s["title"] for s in stops] == ["Manali", "Jispa"]
        assert stops[1]["km"] == 140
        assert stops[1]["visibility"] == itinerary.PARTICIPANTS

    def test_ignores_non_numeric_index(self):
        assert itinerary.from_post({"it_title_x": "Mist"}) == []
