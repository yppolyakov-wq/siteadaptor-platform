"""FB-33 M3-6b (макет M0-7): окно блока «Banner» — подписи плиток и «Wo zeigen» через черновик.

Замки C0: подписи одной картой мест (число запросов не растёт с числом баннеров); «Wo zeigen»
только при одном баннере; места — только существующие и открытые сайтом (IDOR: черновые,
выключенные, выдуманные — отказ) при правке и при записи; права на библиотеку; «Abbrechen»
откатывает места; база при «Speichern» сверяется (своё сообщение; «Trotzdem speichern» —
трёхстороннее слияние); баннер убрали из блока — места не пишутся, сообщение.
"""

import datetime
import re

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.core import aufbau_draft, window_banner
from apps.core.models import Banner
from apps.core.tests.test_fb27_r2_draft import Browser, _tenant
from apps.core.tests.test_fb33_e9_cancel_anchor import said  # E9: итог «Abbrechen» в адресе
from apps.core.tests.test_fb33_m3_window_before import _panel

pytestmark = pytest.mark.django_db


def _cfg(pick, bn2=None):
    blocks = [{"key": "banner", "id": "bn1", "enabled": True, "data": {"pick": pick}}]
    if bn2 is not None:
        blocks.append({"key": "banner", "id": "bn2", "enabled": True, "data": {"pick": bn2}})
    return {"sections": [{"key": "hero"}], "page_blocks": {"info": blocks}}


def _shop(pick=(), bn2=None):
    tenant = _tenant()
    tenant.site_config = _cfg([str(p) for p in pick], bn2)
    tenant.save()
    return tenant


def _banner(title="Herbst", **kw):
    return Banner.objects.create(title=title, **kw)


def _cat(slug="brot", active=True):
    from apps.catalog.models import Category

    return Category.objects.create(name={"de": slug.title()}, slug=slug, is_active=active)


def _raw(b, code="text"):
    return (b.session.get(aufbau_draft.SESSION_KEY) or {}).get(code)


def _token(html):
    return re.search(r'name="wopen" value="([A-Za-z0-9_-]+)"', _panel(html)).group(1)


class _Req:
    def __init__(self, session):
        self.session = session


# ───────────── C3: подписи плиток ─────────────


def test_tile_captions_say_when_and_where():
    today = timezone.localdate()
    soon = today + datetime.timedelta(days=5)
    ends = today + datetime.timedelta(days=10)
    _cat("brot")
    a = _banner("Herbst", ends=ends, show_on=["category:brot", "category:x"])
    _banner("Stollen", starts=soon)
    c = _banner("Frühstück")
    d = _banner("Sonntag", is_active=False)
    tenant = _shop([a.pk])
    tenant.site_config["hero_banners"] = {"pick": [str(c.pk)]}
    tenant.save()
    html = _panel(Browser(tenant).get("?seite=text&block=bn1"))
    caps = re.findall(r"data-schema-banner-caption>([^<]*)<", html)
    # «Über uns» (выбор в блоке) + «brot»; несуществующая «x» не считается (ревью M3-6)
    assert f"bis {ends.day:02d}.{ends.month:02d}. · 2 Seiten" in caps
    assert f"ab {soon.day:02d}.{soon.month:02d}. · geplant" in caps
    assert "immer · Startseite" in caps
    assert "ausgeblendet" in caps
    assert d.pk  # выключенный — тоже в библиотеке


def test_library_note_and_no_new_banner_button():
    a = _banner()
    html = _panel(Browser(_shop([a.pk])).get("?seite=text&block=bn1"))
    assert (
        "Alle Banner liegen in der Bibliothek (Website › Banner). Hier wird nur gewählt, "
        "welcher in diesem Block steht." in html
    )
    assert "Neuer Banner" not in html


def test_captions_cost_the_same_queries_for_one_and_many_banners():
    def queries(n):
        Banner.objects.all().delete()
        pks = [_banner(f"B{i}", show_on=["category:brot"]).pk for i in range(n)]
        tenant = _shop(pks[:1])
        b = Browser(tenant)
        b.get("?seite=text&block=bn1")
        with CaptureQueriesContext(connection) as ctx:
            b.get("?seite=text&block=bn1")
        return len(ctx)

    assert queries(1) == queries(6)


# ───────────── C4: «Wo zeigen» ─────────────


def test_places_only_with_one_banner_slider_links_to_library():
    a, b2 = _banner("A"), _banner("B")
    one = _panel(Browser(_shop([a.pk])).get("?seite=text&block=bn1"))
    assert 'data-window-part="places"' in one and "Wo zeigen" in one
    two = _panel(Browser(_shop([a.pk, b2.pk])).get("?seite=text&block=bn1"))
    assert 'data-window-part="places"' not in two
    assert two.count("Wo zeigen bearbeiten →") == 2
    assert f"/dashboard/site/banner/{a.pk}/" in two


def test_add_and_remove_places_go_to_the_draft_and_save_writes_them():
    a = _banner("A", show_on=["category:alt"])
    _cat("alt")
    brot = _cat("brot")
    tenant = _shop([a.pk])
    b = Browser(tenant)
    html = b.get("?seite=text&block=bn1&wo=bro")
    panel = _panel(html)
    assert 'value="category:brot"' in panel, "поиск нашёл категорию"
    token = _token(html)
    b.post(seite="text", op="places", ref="bn1", value="add", wo_add="category:brot", wopen=token)
    a.refresh_from_db()
    assert a.show_on == ["category:alt"], "библиотека не тронута до «Speichern»"
    assert _raw(b)["show_on"] == {str(a.pk): ["category:alt", "category:brot"]}
    b.post(seite="text", op="places", ref="bn1", value="del:category:alt", wopen=token)
    assert _raw(b)["show_on"] == {str(a.pk): ["category:brot"]}
    assert "Änderungen: 1" in b.get("?seite=text")
    _resp, msgs = b.post(seite="text", op="save")
    assert msgs == ["Gespeichert."]
    a.refresh_from_db()
    assert a.show_on == ["category:brot"] and brot.pk


def test_places_refuse_unknown_inactive_or_garbage_pages():
    """IDOR-замок: в обход формы нельзя поставить выключенную, выдуманную или чужую страницу."""
    from apps.promotions.models import Promotion

    a = _banner("A")
    _cat("aus", active=False)
    tenant = _shop([a.pk])
    b = Browser(tenant)
    draft_promo = Promotion.objects.filter(status="draft").first()
    bad = ["category:aus", "category:gibtsnicht", "product:not-a-uuid", "zzz", "event:1"]
    if draft_promo is not None:
        bad.append(f"promotion:{draft_promo.pk}")
    for value in bad:
        _resp, msgs = b.post(seite="text", op="places", ref="bn1", value="add", wo_add=value)
        assert msgs and "nicht öffentlich" in msgs[0], value
    assert _raw(b) is None


def test_places_refused_without_banner_rights(monkeypatch):
    a = _banner("A")
    _cat("brot")
    b = Browser(_shop([a.pk]))
    monkeypatch.setattr("apps.core.view_perms.url_allowed", lambda user, url, method="GET": False)
    _resp, msgs = b.post(seite="text", op="places", ref="bn1", value="add", wo_add="category:brot")
    assert msgs == ["„Wo zeigen“ darf nur ändern, wer auch die Banner bearbeiten darf."]
    assert _raw(b) is None
    html = _panel(b.get("?seite=text&block=bn1&wo=bro"))
    assert 'name="wo_add"' not in html and 'value="del:' not in html


def test_places_only_for_the_banner_of_this_block():
    a, other = _banner("A"), _banner("Fremd")
    _cat("brot")
    b = Browser(_shop([a.pk, other.pk]))  # слайдер — места не здесь
    _resp, msgs = b.post(seite="text", op="places", ref="bn1", value="add", wo_add="category:brot")
    assert msgs == ["Diese Änderung ist hier nicht möglich."]
    assert _raw(b) is None


def test_abbrechen_restores_places_byte_for_byte():
    a = _banner("A")
    _cat("brot")
    b = Browser(_shop([a.pk]))
    token = _token(b.get("?seite=text&block=bn1"))
    b.post(seite="text", op="places", ref="bn1", value="add", wo_add="category:brot", wopen=token)
    _resp, msgs = said(*b.post(seite="text", op="revert", ref="bn1", wopen=token))
    assert msgs == ["Änderungen an diesem Block zurückgenommen."]
    assert aufbau_draft.get(_Req(b.session), "text") is None


def test_library_change_is_a_conflict_and_force_merges_three_way():
    a = _banner("A", show_on=["category:alt"])
    for slug in ("alt", "brot", "neu"):
        _cat(slug)
    b = Browser(_shop([a.pk]))
    b.post(seite="text", op="places", ref="bn1", value="add", wo_add="category:brot")
    b.post(seite="text", op="places", ref="bn1", value="del:category:alt")
    a.show_on = ["category:alt", "category:neu"]  # в библиотеке добавили «neu»
    a.save()
    assert "Trotzdem speichern" in b.get("?seite=text")
    _resp, msgs = b.post(seite="text", op="save")
    assert msgs == [window_banner.conflict_note()]
    a.refresh_from_db()
    assert a.show_on == ["category:alt", "category:neu"]
    _resp, msgs = b.post(seite="text", op="save", force="1")
    assert msgs == ["Gespeichert."]
    a.refresh_from_db()
    assert a.show_on == ["category:neu", "category:brot"], "своё удаление и добавление + чужое"


def test_banner_removed_from_the_block_drops_the_places_edit():
    a, other = _banner("A"), _banner("B")
    _cat("brot")
    b = Browser(_shop([a.pk]))
    b.post(seite="text", op="places", ref="bn1", value="add", wo_add="category:brot")
    b.post(seite="text", ref="bn1", pick_op=f"remove:{a.pk}")
    b.post(seite="text", ref="bn1", pick_op=f"add:{other.pk}")
    _resp, msgs = b.post(seite="text", op="save")
    assert msgs[0] == "Gespeichert." and window_banner.dropped_note() in msgs
    a.refresh_from_db()
    assert a.show_on == []


def test_place_gone_before_save_is_not_written():
    a = _banner("A")
    brot = _cat("brot")
    b = Browser(_shop([a.pk]))
    b.post(seite="text", op="places", ref="bn1", value="add", wo_add="category:brot")
    brot.is_active = False
    brot.save()
    _resp, msgs = b.post(seite="text", op="save")
    assert window_banner.gone_note() in msgs
    a.refresh_from_db()
    assert a.show_on == []


def test_home_is_a_read_only_chip_and_search_is_capped():
    a = _banner("A")
    tenant = _shop([a.pk])
    tenant.site_config["hero_banners"] = {"pick": [str(a.pk)]}
    tenant.save()
    html = _panel(Browser(tenant).get("?seite=text&block=bn1&wo=" + "x" * 300))
    chip = html[html.index("data-schema-place-home") :]
    chip = chip[: chip.index("</li>")]
    assert "Startseite" in chip and "<button" not in chip
    assert 'value="' + "x" * 80 + '"' in html and "x" * 81 not in html


def test_places_part_lives_on_the_was_tab():
    from apps.core import block_window

    assert block_window.PART_TAB["places"] == "was"
    assert block_window.PANEL_KEYS["places"] == "places"
