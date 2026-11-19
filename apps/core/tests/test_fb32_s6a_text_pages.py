"""FB-32 S6a: «Über uns» и своя страница «Seite» — текст и карточка контактов строками схемы
«Seitenaufbau» (как разделы детали и корзины): свои блоки встают над текстом и между ним и
контактами. Порядок разделов постоянный, текст не скрывается, видимость контактов — прежний
`about_contact`. Без якорей страница рисуется прежней разметкой (снимки
`test_fb32_s6_pages_golden.py`)."""

import pytest

from apps.core import detail_parts, site_schema
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb29_banner_pick import _cfg, _tenant
from apps.core.tests.test_fb32_s6_pages_golden import TEXT, _about, _page

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def test_info_and_own_pages_have_section_rows_without_purchase():
    assert detail_parts.section_keys("info") == ("pagetext", "contact")
    assert detail_parts.section_keys("seite:anfahrt") == ("pagetext",)
    assert detail_parts.section_keys("seite:") == ()
    assert not detail_parts.has_kauf("info") and not detail_parts.has_kauf("seite:x")
    assert detail_parts.has_kauf("event_detail")
    rows = site_schema.blocks_for({}, "text")
    by = {r["ref"]: r for r in rows}
    assert by["pagetext"]["pinned"] and by["pagetext"]["fixed"]
    assert by["contact"]["fixed"] and not by["contact"]["pinned"]
    assert detail_parts.KAUF_REF not in by


def test_text_cannot_be_hidden_or_moved_and_contact_cannot_be_moved():
    t = _tenant()
    for ref, op in (("pagetext", "toggle"), ("pagetext", "down"), ("contact", "up")):
        with pytest.raises(site_schema.SchemaError):
            site_schema.apply(t, "text", op, ref=ref)


def test_hiding_contact_in_the_draft_writes_the_old_switch():
    b = Browser(_tenant())
    b.post(seite="text", op="toggle", ref="contact")
    b.post(seite="text", op="save")
    cfg = _cfg(b.tenant)
    assert cfg["about_contact"] is False
    assert not (cfg.get("page_blocks") or {}).get("info"), "без своих блоков якоря не хранятся"


def test_own_block_above_the_text_is_drawn_above_it():
    cfg = {"page_blocks": {"info": [TEXT, {"key": "pagetext"}, {"key": "contact"}]}}
    html = _about(cfg)
    assert html.index("Bus 5") < html.index('data-edit="about_title"') < html.index("Hauptstr")


def test_own_block_between_text_and_contact():
    cfg = {"page_blocks": {"info": [{"key": "pagetext"}, TEXT, {"key": "contact"}]}}
    html = _about(cfg)
    assert html.index('data-edit="about_title"') < html.index("Bus 5") < html.index("Hauptstr")
    hidden = _about({**cfg, "about_contact": False})
    assert "Hauptstr" not in hidden and "Bus 5" in hidden, "блок скрытого раздела остаётся"


def test_own_page_block_above_the_article():
    html = _page({"page_blocks": {"info": [TEXT, {"key": "pagetext"}]}})
    assert html.index("Bus 5") < html.index("data-content-page")


def test_lift_keeps_anchors_only_with_a_block_above_the_last_section():
    cfg: dict = {}
    rows = [{"key": "pagetext"}, {"key": "contact", "enabled": True}, TEXT]
    assert detail_parts.lift(cfg, "info", rows) == [TEXT]
    rows = [{"key": "pagetext"}, TEXT, {"key": "contact", "enabled": False}]
    out = detail_parts.lift(cfg, "info", rows)
    assert out == [{"key": "pagetext"}, TEXT, {"key": "contact"}] and cfg["about_contact"] is False
    # текст своей страницы не скрывается даже присланным `enabled: False`
    assert detail_parts.lift({}, "seite:x", [{"key": "pagetext", "enabled": False}, TEXT]) == [TEXT]


def test_own_block_between_sections_moves_up_and_down():
    """Ревью S6a: разделы сами не двигаются, но своим блокам они — места."""
    from apps.tenants import siteconfig

    t = _tenant()
    t.site_config = {"page_blocks": {"info": [{"key": "pagetext"}, TEXT, {"key": "contact"}]}}
    t.save(update_fields=["site_config"])
    rows = {r["ref"]: r for r in site_schema.blocks_for(_cfg(t), "text")}
    assert rows["t-s6"]["can_up"] and rows["t-s6"]["can_down"]
    assert not rows["pagetext"]["can_up"] and not rows["contact"]["can_down"]
    site_schema.apply(t, "text", "up", ref="t-s6")
    keys = [
        r.get("id") or r["key"] for r in siteconfig.normalize(t.site_config)["page_blocks"]["info"]
    ]
    assert keys == ["t-s6", "pagetext", "contact"]
    assert _about(t.site_config).index("Bus 5") < _about(t.site_config).index("about_title")


def test_every_hideable_section_of_a_fixed_page_has_a_visibility_key():
    """Ревью S6a: видимость разделов таких страниц пишется только в прежние ключи."""
    from apps.core import detail_sections

    for module in detail_parts.FIXED_ORDER_MODULES:
        for s in detail_sections.sections_for(module):
            if s.hideable:
                assert s.key in detail_parts.VISIBILITY_KEYS.get(module, {}), (module, s.key)


def test_odd_seite_hosts_have_no_sections_and_text_is_never_hidden():
    from apps.tenants import siteconfig

    for host in ("seite:Foo", "seite:a:b", "seite:x/y"):
        assert detail_parts.section_keys(host) == ()
    assert (
        siteconfig.detail_section_hidden({"page_detail": {"hidden": ["pagetext"]}}, "page") == set()
    )


def test_draft_started_before_section_rows_is_not_a_false_conflict():
    from apps.core import aufbau_draft

    saved = {"items": [TEXT]}
    legacy = {"host": "info", "contact": False, "items": [TEXT]}
    legacy["base"] = aufbau_draft._fingerprint({**saved, "contact": True})
    assert aufbau_draft._base_fingerprint(saved, {}, legacy) == legacy["base"]
    assert aufbau_draft.changes(saved, legacy) == 1, "переключатель старого черновика учтён"
    fresh = {"host": "info", "items": [{"key": "pagetext"}, TEXT]}
    assert aufbau_draft._base_fingerprint(saved, {}, fresh) == aufbau_draft._fingerprint(saved)


# ── S6b: «Versand» ──────────────────────────────────────────────────────────────


def test_versand_rows_are_fixed_and_cannot_be_hidden():
    assert detail_parts.section_keys("versand") == ("pagetext", "costs")
    rows = {r["ref"]: r for r in site_schema.blocks_for({}, "text@versand")}
    assert rows["pagetext"]["pinned"] and rows["costs"]["pinned"], "§ 6 PAngV: не скрываются"
    t = _tenant()
    with pytest.raises(site_schema.SchemaError):
        site_schema.apply(t, "text@versand", "toggle", ref="costs")


def test_versand_own_block_between_text_and_costs():
    from apps.core.tests.test_fb32_s6_pages_golden import _versand

    cfg = {"page_blocks": {"info": [{"key": "pagetext"}, TEXT, {"key": "costs"}]}}
    html = _versand(cfg, body="<p>Wir liefern montags.</p>")
    assert html.index("Wir liefern") < html.index("Bus 5") < html.index("data-shipping-costs")
    assert html.count("data-shipping-row=") == 2


def test_versand_list_switched_off_stays_off_with_rows():
    from apps.core.tests.test_fb32_s6_pages_golden import _versand

    cfg = {"page_blocks": {"info": [TEXT, {"key": "pagetext"}, {"key": "costs"}]}}
    html = _versand(cfg, body="<p>Wir liefern montags.</p>", show=False)
    assert "data-shipping-row=" not in html and html.index("Bus 5") < html.index("Wir liefern")
    # без своего текста список виден всегда (как раньше)
    from apps.core.models import ContentPage
    from apps.orders.models import ShippingMethod

    ContentPage.objects.filter(slug="versand").delete()
    ShippingMethod.objects.update(active=False)
    assert "data-shipping-row=" in _versand(cfg)


def test_versand_without_own_text_shows_the_list_even_with_the_box_unticked():
    from apps.core.models import ContentPage
    from apps.core.tests.test_fb32_s6_pages_golden import _versand

    ContentPage.objects.create(
        slug="versand", title="Versand", body="", show_shipping_methods=False
    )
    cfg = {"page_blocks": {"info": [TEXT, {"key": "pagetext"}, {"key": "costs"}]}}
    html = _versand(cfg)
    assert "data-shipping-row=" in html, "§ 6 PAngV: без своего текста список виден всегда"


# ── S6c: «Kontakt» и «Anfrage» ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "host,code,key",
    (
        ("message", "contact", "form"),
        ("anfrage", "anfrage", "form"),
        ("gift", "gift", "form"),
        ("loyalty", "loyalty", "programs"),
    ),
)
def test_form_pages_have_one_fixed_form_row(host, code, key):
    assert detail_parts.section_keys(host) == (key,)
    rows = {r["ref"]: r for r in site_schema.blocks_for({}, code)}
    assert rows[key]["pinned"] and not detail_parts.has_kauf(host)


def test_own_block_above_the_contact_form_and_never_inside_it():
    from apps.core.tests.test_fb32_s6_pages_golden import _anfrage, _kontakt

    cfg = {"page_blocks": {"info": [TEXT, {"key": "form"}]}}
    for render, marker in ((_kontakt, "data-contact-layout"), (_anfrage, "data-anfrage-layout")):
        html = render(cfg)
        assert html.index("Bus 5") < html.index(marker), marker
        for form in html.split("<form")[1:]:
            assert "Bus 5" not in form.split("</form>")[0], "свой блок не внутри формы"
        assert html.count("Bus 5") == 1


def test_own_block_above_gift_form_and_loyalty_programs():
    from apps.core.tests.test_fb32_s6_pages_golden import _gift, _treue

    html = _gift({"page_blocks": {"info": [TEXT, {"key": "form"}]}})
    assert html.index("Bus 5") < html.index("<form")
    form = html[html.index("<form") : html.index("</form>")]
    assert "Bus 5" not in form, "свой блок не внутри формы оплаты"
    html = _treue({"page_blocks": {"info": [TEXT, {"key": "programs"}]}})
    assert html.index("Bus 5") < html.index("Kaffeekarte") and html.count("Bus 5") == 1


# ── S6e: «Blogbeitrag» и «Finder» ───────────────────────────────────────────────


def test_blog_more_posts_hides_through_the_schema_even_without_own_blocks():
    from apps.core.tests.test_fb32_s6_pages_golden import _blog
    from apps.tenants.tests.factories import TenantFactory

    b = Browser(TenantFactory(business_type="cafe", disabled_modules=[]))  # блог включён
    b.post(seite="blog_post", op="toggle", ref="more")
    b.post(seite="blog_post", op="save")
    cfg = _cfg(b.tenant)
    assert cfg["blog_show_more"] is False and not (cfg.get("page_blocks") or {}).get("blog_post")
    assert "Post 1" in _blog({}) and "Post 1" not in _blog({"blog_show_more": False})


def test_blog_own_block_between_article_and_more_posts():
    from apps.core.tests.test_fb32_s6_pages_golden import _blog

    html = _blog({"page_blocks": {"info": [{"key": "article"}, TEXT, {"key": "more"}]}})
    assert html.index("<h1") < html.index("Bus 5") < html.index("Post 1")
    from apps.tenants.tests.factories import TenantFactory

    t = TenantFactory(business_type="cafe", disabled_modules=[])
    with pytest.raises(site_schema.SchemaError, match="fixed"):
        site_schema.apply(t, "blog_post", "toggle", ref="article")


def test_finder_own_block_above_the_wizard():
    from apps.core.tests.test_fb32_s6_pages_golden import _finder

    html = _finder({"page_blocks": {"info": [TEXT, {"key": "wizard"}]}})
    assert html.index("Bus 5") < html.index("<h1") and html.count("Bus 5") == 1


# ── S6f: деталь акции ───────────────────────────────────────────────────────────

OFFER = {"key": "offer", "style": "plakat"}


def test_promo_offer_is_a_pinned_axis_row_and_related_hides():
    from apps.tenants import siteconfig

    assert detail_parts.section_keys("promo_detail") == ("offer", "share", "card", "related")
    # FB-33 M2g: «Teilen» и визитка — «на месте», не двигаются и не якоря
    assert detail_parts.flow_section_keys("promo_detail") == ("offer", "related")
    assert detail_parts.anchor_keys("promo_detail") == frozenset({"related"})
    cfg = siteconfig.normalize({"page_blocks": {"promo_detail": [OFFER, TEXT, {"key": "related"}]}})
    rows = {r["ref"]: r for r in site_schema.blocks_for(cfg, "promo")}
    assert rows["offer"]["pinned"] and not rows["related"]["pinned"]
    assert detail_parts.KAUF_REF not in rows, "покупка — сама строка «Angebot»"


def test_promo_rows_keep_the_offer_style_and_compact_without_anchors():
    from apps.tenants import siteconfig

    def norm(rows):
        return siteconfig.normalize({"page_blocks": {"promo_detail": rows}})["page_blocks"].get(
            "promo_detail", []
        )

    def bare(rows):  # строки без полей очистки блоков: ключ, id, вид
        return [
            {k: v for k, v in r.items() if k in ("key", "style")}
            | ({"id": r["id"]} if r.get("id") else {})
            for r in rows
        ]

    t_row = {"key": "text", "id": "t-s6"}

    assert bare(norm([OFFER, TEXT, {"key": "related"}])) == [OFFER, t_row, {"key": "related"}]
    assert norm([{"key": "offer"}, TEXT, {"key": "related"}])[0] == {"key": "offer"}
    assert [
        r.get("id") or r["key"] for r in norm([{"key": "offer"}, {"key": "related"}, TEXT])
    ] == ["t-s6"], "блоки после последнего раздела — без якорей и без голой строки оси"
    assert bare(norm([OFFER, {"key": "related"}, TEXT]))[0] == OFFER, "вид строки оси не теряется"
    cfg: dict = {}
    out = detail_parts.lift(
        cfg,
        "promo_detail",
        [{**OFFER, "enabled": True}, TEXT, {"key": "related", "enabled": False}],
    )
    assert out == [OFFER, TEXT, {"key": "related"}] and cfg["promo_show_related"] is False


def test_promo_own_blocks_above_the_offer_and_between_offer_and_related():
    from apps.core.tests.test_fb32_s6_pages_golden import _promo_detail

    html = _promo_detail({"page_blocks": {"info": [TEXT, {"key": "offer"}, {"key": "related"}]}})
    assert html.index("Bus 5") < html.index("md:grid-cols-2"), "блок над «Angebot»"
    html = _promo_detail({"page_blocks": {"info": [{"key": "offer"}, TEXT, {"key": "related"}]}})
    assert html.index("md:grid-cols-2") < html.index("Bus 5") < html.index("data-promo-related")
    assert html.count("Bus 5") == 1


def test_promo_related_hidden_keeps_own_block_and_skips_the_strip():
    from apps.core.tests.test_fb32_s6_pages_golden import _promo_detail

    cfg = {
        "promo_show_related": False,
        "page_blocks": {"info": [{"key": "offer"}, TEXT, {"key": "related"}]},
    }
    html = _promo_detail(cfg)
    assert "data-promo-related" not in html and "Bus 5" in html


def test_promo_offer_style_changes_but_offer_never_hides_or_moves():
    from apps.tenants.tests.factories import TenantFactory

    t = TenantFactory(business_type="cafe", disabled_modules=[])
    t.site_config = {"page_blocks": {"promo_detail": [OFFER, TEXT, {"key": "related"}]}}
    t.save(update_fields=["site_config"])
    for op in ("toggle", "up", "down"):
        with pytest.raises(site_schema.SchemaError):
            site_schema.apply(t, "promo", op, ref="offer")
    site_schema.apply(t, "promo", "catview", ref="offer", value="kompakt")
    rows = _cfg(t)["page_blocks"]["promo_detail"]
    assert rows[0]["style"] == "kompakt" and rows[-1] == {"key": "related"}


def test_template_choice_keeps_the_offer_place_when_anchored():
    from apps.tenants import siteconfig

    cfg = {"page_blocks": {"promo_detail": [OFFER, TEXT, {"key": "related"}]}}
    rows = siteconfig.drop_page_views(cfg, "promo_detail")["page_blocks"]["promo_detail"]
    assert rows == [{"key": "offer"}, TEXT, {"key": "related"}]


def test_promo_writer_without_related_row_keeps_its_visibility():
    """Ревью S6f: черновик до S6f или писатель без строки «Weitere Aktionen» не включает её молча."""
    cfg = {"promo_show_related": False}
    out = detail_parts.lift(cfg, "promo_detail", [{**OFFER, "enabled": True}, TEXT])
    assert cfg["promo_show_related"] is False and out == [{**OFFER, "enabled": True}, TEXT]
    assert detail_parts.promo_slots({"page_blocks": {"promo_detail": [OFFER, TEXT]}}) == {}


# ── S6g-1: «Lehrer», «Kalender», «Karten» ──────────────────────────────────────


@pytest.mark.parametrize(
    "host,key", (("teachers", "teacherlist"), ("event_calendar", "calendar"), ("passes", "plans"))
)
def test_new_page_types_have_one_fixed_row(host, key):
    from apps.core import studio_pages

    assert detail_parts.section_keys(host) == (key,)
    pt = next(p for p in studio_pages.PAGE_TYPES if p.block_host == host)
    rows = {r["ref"]: r for r in site_schema.blocks_for({}, pt.code)}
    assert rows[key]["pinned"] and not detail_parts.has_kauf(host)


def test_own_blocks_above_teachers_calendar_and_passes_not_inside_forms():
    from apps.core.tests.test_fb32_s6_pages_golden import _kalender, _karten, _lehrer

    for render, key in ((_lehrer, "teacherlist"), (_kalender, "calendar"), (_karten, "plans")):
        html = render({"page_blocks": {"info": [TEXT, {"key": key}]}})
        assert html.index("Bus 5") < html.index("<h1"), key
        for form in html.split("<form")[1:]:
            assert "Bus 5" not in form.split("</form>")[0]
        tail = render({"page_blocks": {"info": [TEXT]}})
        assert tail.index("<h1") < tail.index("Bus 5"), "без якоря — блоки под страницей"


def test_section_keys_never_collide_with_block_types():
    """S6g-1: раздел `list` у «Lehrer» совпал с блоком «Liste» — нормализация молча выбросила
    блоки страницы. Ключ раздела не должен быть типом блока."""
    from apps.core import detail_sections
    from apps.tenants import siteconfig

    for module, secs in detail_sections.DETAIL_SECTIONS.items():
        for s in secs:
            assert not siteconfig.cblock_type(s.key), (module, s.key)
            assert s.key not in siteconfig.PAGE_REF_BLOCKS, (module, s.key)


# ── S6g-2: «Termin» (ресурсы) и выбор времени ──────────────────────────────────


def test_termin_resources_page_shows_its_services_blocks_but_not_in_the_widget():
    from apps.core.tests.test_fb32_s6_pages_golden import _termin

    html = _termin({"page_blocks": {"info": [TEXT]}})
    assert "Bus 5" in html, "хост `services` теперь выводится и у бизнеса без услуг"
    assert "Bus 5" not in _termin({"page_blocks": {"info": [TEXT]}}, embed="1")


def test_slots_own_block_above_the_box_never_inside_it_nor_in_box_or_widget():
    from apps.core.tests.test_fb32_s6_pages_golden import _slots

    cfg = {"page_blocks": {"info": [TEXT, {"key": "slots"}]}}
    html = _slots(cfg)
    assert html.index("Bus 5") < html.index('id="svc-box"')
    box = html[html.index('id="svc-box"') :]
    assert "Bus 5" not in box[: box.index("_svc_box") if "_svc_box" in box else len(box)]
    assert "Bus 5" not in _slots(cfg, embed="1")
    assert "Bus 5" not in _slots(cfg, box="1"), "подмена коробки (?box=1) — без блоков"


def test_slots_page_type_and_preview():
    from apps.core import studio_pages
    from apps.core.tests.test_fb32_s6_pages_golden import _resource

    pt = next(p for p in studio_pages.PAGE_TYPES if p.code == "booking_slots")
    assert site_schema._preview_url(pt) == ""
    res = _resource()
    assert site_schema._preview_url(pt).endswith(f"/{res.pk}/")
    rows = {r["ref"]: r for r in site_schema.blocks_for({}, "booking_slots")}
    assert rows["slots"]["pinned"]


# ── S6g-3: «Kombi-Detail» ───────────────────────────────────────────────────────


def test_combo_rows_config_fixed_others_hide():
    assert detail_parts.section_keys("combo_detail") == (
        "config",
        "reviews",
        "examples",
        "cta",
        "related",
    )
    rows = {r["ref"]: r for r in site_schema.blocks_for({}, "combo")}
    assert rows["config"]["pinned"] and not rows["related"]["pinned"]
    assert detail_parts.KAUF_REF not in rows


def test_combo_own_block_between_configurator_and_reviews_never_in_the_form():
    from apps.core.tests.test_fb32_s6_pages_golden import _combo

    cfg = {"page_blocks": {"info": [{"key": "config"}, TEXT, {"key": "reviews"}]}}
    html = _combo(cfg)
    assert html.index("data-combo-form") < html.index("Bus 5") < html.index("Menü B")
    form = html[html.index("<form") : html.index("</form>")]
    assert "Bus 5" not in form and html.count("Bus 5") == 1


def test_combo_hidden_sections_disappear_with_or_without_own_blocks():
    from apps.core.tests.test_fb32_s6_pages_golden import _combo

    hidden = {
        "combo_show_examples": False,
        "combo_show_cta": False,
        "combo_show_related": False,
    }
    for cfg in (hidden, {**hidden, "page_blocks": {"info": [{"key": "config"}, TEXT]}}):
        html = _combo(cfg)
        assert "Beispiele unserer Arbeit" not in html and "Menü B" not in html
        assert "Sie planen" not in html and "data-combo-form" in html


def test_combo_hide_through_the_schema_writes_the_flag():
    cfg: dict = {}
    rows = [{"key": "config"}, {"key": "reviews", "enabled": False}, TEXT]
    detail_parts.lift(cfg, "combo_detail", rows)
    assert cfg["combo_show_reviews"] is False
    from apps.tenants import siteconfig

    assert siteconfig.normalize(cfg)["combo_show_reviews"] is False
