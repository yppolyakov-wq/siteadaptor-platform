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


# ────────────────────── PT-5: экран «Aktionstypen» ──────────────────────


def _cabinet_request(method, path, data=None, tenant=None):
    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware

    r = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda x: None).process_request(r)
    MessageMiddleware(lambda x: None).process_request(r)
    r.user = get_user_model()(is_active=True)
    r.tenant = tenant
    return r


def test_screen_lists_own_and_builtin_types_with_counts():
    from apps.promotions import views

    t = _tenant("pt8")
    _promo("W1", promo_type="discount", discount_percent=10, group="Wochenangebote")
    _promo("W2", promo_type="discount", discount_percent=10, group="Wochenangebote")
    _promo("M1", promo_type="discount", discount_style="mystery", group="Wochenangebote")

    rows = views._promo_type_rows(_cabinet_request("get", "/promotions/typen/", tenant=t))
    by_key = {r["key"]: r for r in rows}
    assert by_key["Wochenangebote"]["count"] == 3 and not by_key["Wochenangebote"]["builtin"]
    assert by_key["sys:mystery"]["count"] == 1 and by_key["sys:mystery"]["builtin"]


def test_screen_saves_all_four_axes_and_keeps_other_config():
    from apps.promotions import views

    # probe-ключ W6-класса: переживает normalize (как в замках волны SM)
    t = _tenant("pt9", notify={"order_confirmed": {"email": False}})
    _promo("W1", promo_type="discount", discount_percent=10, group="Räumung")

    resp = views.promo_type_save(
        _cabinet_request(
            "post",
            "/promotions/typen/speichern/",
            {
                "style:Räumung": "countdown",
                "card:Räumung": "ring",
                "mode:Räumung": "slider",
                "cols:Räumung": "4",
                "rows:Räumung": "2",
            },
            tenant=t,
        )
    )
    assert resp.status_code == 302
    t.refresh_from_db()
    cfg = siteconfig.normalize(t.site_config)
    entry = cfg["promo_groups"]["Räumung"]
    assert entry["style"] == "countdown" and entry["card"] == "ring"
    assert entry["layout"]["scroll"] is True and entry["layout"]["cols"] == 4
    assert entry["layout"]["rows"] == 2
    # targeted-write: соседние ключи конфига целы (W9-3)
    assert cfg["notify"]["order_confirmed"]["email"] is False


def test_clearing_all_axes_removes_the_record():
    """Presence-minimal: пустой тип не материализует ключ (golden целы)."""
    from apps.promotions import views

    t = _tenant("pt10", promo_groups={"Räumung": {"style": "countdown", "card": "ring"}})
    _promo("W1", promo_type="discount", discount_percent=10, group="Räumung")

    views.promo_type_save(
        _cabinet_request(
            "post",
            "/promotions/typen/speichern/",
            {"style:Räumung": "", "card:Räumung": "", "mode:Räumung": "grid", "cols:Räumung": ""},
            tenant=t,
        )
    )
    t.refresh_from_db()
    assert "promo_groups" not in siteconfig.normalize(t.site_config)


def test_screen_has_a_navigation_entry():
    """Инвариант X7: у каждого экрана кабинета есть вход из навигации."""
    from apps.core import nav_registry

    assert any(e.url_name == "promotions:promo-type-list" for e in nav_registry.ENTRIES)


# ──────────────── PT-6: несколько секций акций по типам ────────────────


def _home(tenant):
    from django.contrib.sessions.middleware import SessionMiddleware

    req = RequestFactory().get("/")
    SessionMiddleware(lambda x: None).process_request(req)
    req.tenant = tenant
    return public_views.storefront_home(req).content.decode()


def _promo_list_block(type_key, **data):
    return {"key": "promo_list", "id": f"b-{type_key}", "data": {"type": type_key, **data}}


def test_home_can_show_several_promo_sections_one_per_type():
    """Решение владельца Р-2: «Anti-Food-Waste» и «Wochenangebote» рядом, каждая своя."""
    t = _tenant(
        "pt11",
        sections=[
            _promo_list_block("Anti-Food-Waste"),
            _promo_list_block("Wochenangebote"),
        ],
        promo_groups={"Anti-Food-Waste": {"layout": {"preset": "cols3", "scroll": True}}},
    )
    for i in range(2):
        _promo(f"Rest{i}", promo_type="discount", discount_percent=50, group="Anti-Food-Waste")
    for i in range(2):
        _promo(f"Woche{i}", promo_type="discount", discount_percent=10, group="Wochenangebote")

    body = _home(t)
    assert 'data-sf-promo-type="Anti-Food-Waste"' in body
    assert 'data-sf-promo-type="Wochenangebote"' in body
    assert "Rest0" in body and "Woche0" in body
    # оси ТИПА действуют и в секции: лентой ровно одна из двух
    assert body.count("data-promo-strip") == 1


def test_promo_section_block_is_failsafe_without_a_type():
    """Мусорный тип — блок исчезает, страница жива (как у блока одной акции).

    LB-1 (осознанная переписка): блок PT-6 стал блоком «Liste», и ПУСТОЙ тип теперь
    значит «все акции» (у нового блока «нет фильтра» = «всё»), а не «ничего». Метки
    типа у такого блока нет — он не про один тип."""
    t = _tenant("pt12", sections=[_promo_list_block(""), _promo_list_block("sys:erfunden")])
    _promo("Irgendwas", promo_type="discount", discount_percent=10, group="Wochenangebote")
    body = _home(t)
    # выдуманный тип не рисуется вовсе; пустой — секцией всех акций, без метки типа
    assert "data-sf-promo-type" not in body
    assert body.count('data-sf-list="promotions"') == 1


def test_promo_section_block_survives_normalize():
    """Блок повторяемый: два блока одного типа не схлопываются в один.

    LB-1: легаси-ключ `promo_list` читается блоком «Liste» (источник — акции)."""
    cfg = siteconfig.normalize(
        {"sections": [_promo_list_block("A", title="Erste"), _promo_list_block("A", limit=3)]}
    )
    blocks = [s for s in cfg["sections"] if s.get("key") == "list"]
    assert len(blocks) == 2
    assert blocks[0]["data"] == {"source": "promotions", "type": "A", "title": "Erste"}
    assert blocks[1]["data"]["limit"] == 3
    # мусор вместо лимита отбрасывается
    bad = siteconfig.normalize({"sections": [_promo_list_block("A", limit="viel")]})
    assert "limit" not in [s for s in bad["sections"] if s.get("key") == "list"][0]["data"]


def test_promo_section_block_works_on_any_page_not_only_home():
    """Запрос владельца: блок с выбранным типом выводится В ЛЮБОМ МЕСТЕ.

    Он повторяемый C-блок, поэтому живёт и в `page_blocks` — на каждом хосте из
    `PAGE_BLOCK_HOSTS` (а каждый хост обязан выводиться шаблоном, замок STU-14).
    Проверяем на «О нас» (хост `info`) и на странице корзины (хост `cart`).
    """
    from django.contrib.sessions.middleware import SessionMiddleware

    t = _tenant(
        "pt13",
        page_blocks={
            "info": [_promo_list_block("Räumung", title="Restposten")],
            "cart": [_promo_list_block("sys:mystery")],
        },
    )
    for i in range(2):
        _promo(f"Rest{i}", promo_type="discount", discount_percent=40, group="Räumung")
    _promo("Wundertüte", promo_type="discount", discount_style="mystery")

    def _page(view, path):
        req = RequestFactory().get(path)
        SessionMiddleware(lambda x: None).process_request(req)
        req.tenant = t
        return view(req).content.decode()

    about = _page(public_views.about_page, "/ueber-uns/")
    assert 'data-sf-promo-type="Räumung"' in about
    assert "Restposten" in about and "Rest0" in about

    from apps.orders import public_views as orders_public

    cart = _page(orders_public.cart_view, "/warenkorb/")
    assert 'data-sf-promo-type="sys:mystery"' in cart
    assert "Wundertüte" in cart


def test_block_type_is_allowed_on_every_page_host():
    """Инвариант: блок не должен выпадать на части страниц (класс «молча выпал»)."""
    for host in siteconfig.PAGE_BLOCK_HOSTS:
        cfg = siteconfig.normalize({"page_blocks": {host: [_promo_list_block("A")]}})
        # LB-1: легаси-ключ доезжает до каждой страницы уже блоком «Liste»
        assert cfg["page_blocks"][host][0]["key"] == "list", host


# ──────────── PT-7: охват Студии на странице типа ────────────


def test_studio_scope_reads_the_right_field_not_the_whole_record():
    """Запись типа стала словарём — пилюля охвата обязана читать своё поле."""
    from apps.core import studio_scope

    t = _tenant("pt14", promo_groups={"Räumung": {"style": "countdown", "card": "ring"}})

    style = studio_scope.read_state(t, "promo_group_style", "Räumung", "promo_group")
    assert style.own_value == "countdown" and style.overridden

    card = studio_scope.read_state(t, "promo_card_form", "Räumung", "promo_group")
    assert card.own_value == "ring" and card.overridden

    # тип без своих настроек наследует: пилюля честно пишет «для всех»
    empty = studio_scope.read_state(t, "promo_card_form", "Wochenangebote", "promo_group")
    assert empty.own_value == "" and not empty.overridden


def test_studio_scope_write_does_not_drop_the_other_axes():
    """Класс W6 внутри одной записи: смена шаблона не должна стирать карточку."""
    from apps.core import studio_scope

    t = _tenant(
        "pt15",
        promo_groups={"Räumung": {"style": "countdown", "card": "ring", "layout": {"cols": 4}}},
    )
    studio_scope.write_value(t, "promo_group_style", "Räumung", "magazin", "promo_group")
    t.refresh_from_db()
    entry = siteconfig.normalize(t.site_config)["promo_groups"]["Räumung"]
    assert entry["style"] == "magazin", "шаблон не записался"
    assert entry["card"] == "ring", "форма карточки типа стёрта записью шаблона"
    assert entry["layout"]["cols"] == 4, "раскладка типа стёрта записью шаблона"

    # снятие последней оси убирает запись целиком (presence-minimal)
    studio_scope.write_value(t, "promo_card_form", "Räumung", "", "promo_group")
    studio_scope.write_value(t, "promo_group_style", "Räumung", "", "promo_group")
    t.refresh_from_db()
    left = siteconfig.normalize(t.site_config).get("promo_groups", {}).get("Räumung")
    assert set(left) == {"layout"} and left["layout"]["cols"] == 4, left


def test_card_form_on_a_type_page_writes_the_type_not_a_promotion():
    """До карты object_by_type пилюля искала Promotion по имени рубрики → ошибка."""
    from apps.core import studio_scope

    t = _tenant("pt16")
    _promo("Restposten", promo_type="discount", discount_percent=40, group="Räumung")
    studio_scope.write_value(t, "promo_card_form", "Räumung", "coupon", "promo_group")
    t.refresh_from_db()
    assert siteconfig.normalize(t.site_config)["promo_groups"]["Räumung"]["card"] == "coupon"
    # поле самой акции не тронуто — правили ТИП
    assert Promotion.objects.get(title={"de": "Restposten"}).card_style == ""


def test_partial_post_does_not_wipe_the_other_axes():
    """Инвариант W0: ось правится только когда её поле пришло в POST."""
    from apps.promotions import views

    t = _tenant(
        "pt17",
        promo_groups={"Räumung": {"style": "countdown", "card": "ring", "layout": {"cols": 4}}},
    )
    _promo("W1", promo_type="discount", discount_percent=10, group="Räumung")

    # пришла ТОЛЬКО раскладка — шаблон и карточка обязаны выжить
    views.promo_type_save(
        _cabinet_request("post", "/promotions/typen/speichern/", {"cols:Räumung": "6"}, tenant=t)
    )
    t.refresh_from_db()
    entry = siteconfig.normalize(t.site_config)["promo_groups"]["Räumung"]
    assert entry["style"] == "countdown" and entry["card"] == "ring"
    assert entry["layout"]["cols"] == 6
