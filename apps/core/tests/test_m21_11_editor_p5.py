"""M21.11 P5: пакет 🟢 редактора — серверная граница (белый список) и вспомогательные
эндпоинты (медиатека, цели ссылок)."""

import json

import pytest

from apps.core import content_page_views as views
from apps.core import richtext
from apps.core.models import MediaAsset, Membership
from apps.core.tests.test_m21_10_text_pages_hub import _req, _user

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def test_new_inline_tags_survive():
    html = "<p>a<s>b</s><strike>c</strike>m<sup>2</sup>H<sub>2</sub>O</p>"
    assert richtext.sanitize_page(html) == html


def test_paragraph_styles_are_exclusive_and_whitelisted():
    out = richtext.sanitize_page('<p class="sf-lead sf-note evil">x</p>')
    assert out == '<p class="sf-note">x</p>'


def test_button_gallery_and_faq():
    html = (
        '<p><a class="sf-btn" href="/seite/kontakt/">Los</a></p>'
        '<div class="sf-gallery"><figure><img src="/media/pages/a.png" alt="A"></figure></div>'
        "<details open><summary>Frage</summary><p>Antwort</p></details>"
        '<div class="sf-grid3"><div><p>1</p></div></div>'
    )
    out = richtext.sanitize_page(html)
    assert 'class="sf-btn"' in out and 'href="/seite/kontakt/"' in out
    assert 'class="sf-gallery"' in out and "<summary>Frage</summary>" in out
    assert "<details>" in out  # «open» — служебный атрибут редактора, не сохраняется
    assert 'class="sf-grid3"' in out


def test_link_and_attributes_still_blocked():
    out = richtext.sanitize_page(
        '<a class="sf-btn" href="javascript:alert(1)" onclick="x" style="color:red">x</a>'
        '<details ontoggle="alert(1)"><summary style="x">q</summary></details>'
    )
    assert "javascript" not in out and "onclick" not in out and "style" not in out
    assert "ontoggle" not in out


def test_descriptions_do_not_gain_page_tags():
    assert "<details>" not in richtext.sanitize("<details><summary>q</summary></details>")
    assert "<s>" not in richtext.sanitize("<s>x</s>")


def test_editor_rules_ship_new_tags_to_js():
    rules = richtext.editor_rules()
    for tag in ("S", "STRIKE", "SUP", "SUB", "DETAILS", "SUMMARY"):
        assert tag in rules["pageTags"]
    assert "A" in rules["classTags"]


def test_media_list_returns_only_our_images():
    MediaAsset.objects.create(path="pages/a.png", url="/media/pages/a.png", mime_type="image/png")
    MediaAsset.objects.create(path="x.pdf", url="/media/x.pdf", mime_type="application/pdf")
    MediaAsset.objects.create(path="e.png", url="https://evil.example/e.png", mime_type="image/png")
    data = json.loads(views.page_media_list(_req()).content)
    assert [i["url"] for i in data["items"]] == ["/media/pages/a.png"]


def test_media_list_needs_seiten_edit():
    from django.core.exceptions import PermissionDenied

    staff = _user(Membership.ROLE_STAFF)
    try:
        resp = views.page_media_list(_req(user=staff))
    except PermissionDenied:
        return
    assert resp.status_code == 403


def test_link_targets_are_local_urls():
    from apps.tenants import menu

    for item in menu.link_targets(_req().tenant):
        assert item["url"].startswith("/") and not item["url"].startswith("//")
        assert item["label"]
