"""LB-4d-2: пресеты листингов по архетипу — блоки над и под основным списком.

План — `docs/lb4-home-lists-archetypes-plan-2026-10-04.md` §12.2. Замки ДО кода:

* у каждого листинга (каталог, услуги, номера, события, туры) есть «Standard» и хотя бы
  один блочный пресет; каждый блок пресета проходит normalize (Save его не теряет);
* пресет кладёт блоки над основным списком (`above`) и/или под ним (`below`) — блоки
  владельца остаются на своей стороне; повторное применение ничего не дублирует,
  «Standard» забирает назад только блоки пресета;
* блок источника выключенного модуля пресет не кладёт; пресет, от которого ничего не
  осталось, не предлагается (правило STU-9); рекомендованный типу бизнеса — первым;
* Студия предлагает пикер на своей странице, витрина рисует блоки по обе стороны списка.
"""

import itertools
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.core import page_presets, views
from apps.promotions.models import Promotion
from apps.reviews.models import Review
from apps.stays import public_views as stays_public
from apps.stays.models import StayUnit
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

_N = itertools.count()
LISTING_HOSTS = ("catalog", "services", "stay_rooms", "events", "tours")


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(disabled=(), business_type="retail", **cfg):
    t = TenantFactory(
        slug=f"lb4dp{next(_N)}",
        name="LB4DP",
        disabled_modules=list(disabled),
        business_type=business_type,
    )
    t.site_config = cfg
    t.save(update_fields=["site_config"])
    return t


def _specs(preset):
    return list(preset.get("blocks", ())) + list(preset.get("below", ()))


def _rows(cfg, host):
    return (cfg.get("page_blocks") or {}).get(host) or []


def _split(cfg, host):
    above, below = siteconfig.split_at_main(_rows(cfg, host))
    return above, below


# ───────────────────────────── реестр ─────────────────────────────


def test_every_listing_has_standard_and_a_block_preset():
    for host in LISTING_HOSTS:
        reg = page_presets.PAGE_PRESETS.get(host)
        assert reg, host
        presets = reg["presets"]
        assert presets[0]["key"] == "standard" and not _specs(presets[0]), host
        assert any(_specs(p) for p in presets), host
        assert reg["prefix"].startswith("pb-") and reg["prefix"].endswith("-"), host


def test_listing_preset_blocks_survive_normalize_on_both_sides():
    for host in LISTING_HOSTS:
        reg = page_presets.PAGE_PRESETS[host]
        for preset in reg["presets"]:
            if not _specs(preset):
                continue
            cfg = {}
            assert page_presets.apply_page_preset(cfg, host, preset["key"])
            cfg = siteconfig.normalize(cfg)
            seeded = [b for b in _rows(cfg, host) if not siteconfig.is_main_marker(b)]
            assert len(seeded) == len(_specs(preset)), (host, preset["key"])
            for block, (kind, data) in zip(seeded, _specs(preset), strict=True):
                assert block["key"] == kind
                for k, v in data.items():
                    assert block["data"].get(k) == v, (host, preset["key"], k)


# ───────────────────────────── применение ─────────────────────────────


def _stays_preset():
    reg = page_presets.PAGE_PRESETS["stay_rooms"]
    return next(p for p in reg["presets"] if p.get("blocks") and p.get("below"))


def test_preset_puts_blocks_above_and_below_and_keeps_owner_blocks():
    preset = _stays_preset()
    owner_up = {"key": "text", "id": "own-up", "enabled": True, "data": {"text": "Hallo"}}
    owner_down = {"key": "text", "id": "own-down", "enabled": True, "data": {"text": "Tschüss"}}
    cfg = siteconfig.normalize(
        {"page_blocks": {"stay_rooms": [owner_up, {"key": siteconfig.MAIN_LIST_KEY}, owner_down]}}
    )
    assert page_presets.apply_page_preset(cfg, "stay_rooms", preset["key"])
    cfg = siteconfig.normalize(cfg)
    above, below = _split(cfg, "stay_rooms")
    assert [b["id"] for b in above][0] == "own-up"  # блок владельца — первым сверху
    assert above[-1]["id"].startswith("pb-stays-") and len(above) == 1 + len(preset["blocks"])
    assert [b["id"] for b in below][-1] == "own-down"  # снизу — после пресетных
    assert len(below) == 1 + len(preset["below"])
    # повтор — без дублей
    again = dict(cfg)
    page_presets.apply_page_preset(again, "stay_rooms", preset["key"])
    assert _rows(siteconfig.normalize(again), "stay_rooms") == _rows(cfg, "stay_rooms")
    # «Standard» забирает только своё
    page_presets.apply_page_preset(cfg, "stay_rooms", "standard")
    left = [b.get("id") for b in _rows(siteconfig.normalize(cfg), "stay_rooms")]
    assert "own-up" in left and "own-down" in left
    assert not [i for i in left if str(i).startswith("pb-stays-")]
    assert page_presets.current_preset(siteconfig.normalize(cfg), "stay_rooms") == "standard"


def test_current_preset_is_detected_by_blocks_on_either_side():
    preset = _stays_preset()
    cfg = {}
    page_presets.apply_page_preset(cfg, "stay_rooms", preset["key"])
    assert page_presets.current_preset(siteconfig.normalize(cfg), "stay_rooms") == preset["key"]


def test_blocks_of_switched_off_modules_are_not_seeded():
    t = _tenant(disabled=["promotions"], business_type="hotel")
    preset = _stays_preset()
    cfg = {}
    page_presets.apply_page_preset(cfg, "stay_rooms", preset["key"], tenant=t)
    seeded = [
        b
        for b in _rows(siteconfig.normalize(cfg), "stay_rooms")
        if not siteconfig.is_main_marker(b)
    ]
    assert seeded and all(b["data"]["source"] != "promotions" for b in seeded)


def test_preset_with_nothing_left_is_not_offered():
    t = _tenant(disabled=["events"], business_type="events")
    keys = [p["key"] for p in page_presets.presets_for("events", "events", tenant=t)]
    assert keys == ["standard"]


def test_recommended_preset_comes_first_for_its_business_type():
    cards = page_presets.presets_for("stay_rooms", "hotel")
    assert cards[0]["recommended"] and cards[0]["key"] != "standard"


# ───────────────────────────── Студия и витрина ─────────────────────────────


def _builder(tenant):
    req = RequestFactory().get("/dashboard/site/home/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return views.home_builder_view(req).content.decode()


def test_studio_offers_listing_presets_of_active_modules():
    t = _tenant(disabled=["events"], business_type="hotel")
    body = _builder(t)
    assert f'value="use_page_preset:stay_rooms:{_stays_preset()["key"]}"' in body
    assert "use_page_preset:events:" not in body  # модуль событий выключен


def test_storefront_renders_preset_blocks_on_both_sides_of_the_list():
    unit = StayUnit.objects.create(name="Doppelzimmer", price_cents=9000)
    # второй номер: с одним `/unterkunft/` сразу уводит на страницу номера
    StayUnit.objects.create(name="Einzelzimmer", price_cents=7000)
    Promotion.objects.create(
        title={"de": "Frühbucher"},
        status="active",
        discount_percent=10,
        stay_unit=unit,
        ends_at=timezone.now() + timedelta(days=10),
    )
    Review.objects.create(
        entity_kind="stay",
        entity_id=unit.pk,
        rating=5,
        author_name="Anna",
        email="anna@example.de",
        comment="Wunderbar",
        is_published=True,
    )
    t = _tenant(business_type="hotel")
    cfg = siteconfig.normalize(t.site_config)
    page_presets.apply_page_preset(cfg, "stay_rooms", _stays_preset()["key"], tenant=t)
    t.site_config = siteconfig.normalize(cfg)
    t.save(update_fields=["site_config"])
    req = RequestFactory().get("/unterkunft/")
    SessionMiddleware(lambda r: None).process_request(req)
    req.tenant = t
    body = stays_public.unterkunft_index(req).content.decode()
    promo = body.index('data-sf-list="promotions"')
    # основной список (карточка номера) — между блоком акций и блоком отзывов
    room = body.index(f"/unterkunft/{unit.pk}/", body.index("</section>", promo))
    assert body.index('data-sf-list="reviews"', room) > room
