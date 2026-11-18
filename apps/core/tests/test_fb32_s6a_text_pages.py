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
