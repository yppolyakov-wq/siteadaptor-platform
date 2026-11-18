"""T-8.10d.1: подписка портала сочетанием фильтров (`docs/t8-10d1-combined-follows-plan-2026-11-18.md`):
одна кнопка «Folgen» на выдаче, чипы на странице подтверждения, подпись «Friseur · Mitte,
Burg/Höhscheid · familienfreundlich», замена старых одиночных подписок галочкой."""

import pytest

from apps.aggregator import follow, follow_query, follow_views
from apps.aggregator.models import FollowSubscription, PortalUser
from apps.aggregator.tests.test_follow_query import CITY, _email, _portal, _qd, _req

pytestmark = pytest.mark.django_db

KAT, MITTE, BURG, TAG = "friseur", "mitte", "burg-hoehscheid", "familienfreundlich"


def _combo():
    return _qd(art="suche", kat=KAT, stadtteil=[MITTE, BURG], merkmal=TAG)


def test_combination_label_groups_values_by_type():
    target = follow.parse_target(_combo(), portal=_portal())
    assert target.kind == FollowSubscription.TARGET_QUERY
    label = target.label
    assert label.startswith("Friseur · ") and label.endswith(" · familienfreundlich")
    assert "Burg/Höhscheid, Mitte" in label and label.count(" · ") == 2, label


def test_follow_page_shows_chips_with_remove_and_add_links(settings):
    settings.ROOT_URLCONF = "config.urls_portal"
    portal = _portal()
    resp = follow_views.follow_page(_req("get", "/folgen/", _combo(), portal=portal))
    html = resp.content.decode()
    assert html.count("data-follow-chip") == 4  # Friseur, Mitte, Burg/Höhscheid, familienfreundlich
    assert 'data-follow-add="stadtteil"' in html and 'data-follow-add="merkmal"' in html
    groups = follow_query.combo_groups(
        follow.parse_target(_combo(), portal=portal).query, _combo(), city=CITY
    )
    stadt = next(g for g in groups if g["name"] == "stadtteil")
    removed = next(c["remove"] for c in stadt["chips"] if c["label"] == "Mitte")
    assert "stadtteil=" + BURG in removed and "stadtteil=" + MITTE not in removed


def test_logged_in_resident_can_replace_covered_single_follows(settings):
    settings.ROOT_URLCONF = "config.urls_portal"
    portal = _portal()
    user = PortalUser.objects.create(email=_email())
    for params in ({"bereich": KAT}, {"stadtteil": MITTE}, {"stadtteil": "wald"}):
        follow.follow_now(
            user,
            follow.parse_target(_qd(**params), portal=portal),
            frequency="daily",
            portal=portal,
        )
    page = follow_views.follow_page(_req("get", "/folgen/", _combo(), portal=portal, user=user))
    assert "data-follow-replace" in page.content.decode()
    data = {**{k: v for k, v in _combo().lists()}, "frequency": "daily", "replace_singles": "1"}
    req = _req("post", "/folgen/?" + _combo().urlencode(), data, portal=portal, user=user)
    req.GET = _combo()
    follow_views.follow_page(req)
    kinds = set(
        FollowSubscription.objects.filter(user=user).values_list("target_kind", "target_key")
    )
    assert (FollowSubscription.TARGET_DISTRICT, "wald") in kinds, "не покрытая — остаётся"
    assert (FollowSubscription.TARGET_DISTRICT, MITTE) not in kinds
    assert any(k == FollowSubscription.TARGET_QUERY for k, _ in kinds)


def test_without_the_checkbox_old_follows_stay(settings):
    settings.ROOT_URLCONF = "config.urls_portal"
    portal = _portal()
    user = PortalUser.objects.create(email=_email())
    follow.follow_now(
        user,
        follow.parse_target(_qd(stadtteil=MITTE), portal=portal),
        frequency="daily",
        portal=portal,
    )
    data = {"frequency": "daily"}
    req = _req("post", "/folgen/", data, portal=portal, user=user)
    req.GET = _combo()
    follow_views.follow_page(req)
    assert FollowSubscription.objects.filter(user=user, target_key=MITTE).exists()


def test_replace_keeps_telegram_and_other_portal_follows(settings):
    settings.ROOT_URLCONF = "config.urls_portal"
    portal = _portal()
    user = PortalUser.objects.create(email=_email())
    mitte = follow.parse_target(_qd(stadtteil=MITTE), portal=portal)
    follow.follow_now(user, mitte, frequency="daily", portal=portal)
    follow.follow_now(user, mitte, frequency="daily", portal=portal, channel="telegram")
    follow.follow_now(user, mitte, frequency="daily", portal=None)
    data = {"frequency": "daily", "replace_singles": "1"}
    req = _req("post", "/folgen/", data, portal=portal, user=user)
    req.GET = _combo()
    follow_views.follow_page(req)
    left = FollowSubscription.objects.filter(user=user, target_key=MITTE)
    assert set(left.values_list("channel", "portal_id")) == {
        ("telegram", portal.pk),
        ("email", None),
    }


def test_replace_frees_slots_under_the_follow_limit(settings):
    settings.ROOT_URLCONF = "config.urls_portal"
    settings.AGGREGATOR_FOLLOW = {**settings.AGGREGATOR_FOLLOW, "max_follows": 2}
    portal = _portal()
    user = PortalUser.objects.create(email=_email())
    for params in ({"bereich": KAT}, {"stadtteil": MITTE}):
        follow.follow_now(
            user,
            follow.parse_target(_qd(**params), portal=portal),
            frequency="daily",
            portal=portal,
        )
    data = {"frequency": "daily", "replace_singles": "1"}
    req = _req("post", "/folgen/", data, portal=portal, user=user)
    req.GET = _combo()
    resp = follow_views.follow_page(req)
    assert "data-follow-limit" not in resp.content.decode()
    kinds = list(FollowSubscription.objects.filter(user=user).values_list("target_kind", flat=True))
    assert kinds == [FollowSubscription.TARGET_QUERY]


def test_add_forms_carry_only_known_params(settings):
    settings.ROOT_URLCONF = "config.urls_portal"
    params = _combo()
    params.setlist("junk", ["x"] * 50)
    html = follow_views.follow_page(
        _req("get", "/folgen/", params, portal=_portal())
    ).content.decode()
    assert 'name="junk"' not in html


# --- P4: «Sofort» у комбинаций ------------------------------------------------------------


def _combo_target(portal, kat=KAT):
    return follow.parse_target(_qd(art="suche", kat=kat, stadtteil=MITTE), portal=portal)


def test_combination_can_be_instant_and_is_offered_sofort():
    portal = _portal()
    user = PortalUser.objects.create(email=_email())
    sub = follow.follow_now(user, _combo_target(portal), frequency="instant", portal=portal)
    assert sub.frequency == FollowSubscription.FREQ_INSTANT
    keys = [k for k, _l in follow.frequency_choices(user, _combo_target(portal), sub=sub)]
    assert FollowSubscription.FREQ_INSTANT in keys


def test_instant_combinations_are_capped_and_sofort_is_hidden_over_the_cap(settings):
    settings.AGGREGATOR_FOLLOW = {**settings.AGGREGATOR_FOLLOW, "max_instant_query_follows": 1}
    portal = _portal()
    user = PortalUser.objects.create(email=_email())
    first = follow.follow_now(user, _combo_target(portal), frequency="instant", portal=portal)
    other = _combo_target(portal, kat="restaurants")
    second = follow.follow_now(user, other, frequency="instant", portal=portal)
    assert second.frequency == FollowSubscription.FREQ_DAILY, "сверх потолка — сводкой"
    assert FollowSubscription.FREQ_INSTANT not in dict(follow.frequency_choices(user, other))
    assert follow.set_frequency(second, "instant") is False
    # сама мгновенная может остаться «Sofort», повтор той же — не новое место
    assert follow.set_frequency(first, "instant") is True
    again = follow.follow_now(user, _combo_target(portal), frequency="instant", portal=portal)
    assert again.frequency == FollowSubscription.FREQ_INSTANT


def test_section_follow_still_never_instant():
    portal = _portal()
    target = follow.parse_target(_qd(stadtteil=MITTE), portal=portal)
    assert FollowSubscription.FREQ_INSTANT not in dict(follow.frequency_choices(None, target))


# --- P3: «Bearbeiten» в «Ich folge» -----------------------------------------------------------


def _edit_post(user, portal, sub, params, frequency="weekly"):
    qd = _qd(art="suche", **params)
    qd["bearbeiten"] = str(sub.pk)
    req = _req("post", "/folgen/", {"frequency": frequency}, portal=portal, user=user)
    req.GET = qd
    return follow_views.follow_page(req)


def test_edit_link_opens_same_panel_with_chips_and_current_frequency(settings):
    settings.ROOT_URLCONF = "config.urls_portal"
    portal = _portal()
    user = PortalUser.objects.create(email=_email())
    sub = follow.follow_now(user, _combo_target(portal), frequency="weekly", portal=portal)
    url = follow.edit_url(sub, portal=portal, next_url="/konto/")
    assert f"bearbeiten={sub.pk}" in url and "kat=" + KAT in url
    query = url.split("?", 1)[1]
    from django.http import QueryDict

    html = follow_views.follow_page(
        _req("get", "/folgen/", QueryDict(query), portal=portal, user=user)
    ).content.decode()
    assert "data-follow-editing" in html and "data-follow-chip" in html
    assert 'value="weekly" checked' in html
    assert "Sie folgen bereits" not in html


def test_saving_edit_replaces_the_combination_in_place(settings):
    settings.ROOT_URLCONF = "config.urls_portal"
    portal = _portal()
    user = PortalUser.objects.create(email=_email())
    sub = follow.follow_now(user, _combo_target(portal), frequency="daily", portal=portal)
    _edit_post(user, portal, sub, {"kat": KAT, "stadtteil": [MITTE, BURG]})
    left = list(FollowSubscription.objects.filter(user=user))
    assert len(left) == 1 and left[0].pk != sub.pk and left[0].frequency == "weekly"
    assert ["stadtteil", BURG] in left[0].query["p"]


def test_edit_matching_existing_combination_merges(settings):
    settings.ROOT_URLCONF = "config.urls_portal"
    portal = _portal()
    user = PortalUser.objects.create(email=_email())
    other = follow.follow_now(
        user, _combo_target(portal, kat="restaurants"), frequency="daily", portal=portal
    )
    sub = follow.follow_now(user, _combo_target(portal), frequency="daily", portal=portal)
    _edit_post(user, portal, sub, {"kat": "restaurants", "stadtteil": MITTE})
    left = list(FollowSubscription.objects.filter(user=user))
    assert [s.pk for s in left] == [other.pk] and left[0].frequency == "weekly"


def test_cannot_edit_someone_elses_follow(settings):
    settings.ROOT_URLCONF = "config.urls_portal"
    portal = _portal()
    owner = PortalUser.objects.create(email=_email())
    intruder = PortalUser.objects.create(email=_email())
    sub = follow.follow_now(owner, _combo_target(portal), frequency="daily", portal=portal)
    _edit_post(intruder, portal, sub, {"kat": "restaurants", "stadtteil": MITTE})
    assert FollowSubscription.objects.filter(pk=sub.pk).exists()


def test_account_row_shows_edit_only_for_combinations(settings):
    settings.ROOT_URLCONF = "config.urls_portal"
    portal = _portal()
    user = PortalUser.objects.create(email=_email())
    combo = follow.follow_now(user, _combo_target(portal), frequency="daily", portal=portal)
    single = follow.follow_now(
        user,
        follow.parse_target(_qd(stadtteil=MITTE), portal=portal),
        frequency="daily",
        portal=portal,
    )
    assert follow.edit_url(combo, portal=portal)
    assert follow.edit_url(single, portal=portal) == ""


# --- дневной потолок писем «Sofort» (владелец, 2026-11-18: 10) ----------------------------------


def test_instant_combinations_wait_after_the_daily_mail_cap(monkeypatch, settings):
    from django.utils import timezone

    from apps.aggregator import follow_digest
    from apps.aggregator.models import FollowDigest

    settings.AGGREGATOR_FOLLOW = {**settings.AGGREGATOR_FOLLOW, "max_instant_mails_per_day": 2}
    monkeypatch.setattr(follow_digest, "in_quiet_hours", lambda now: False)
    portal = _portal()
    user = PortalUser.objects.create(email=_email())
    follow.follow_now(user, _combo_target(portal), frequency="instant", portal=portal)
    seen = []
    monkeypatch.setattr(
        follow_digest, "build_digest", lambda u, subs, now=None: seen.append(subs) or None
    )
    now = timezone.now()
    follow_digest.instant_for_user(user, now=now)
    assert seen and seen[-1], "до потолка комбинация идёт в мгновенное письмо"
    day = timezone.localtime(now).date().isoformat()
    FollowDigest.objects.create(user=user, period_key=f"i:{day}T05:00", item_keys=["x|y|z"])
    seen.clear()
    follow_digest.instant_for_user(user, now=now)
    assert seen and seen[-1], "письма только по компаниям потолок не тратят"
    for i in range(2):
        FollowDigest.objects.create(
            user=user, period_key=f"i:{day}T0{i}:00", item_keys=[follow_digest.QUERY_MARK]
        )
    seen.clear()
    assert follow_digest.instant_for_user(user, now=now) is False
    assert not seen, "сверх потолка комбинации ждут до завтра (письма нет)"
    assert follow_digest.instant_mails_today(user, now) == 2


def test_follow_page_tells_the_daily_instant_cap(settings):
    settings.ROOT_URLCONF = "config.urls_portal"
    html = follow_views.follow_page(_req("get", "/folgen/", _combo(), portal=_portal()))
    assert "10 „Sofort“-E-Mails am Tag" in html.content.decode()


def test_waiting_combination_keeps_its_window_while_business_still_goes(monkeypatch, settings):
    """Ревью: сверх потолка письмо по компании уходит, а `last_sent_at` ждущей комбинации не
    сдвигается — её новинки придут на следующий день (ничего не теряется)."""
    from django.utils import timezone

    from apps.aggregator import follow_digest
    from apps.aggregator.models import FollowDigest

    settings.AGGREGATOR_FOLLOW = {**settings.AGGREGATOR_FOLLOW, "max_instant_mails_per_day": 1}
    monkeypatch.setattr(follow_digest, "in_quiet_hours", lambda now: False)
    portal = _portal()
    user = PortalUser.objects.create(email=_email())
    combo = follow.follow_now(user, _combo_target(portal), frequency="instant", portal=portal)
    now = timezone.now()
    day = timezone.localtime(now).date().isoformat()
    FollowDigest.objects.create(
        user=user, period_key=f"i:{day}T00:00", item_keys=[follow_digest.QUERY_MARK]
    )
    seen = []
    monkeypatch.setattr(
        follow_digest, "build_digest", lambda u, subs, now=None: seen.append(subs) or None
    )
    follow_digest.instant_for_user(user, now=now)
    assert not seen, "комбинация ждёт"
    combo.refresh_from_db()
    assert combo.last_sent_at is None, "окно «нового» не сдвинуто"
    tomorrow = now + timezone.timedelta(days=1)
    follow_digest.instant_for_user(user, now=tomorrow)
    assert seen and combo in seen[-1], "на следующий день комбинация снова в письме"


def test_bad_daily_cap_setting_falls_back_to_default(settings):
    from apps.aggregator import follow_digest

    settings.AGGREGATOR_FOLLOW = {**settings.AGGREGATOR_FOLLOW, "max_instant_mails_per_day": "x"}
    assert follow_digest.max_instant_mails_per_day() == follow_digest.MAX_INSTANT_MAILS_PER_DAY
    settings.AGGREGATOR_FOLLOW = {**settings.AGGREGATOR_FOLLOW, "max_instant_mails_per_day": 0}
    assert follow_digest.max_instant_mails_per_day() == 1
