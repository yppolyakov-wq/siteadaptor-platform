"""DS-3c (Fokus): сборки (Startpakete) — Look + виды вывода одним кликом.
Адверсариальный цикл по образцу test_looks: каждая сборка × каждый архетип
применяется идемпотентно, оси материализованы, чужие ключи целы."""

import pytest

from apps.tenants import siteconfig, sitetemplates
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ARCHETYPES = [k for k, _ in Tenant.BUSINESS_TYPES if k != "other"]


def test_registry_valid():
    from apps.core import page_presets as pp

    for b in sitetemplates.BUNDLES:
        assert sitetemplates.get_look_family(b["look"]) is not None, b["key"]
        styles = b["config"].get("section_styles", {})
        for sec, st in styles.items():
            assert st in siteconfig.SECTION_STYLES.get(sec, ()), (b["key"], sec, st)
        preset = (b["config"].get("catalog_layout") or {}).get("preset")
        if preset:
            assert (
                preset in siteconfig.LAYOUT_PRESETS
                or preset in siteconfig.PAGE_EXTRA_PRESETS["catalog_layout"]
            )
        # DL-3: страничные пресеты сборки обязаны существовать в реестре ST-2
        # (мёртвый ключ применился бы молча — apply_page_preset вернул бы False).
        for host, pid in (b["config"].get("page_presets") or {}).items():
            reg = pp.PAGE_PRESETS.get(host)
            assert reg is not None, (b["key"], host)
            assert any(p["key"] == pid for p in reg["presets"]), (b["key"], host, pid)


@pytest.mark.parametrize("business_type", ARCHETYPES)
def test_every_bundle_applies_and_is_idempotent(business_type):
    for b in sitetemplates.BUNDLES:
        tenant = TenantFactory(
            business_type=business_type,
            site_config={"notify": {"customer": {"email": True}}, "board": {"order": ["done"]}},
        )
        assert sitetemplates.apply_bundle(tenant, b["key"]) is True
        cfg = tenant.site_config
        assert siteconfig.normalize(cfg) == cfg  # normalize идемпотентен
        if b["config"].get("hero_style"):
            assert cfg["hero_style"] == b["config"]["hero_style"]
        if b["config"].get("nav_cta"):
            assert cfg["nav"]["cta"] is True
        for sec, st in b["config"].get("section_styles", {}).items():
            row = next(r for r in cfg["sections"] if r["key"] == sec)
            assert row["style"] == st
        for sec in b["config"].get("sections_on", ()):
            assert next(r for r in cfg["sections"] if r["key"] == sec)["enabled"] is True
        # чужие ключи целы (W6-инвариант через apply_look-базу)
        assert cfg["notify"] == {"customer": {"email": True}}
        assert cfg["board"]["order"] == ["done"]
        # повторное применение — идемпотентно
        before = dict(cfg)
        sitetemplates.apply_bundle(tenant, b["key"])
        assert tenant.site_config == before


def test_unknown_bundle_false():
    tenant = TenantFactory(business_type="catering")
    assert sitetemplates.apply_bundle(tenant, "junk") is False


def test_bundles_for_recommended_first():
    keys = [b["key"] for b in sitetemplates.bundles_for("catering")]
    assert "fokus" in keys


DEAL_BUNDLES = ("deal_prospekt", "deal_frisch", "deal_neon", "deal_blatt", "deal_smart")


def test_every_archetype_sees_exactly_one_fokus():
    """DS-8: у каждого архетипа своя вариация Fokus — и ровно одна карточка
    (иначе владелец видит пять одинаковых «Fokus»). DL-3: поверх — пять
    универсальных дил-шаблонов (свои label'ы), рекомендация — первой."""
    for bt in ARCHETYPES:
        got = [b for b in sitetemplates.bundles_for(bt) if b["label"] == "Fokus"]
        assert len(got) <= 1, (bt, [b["key"] for b in got])
    for bt in ("hotel", "restaurant", "cafe", "bakery", "catering"):
        keys = [b["key"] for b in sitetemplates.bundles_for(bt)]
        assert keys[0].startswith("fokus"), (bt, keys)  # рекомендованная — первая
        assert set(DEAL_BUNDLES) <= set(keys), (bt, keys)
        assert len(keys) == 1 + len(DEAL_BUNDLES), (bt, keys)


def test_deal_bundles_universal_and_composed():
    """DL-3: дил-шаблоны видны ЛЮБОМУ типу бизнеса (пустой recommended_for) и
    несут композицию канваса: акции первыми (spotlight/rows) + направления."""
    by_key = {b["key"]: b for b in sitetemplates.BUNDLES}
    for key in DEAL_BUNDLES:
        b = by_key[key]
        assert b["recommended_for"] == (), key
        assert b["look"] == key.removeprefix("deal_"), key
        cfg = b["config"]
        assert cfg["section_styles"]["promotions"] in ("spotlight", "rows"), key
        # Акции — главный контент дил-шаблона (общее у всех пяти). Второй блок
        # у каждого СВОЙ (DL-9: газета несёт прайс-лист вместо плиток категорий),
        # поэтому «categories у всех» здесь больше не требуется — осознанно.
        assert "promotions" in cfg["sections_on"], key
        assert not (set(cfg["sections_on"]) & set(cfg["sections_off"])), key
    for bt in ARCHETYPES:
        keys = {b["key"] for b in sitetemplates.bundles_for(bt)}
        assert set(DEAL_BUNDLES) <= keys, bt
    assert by_key["deal_smart"]["config"]["section_styles"]["promotions"] == "rows"
    assert by_key["deal_smart"]["config"]["hero_style"] == "plain"
    assert by_key["deal_blatt"]["config"]["nav_style"] == "centered"


def test_deal_bundles_differ_structurally():
    """DL-9 (фидбэк «выглядят одинаково, только цвет меняется»): у КАЖДОЙ пары
    дил-шаблонов различается сама страница — набор блоков и/или их порядок,
    а не только кожа. Замок держит инвариант при будущих правках реестра."""
    by_key = {b["key"]: b["config"] for b in sitetemplates.BUNDLES}
    shapes = {}
    for key in DEAL_BUNDLES:
        cfg = by_key[key]
        shapes[key] = (tuple(cfg["sections_on"]), tuple(cfg.get("sections_order", ())))
    for a in DEAL_BUNDLES:
        for b in DEAL_BUNDLES:
            if a < b:
                assert shapes[a] != shapes[b], (a, b, shapes[a])
    # Порядок задан у всех и начинается с главного блока шаблона.
    assert by_key["deal_neon"]["sections_order"][1] == "promotions"  # акции сразу
    assert "hero" not in by_key["deal_smart"]["sections_on"]  # маркетплейс без баннера
    assert by_key["deal_smart"]["sections_order"][0] == "promotions"
    assert "products" in by_key["deal_blatt"]["sections_on"]  # газета несёт прайс


@pytest.mark.parametrize("key", ["deal_prospekt", "deal_neon", "deal_blatt", "deal_smart"])
def test_sections_order_applied_and_survives_normalize(key):
    """DL-9a: ось sections_order переставляет блоки главной и переживает
    normalize (порядок — часть данных, не косметика)."""
    tenant = TenantFactory(business_type="grocery")
    assert sitetemplates.apply_bundle(tenant, key) is True
    cfg = tenant.site_config
    enabled = [s["key"] for s in cfg["sections"] if s["enabled"]]
    wanted = [
        k
        for k in next(b for b in sitetemplates.BUNDLES if b["key"] == key)["config"][
            "sections_order"
        ]
        if k in enabled
    ]
    assert enabled[: len(wanted)] == wanted, (key, enabled)
    # Идемпотентность: повторное применение не перемешивает.
    sitetemplates.apply_bundle(tenant, key)
    assert [s["key"] for s in tenant.site_config["sections"] if s["enabled"]] == enabled


def test_bundle_page_presets_seed_pages():
    """DL-3: ось page_presets — сборка красит и «О нас»/корзину (блоки ST-2
    с префиксом семейства), блоки владельца целы."""
    tenant = TenantFactory(
        business_type="grocery",
        site_config={"page_blocks": {"info": [{"key": "text", "id": "own-1", "data": {}}]}},
    )
    assert sitetemplates.apply_bundle(tenant, "deal_prospekt") is True
    cfg = tenant.site_config
    ids = [b["id"] for b in cfg["page_blocks"]["info"]]
    assert "own-1" in ids  # блок владельца жив
    assert any(i.startswith("pb-about-bild-") for i in ids)
    # flat-ключ пресета: дефолт True → сигнален только "schlicht" (False).
    other = TenantFactory(business_type="grocery")
    assert sitetemplates.apply_bundle(other, "deal_neon") is True
    assert other.site_config["cart_show_upsell"] is False


def test_fokus_variants_carry_archetype_output_views():
    """Каждая вариация несёт ДНК Fokus + свои виды вывода."""
    by_key = {b["key"]: b for b in sitetemplates.BUNDLES}
    for key in ("fokus", "fokus_hotel", "fokus_gastro", "fokus_cafe", "fokus_bakery"):
        cfg = by_key[key]["config"]
        assert cfg["hero_style"] == "split" and cfg["nav_cta"] is True
        assert cfg["section_styles"]["trust"] == "compact"
        # sections_off и sections_on не пересекаются (иначе гонка вкл/выкл)
        assert not (set(cfg["sections_on"]) & set(cfg["sections_off"])), key
    assert by_key["fokus_hotel"]["config"]["hero_widget"] == "stays"
    assert "stay_rooms" in by_key["fokus_hotel"]["config"]["sections_on"]
    assert by_key["fokus_gastro"]["config"]["section_styles"]["products"] == "preisliste_karte"
    assert by_key["fokus_cafe"]["config"]["section_styles"]["products"] == "preisliste_kompakt"
    assert by_key["fokus_bakery"]["config"]["section_styles"]["categories"] == "compact"


def test_bundle_applies_sections_off_and_hero_widget():
    tenant = TenantFactory(
        business_type="hotel",
        site_config={"sections": [{"key": "archetypes", "enabled": True}]},
    )
    assert sitetemplates.apply_bundle(tenant, "fokus_hotel") is True
    cfg = tenant.site_config
    rows = {s["key"]: s for s in cfg["sections"]}
    assert rows["archetypes"]["enabled"] is False  # шумная секция выключена
    assert rows["stay_rooms"]["enabled"] is True
    assert rows["stay_search"]["enabled"] is False  # дубль поиска в баннере
    assert cfg["site_defaults"]["hero_widget"] == "stays"
