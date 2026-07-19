"""Спринт D.2: C-блоки (повторяемые «кубики») — нормализация + рендер."""

import pytest
from django.template import Context
from django.test import RequestFactory

from apps.tenants import siteconfig
from apps.tenants.templatetags import siteui

# --- нормализация -----------------------------------------------------------------


def test_normalize_keeps_multiple_cblocks_with_ids_and_data():
    cfg = siteconfig.normalize(
        {
            "sections": [
                {"key": "hero", "enabled": True},
                {"key": "text", "id": "a1", "enabled": True, "data": {"title": "T", "body": "B"}},
                {"key": "text", "id": "a2", "enabled": True, "data": {"title": "Zwei"}},
                {"key": "button", "data": {"label": "Los", "url": "/x"}},  # id сгенерится
            ]
        }
    )
    blocks = [s for s in cfg["sections"] if s["key"] in siteconfig.REPEATABLE_BLOCKS]
    assert len(blocks) == 3  # два text + button, НЕ дедуплены по key
    assert blocks[0]["id"] == "a1" and blocks[0]["data"]["body"] == "B"
    assert blocks[2]["id"]  # автогенерируемый id непустой
    assert blocks[2]["data"] == {"label": "Los", "url": "/x"}


def test_cblock_data_sanitized_per_type():
    cfg = siteconfig.normalize(
        {"sections": [{"key": "image_text", "data": {"url": "/i.jpg", "side": "bogus"}}]}
    )
    block = next(s for s in cfg["sections"] if s["key"] == "image_text")
    assert block["data"]["side"] == "left"  # мусорный side → дефолт
    assert block["data"]["url"] == "/i.jpg"


def test_cblocks_capped():
    raw = [{"key": "spacer"} for _ in range(50)]
    cfg = siteconfig.normalize({"sections": raw})
    blocks = [s for s in cfg["sections"] if s["key"] == "spacer"]
    assert len(blocks) == siteconfig._MAX_CBLOCKS


def test_unknown_section_key_still_dropped():
    cfg = siteconfig.normalize({"sections": [{"key": "totally-unknown"}]})
    keys = {s["key"] for s in cfg["sections"]}
    assert "totally-unknown" not in keys


# --- рендер ------------------------------------------------------------------------


def _render(block):
    ctx = Context({"request": RequestFactory().get("/")})
    return siteui.render_block(ctx, block)


def test_render_text_block():
    html = _render({"key": "text", "id": "x", "data": {"title": "Hallo", "body": "Welt"}})
    assert "Hallo" in html and "Welt" in html


def test_render_button_block():
    html = _render({"key": "button", "id": "x", "data": {"label": "Buchen", "url": "/t/"}})
    assert "Buchen" in html and 'href="/t/"' in html


def test_render_image_text_side_order():
    html = _render(
        {"key": "image_text", "id": "x", "data": {"url": "/i.jpg", "title": "A", "side": "right"}}
    )
    assert "md:order-2" in html and "/i.jpg" in html


def test_render_empty_text_block_is_blank():
    assert _render({"key": "text", "id": "x", "data": {}}).strip() == ""


# --- UC6-2: стиль текста блока (align/size/color, палитра темы) --------------------


def test_text_style_keeps_only_valid_non_default_values():
    cfg = siteconfig.normalize(
        {
            "sections": [
                {
                    "key": "text",
                    "id": "s1",
                    "data": {
                        "title": "T",
                        "align": "center",
                        "size": "xl",
                        "color": "accent",
                    },
                },
                {
                    "key": "text",
                    "id": "s2",
                    # дефолты/мусор → ключей стиля НЕТ (старые конфиги байт-в-байт)
                    "data": {"title": "U", "align": "left", "size": "#f00", "color": "red"},
                },
            ]
        }
    )
    b1, b2 = (s for s in cfg["sections"] if s["key"] == "text")
    assert b1["data"]["align"] == "center"
    assert b1["data"]["size"] == "xl"
    assert b1["data"]["color"] == "accent"
    assert "align" not in b2["data"] and "size" not in b2["data"] and "color" not in b2["data"]


def test_image_text_style_flows_through():
    cfg = siteconfig.normalize(
        {
            "sections": [
                {"key": "image_text", "data": {"title": "T", "align": "right", "color": "muted"}}
            ]
        }
    )
    block = next(s for s in cfg["sections"] if s["key"] == "image_text")
    assert block["data"]["align"] == "right" and block["data"]["color"] == "muted"


def test_render_text_block_applies_style_classes():
    html = _render(
        {
            "key": "text",
            "enabled": True,
            "data": {"title": "T", "body": "B", "align": "center", "size": "xl", "color": "accent"},
        }
    )
    assert "text-center" in html
    assert "md:text-4xl" in html
    assert "var(--accent)" in html


# --- UC6-3: ширина блока (w23/w12) + положение --------------------------------------


def test_cblock_width_w23_w12_and_pos():
    cfg = siteconfig.normalize(
        {
            "sections": [
                {"key": "text", "id": "w1", "data": {"title": "T"}, "width": "w23", "pos": "right"},
                {"key": "text", "id": "w2", "data": {"title": "U"}, "width": "w12"},
                {"key": "text", "id": "w3", "data": {"title": "V"}, "width": "bogus", "pos": "up"},
            ]
        }
    )
    b1, b2, b3 = (s for s in cfg["sections"] if s["key"] == "text")
    assert b1["width"] == "w23" and b1["pos"] == "right"
    assert b2["width"] == "w12" and "pos" not in b2  # центр = без ключа
    assert b3["width"] == "contained" and "pos" not in b3  # мусор → дефолты


def test_section_width_not_extended_to_w23():
    """Секции остаются на contained/full — w23 только у C-блоков."""
    cfg = siteconfig.normalize({"sections": [{"key": "products", "enabled": True, "width": "w23"}]})
    sec = next(s for s in cfg["sections"] if s["key"] == "products")
    assert sec["width"] == "contained"


# --- UC6-4: скругление фото + 📷 на канве -------------------------------------------


def test_image_rounded_validated_and_rendered():
    cfg = siteconfig.normalize(
        {
            "sections": [
                {"key": "image", "id": "r1", "data": {"url": "/i.jpg", "rounded": "3xl"}},
                {"key": "image", "id": "r2", "data": {"url": "/i.jpg", "rounded": "bogus"}},
            ]
        }
    )
    b1, b2 = (s for s in cfg["sections"] if s["key"] == "image")
    assert b1["data"]["rounded"] == "3xl"
    assert "rounded" not in b2["data"]  # мусор → дефолт (без ключа)
    html = _render({"key": "image", "id": "r1", "data": {"url": "/i.jpg", "rounded": "3xl"}})
    assert "rounded-3xl" in html and "rounded-2xl" not in html


def test_image_block_photo_button_only_in_preview():
    ctx = Context({"request": RequestFactory().get("/"), "is_preview": True})
    html = siteui.render_block(ctx, {"key": "image", "id": "px", "data": {"url": "/i.jpg"}})
    assert 'data-edit-model="cblock"' in html and 'data-edit-pk="px"' in html
    # публичная витрина (не превью) — кнопки нет
    html_pub = _render({"key": "image", "id": "px", "data": {"url": "/i.jpg"}})
    assert "data-photo-edit" not in html_pub


# --- UC6-3a/3b: ряды узких блоков + новые ширины ------------------------------------


def test_group_block_rows_groups_consecutive_narrow():
    blocks = [
        {"key": "hero", "enabled": True},
        {"key": "text", "id": "a", "width": "w12"},
        {"key": "text", "id": "b", "width": "w12"},
        {"key": "text", "id": "c", "width": "contained"},
    ]
    out = siteconfig.group_block_rows(blocks)
    assert [b.get("key") for b in out] == ["hero", "_row", "text"]
    assert [x["id"] for x in out[1]["row"]] == ["a", "b"]


def test_group_block_rows_newline_breaks_row():
    blocks = [
        {"key": "text", "id": "a", "width": "w13"},
        {"key": "text", "id": "b", "width": "w13", "newline": True},
        {"key": "text", "id": "c", "width": "w13"},
    ]
    out = siteconfig.group_block_rows(blocks)
    assert len(out) == 2  # newline разорвал ряд; c прилип ко второму
    assert [x["id"] for x in out[0]["row"]] == ["a"]
    assert [x["id"] for x in out[1]["row"]] == ["b", "c"]


def test_new_widths_and_newline_validated():
    cfg = siteconfig.normalize(
        {
            "sections": [
                {
                    "key": "text",
                    "id": "n1",
                    "data": {"title": "T"},
                    "width": "w14",
                    "newline": True,
                },
                {"key": "text", "id": "n2", "data": {"title": "U"}, "width": "w16"},
            ]
        }
    )
    b1, b2 = (s for s in cfg["sections"] if s["key"] == "text")
    assert b1["width"] == "w14" and b1["newline"] is True
    assert b2["width"] == "w16" and "newline" not in b2


# --- UC6-6b: visual (тень/фон/отступ/радиус) на C-блоках ----------------------------


def test_cblock_visual_kept_only_when_set_and_wrapper_emits_vars():
    from django.template.loader import render_to_string

    cfg = siteconfig.normalize(
        {
            "sections": [
                {
                    "key": "text",
                    "id": "v1",
                    "data": {"title": "T"},
                    "visual": {"shadow": True, "radius": 12},
                },
                {"key": "text", "id": "v2", "data": {"title": "U"}, "visual": {"shadow": False}},
            ]
        }
    )
    b1, b2 = (s for s in cfg["sections"] if s["key"] == "text")
    assert b1["visual"]["shadow"] is True and b1["visual"]["radius"] == 12
    assert "visual" not in b2  # все нули → ключа нет (golden-паритет)
    html = render_to_string(
        "storefront/_section_block.html", {"b": b1}, request=RequestFactory().get("/")
    )
    assert "--sf-sh" in html and "--sf-r:12px" in html  # обёртка отдала переменные
    assert 'class="cb-box' in html  # контейнер блока их потребляет


# --- UC6-6c: пресеты отображения при вставке ----------------------------------------


def test_cblock_insert_preset_merges_demo_and_variant():
    p = siteconfig.cblock_insert_preset("text", "banner")
    assert p["data"]["title"]  # демо-заголовок остался
    assert p["data"]["color"] == "accent" and p["data"]["size"] == "xl"
    assert p["visual"]["shadow"] is True and p["visual"]["radius"] == 16
    # неизвестный/пустой вариант → стандарт (чистые демо-данные)
    assert siteconfig.cblock_insert_preset("text", "nope") == {
        "data": siteconfig.CBLOCK_DEMO_DATA["text"]
    }
    assert siteconfig.cblock_insert_preset("spacer", "") == {"data": {}}


def test_all_cblock_variants_survive_normalize():
    """Каждый пресет реестра проходит normalize БЕЗ потерь — иначе выбор
    варианта молча давал бы стандартный блок."""
    for btype, variants in siteconfig.CBLOCK_VARIANTS.items():
        for v in variants:
            preset = siteconfig.cblock_insert_preset(btype, v["key"])
            cfg = siteconfig.normalize(
                {"sections": [{"key": btype, "id": "x1", "enabled": True, **preset}]}
            )
            block = next(s for s in cfg["sections"] if s["key"] == btype)
            for prop in ("width", "pos", "newline"):
                if prop in preset:
                    assert block.get(prop) == preset[prop], (btype, v["key"], prop)
            if "visual" in preset:
                for k, val in preset["visual"].items():
                    assert block["visual"][k] == val, (btype, v["key"], k)
            for k, val in preset["data"].items():
                assert block["data"].get(k) == val, (btype, v["key"], k)


def test_cblock_variants_ten_per_type_unique_keys():
    """UC6-8 (курс владельца «~10 видов на тип»): каждый повторяемый тип C-блока
    имеет ≥10 пресетов отображения с уникальными ключами (в инсертере +«Standard»)."""
    for btype in ("text", "image", "image_text", "button", "promo"):
        variants = siteconfig.CBLOCK_VARIANTS.get(btype, [])
        keys = [v["key"] for v in variants]
        assert len(variants) >= 10, (btype, len(variants))
        assert len(keys) == len(set(keys)), (btype, "duplicate keys")
        for v in variants:
            assert v.get("key") and v.get("label"), (btype, v)


# --- UC6-6d: варианты отображения фикс-секций (FAQ) ---------------------------------


def test_section_style_validated_by_registry():
    cfg = siteconfig.normalize(
        {
            "sections": [
                {"key": "faq", "enabled": True, "style": "cards"},
                {"key": "products", "enabled": True, "style": "cards"},  # не в реестре
            ]
        }
    )
    faq = next(s for s in cfg["sections"] if s["key"] == "faq")
    products = next(s for s in cfg["sections"] if s["key"] == "products")
    assert faq["style"] == "cards"
    assert "style" not in products  # только секции из SECTION_STYLES
    # мусорный стиль → без ключа (дефолт-аккордеон)
    cfg2 = siteconfig.normalize({"sections": [{"key": "faq", "enabled": True, "style": "xxx"}]})
    assert "style" not in next(s for s in cfg2["sections"] if s["key"] == "faq")


def test_faq_renders_five_styles():
    from django.template import Context

    site = {"faq": [{"q": "Frage?", "a": "Antwort."}, {"q": "F2?", "a": "A2."}]}

    def render(style):
        ctx = Context({"request": RequestFactory().get("/"), "site": site})
        return siteui.render_block(
            ctx,
            {"key": "faq", "enabled": True, "style": style}
            if style
            else {"key": "faq", "enabled": True},
        )

    assert "<details" in render("")  # дефолт — аккордеон (байт-семантика)
    assert "<details" not in render("list") and "Frage?" in render("list")
    assert "md:grid-cols-2" in render("twocol")
    assert "bg-gray-50" in render("cards")
    assert "var(--accent)" in render("numbered") and "<ol" in render("numbered")


def test_testimonials_and_process_styles_render():
    """UC6-6d2: «подобные FAQ» — отзывы и шаги, по 5 видов (4 варианта + дефолт)."""
    from django.template import Context

    site = {
        "testimonials": [{"name": "Anna", "text": "Super!"}],
        "process": [{"title": "Anruf", "text": "Wir melden uns."}],
    }

    def render(key, style):
        row = {"key": key, "enabled": True}
        if style:
            row["style"] = style
        ctx = Context({"request": RequestFactory().get("/"), "site": site})
        return siteui.render_block(ctx, row)

    assert "bg-white rounded-2xl" in render("testimonials", "")  # дефолт-карточки
    assert "text-2xl" in render("testimonials", "quotes")
    assert "border-left:4px solid var(--accent)" in render("testimonials", "accent")
    assert "divide-y" in render("testimonials", "list")
    assert "max-w-2xl" in render("testimonials", "single")

    assert "sm:grid-cols-3" in render("process", "")  # дефолт-сетка
    assert "border-l-2" in render("process", "timeline")
    assert "flex flex-wrap" in render("process", "row")
    assert "items-baseline" in render("process", "minimal")
    assert "sm:grid-cols-2" in render("process", "twocol")

    # реестр принимает style у testimonials/process
    cfg = siteconfig.normalize(
        {
            "sections": [
                {"key": "testimonials", "enabled": True, "style": "quotes"},
                {"key": "process", "enabled": True, "style": "timeline"},
            ]
        }
    )
    assert next(s for s in cfg["sections"] if s["key"] == "testimonials")["style"] == "quotes"
    assert next(s for s in cfg["sections"] if s["key"] == "process")["style"] == "timeline"


def test_gallery_team_trust_styles_render():
    """UC6-6f: варианты отображения галереи/команды/trust."""
    from django.template import Context

    site = {
        "gallery": [{"url": "/a.jpg", "alt": {}}],
        "gallery_video": "",
        "team": [{"name": "Mia", "role": "Chefin", "photo": ""}],
        "trust": {"since": "1998", "marks": ["Bio"]},
    }

    def render(key, style):
        row = {"key": key, "enabled": True}
        if style:
            row["style"] = style
        ctx = Context({"request": RequestFactory().get("/"), "site": site})
        return siteui.render_block(ctx, row)

    assert "aspect-square rounded-xl" in render("gallery", "")  # дефолт-сетка
    assert "overflow-x-auto" in render("gallery", "strip")
    assert "pb-6 rounded shadow-md" in render("gallery", "polaroid")
    assert "rounded-3xl" in render("gallery", "soft")
    assert "sm:grid-cols-2" in render("gallery", "large")

    assert "bg-white rounded-2xl shadow-sm" in render("team", "")  # дефолт-карточки
    assert "rounded-full" in render("team", "circles")
    assert "w-14 h-14 rounded-full" in render("team", "list")
    assert "aspect-square rounded-xl" in render("team", "compact")
    # UC6-8: 5-й вид «duo» — широкие карточки, фото сбоку (grid + flex-строка).
    duo = render("team", "duo")
    assert "md:grid-cols-2" in duo and "flex items-center gap-4 bg-white" in duo

    assert "justify-center" in render("trust", "")
    assert "justify-start text-left" in render("trust", "left")
    assert "border-color:var(--accent)" in render("trust", "badges")
    assert "bg-white rounded-2xl" not in render("trust", "plain")
    # UC6-8: 5-й вид «cards» — каждый показатель в рамке.
    assert "border border-gray-200 rounded-xl px-5 py-3" in render("trust", "cards")


def test_team_trust_five_styles_registry():
    """UC6-8: team/trust дотянуты до 5 видов (Standard + 4 в реестре)."""
    for key in ("team", "trust"):
        assert len(siteconfig.SECTION_STYLES[key]) == 4, key  # +Standard = 5
        for st in siteconfig.SECTION_STYLES[key]:
            assert st in siteconfig.SECTION_STYLE_LABELS, (key, st)


def test_promo_block_style_hint_survives_normalize():
    cfg = siteconfig.normalize(
        {
            "sections": [
                {"key": "promo", "id": "p1", "data": {"promo_pk": "x", "style_hint": "countdown"}},
                {"key": "promo", "id": "p2", "data": {"promo_pk": "x", "style_hint": "bogus"}},
            ]
        }
    )
    b1, b2 = (s for s in cfg["sections"] if s["key"] == "promo")
    assert b1["data"]["style_hint"] == "countdown"
    assert "style_hint" not in b2["data"]  # мусор → без ключа


# --- UC6-7a: page_blocks — C-блоки на любой странице --------------------------------


def test_normalize_page_blocks_whitelist_and_clean():
    cfg = siteconfig.normalize(
        {
            "page_blocks": {
                "services": [{"key": "text", "id": "s1", "data": {"title": "T"}, "width": "w12"}],
                "legal": [{"key": "text", "id": "l1", "data": {"title": "X"}}],  # вне whitelist
                "catalog": "junk",
            }
        }
    )
    pb = cfg["page_blocks"]
    assert set(pb) == {"services"}
    block = pb["services"][0]
    assert block["key"] == "text" and block["width"] == "w12"
    assert block["data"]["title"] == "T"
    # без page_blocks — ключа в normalize НЕТ (golden-паритет)
    assert "page_blocks" not in siteconfig.normalize({})


def test_page_blocks_tag_renders_and_uses_preview_draft():
    from types import SimpleNamespace

    from django.template import Context

    cfg = {
        "page_blocks": {"services": [{"key": "text", "id": "s1", "data": {"title": "Live-Titel"}}]}
    }
    req = RequestFactory().get("/termin/")
    req.tenant = SimpleNamespace(site_config=cfg)
    html = siteui.page_blocks(Context({"request": req}), "services")
    assert "Live-Titel" in html and 'data-sf-section="s1"' in html

    # пустой хост на публичной странице — ничего (страница не «грязнится»)
    assert siteui.page_blocks(Context({"request": req}), "catalog") == ""

    # ?preview=1 — черновик сессии главнее опубликованного
    req2 = RequestFactory().get("/termin/?preview=1")
    req2.tenant = SimpleNamespace(site_config=cfg)
    req2.session = {
        "site_preview_draft": {
            "page_blocks": {"services": [{"key": "text", "id": "s1", "data": {"title": "Entwurf"}}]}
        }
    }
    html2 = siteui.page_blocks(Context({"request": req2}), "services")
    assert "Entwurf" in html2 and "Live-Titel" not in html2


def test_contact_styles_render():
    """ST-2: варианты контакт-секции — "" карта снизу | split сбоку | map_first
    сверху | compact плоско без карты; normalize принимает style у contact."""
    from types import SimpleNamespace

    tenant = SimpleNamespace(
        address="Hauptstr. 1",
        opening_hours="Mo–Fr 9–18",
        public_phone="+49 2103 111",
        public_email="",
        open_status="",
        todays_hours="",
        map_url="",
        latitude=51.16,
        longitude=6.93,
    )

    def render(style):
        row = {"key": "contact", "enabled": True}
        if style:
            row["style"] = style
        req = RequestFactory().get("/")
        req.tenant = tenant
        return siteui.render_block(Context({"request": req, "site": {}}), row)

    std = render("")
    assert "bg-white rounded-2xl" in std and "overflow-hidden mt-6 relative" in std
    split = render("split")
    assert "lg:grid-cols-3" in split and "min-h-[16rem]" in split
    first = render("map_first")
    assert "overflow-hidden mb-6 relative" in first
    compact = render("compact")
    assert "sf-contact-map" not in compact and "bg-white rounded-2xl" not in compact
    assert "+49 2103 111" in compact

    cfg = siteconfig.normalize(
        {"sections": [{"key": "contact", "enabled": True, "style": "compact"}]}
    )
    assert next(s for s in cfg["sections"] if s["key"] == "contact")["style"] == "compact"


def test_spacer_height_variants():
    """ST-7a: высота spacer — presence-minimal (дефолт = без ключа, py-6 как
    раньше), варианты реестра проходят normalize, рендер ветвит по height."""
    cfg = siteconfig.normalize(
        {
            "sections": [
                {"key": "spacer", "id": "s1", "data": {"height": "xl"}},
                {"key": "spacer", "id": "s2", "data": {}},
                {"key": "spacer", "id": "s3", "data": {"height": "bogus"}},
            ]
        }
    )
    by_id = {s["id"]: s for s in cfg["sections"] if s["key"] == "spacer"}
    assert by_id["s1"]["data"] == {"height": "xl"}
    assert by_id["s2"]["data"] == {} and by_id["s3"]["data"] == {}  # мусор → дефолт

    def render(height):
        row = {"key": "spacer", "enabled": True, "data": ({"height": height} if height else {})}
        return siteui.render_block(Context({"request": RequestFactory().get("/")}), row)

    assert "py-6" in render("")  # дефолт байт-в-байт прежний
    assert "py-2" in render("sm") and "py-12" in render("lg") and "py-20" in render("xl")

    # варианты реестра: у spacer 4, каждый с key+label, insert-preset валиден
    vs = siteconfig.CBLOCK_VARIANTS["spacer"]
    assert len(vs) == 4 and len({v["key"] for v in vs}) == 4
    preset = siteconfig.cblock_insert_preset("spacer", "sehr_gross")
    assert preset["data"]["height"] == "xl"


def test_cta_about_usp_styles_render():
    """ST-7b: стили простых секций cta/about/usp_bar; "" = прежний вид."""
    site = {
        "cta": {"title": "Jetzt buchen", "text": "", "button_label": "Los", "button_url": "/x"},
        "about_title": "Über uns",
        "about_text": "Wir sind da.",
        "usp_bar": [{"icon": "truck", "label": "Versand"}],
    }

    def render(key, style):
        row = {"key": key, "enabled": True}
        if style:
            row["style"] = style
        ctx = Context({"request": RequestFactory().get("/"), "site": site})
        return siteui.render_block(ctx, row)

    std = render("cta", "")  # "" = акцент-band по центру (как раньше)
    assert 'style="background: var(--accent);"' in std and "text-center text-white" in std
    assert "text-left" in render("cta", "left")
    cards = render("cta", "cards")
    assert "bg-white rounded-2xl" in cards and "hover:opacity-90" in cards
    minimal = render("cta", "minimal")
    assert "shadow-sm" not in minimal and "hover:underline" in minimal

    a_std = render("about", "")
    assert "bg-white rounded-2xl shadow-sm" in a_std and "border-left" not in a_std
    assert "border-left:4px solid var(--accent)" in render("about", "accent")
    assert "bg-white" not in render("about", "plain")
    assert "max-w-2xl mx-auto text-center" in render("about", "single")

    assert "bg-white rounded-2xl shadow-sm" in render("usp_bar", "")
    assert "bg-white rounded-2xl shadow-sm" not in render("usp_bar", "plain")
    assert "border border-gray-200 rounded-xl" in render("usp_bar", "cards")
    assert "text-xs text-gray-500" in render("usp_bar", "compact")

    cfg = siteconfig.normalize({"sections": [{"key": "cta", "enabled": True, "style": "cards"}]})
    assert next(s for s in cfg["sections"] if s["key"] == "cta")["style"] == "cards"


@pytest.mark.django_db
def test_reviews_section_styles_render():
    """ST-7b: стили секции отзывов (BusinessReview SHARED по schema_name)."""
    import uuid as _uuid

    from django.db import connection

    from apps.aggregator.models import BusinessReview, PortalUser

    u = PortalUser.objects.create(email=f"{_uuid.uuid4().hex}@k.test")
    BusinessReview.objects.create(
        tenant_schema=connection.schema_name, tenant_slug="x", author=u, rating=5, comment="Top!"
    )

    def render(style):
        row = {"key": "reviews", "enabled": True}
        if style:
            row["style"] = style
        ctx = Context({"request": RequestFactory().get("/"), "site": {}})
        return siteui.render_block(ctx, row)

    assert "Top!" in render("")
    assert "space-y-8 max-w-2xl" in render("quotes")
    assert "divide-y divide-gray-200" in render("list")
    assert "space-y-4 max-w-2xl" in render("single")
