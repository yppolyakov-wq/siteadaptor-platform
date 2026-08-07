"""S6: группы/направления акций — публичная /aktionen/ + цели promo_group в меню."""

import pytest
from django.http import Http404
from django.test import RequestFactory

from apps.promotions import public_views
from apps.promotions.models import Promotion
from apps.tenants import menu
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(**kw):
    return TenantFactory(schema_name="public", slug=kw.pop("slug", "pg"), name="PG", **kw)


def _get(path, params=None, tenant=None):
    req = RequestFactory().get(path, params or {})
    req.tenant = tenant
    return req


def test_promotion_list_filters_by_group():
    tenant = _tenant(slug="pg1")
    Promotion.objects.create(title={"de": "FastFoodDeal"}, status="active", group="Fastfood")
    Promotion.objects.create(title={"de": "FertigDeal"}, status="active", group="Fertiggerichte")

    body = public_views.promotion_list(_get("/aktionen/", tenant=tenant)).content.decode()
    assert "FastFoodDeal" in body and "FertigDeal" in body  # все
    assert "Fastfood" in body and "Fertiggerichte" in body  # чипы групп

    filtered = public_views.promotion_list(
        _get("/aktionen/", {"gruppe": "Fastfood"}, tenant)
    ).content.decode()
    assert "FastFoodDeal" in filtered and "FertigDeal" not in filtered


def test_promotion_list_404_when_module_disabled():
    tenant = _tenant(slug="pg2", disabled_modules=["promotions"])
    with pytest.raises(Http404):
        public_views.promotion_list(_get("/aktionen/", tenant=tenant))


def test_menu_promo_group_resolves_only_with_active_promo():
    tenant = _tenant(
        slug="pg3",
        site_config={
            "menus": {
                "top": {
                    "items": [
                        {"label": "FF-Aktionen", "type": "promo_group", "target": "Fastfood"},
                    ]
                }
            }
        },
    )
    assert menu.resolve_menu(tenant, "top") == []  # группа пуста → пункт отброшен
    Promotion.objects.create(title={"de": "x"}, status="active", group="Fastfood")
    items = menu.resolve_menu(tenant, "top")
    assert items and items[0]["url"].startswith("/aktionen/?gruppe=Fastfood")


# --- i18n метки группы (2026-08-01) -----------------------------------------
# Ключ фасета `?gruppe=` остаётся ПЛОСКИМ немецким значением (ссылки не должны
# разъезжаться между локалями), переводится только показ.


def test_group_localized_falls_back_to_plain():
    p = Promotion(title={"de": "x"}, group="Wochenangebote")
    assert p.group_localized == "Wochenangebote"


def test_promotion_list_shows_localized_group_label_but_keeps_key():
    from django.utils import translation

    tenant = _tenant(slug="pgi", enabled_locales=["de", "en"])
    Promotion.objects.create(
        title={"de": "Deal", "en": "Deal"},
        status="active",
        group="Wochenangebote",
        group_i18n={"en": "Weekly offers"},
    )
    with translation.override("en"):
        body = public_views.promotion_list(_get("/aktionen/", tenant=tenant)).content.decode()
    assert "Weekly offers" in body  # заголовок секции и чип — на локали
    assert "?gruppe=Wochenangebote" in body  # ключ фильтра остался немецким


def test_group_chips_keep_labels_of_other_groups_when_filtered():
    """Карта меток строится по НЕотфильтрованной выдаче — иначе чип невыбранной
    группы остался бы без перевода."""
    from django.utils import translation

    tenant = _tenant(slug="pgi2", enabled_locales=["de", "en"])
    Promotion.objects.create(
        title={"de": "A"}, status="active", group="Wochenangebote", group_i18n={"en": "Weekly"}
    )
    Promotion.objects.create(
        title={"de": "B"}, status="active", group="Räumung", group_i18n={"en": "Clearance"}
    )
    with translation.override("en"):
        body = public_views.promotion_list(
            _get("/aktionen/", {"gruppe": "Wochenangebote"}, tenant)
        ).content.decode()
    assert "Clearance" in body and "Weekly" in body


# --- фидбэк 2026-08-07: страница акций не должна выглядеть пустой -------------
# Характеризация ДО правки: сейчас КАЖДАЯ группа получает свою секцию, поэтому
# группа из одной акции занимает целую строку сетки (3 колонки) — у демо-
# ресторана 6 акций разложены на 5 групп, из них 4 одиночные.


def test_single_item_group_does_not_get_its_own_section():
    """Группа из ОДНОЙ акции не заслуживает секции: заголовок + строка на три
    колонки ради одной карточки и есть та самая «незаполненность»."""
    tenant = _tenant(slug="pgs1")
    for i in range(2):
        Promotion.objects.create(title={"de": f"Big{i}"}, status="active", group="Gross")
    Promotion.objects.create(title={"de": "Solo"}, status="active", group="Klein")

    body = public_views.promotion_list(_get("/aktionen/", tenant=tenant)).content.decode()
    # Заголовок секции — <h2>; у группы из одной акции его быть не должно.
    assert "<h2" in body and "Gross" in body, "группа из двух акций осталась секцией"
    import re

    headings = re.findall(r"<h2[^>]*>(.*?)</h2>", body, re.S)
    assert not any("Klein" in h for h in headings), f"одиночная группа получила секцию: {headings}"
    assert "Solo" in body, "акция из одиночной группы пропала со страницы"


def test_grouping_survives_for_kits_with_full_groups():
    """Регрессия для aktionsmarkt (4 группы по 8/4/3/2): там группировка — смысл
    страницы, и порог её ломать не должен."""
    tenant = _tenant(slug="pgs2")
    for grp, n in (("A", 4), ("B", 3), ("C", 2)):
        for i in range(n):
            Promotion.objects.create(title={"de": f"{grp}{i}"}, status="active", group=grp)
    body = public_views.promotion_list(_get("/aktionen/", tenant=tenant)).content.decode()
    import re

    headings = " ".join(re.findall(r"<h2[^>]*>(.*?)</h2>", body, re.S))
    for grp in ("A", "B", "C"):
        assert grp in headings, f"группа {grp} потеряла секцию"
