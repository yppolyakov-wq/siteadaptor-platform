"""NT-A2: центр подписок «Benachrichtigungen auswählen» (план nt-notification-preferences §2 A2).

Замки: diff только по видам центра; раздел покрывает свои категории; все категории — раздел;
лимит по итоговому числу без частичной записи; DOI v2 — GET без эффектов, POST только
добавляет, мусор отбрасывается; одинаковый ответ анонима; тема портала; каналы раздельно.
"""

import uuid
from unittest import mock

import pytest
from django.http import QueryDict
from django.test import override_settings
from django.utils import timezone

from apps.aggregator import follow, follow_center, follow_views
from apps.aggregator.models import FollowSubscription, PortalUser
from apps.aggregator.tests.test_follow import _listing, _portal, _req, _stamp, _tenant
from apps.core import city_categories as cc

pytestmark = pytest.mark.django_db
CITY = "Solingen"
FOOD = "lebensmittel-getraenke"


def _user():
    return PortalUser.objects.create(email=f"{uuid.uuid4().hex}@kunde.test")


def _sel(**kw):
    return follow_center.Selection(**{k: set(v) for k, v in kw.items()})


def _kinds(user):
    return set(
        FollowSubscription.objects.filter(user=user).values_list("target_kind", "target_key")
    )


def test_apply_diff_touches_only_center_kinds():
    portal = _portal()
    user = _user()
    tenant = _tenant()
    follow.follow_now(
        user, follow.Target("business", tenant.schema_name), frequency="daily", portal=portal
    )
    follow_center.apply(
        user,
        _sel(categories={"brot-backwaren", "obst-gemuese"}, tags={"vegan"}),
        frequency="weekly",
        portal=portal,
    )
    assert ("category", "brot-backwaren") in _kinds(user)
    result = follow_center.apply(
        user, _sel(categories={"brot-backwaren"}), frequency="weekly", portal=portal
    )
    assert (result.added, result.removed) == (0, 2)
    assert _kinds(user) == {("business", tenant.schema_name), ("category", "brot-backwaren")}
    assert set(
        FollowSubscription.objects.filter(user=user, target_kind="category").values_list(
            "frequency", flat=True
        )
    ) == {"weekly"}


def test_section_covers_its_categories_and_full_set_folds():
    portal = _portal()
    norm = follow_center.normalize(_sel(sections={FOOD}, categories={"brot-backwaren"}), portal)
    assert norm.sections == {FOOD} and norm.categories == set()
    members = {c.key for c in cc.CATEGORIES if c.section == FOOD}
    norm = follow_center.normalize(_sel(categories=members), portal)
    assert norm.sections == {FOOD} and norm.categories == set()
    junk = follow_center.normalize(
        _sel(categories={"weg", FOOD}, tags={"erfunden", "halal"}, districts={"nope"}), portal
    )
    assert junk.categories == set() and junk.tags == {"halal"} and junk.districts == set()


def test_limit_counts_final_set_and_writes_nothing(settings):
    settings.AGGREGATOR_FOLLOW = {**settings.AGGREGATOR_FOLLOW, "max_follows": 2}
    portal = _portal()
    user = _user()
    follow_center.apply(user, _sel(tags={"vegan"}), frequency="daily", portal=portal)
    with pytest.raises(follow.FollowLimitReached):
        follow_center.apply(
            user, _sel(tags={"vegan", "bio", "halal"}), frequency="daily", portal=portal
        )
    assert _kinds(user) == {("tag", "vegan")}
    # замена в пределах лимита проходит (итог = 2)
    follow_center.apply(user, _sel(tags={"bio", "halal"}), frequency="daily", portal=portal)
    assert _kinds(user) == {("tag", "bio"), ("tag", "halal")}


def test_channels_do_not_mix():
    portal = _portal()
    user = _user()
    follow_center.apply(
        user,
        _sel(tags={"vegan"}),
        frequency="daily",
        portal=portal,
        channel=FollowSubscription.CHANNEL_TELEGRAM,
    )
    follow_center.apply(user, _sel(), frequency="daily", portal=portal)
    assert FollowSubscription.objects.filter(user=user, channel="telegram").count() == 1


def test_theme_portal_drops_foreign_categories():
    portal = _portal(theme_categories=["brot-backwaren"])
    norm = follow_center.normalize(_sel(categories={"brot-backwaren", "obst-gemuese"}), portal)
    assert norm.categories == {"brot-backwaren"}
    assert [n["section"].key for n in follow_center.tree(portal)] == [FOOD]


def test_brands_only_existing():
    portal = _portal()
    tenant = _tenant()
    _listing(tenant, brand="Bosch")
    _listing(tenant, brand="bosch")
    assert follow_center.brands(portal) == [("bosch", "Bosch")]  # одна марка, без регистра


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_logged_in_post_saves_and_redirects():
    portal = _portal()
    user = _user()
    data = QueryDict(mutable=True)
    data.setlist("kategorie", ["brot-backwaren"])
    data.setlist("merkmal", ["halal"])
    data["frequency"] = "daily"
    req = _req("post", "/folgen/auswahl/", data, portal=portal, user=user)
    resp = follow_views.follow_center_view(req)
    assert resp.status_code == 302 and "ok=1" in resp["Location"]
    assert _kinds(user) == {("category", "brot-backwaren"), ("tag", "halal")}
    req = _req("get", "/folgen/auswahl/", portal=portal, user=user)
    html = follow_views.follow_center_view(req).content.decode()
    assert 'value="brot-backwaren" data-ft-cat checked' in html
    assert "no-store" in follow_views.follow_center_view(req).get("Cache-Control", "")


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_anonymous_gets_one_doi_and_confirm_only_adds(isolated_ratelimit):
    portal = _portal()
    email = f"{uuid.uuid4().hex}@kunde.test"
    existing = PortalUser.objects.create(email=email)
    follow_center.apply(existing, _sel(tags={"bio"}), frequency="daily", portal=portal)
    data = QueryDict(mutable=True)
    data.setlist("kategorie", ["brot-backwaren"])
    data.update({"email": email, "frequency": "weekly", "stamp": _stamp(), "website": ""})
    with mock.patch("apps.aggregator.tasks.send_follow_confirm_email.delay") as send:
        resp = follow_views.follow_center_view(
            _req("post", "/folgen/auswahl/", data, portal=portal)
        )
    assert resp.status_code == 200 and send.call_count == 1
    url = send.call_args.kwargs["url"]
    token = url.rstrip("/").rsplit("/", 1)[1]
    # GET подтверждения ничего не меняет
    follow_views.follow_confirm(_req("get", "/", portal=portal), token)
    assert ("category", "brot-backwaren") not in _kinds(existing)
    resp = follow_views.follow_confirm(_req("post", "/", portal=portal), token)
    assert resp.status_code == 200
    assert _kinds(existing) == {("tag", "bio"), ("category", "brot-backwaren")}  # bio не стёрт


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_anonymous_response_same_when_rate_limited(isolated_ratelimit):
    portal = _portal()
    data = QueryDict(mutable=True)
    data.setlist("merkmal", ["vegan"])
    data.update(
        {"email": "x@kunde.test", "frequency": "daily", "stamp": _stamp(), "website": "bot"}
    )
    with mock.patch("apps.aggregator.tasks.send_follow_confirm_email.delay") as send:
        resp = follow_views.follow_center_view(
            _req("post", "/folgen/auswahl/", data, portal=portal)
        )
    assert resp.status_code == 200 and send.call_count == 0
    assert "data-follow-check-inbox" in resp.content.decode()  # тот же ответ, что при отправке


def test_center_token_revalidated():
    portal = _portal()
    token = follow_center.make_token(
        email="a@kunde.test",
        selection=_sel(categories={"brot-backwaren", "weg"}, tags={"erfunden"}),
        frequency="daily",
        portal=portal,
        locale="de",
    )
    payload = follow.load_doi_token(token)
    sel = follow_center.selection_of(payload, portal)
    assert sel.categories == {"brot-backwaren"} and sel.tags == set()
    assert timezone.now()


def test_theme_portal_save_keeps_foreign_subscriptions():
    main = _portal()
    themed = _portal(theme_categories=["brot-backwaren"], theme_tags=["vegan"])
    user = _user()
    follow_center.apply(
        user, _sel(categories={"obst-gemuese"}, tags={"halal"}), frequency="daily", portal=main
    )
    follow_center.apply(user, _sel(categories={"brot-backwaren"}), frequency="daily", portal=themed)
    assert {
        ("category", "obst-gemuese"),
        ("tag", "halal"),
        ("category", "brot-backwaren"),
    } <= _kinds(user)


def test_unknown_brand_rejected_and_unshown_brand_kept():
    portal = _portal()
    user = _user()
    FollowSubscription.objects.create(
        user=user,
        target_kind="brand",
        target_key="nischenmarke",
        city=CITY,
        portal=portal,
        token=uuid.uuid4().hex,
        confirmed_at=timezone.now(),
    )
    assert follow_center.normalize(_sel(brands={"erfunden"}), portal).brands == set()
    follow_center.apply(user, _sel(tags={"bio"}), frequency="daily", portal=portal)
    assert ("brand", "nischenmarke") in _kinds(user)  # не показана в списке — не снимается


def test_apply_without_frequency_keeps_chosen_frequency():
    """Ревью NT: бот сохраняет категории раздела с пустой частотой — выбранная жителем
    «wöchentlich» у прочих подписок центра не сбрасывается в «täglich»."""
    portal = _portal()
    user = _user()
    follow_center.apply(user, _sel(tags={"vegan"}), frequency="weekly", portal=portal)
    follow_center.apply(user, _sel(tags={"vegan", "bio"}), frequency="", portal=portal)
    freqs = dict(
        FollowSubscription.objects.filter(user=user).values_list("target_key", "frequency")
    )
    assert freqs["vegan"] == "weekly"


# --- T-8.7b: «Folgen» страницы раздела → центр с предотметкой ----------------------------


def _center_get(portal, query, user=None):
    req = _req("get", "/folgen/auswahl/", query, portal=portal, user=user)
    return follow_views.follow_center_view(req)


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_preselect_from_link_keeps_previous_choice_and_writes_nothing():
    portal = _portal()
    user = _user()
    follow_center.apply(
        user, _sel(categories={"brot-backwaren"}, tags={"bio"}), frequency="daily", portal=portal
    )
    before = _kinds(user)
    html = _center_get(portal, {"bereich": "obst-gemuese"}, user).content.decode()
    assert _kinds(user) == before, "GET ничего не пишет"
    assert 'value="brot-backwaren" data-ft-cat checked' in html, "прежний выбор не снят"
    assert 'value="obst-gemuese" data-ft-cat checked' in html, "категория страницы отмечена"
    assert 'value="bio" checked' in html
    assert "data-follow-preselected" in html and "data-ft-preselected" in html
    # «Speichern» той же формы — итог: прежнее ∪ отмеченное
    data = {"kategorie": ["brot-backwaren", "obst-gemuese"], "merkmal": ["bio"]}
    data["frequency"] = "daily"
    follow_views.follow_center_view(_req("post", "/folgen/auswahl/", data, portal, user))
    assert _kinds(user) == before | {("category", "obst-gemuese")}


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_preselect_whole_section_checks_its_categories_and_district():
    portal = _portal()
    html = _center_get(portal, {"bereich": FOOD}).content.decode()
    members = [c.key for c in cc.CATEGORIES if c.section == FOOD]
    assert f'value="{FOOD}" data-ft-whole checked' in html
    assert all(f'value="{k}" data-ft-cat checked' in html for k in members)
    assert f'id="ft-s-{FOOD}"' in html
    html = _center_get(portal, {"stadtteil": "ohligs-aufderhoehe-merscheid"}).content.decode()
    assert 'value="ohligs-aufderhoehe-merscheid" checked' in html
    assert 'id="ft-stadtteile"' in html


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_preselect_junk_is_dropped_and_not_reflected():
    portal = _portal()
    evil = "<script>alert(1)</script>"
    query = QueryDict(mutable=True)
    query.setlist("bereich", [evil, "weg", *[f"x{i}" for i in range(300)]])
    query.setlist("merkmal", ["erfunden"])
    query["next"] = "https://evil.example/"
    html = _center_get(portal, query).content.decode()
    assert evil not in html and "alert(1)" not in html
    assert "data-follow-preselected" not in html
    back = html.split("data-follow-back")[0].rsplit("<a ", 1)[1]
    assert "evil.example" not in back, "чужой next не становится ссылкой «Zurück»"


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_preselect_over_limit_warns_without_saving(settings):
    settings.AGGREGATOR_FOLLOW = {**settings.AGGREGATOR_FOLLOW, "max_follows": 1}
    portal = _portal()
    user = _user()
    follow_center.apply(user, _sel(tags={"bio"}), frequency="daily", portal=portal)
    resp = _center_get(portal, {"bereich": "obst-gemuese"}, user)
    assert "data-follow-limit" in resp.content.decode()
    assert _kinds(user) == {("tag", "bio")}


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_back_link_and_saved_redirect_keep_safe_next():
    portal = _portal()
    user = _user()
    html = _center_get(portal, {"bereich": FOOD, "next": "/?kat=" + FOOD}, user).content.decode()
    assert f'href="/?kat={FOOD}"' in html and "data-follow-back" in html
    data = QueryDict(mutable=True)
    data.setlist("bereich", [FOOD])
    data["frequency"] = "daily"
    req = _req("post", f"/folgen/auswahl/?next=/%3Fkat%3D{FOOD}", data, portal, user)
    resp = follow_views.follow_center_view(req)
    assert resp.status_code == 302 and "ok=1" in resp["Location"] and "next=" in resp["Location"]


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_anonymous_preselect_shows_email_form_and_old_follow_page_still_works():
    portal = _portal()
    html = _center_get(portal, {"bereich": FOOD}).content.decode()
    assert 'name="email"' in html and "noch nicht abonniert" in html
    resp = follow_views.follow_page(_req("get", "/folgen/", {"bereich": FOOD}, portal))
    assert resp.status_code == 200, "старые ссылки из писем — прежняя форма"


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_following_button_of_section_leads_to_center():
    from django.template.loader import render_to_string

    target = follow.Target("category", "obst-gemuese", CITY)
    html = render_to_string(
        "aggregator/_follow_button.html",
        {"follow_target": target, "following": True, "next_url": "/?kat=obst-gemuese"},
    )
    assert "/folgen/auswahl/?bereich=obst-gemuese" in html and "#ft-s-" in html
    biz = follow.Target("business", "x", CITY)
    html = render_to_string("aggregator/_follow_button.html", {"follow_target": biz})
    assert "/folgen/?" in html and "/folgen/auswahl/" not in html


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_theme_portal_preselects_its_part_or_falls_back_to_the_follow_form():
    portal = _portal(theme_categories=["brot-backwaren"])
    html = _center_get(portal, {"bereich": FOOD}).content.decode()
    assert 'value="brot-backwaren" data-ft-cat checked' in html, "своя часть раздела"
    assert "data-follow-preselected" in html
    resp = _center_get(portal, {"bereich": "obst-gemuese"})
    assert resp.status_code == 302 and resp["Location"].startswith("/folgen/?bereich=obst-gemuese")
    resp = _center_get(portal, {"bereich": "weg"})
    assert resp.status_code == 200, "мусор — обычный центр, не редирект"
