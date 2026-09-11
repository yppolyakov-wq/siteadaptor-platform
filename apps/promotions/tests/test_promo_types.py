"""PT: тип акции как ось вывода (план docs/pt-promo-types-plan-2026-09-11.md).

Что запирает файл:
  * один параметр витрины на всю ось — `?gruppe=` понимает и свою рубрику
    владельца, и встроенный тип `sys:*` (второй параметр был бы двумя контролами
    на один смысл, прецедент LAY-7c);
  * встроенный тип предлагается ТОЛЬКО когда у него есть живые акции (STU-9);
  * настройки типа: строка (легаси «только шаблон») читается как раньше и
    сохраняется строкой; словарь несёт раскладку и форму карточки;
  * у секции и у страницы типа ДЕЙСТВУЮТ его собственные оси вывода — до волны
    сетка была общей на страницу, и «эта лентой, та сеткой» было невозможно.
"""

import pytest
from django.test import RequestFactory

from apps.promotions import promo_types, public_views
from apps.promotions.models import Promotion
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(slug, **cfg):
    t = TenantFactory(schema_name="public", slug=slug, name="PT")
    if cfg:
        t.site_config = cfg
        t.save(update_fields=["site_config"])
    return t


def _promo(title, **kw):
    return Promotion.objects.create(title={"de": title}, status="active", **kw)


def _body(tenant, params=None):
    req = RequestFactory().get("/aktionen/", params or {})
    req.tenant = tenant
    return public_views.promotion_list(req).content.decode()


# ───────────────────────────── реестр типов ─────────────────────────────


def test_builtin_type_is_offered_only_when_it_has_live_promotions():
    """Правило STU-9: не обещать страницу, на которой ничего нет."""
    t = _tenant("pt1")
    # promo_type у модели по умолчанию «reservation» — в спеке демо-китов он
    # задаётся явно, а здесь важно, чтобы живых встроенных типов не было вовсе.
    _promo("Nur Rabatt", promo_type="discount", discount_percent=10, group="Wochenangebote")
    assert promo_types.live_builtin_keys(Promotion.objects.filter(status="active")) == []

    _promo("Wundertüte", promo_type="discount", discount_style="mystery")
    live = promo_types.live_builtin_keys(Promotion.objects.filter(status="active"))
    assert live == ["sys:mystery"]
    # и тип появился в ряду типов витрины
    assert "Mystery" in _body(t)


def test_same_parameter_serves_own_rubric_and_builtin_type():
    """Одна ось — один параметр: `?gruppe=` фильтрует и рубрику, и механику."""
    t = _tenant("pt2")
    _promo("Geheimnis", promo_type="discount", discount_style="mystery", group="Wochenangebote")
    _promo("Normalpreis", promo_type="discount", discount_percent=10, group="Wochenangebote")
    _promo("Andere Gruppe", promo_type="discount", discount_percent=10, group="Räumung")

    own = _body(t, {"gruppe": "Räumung"})
    assert "Andere Gruppe" in own and "Geheimnis" not in own

    builtin = _body(t, {"gruppe": "sys:mystery"})
    assert "Geheimnis" in builtin and "Normalpreis" not in builtin


def test_unknown_sys_key_filters_by_rubric_and_does_not_crash():
    """Ключ — свободный текст: выдуманный `sys:` не роняет страницу."""
    t = _tenant("pt3")
    _promo("Irgendwas", promo_type="discount", discount_percent=10, group="Wochenangebote")
    assert "Irgendwas" not in _body(t, {"gruppe": "sys:erfunden"})


def test_reservable_has_exactly_one_control():
    """Чип «Reservierbar» стал ТИПОМ; параметр старых ссылок продолжает работать."""
    t = _tenant("pt4")
    _promo("Vorbestellen", promo_type="reservation", available_quantity=5)
    _promo("Nur Rabatt", promo_type="discount", discount_percent=10)

    body = _body(t)
    assert body.count("reservierbar=1") == 0, "дублирующий системный чип вернулся"
    assert "gruppe=sys%3Areservation" in body or "gruppe=sys:reservation" in body

    legacy = _body(t, {"reservierbar": "1"})
    assert "Vorbestellen" in legacy and "Nur Rabatt" not in legacy


# ─────────────────────────── настройки типа ───────────────────────────


def test_settings_read_legacy_string_and_new_dict():
    assert promo_types.settings_for({"A": "prospekt"}, "A") == {"style": "prospekt"}
    assert promo_types.settings_for({"A": {"card": "coupon"}}, "A") == {"card": "coupon"}
    assert promo_types.settings_for({"A": "prospekt"}, "B") == {}
    assert promo_types.settings_for(None, "A") == {}
    assert promo_types.settings_for({"A": 5}, "A") == {}


def test_storage_keeps_string_while_only_template_is_set():
    """Конфиги живых сайтов не переписываются — golden-эталоны целы."""
    assert siteconfig.normalize_promo_groups({"A": "prospekt"}) == {"A": "prospekt"}
    assert siteconfig.normalize_promo_groups({"A": {"style": "prospekt"}}) == {"A": "prospekt"}
    full = siteconfig.normalize_promo_groups({"A": {"style": "magazin", "card": "coupon"}})
    assert full["A"]["style"] == "magazin" and full["A"]["card"] == "coupon"
    # мусор в любом слое выбрасывается, ключ не материализуется
    assert siteconfig.normalize_promo_groups({"A": {"style": "x", "card": "y"}}) == {}
    assert "promo_groups" not in siteconfig.normalize({})


def test_type_layout_beats_page_layout_in_its_section():
    """«Anti-Food-Waste лентой, Wochenangebote сеткой» — до волны было невозможно."""
    t = _tenant(
        "pt5",
        promo_groups={"Anti-Food-Waste": {"layout": {"preset": "cols3", "scroll": True}}},
    )
    for i in range(2):
        _promo(f"Rest{i}", promo_type="discount", discount_percent=50, group="Anti-Food-Waste")
    for i in range(2):
        _promo(f"Woche{i}", promo_type="discount", discount_percent=10, group="Wochenangebote")

    body = _body(t)
    # ленту получает ровно одна секция из двух
    assert body.count("data-promo-strip") == 1
    assert body.count('data-grid="promo_list"') == 2


def test_type_card_form_sits_between_promotion_and_site():
    """Приоритет «своё у акции → тип → сайт» — как у товара с категорией."""
    t = _tenant(
        "pt6",
        promo_groups={"Räumung": {"card": "coupon"}},
        site_defaults={"promo_card": "regal"},
    )
    _promo("Restposten", promo_type="discount", discount_percent=40, group="Räumung")

    page = _body(t, {"gruppe": "Räumung"})
    assert "sf-coupon" in page or "coupon" in page
    # у типа без своей формы остаётся дефолт сайта
    _promo("Wochenware", promo_type="discount", discount_percent=10, group="Wochenangebote")
    other = _body(t, {"gruppe": "Wochenangebote"})
    assert "coupon" not in other


def test_builtin_types_do_not_duplicate_sections():
    """Встроенный тип пересекается с рубрикой — вторая секция была бы дублем."""
    t = _tenant("pt7")
    for i in range(2):
        _promo(
            f"Geheim{i}", promo_type="discount", discount_style="mystery", group="Wochenangebote"
        )

    body = _body(t)
    assert body.count('data-grid="promo_list"') == 1
