"""FB-29.2 S3: сайт читает баннеры из библиотеки там, где они выбраны; перенос прежних
слайдов — отдельной командой, повторяемой и обратимой. Без выбора всё как раньше."""

import datetime

import pytest
from django.template import Context, Template
from django.test import RequestFactory
from django.utils import timezone

from apps.core import banners
from apps.core.models import Banner
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

SLIDES = [
    {"image": "/media/hero/a.jpg", "title": "Herbst", "text": "Neu", "button_label": "Los",
     "button_url": "/sortiment/", "align": "left"},
    {"image": "/media/hero/b.jpg", "title": "Winter", "starts": "2026-01-01", "click_all": True},
]  # fmt: skip


def _tenant(**cfg):
    tenant = TenantFactory(business_type="online_shop")
    tenant.site_config = {**(tenant.site_config or {}), **cfg}
    tenant.save(update_fields=["site_config"])
    return Tenant.objects.get(pk=tenant.pk)


def _slides(tenant):
    """Что отдаст тег витрины для баннера главной."""
    request = RequestFactory().get("/")
    request.tenant = tenant
    cfg = siteconfig.normalize(tenant.site_config)
    tpl = Template(
        "{% load siteui %}{% hero_slides site.heroes site.hero_banners as slides %}"
        "{% for h in slides %}[{{ h.title }}|{{ h.image }}|{{ h.href }}|{{ h.align }}]{% endfor %}"
    )
    return tpl.render(Context({"request": request, "site": cfg}))


def test_without_a_pick_the_site_shows_the_old_slides():
    tenant = _tenant(heroes=SLIDES)
    out = _slides(tenant)
    assert "[Herbst|/media/hero/a.jpg|/sortiment/|left]" in out and "Winter" in out


def test_picked_banners_replace_the_old_slides_in_the_owners_order():
    tenant = _tenant(heroes=SLIDES)
    a = banners.create({"title": "A", "image": {"url": "/media/hero/x.jpg"}, "button_url": "/a/"})
    b = banners.create({"title": "B", "image": {"url": "/media/hero/y.jpg"}})
    tenant.site_config = {**tenant.site_config, "hero_banners": {"pick": [str(b.pk), str(a.pk)]}}
    tenant.save(update_fields=["site_config"])
    out = _slides(Tenant.objects.get(pk=tenant.pk))
    assert out.index("[B|") < out.index("[A|") and "Herbst" not in out
    assert "[A|/media/hero/x.jpg|/a/|]" in out


def test_pick_survives_normalize_and_rubbish_does_not():
    cfg = siteconfig.normalize(
        {"hero_banners": {"pick": ["nope", "3f2b8c1e-5d44-4c0e-9a57-0d2f6a1b7c33"], "interval": 99,
                          "arrows": "on", "auto": "false", "evil": "<x>"}}
    )  # fmt: skip
    assert cfg["hero_banners"] == {
        "pick": ["3f2b8c1e-5d44-4c0e-9a57-0d2f6a1b7c33"], "arrows": True, "auto": False,
    }  # fmt: skip
    assert "hero_banners" not in siteconfig.normalize({})  # ключа нет, пока нечего хранить
    assert siteconfig.normalize(cfg) == cfg


def test_import_moves_the_slides_and_the_site_looks_the_same():
    tenant = _tenant(heroes=SLIDES)
    before = _slides(tenant)
    report = banners.import_legacy(tenant)
    assert report == {"created": 2, "skipped": 0}
    tenant = Tenant.objects.get(pk=tenant.pk)
    assert len(tenant.site_config["hero_banners"]["pick"]) == 2
    assert tenant.site_config["heroes"], "прежние слайды остаются — для отката"
    assert _slides(tenant) == before
    first = Banner.objects.get(legacy_key="heroes:0")
    assert first.title == "Herbst" and first.sort_order == 0 and first.align == "left"


def test_import_twice_creates_no_duplicates():
    tenant = _tenant(heroes=SLIDES)
    banners.import_legacy(tenant)
    again = banners.import_legacy(Tenant.objects.get(pk=tenant.pk))
    assert again == {"created": 0, "skipped": 0} and Banner.objects.count() == 2
    assert len(Tenant.objects.get(pk=tenant.pk).site_config["hero_banners"]["pick"]) == 2


def test_import_carries_translations():
    tenant = _tenant(
        heroes=SLIDES, i18n={"ru": {"heroes": [{"title": "Осень", "text": "Новое"}, {}]}}
    )
    banners.import_legacy(tenant)
    first = Banner.objects.get(legacy_key="heroes:0")
    assert first.title_i18n == {"ru": "Осень"} and first.text_i18n == {"ru": "Новое"}
    assert Banner.objects.get(legacy_key="heroes:1").title_i18n == {}


def test_import_skips_a_broken_slide_and_says_so():
    tenant = _tenant(heroes=[SLIDES[0]])
    cfg = dict(tenant.site_config)
    cfg["heroes"] = [SLIDES[0], {"image": "/media/hero/c.jpg", "title": "Kaputt"}]
    tenant.site_config = cfg
    tenant.save(update_fields=["site_config"])
    # битая дата в самом слайде до переноса отсекается normalize; ломаем запись на лету
    orig = banners.create

    def flaky(raw, **kwargs):
        if raw.get("title") == "Kaputt":
            raise ValueError("date")
        return orig(raw, **kwargs)

    banners.create = flaky
    try:
        report = banners.import_legacy(Tenant.objects.get(pk=tenant.pk))
    finally:
        banners.create = orig
    assert report == {"created": 1, "skipped": 1}
    assert len(Tenant.objects.get(pk=tenant.pk).site_config["hero_banners"]["pick"]) == 1


def test_undo_restores_the_config_and_removes_only_imported_banners():
    tenant = _tenant(heroes=SLIDES)
    own = banners.create({"title": "Eigener"})
    before = siteconfig.normalize(tenant.site_config)
    banners.import_legacy(tenant)
    banners.undo_legacy(Tenant.objects.get(pk=tenant.pk))
    tenant = Tenant.objects.get(pk=tenant.pk)
    assert siteconfig.normalize(tenant.site_config) == before
    assert list(Banner.objects.values_list("pk", flat=True)) == [own.pk]


def test_owner_pick_is_not_overwritten_by_import():
    tenant = _tenant(heroes=SLIDES)
    own = banners.create({"title": "Eigener"})
    tenant.site_config = {**tenant.site_config, "hero_banners": {"pick": [str(own.pk)]}}
    tenant.save(update_fields=["site_config"])
    banners.import_legacy(Tenant.objects.get(pk=tenant.pk))
    assert Tenant.objects.get(pk=tenant.pk).site_config["hero_banners"]["pick"] == [str(own.pk)]


def test_banner_block_shows_the_picked_banner_or_its_own_slide():
    tenant = _tenant()
    request = RequestFactory().get("/")
    request.tenant = tenant
    tpl = Template(
        "{% load siteui %}{% banner_slide block as h %}[{{ h.title }}|{{ h.url }}|{{ h.href }}]"
    )
    own = {"url": "/media/hero/o.jpg", "title": "Eigen", "button_url": "/x/"}
    assert (
        tpl.render(Context({"request": request, "block": own})) == "[Eigen|/media/hero/o.jpg|/x/]"
    )
    b = banners.create({"title": "Aus der Bibliothek", "image": {"url": "/media/hero/l.jpg"}})
    picked = {**own, "pick": [str(b.pk)]}
    out = tpl.render(Context({"request": request, "block": picked}))
    assert out == "[Aus der Bibliothek|/media/hero/l.jpg|]"
    gone = banners.create(
        {"title": "Vorbei", "ends": timezone.localdate() - datetime.timedelta(days=1)}
    )
    out = tpl.render(Context({"request": request, "block": {**own, "pick": [str(gone.pk)]}}))
    assert out == "[||]", "выбранный баннер вне срока — блок пуст, свой слайд не подменяет"


# ───────── ревью silent-failure-hunter ─────────


def test_other_pages_take_the_photo_of_the_first_shown_banner():
    tenant = _tenant(heroes=SLIDES)
    assert banners.first_image(tenant.site_config) == "/media/hero/a.jpg"
    b = banners.create({"title": "B", "image": {"url": "/media/hero/y.jpg"}})
    cfg = {**tenant.site_config, "hero_banners": {"pick": [str(b.pk)]}}
    assert banners.first_image(cfg) == "/media/hero/y.jpg"
    for path in (
        "apps/core/page_settings.py",
        "apps/core/listing_composition.py",
        "apps/promotions/public_views.py",
    ):
        import pathlib

        assert "first_image(" in pathlib.Path(path).read_text(), path


def test_library_failure_does_not_break_the_home_page(monkeypatch):
    from django.db import DatabaseError

    tenant = _tenant(heroes=SLIDES)
    cfg = {**tenant.site_config, "hero_banners": {"pick": ["3f2b8c1e-5d44-4c0e-9a57-0d2f6a1b7c33"]}}
    tenant.site_config = cfg
    tenant.save(update_fields=["site_config"])

    def boom(*args, **kwargs):
        raise DatabaseError("no such table")

    monkeypatch.setattr(banners, "resolve", boom)
    out = _slides(Tenant.objects.get(pk=tenant.pk))
    assert "Herbst" in out, "при сбое библиотеки главная показывает прежние слайды"
    assert banners.first_image(cfg) == ""


def test_translations_follow_the_raw_position_when_a_slide_is_dropped():
    tenant = _tenant(
        heroes=[{"title": ""}, SLIDES[0]],
        i18n={"ru": {"heroes": [{"title": "Пусто"}, {"title": "Осень"}]}},
    )
    report = banners.import_legacy(tenant)
    assert report["created"] == 1
    assert Banner.objects.get().title_i18n == {"ru": "Осень"}


def test_second_import_does_not_bring_back_a_deleted_banner():
    tenant = _tenant(heroes=SLIDES)
    banners.import_legacy(tenant)
    tenant = Tenant.objects.get(pk=tenant.pk)
    banners.delete(tenant, Banner.objects.get(legacy_key="heroes:0"))
    banners.import_legacy(Tenant.objects.get(pk=tenant.pk))
    assert Banner.objects.count() == 1


def test_command_fails_loudly_on_an_unknown_schema():
    from django.core.management import call_command
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command("import_banners", schema="gibt-es-nicht")
    with pytest.raises(CommandError):
        call_command("import_banners", schema="public")
