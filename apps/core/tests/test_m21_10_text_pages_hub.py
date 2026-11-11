"""M21.10: «Seiten» — один центр всех текстовых страниц (системные, правовые, свои)."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory

from apps.core import content_page_views as views
from apps.core import content_pages, legal, view_perms
from apps.core.models import ContentPage, LegalDoc, Membership
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture
def orders_on(monkeypatch):
    from apps.core import modules

    monkeypatch.setattr(modules, "is_module_active", lambda t, k, **kw: True)


def _user(role=Membership.ROLE_OWNER):
    import uuid

    name = f"u-{uuid.uuid4().hex[:8]}"
    user = get_user_model().objects.create_user(username=name, password="pw1234567")
    Membership.objects.create(user=user, role=role)
    return user


def _tenant(**kw):
    kw.setdefault("enabled_locales", ["de", "en"])
    kw.setdefault("default_locale", "de")
    return TenantFactory.build(schema_name="public", slug="t", name="T", **kw)


def _req(path="/x/", method="get", data=None, user=None, tenant=None):
    rf = RequestFactory()
    req = rf.post(path, data or {}) if method == "post" else rf.get(path)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = user or _user()
    req.tenant = tenant or _tenant()
    return req


# --- хаб ---------------------------------------------------------------------------


def test_hub_shows_system_legal_and_own_groups(orders_on):
    ContentPage.objects.create(slug="zahlungsarten", title="Zahlungsarten", is_published=True)
    html = views.pages_list(_req()).content.decode()
    assert 'data-system-row="ueber-uns"' in html and 'data-system-row="versand"' in html
    assert 'data-legal-row="datenschutz"' in html
    assert 'data-page-row="zahlungsarten"' in html
    # системная без своей страницы — «Bearbeiten» ведёт на форму-заготовку (GET без записи)
    assert "/dashboard/site/seiten/system/versand/" in html
    assert not ContentPage.objects.filter(slug__in=["versand", "ueber-uns"]).exists()


def test_versand_only_while_shop_takes_orders(monkeypatch):
    from apps.core import modules

    monkeypatch.setattr(modules, "is_module_active", lambda t, k, **kw: k != "orders")
    slugs = [r.slug for r in content_pages.system_rows(_tenant())]
    assert slugs == ["ueber-uns"]
    with pytest.raises(Http404):
        views.page_system(_req(), "versand")


def test_staff_sees_legal_rows_locked():
    req = _req(user=_user(Membership.ROLE_STAFF))
    assert not view_perms.allowed(req.user, "legal-page-edit", "GET")
    html = views.pages_list(req).content.decode()
    assert "data-legal-locked" in html
    assert "/dashboard/site/seiten/recht/" not in html


# --- системные страницы ------------------------------------------------------------


def test_system_get_creates_nothing_and_post_creates_with_fixed_slug(orders_on):
    resp = views.page_system(_req(), "ueber-uns")
    assert resp.status_code == 200 and not ContentPage.objects.exists()
    assert "data-system-slug" in resp.content.decode()
    views.page_system(
        _req(
            method="post",
            data={"title": "Über uns", "slug": "boese", "body": "<p>Hi</p>", "is_published": "1"},
        ),
        "ueber-uns",
    )
    page = ContentPage.objects.get()
    assert page.slug == "ueber-uns"  # адрес системной страницы закреплён
    # вторая заходка — уже правка существующей
    assert views.page_system(_req(), "ueber-uns").status_code == 302


def test_about_draft_starts_from_home_text_escaped():
    tenant = _tenant(site_config={"about_text": "Tom & Jerry <b>x</b>\nZeile 2\n\nAbsatz"})
    page = content_pages.initial_system_page("ueber-uns", tenant)
    assert page.body == ("<p>Tom &amp; Jerry &lt;b&gt;x&lt;/b&gt;<br>Zeile 2</p><p>Absatz</p>")
    assert page._state.adding


def test_existing_system_page_slug_cannot_be_changed():
    page = ContentPage.objects.create(slug="versand", title="Versand", is_published=True)
    content_pages.save_page(page, title="Versand", slug="anders", body="", is_published=True)
    page.refresh_from_db()
    assert page.slug == "versand"


def test_body_size_cap():
    page = ContentPage(is_published=True)
    with pytest.raises(content_pages.PageError):
        content_pages.save_page(
            page, title="X", slug="", body="a" * (content_pages.BODY_MAX + 1), is_published=True
        )


# --- правовые тексты в «Seiten» ----------------------------------------------------


def test_legal_page_edit_is_owner_only_on_both_methods():
    for role in (Membership.ROLE_STAFF, Membership.ROLE_ADMIN):
        user = _user(role)
        assert not view_perms.allowed(user, "legal-page-edit", "GET")
        assert not view_perms.allowed(user, "legal-page-edit", "POST")
    owner = _user()
    assert view_perms.allowed(owner, "legal-page-edit", "POST")


def test_legal_page_edit_saves_per_locale_with_presence_guard():
    LegalDoc.objects.create(kind="agb", locale="en", text="Old EN")
    resp = views.legal_page_edit(
        _req(method="post", data={"doc_de": "<p>§ 1 <script>x</script>Geltung</p>"}), "agb"
    )
    assert resp.status_code == 302
    assert LegalDoc.objects.get(kind="agb", locale="de").text == "<p>§ 1 Geltung</p>"
    assert LegalDoc.objects.get(kind="agb", locale="en").text == "Old EN"  # не прислано
    views.legal_page_edit(_req(method="post", data={"doc_en": " "}), "agb")
    assert not LegalDoc.objects.filter(kind="agb", locale="en").exists()


def test_legal_page_edit_unknown_kind_is_404_and_shows_fallback():
    with pytest.raises(Http404):
        views.legal_page_edit(_req(), "evil")
    html = views.legal_page_edit(_req(), "impressum").content.decode()
    assert 'name="doc_de"' in html and 'name="doc_en"' in html
    assert "data-take-fallback" in html and 'data-rte="page"' in html


def test_save_legal_doc_whitelists_kind_and_locale():
    with pytest.raises(ValueError):
        legal.save_legal_doc("evil", "de", "x")
    with pytest.raises(ValueError):
        legal.save_legal_doc("agb", "xx", "x")


# --- B3: белый список страниц — один источник для сервера и редактора ------------------


def test_page_sanitizer_keeps_new_layout_classes_and_tags():
    from apps.core.richtext import sanitize_page

    out = sanitize_page(
        '<figure class="sf-img-md sf-float-right evil"><img src="/media/pages/a.webp" '
        'alt="Teeladen" class="x"><figcaption>Unser Laden</figcaption></figure>'
        '<p class="sf-justify">Text</p><h4 class="sf-right">Klein</h4><hr>'
        '<blockquote class="sf-center">Zitat</blockquote><li class="sf-left">x</li>'
    )
    assert '<figure class="sf-img-md sf-float-right">' in out
    assert '<img src="/media/pages/a.webp" alt="Teeladen">' in out
    assert "<figcaption>Unser Laden</figcaption>" in out
    assert '<p class="sf-justify">' in out and '<h4 class="sf-right">' in out
    assert "<hr>" in out and '<blockquote class="sf-center">' in out


@pytest.mark.parametrize(
    "dirty",
    [
        '<img src="/media/a.webp" onerror="alert(1)">',
        '<p style="position:fixed">x</p>',
        '<a href="javascript:alert(1)">x</a>',
        "<svg><script>alert(1)</script></svg>",
        '<figure class="sf-img-md\nevil"><img src="/media/a.webp"></figure>',
        '<img src="//evil.example/a.png">',
        '<img src="/media/..%2fsecret">',
        '<a href="data:text/html,x">x</a>',
        '<img src="/media/a.webp" loading="eager">',
    ],
)
def test_page_sanitizer_drops_dangerous_input(dirty):
    from apps.core.richtext import sanitize_page

    out = sanitize_page(dirty)
    for bad in ("onerror", "style=", "javascript:", "<script", "evil", "loading", "data:", "%2f"):
        assert bad not in out


def test_class_groups_are_mutually_exclusive_and_alt_is_capped():
    from apps.core.richtext import ALT_MAX, sanitize_page

    out = sanitize_page(
        '<figure class="sf-img-sm sf-img-full sf-float-left sf-float-right">'
        f'<img src="/media/a.webp" alt="{"x" * (ALT_MAX + 50)}"></figure>'
        '<figure><img src="/media/b.webp" alt=""><figcaption> </figcaption></figure>'
    )
    assert 'class="sf-img-full sf-float-right"' in out
    assert 'alt="' + "x" * ALT_MAX + '"' in out and "x" * (ALT_MAX + 1) not in out
    assert "<figcaption>" not in out  # пустая подпись — не элемент


def test_every_page_tag_counts_as_rich():
    from apps.core.richtext import PAGE_ALLOWED_TAGS, clean_page_input, is_rich

    for tag in PAGE_ALLOWED_TAGS:
        assert is_rich(f"<{tag}>"), tag
    # текст только с <hr> — не «плоский» (иначе показался бы буквами «&lt;hr&gt;»)
    assert clean_page_input("Oben<hr>Unten<script>x</script>") == "Oben<hr>Unten"


def test_editor_gets_rules_from_the_sanitizer_source():
    """Паритет: JS редактора берёт теги/классы из richtext.editor_rules (json_script),
    своих списков в шаблоне нет."""
    import re
    from pathlib import Path

    from django.template import Context, Template

    from apps.core import richtext

    js = Path("templates/catalog/_richtext_editor.html").read_text()
    assert "{% rte_rules_json %}" in js and "RULES.cls" in js and "RULES.rich" in js
    assert "PAGE_TAGS = { H2" not in js and "sf-(?:grid|center" not in js
    html = Template("{% load richtext %}{% rte_rules_json %}").render(Context())
    assert 'id="rte-rules"' in html
    rules = richtext.editor_rules()
    assert set(rules["pageTags"]) >= {"FIGCAPTION", "HR", "H4", "FIGURE", "IMG"}
    # регулярка классов из Python — валидна и для JS (без lookbehind/флагов Python)
    assert re.fullmatch(rules["cls"], "sf-img-md") and not re.fullmatch(rules["cls"], "sf-x")


def test_page_mode_render_wraps_in_page_body_scope():
    from django.template import Context, Template

    out = Template("{% load richtext %}{% rich_block t mode='page' %}").render(
        Context(
            {
                "t": '<figure class="sf-float-left sf-img-sm"><img src="/media/a.webp" alt="A"></figure>'
            }
        )
    )
    assert 'class="rich-text sf-page-body"' in out and "sf-float-left" in out


def test_page_css_is_scoped_and_safe():
    """security-review: классы страниц стилизуются только внутри тела страницы и без
    position/vw (пользовательский HTML не выходит из своей колонки)."""
    from pathlib import Path

    css = Path("static/src/app.css").read_text()
    block = css.split("/* M21.10: разметка страниц", 1)[1].split("*/", 1)[1]
    assert "position" not in block and "vw" not in block
    for line in block.splitlines():
        if "{" in line and not line.strip().startswith(("@media", "/*")):
            assert ".sf-page-body" in line or ".rich-text" in line, line
