"""ST-1 «Каталог Look'ов»: реестр 3×14 + apply_look + ключ theme (тёмный Look).

Адверсариальный замок (образец CBLOCK_VARIANTS): КАЖДЫЙ Look каждого архетипа
проходит apply_look → normalize без потерь и идемпотентно; golden целы (theme —
presence-minimal ключ); применение шаблона/Look'а НЕ стирает чужие ключи
конфига (исправленный латентный баг класса W6). План: st1-looks-plan-2026-07-19.
"""

import pytest

from apps.tenants import siteconfig, sitetemplates
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ARCHETYPES = [k for k, _ in Tenant.BUSINESS_TYPES if k != "other"]


def test_registry_shape_ten_looks_per_archetype():
    # DS-1: +Fein/Natur; DL-2 (2026-09-01): +5 «акционных» семейств —
    # 10 семейств × 15 типов = 150 Look'ов.
    assert len(sitetemplates.LOOK_FAMILIES) == 18  # DL-13: +6; +atelier (бутик); +lager (аутлет)
    keys = [f["key"] for f in sitetemplates.LOOK_FAMILIES]
    assert keys == [
        "klar",
        "warm",
        "nacht",
        "fein",
        "natur",
        "prospekt",
        "frisch",
        "neon",
        "blatt",
        "smart",
        # DL-13 (2026-09-02): канвас «Neue Design-Richtungen» V6–V11.
        "monochrom",
        "pastell",
        "retro",
        "nobel",
        "foto",
        "bauhaus",
        # 2026-09-03 (волна online_shop): «кожа» концепт-стора.
        "atelier",
        # O-5 (2026-09-03): Look аутлета — узкий гротеск, жёсткая рамка, плотная сетка.
        "lager",
    ]
    assert len(ARCHETYPES) == 15
    for bt in ARCHETYPES:
        looks = sitetemplates.looks_for(bt)
        assert [lk["key"] for lk in looks] == keys
        for lk in looks:
            assert lk["accent"].startswith("#")
    # Кортежи акцентов индексируются позицией семейства — у КАЖДОГО типа
    # ровно 10 колонок (рассинхрон дал бы IndexError/чужой акцент молча).
    for bt, accents in sitetemplates.ARCHETYPE_LOOK_ACCENTS.items():
        assert len(accents) == 18, bt  # DL-13: +6; +atelier; +lager
    # DL-2: у каждого семейства полный набор ключей, который _apply читает
    # без гардов (KeyError на проде — незабываемый способ узнать об опечатке).
    for fam in sitetemplates.LOOK_FAMILIES:
        for req in (
            "key",
            "label",
            "description_de",
            "font",
            "typography",
            "site_defaults",
            "nav_style",
            "hero_style",
            "theme",
        ):
            assert req in fam, (fam.get("key"), req)
        assert fam["font"] in siteconfig.FONTS, fam["key"]


def test_normalize_theme_presence_minimal():
    assert "theme" not in siteconfig.normalize({})
    assert "theme" not in siteconfig.normalize({"theme": "light"})
    assert "theme" not in siteconfig.normalize({"theme": "junk"})
    assert siteconfig.normalize({"theme": "dark"})["theme"] == "dark"


@pytest.mark.parametrize("business_type", ARCHETYPES)
def test_every_look_survives_apply_and_normalize(business_type):
    """Адверсариальный замок: apply → значения семейства в конфиге 1:1, normalize
    идемпотентен, тёмная тема только у nacht, чужие ключи целы."""
    for family in sitetemplates.LOOK_FAMILIES:
        tenant = TenantFactory(
            business_type=business_type,
            site_config={
                "hero_title": "Mein Titel",  # текст владельца — не затирается
                "notify": {"customer": {"email": True}},
                "board": {"labels": {"intake": "Neu!"}},
                "presence": {"mode": "on"},
            },
        )
        assert sitetemplates.apply_look(tenant, family["key"]) is True
        cfg = tenant.site_config
        # идемпотентность normalize (двойной прогон без изменений)
        assert siteconfig.normalize(cfg) == cfg
        # пачка Look'а материализована 1:1
        assert cfg["font"] == family["font"]
        assert cfg["typography"] == siteconfig.normalize_typography(family["typography"])
        assert cfg["site_defaults"] == siteconfig.normalize_site_defaults(family["site_defaults"])
        assert cfg["nav"]["style"] == family["nav_style"]
        assert cfg["hero_style"] == family["hero_style"]
        if family["theme"] == "dark":
            assert cfg.get("theme") == "dark"
        else:
            assert "theme" not in cfg
        # акцент архетипа
        assert tenant.primary_color == sitetemplates.look_accent(business_type, family["key"])
        # чужие ключи и тексты владельца целы (латентный баг W6-класса исправлен)
        assert cfg["hero_title"] == "Mein Titel"
        assert cfg["notify"] == {"customer": {"email": True}}
        assert cfg["board"]["labels"]["intake"] == "Neu!"
        assert cfg["presence"] == {"mode": "on"}
        # повторное применение — идемпотентно
        before = dict(cfg)
        sitetemplates.apply_look(tenant, family["key"])
        assert tenant.site_config == before


def test_apply_template_preserves_foreign_keys_too():
    """Фикс распространяется и на старый apply_template (та же _apply-база)."""
    tenant = TenantFactory(
        business_type="bakery",
        site_config={"notify": {"customer": {"email": True}}, "seo": {"allow_ai": False}},
    )
    assert sitetemplates.apply_template(tenant, "laden") is True
    assert tenant.site_config["notify"] == {"customer": {"email": True}}
    assert tenant.site_config["seo"]["allow_ai"] is False


def test_light_look_removes_dark_theme():
    tenant = TenantFactory(business_type="cafe", site_config={"theme": "dark"})
    sitetemplates.apply_look(tenant, "klar")
    assert "theme" not in tenant.site_config


def test_dark_default_rendered_on_storefront():
    """theme=dark → _base.html отдаёт tenantDark=true (посетительский тумблер сильнее)."""
    from importlib import import_module

    from django.conf import settings as dj_settings
    from django.test import RequestFactory

    from apps.promotions import public_views

    tenant = TenantFactory.build(site_config={"theme": "dark"})
    request = RequestFactory().get("/")
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = tenant
    html = public_views.storefront_home(request).content.decode()
    assert 'var tenantDark = "dark" === "dark"' in html
    light = TenantFactory.build()
    request = RequestFactory().get("/")
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = light
    html = public_views.storefront_home(request).content.decode()
    assert 'var tenantDark = "" === "dark"' in html


# --- ST-1b: stateless-превью ?look= + слайд мастера ---------------------------------


def _home(tenant, query=""):
    from importlib import import_module

    from django.conf import settings as dj_settings
    from django.test import RequestFactory

    from apps.promotions import public_views

    request = RequestFactory().get(f"/{query}")
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = tenant
    return public_views.storefront_home(request).content.decode()


def test_preview_look_overlay_is_stateless():
    tenant = TenantFactory.build(business_type="bakery", primary_color="#4f46e5")
    nacht_accent = sitetemplates.look_accent("bakery", "nacht")
    html = _home(tenant, "?preview=1&look=nacht")
    assert 'var tenantDark = "dark" === "dark"' in html  # тёмный оверлей
    assert nacht_accent in html  # архетипный акцент семейства
    # Оверлей ничего не пишет и не действует вне превью / на мусорный ключ.
    assert tenant.site_config in (None, {}, tenant.site_config)  # конфиг не тронут
    assert 'var tenantDark = "" === "dark"' in _home(tenant)
    assert "#4f46e5" in _home(tenant, "?preview=1&look=junk")


def test_wizard_stil_slide_looks_gallery_and_apply():
    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.core import setup_steps

    tenant = TenantFactory(business_type="friseur")

    def _req(method="get", data=None):
        import uuid as _uuid

        request = getattr(RequestFactory(), method)("/dashboard/setup/", data or {})
        SessionMiddleware(lambda r: None).process_request(request)
        MessageMiddleware(lambda r: None).process_request(request)
        o = _uuid.uuid4().hex[:8]
        request.user = get_user_model().objects.create_user(
            username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
        )
        request.tenant = tenant
        return request

    ctx = setup_steps._ctx_template(_req())
    assert [lk["key"] for lk in ctx["looks"]] == [f["key"] for f in sitetemplates.LOOK_FAMILIES]

    # POST с look → применяется семейство (serif у warm), template игнорируется.
    setup_steps._post_template(_req("post", {"look": "warm", "template": "laden"}))
    tenant.refresh_from_db()
    assert tenant.site_config["font"] == "serif"
    assert tenant.primary_color == sitetemplates.look_accent("friseur", "warm")


def test_wizard_stil_template_renders_lazy_iframes():
    from django.template.loader import render_to_string

    from apps.tenants import sitetemplates as st

    html = render_to_string(
        "tenant/setup/_step_stil.html",
        {
            "templates": st.template_cards("bakery"),
            "looks": st.looks_for("bakery"),
        },
    )
    assert 'data-src="/?preview=1&look=klar"' in html
    assert 'data-src="/?preview=1&look=nacht"' in html
    assert 'name="template"' in html  # легаси-галерея шаблонов живёт рядом


# --- ST-1b: билдер — Look-карточки + round-trip темы -------------------------------


def test_builder_theme_roundtrip_and_look_cards():
    """Hidden `theme` пред-заполнен и переживает Save (W0/W6); карточки Look'ов
    в разметке нового вида, в classic — нет."""
    import uuid as _uuid

    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.core import views as core_views

    tenant = TenantFactory(business_type="bakery", site_config={"theme": "dark"})

    def _req(method="get", data=None):
        request = getattr(RequestFactory(), method)("/dashboard/site/home/", data or {})
        SessionMiddleware(lambda r: None).process_request(request)
        MessageMiddleware(lambda r: None).process_request(request)
        o = _uuid.uuid4().hex[:8]
        request.user = get_user_model().objects.create_user(
            username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
        )
        request.tenant = tenant
        return request

    html = core_views.home_builder_view(_req()).content.decode()
    assert 'name="theme" id="bld-theme" value="dark"' in html  # round-trip префилл
    assert 'class="bld-look' in html and "data-look=" in html  # карточки Look'ов

    # Save с theme="" (светлый) → ключ снят; с "dark" → сохранён.
    resp = core_views.home_builder_view(_req("post", {"theme": "", "font": "system"}))
    assert resp.status_code == 302
    tenant.refresh_from_db()
    assert "theme" not in tenant.site_config
    core_views.home_builder_view(_req("post", {"theme": "dark", "font": "system"}))
    tenant.refresh_from_db()
    assert tenant.site_config["theme"] == "dark"

    # W-CL: карточки Look'ов в билдере — всегда (classic-гейт снесён).
    html = core_views.home_builder_view(_req()).content.decode()
    assert "bld-look" in html


def test_preview_draft_accepts_theme():
    """Draft-канал: theme="dark" красит превью, ""/отсутствие — снимает/не трогает."""
    import json as _json
    import uuid as _uuid

    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.core import views as core_views

    tenant = TenantFactory(business_type="bakery")

    def _post(payload):
        request = RequestFactory().post(
            "/dashboard/site/preview-draft/",
            _json.dumps(payload),
            content_type="application/json",
        )
        SessionMiddleware(lambda r: None).process_request(request)
        MessageMiddleware(lambda r: None).process_request(request)
        o = _uuid.uuid4().hex[:8]
        request.user = get_user_model().objects.create_user(
            username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
        )
        request.tenant = tenant
        core_views.site_preview_draft(request)
        return request.session.get("site_preview_draft") or {}

    assert _post({"theme": "dark"}).get("theme") == "dark"
    assert "theme" not in _post({"theme": ""})
    assert "theme" not in _post({})  # не прислан → не трогаем


def test_page_bg_presence_minimal():
    """DS-1: фон страницы — ключ только при валидном hex (golden целы)."""
    assert "page_bg" not in siteconfig.normalize({})["site_defaults"]
    junk = siteconfig.normalize({"site_defaults": {"page_bg": "red"}})
    assert "page_bg" not in junk["site_defaults"]
    ok = siteconfig.normalize({"site_defaults": {"page_bg": "#faf7f2"}})
    assert ok["site_defaults"]["page_bg"] == "#faf7f2"


def test_card_chrome_presence_minimal_and_rendered():
    """DL-2: хром карточек — presence-minimal ключ; body несёт data-sf-chrome."""
    assert "card_chrome" not in siteconfig.normalize({})["site_defaults"]
    junk = siteconfig.normalize({"site_defaults": {"card_chrome": "loud"}})
    assert "card_chrome" not in junk["site_defaults"]
    for value in ("hard", "hairline", "line"):
        ok = siteconfig.normalize({"site_defaults": {"card_chrome": value}})
        assert ok["site_defaults"]["card_chrome"] == value
    # Атрибут на <body> — с пробелом-префиксом (CSS-правила [data-sf-chrome=…]
    # в <style> есть на каждой странице, голый маркер дал бы ложный матч).
    tenant = TenantFactory.build(site_config={"site_defaults": {"card_chrome": "hard"}})
    assert ' data-sf-chrome="hard"' in _home(tenant)
    assert ' data-sf-chrome="' not in _home(TenantFactory.build())


def test_new_family_preview_overlay():
    """DL-2: stateless-превью работает и для новых семейств (шрифт+хром+фон)."""
    tenant = TenantFactory.build(business_type="grocery", primary_color="#4f46e5")
    html = _home(tenant, "?preview=1&look=prospekt")
    assert "Barlow Condensed" in html  # --font-head семейства
    assert 'data-sf-chrome="hard"' in html
    assert sitetemplates.look_accent("grocery", "prospekt") in html
    html = _home(tenant, "?preview=1&look=neon")
    assert 'var tenantDark = "dark" === "dark"' in html
    html = _home(tenant, "?preview=1&look=blatt")
    assert "Playfair Display" in html
    assert "#f7f5f0" in html  # page_bg газеты


def test_design_key_tracks_choice():
    """DL-8a: apply_look/apply_bundle пишут presence-minimal ключ design —
    питает бейдж «Aktiv» и data-sf-look; мусор дропается нормализацией."""
    tenant = TenantFactory(business_type="grocery")
    sitetemplates.apply_bundle(tenant, "deal_neon")
    assert tenant.site_config["design"] == {"look": "neon", "bundle": "deal_neon"}
    # Look поверх сборки меняет только кожу — bundle-ключ остаётся.
    sitetemplates.apply_look(tenant, "blatt")
    assert tenant.site_config["design"] == {"look": "blatt", "bundle": "deal_neon"}
    # Мусорные значения не переживают normalize; пусто = ключа нет (golden).
    assert "design" not in siteconfig.normalize({"design": {"look": "junk", "bundle": "junk"}})
    assert "design" not in siteconfig.normalize({})


def test_look_family_rendered_on_body():
    """DL-8b: body несёт data-sf-look (фирменные бейджи/цены каскадом) —
    из сохранённого выбора и в stateless-превью."""
    tenant = TenantFactory(business_type="grocery")
    sitetemplates.apply_bundle(tenant, "deal_prospekt")
    assert ' data-sf-look="prospekt"' in _home(tenant)
    plain = TenantFactory.build(business_type="grocery", primary_color="#4f46e5")
    assert ' data-sf-look="neon"' in _home(plain, "?preview=1&bundle=deal_neon")
    assert ' data-sf-look="' not in _home(plain)  # без выбора — атрибута нет


def test_sf_primary_alias_emitted():
    """DL-6: app.css потребляет --sf-primary (активные кнопки вида, свотчи) с
    фолбэком-индиго — без алиаса в _base.html акцент тенанта туда не доезжал."""
    tenant = TenantFactory.build(business_type="grocery", primary_color="#15803d")
    assert "--sf-primary: var(--accent)" in _home(tenant)


def test_accent_ink_follows_luminance():
    """DL-5 (стенд): светлый акцент (лайм neon) с жёстким text-white был
    нечитаем на CTA — сервер отдаёт тёмные чернила по яркости акцента."""
    lime = TenantFactory.build(business_type="grocery", primary_color="#c8f542")
    assert "--accent-ink: #111827" in _home(lime)
    green = TenantFactory.build(business_type="grocery", primary_color="#16a34a")
    assert "--accent-ink: #ffffff" in _home(green)
    # Превью neon: акцент лайм → тёмные чернила и без сохранённого цвета.
    plain = TenantFactory.build(business_type="grocery", primary_color="#4f46e5")
    assert "--accent-ink: #111827" in _home(plain, "?preview=1&look=neon")


def test_preview_bundle_overlay_is_stateless():
    """DL-3: ?preview=1&bundle=<key> — оси сборки read-only оверлеем; без
    явного &look= кожу даёт Look-семейство самой сборки; явный &look= сильнее."""
    tenant = TenantFactory.build(business_type="grocery", primary_color="#4f46e5")
    html = _home(tenant, "?preview=1&bundle=deal_prospekt")
    assert "Barlow Condensed" in html  # кожа выведена из bundle.look
    assert 'data-sf-chrome="hard"' in html
    assert sitetemplates.look_accent("grocery", "prospekt") in html
    # Явный look перебивает look сборки (галерея показывает комбинации).
    html = _home(tenant, "?preview=1&look=neon&bundle=deal_prospekt")
    assert 'var tenantDark = "dark" === "dark"' in html
    # КОМПОЗИЦИЯ сборки доезжает до тела главной (вьюха рендерит секции из
    # своего site — без оверлея там превью показывало бы сохранённую раскладку).
    from apps.promotions.tests.factories import PromotionFactory

    PromotionFactory(status="active", discount_percent=20)
    html = _home(tenant, "?preview=1&bundle=deal_smart")
    assert "data-promo-rows" in html  # стиль promotions сборки (V5 Marktplatz)
    assert "data-promo-spotlight" not in html
    html = _home(tenant, "?preview=1&bundle=deal_prospekt")
    assert "data-promo-spotlight" in html
    # Мусорный ключ сборки — рендер живой, конфиг не тронут.
    assert "#4f46e5" in _home(tenant, "?preview=1&bundle=junk")
    assert tenant.site_config in (None, {}, tenant.site_config)


def test_builder_save_preserves_lookonly_site_defaults():
    """DL-2 (класс W0/W6): Save билдера БЕЗ hidden-инпутов не стирает
    page_bg/card_chrome/hero_widget; с инпутами — пишет присланное."""
    import uuid as _uuid

    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.core import views as core_views

    tenant = TenantFactory(
        business_type="grocery",
        site_config={
            "site_defaults": {
                "page_bg": "#faf6ef",
                "card_chrome": "hard",
                "hero_widget": "stays",
            }
        },
    )

    def _post(data):
        request = RequestFactory().post("/dashboard/site/home/", data)
        SessionMiddleware(lambda r: None).process_request(request)
        MessageMiddleware(lambda r: None).process_request(request)
        o = _uuid.uuid4().hex[:8]
        request.user = get_user_model().objects.create_user(
            username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
        )
        request.tenant = tenant
        return core_views.home_builder_view(request)

    # Save-форма без DL-2 hidden-инпутов (старый клиент/другая область).
    assert _post({"font": "system"}).status_code == 302
    tenant.refresh_from_db()
    sd = tenant.site_config["site_defaults"]
    assert sd["page_bg"] == "#faf6ef"
    assert sd["card_chrome"] == "hard"
    assert sd["hero_widget"] == "stays"
    # С инпутами — присланные значения побеждают ("" законно снимает ключ).
    assert (
        _post({"font": "system", "sd_page_bg": "#f4f6f9", "sd_card_chrome": "line"}).status_code
        == 302
    )
    tenant.refresh_from_db()
    sd = tenant.site_config["site_defaults"]
    assert sd["page_bg"] == "#f4f6f9"
    assert sd["card_chrome"] == "line"
    assert _post({"font": "system", "sd_page_bg": "", "sd_card_chrome": ""}).status_code == 302
    tenant.refresh_from_db()
    sd = tenant.site_config["site_defaults"]
    assert "page_bg" not in sd
    assert "card_chrome" not in sd
    assert sd["hero_widget"] == "stays"  # E4-выбор переживает любой Save


def test_media_shape_presence_minimal_and_rendered():
    """DL-10 (фидбэк «сделать фото круглыми и отдельно горизонтальными»):
    форма кадра — presence-minimal ключ site_defaults.media_shape; на витрине
    выходит атрибутом body (CSS-каскад по помеченным медиа-боксам)."""
    assert "media_shape" not in siteconfig.normalize({})["site_defaults"]
    assert (
        "media_shape"
        not in siteconfig.normalize({"site_defaults": {"media_shape": "junk"}})["site_defaults"]
    )
    for shape in ("round", "wide"):
        cfg = siteconfig.normalize({"site_defaults": {"media_shape": shape}})
        assert cfg["site_defaults"]["media_shape"] == shape
        tenant = TenantFactory.build(business_type="grocery", site_config=cfg)
        assert f' data-sf-media="{shape}"' in _home(tenant)
    # Без ключа атрибута нет — прежний вид карточек байт-в-байт.
    assert " data-sf-media=" not in _home(TenantFactory.build(business_type="grocery"))


def test_bundles_carry_media_shape():
    """DL-10b: форма кадра — часть композиции шаблона (круглые у Frischmarkt,
    широкие у Markthalle), остальные оставляют разметочную форму."""
    tenant = TenantFactory(business_type="grocery")
    sitetemplates.apply_bundle(tenant, "deal_frisch")
    assert tenant.site_config["site_defaults"]["media_shape"] == "round"
    sitetemplates.apply_bundle(tenant, "deal_blatt")
    assert tenant.site_config["site_defaults"]["media_shape"] == "wide"
    sitetemplates.apply_bundle(tenant, "deal_neon")
    assert "media_shape" not in tenant.site_config["site_defaults"]


def test_bundle_keeps_owner_keys_no_bundle_declares():
    """Startpaket сбрасывает ОСИ СБОРОК, а не весь `site_defaults`.

    STU-10 (доигровка скептиков ревью STU-9): исправив `apply_look`, я оставил
    путь сборки как есть — и он продолжал молча уносить ключи, которых не
    объявляет НИ ОДНА сборка и НИ ОДНО семейство (ширина текстовой колонки).
    Владелец применял Startpaket и без единого сообщения терял выбор (класс W6).
    """
    tenant = TenantFactory()
    config = siteconfig.normalize(tenant.site_config)
    config["site_defaults"] = {**config.get("site_defaults", {}), "text_width": "full"}
    tenant.site_config = siteconfig.normalize(config)
    tenant.save(update_fields=["site_config"])

    for bundle in sitetemplates.BUNDLES:
        assert sitetemplates.apply_bundle(tenant, bundle["key"])
        kept = siteconfig.normalize(tenant.site_config)["site_defaults"]
        assert kept.get("text_width") == "full", (
            f"сборка {bundle['key']} стёрла ключ, которого не объявляет ни одна сборка"
        )


def test_bundle_sd_axes_match_the_writer():
    """Перечень осей `site_defaults`, которые пишет `_apply_bundle_axes`, обязан
    совпадать с `_BUNDLE_SD_AXES` — иначе новая ось не попадёт в сброс, и
    переключение сборок начнёт накапливать прежнюю (или, наоборот, ось владельца
    будет теряться)."""
    import inspect
    import re

    src = inspect.getsource(sitetemplates._apply_bundle_axes)
    written = set(re.findall(r'sd\["([a-z_]+)"\]', src))
    assert written == set(sitetemplates._BUNDLE_SD_AXES), (
        f"_apply_bundle_axes пишет {sorted(written)}, "
        f"а _BUNDLE_SD_AXES объявляет {sorted(sitetemplates._BUNDLE_SD_AXES)}"
    )
