"""A6 RT4: блог/новости — публичный список/деталь + кабинет CRUD."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory

from apps.events import public_views, views
from apps.events.models import BlogPost
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _pub(method="get", data=None):
    request = getattr(RequestFactory(), method)("/blog/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(name="Waldlicht")
    return request


def _cab(method="get", data=None):
    request = getattr(RequestFactory(), method)("/dashboard/events/blog/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    return request


def _post(**kw):
    kw.setdefault("title", "Hallo Welt")
    kw.setdefault("slug", "hallo-welt")
    kw.setdefault("is_published", True)
    return BlogPost.objects.create(**kw)


# --- публичные страницы -----------------------------------------------------------
def test_blog_index_lists_published_only():
    _post(title="Live", slug="live", is_published=True)
    _post(title="Entwurf", slug="entwurf", is_published=False)
    body = public_views.blog_index(_pub()).content.decode()
    assert "Live" in body and "Entwurf" not in body


def test_blog_detail_renders_published():
    _post(title="Atemübungen", slug="atem", body="Ein und aus.", is_published=True)
    body = public_views.blog_detail(_pub(), slug="atem").content.decode()
    assert "Atemübungen" in body and "Ein und aus." in body


def test_blog_detail_404_for_draft():
    _post(title="Geheim", slug="geheim", is_published=False)
    with pytest.raises(Http404):
        public_views.blog_detail(_pub(), slug="geheim")


# --- кабинет ----------------------------------------------------------------------
def test_cabinet_create_post_slugifies_and_publishes():
    resp = views.blog_list(
        _cab("post", {"title": "Mein Erster Post", "body": "Text", "publish": "on"})
    )
    assert resp.status_code == 302
    post = BlogPost.objects.get(title="Mein Erster Post")
    assert post.slug == "mein-erster-post"
    assert post.is_published and post.published_at is not None


def test_cabinet_create_post_unique_slug_collision():
    _post(title="X", slug="mein-post")
    views.blog_list(_cab("post", {"title": "Mein Post"}))
    slugs = set(BlogPost.objects.values_list("slug", flat=True))
    assert "mein-post" in slugs and "mein-post-2" in slugs


def test_cabinet_edit_saves_and_publishes():
    post = _post(title="Draft", slug="draft", is_published=False)
    views.blog_edit(
        _cab("post", {"action": "save", "title": "Final", "body": "Body", "publish": "on"}),
        pk=post.pk,
    )
    post.refresh_from_db()
    assert post.title == "Final" and post.is_published and post.published_at is not None


def test_cabinet_delete_post():
    post = _post()
    views.blog_edit(_cab("post", {"action": "delete"}), pk=post.pk)
    assert not BlogPost.objects.filter(pk=post.pk).exists()


# --- CM-1: блог — свой модуль (first-class для всех архетипов) -----------------


def test_blog_is_registered_module_recommended_everywhere():
    """CM-1: модуль "blog" в реестре, не-core/не-premium, recommended у ВСЕХ
    типов (активен из коробки, тумблер на «Module»); гейтит кабинет И витрину."""
    from apps.core import modules

    spec = next(s for s in modules.REGISTRY if s.key == "blog")
    assert not spec.core and not spec.premium
    from apps.tenants.models import Tenant

    assert set(spec.recommended_for) == {k for k, _l in Tenant.BUSINESS_TYPES}
    assert "/dashboard/blog/" in spec.url_prefixes and "/blog/" in spec.url_prefixes
    assert modules.module_for_path("/blog/mein-post/").key == "blog"
    assert modules.module_for_path("/dashboard/blog/").key == "blog"


def test_blog_module_active_by_default_and_disableable():
    from apps.core import modules

    tenant = TenantFactory.build(name="X")
    assert modules.is_module_active(tenant, "blog") is True  # из коробки
    tenant.disabled_modules = ["blog"]
    assert modules.is_module_active(tenant, "blog") is False  # тумблер работает


def test_sitemap_includes_published_blog_posts():
    """CM-1/SEO: published-посты и /blog/ в sitemap (draft — нет)."""
    from apps.promotions import public_views as promo_public

    BlogPost.objects.create(title="Sichtbar", slug="sichtbar", is_published=True)
    BlogPost.objects.create(title="Entwurf", slug="entwurf", is_published=False)
    request = RequestFactory().get("/sitemap.xml")
    request.tenant = TenantFactory.build(name="X")
    xml = promo_public.sitemap_xml(request).content.decode()
    assert "/blog/sichtbar/" in xml and "/blog/</loc>" in xml
    assert "entwurf" not in xml


def test_blog_detail_emits_blogposting_jsonld():
    from django.utils import timezone

    post = BlogPost.objects.create(
        title="Herbst-Pflege",
        slug="herbst-pflege",
        excerpt="Drei Tipps.",
        is_published=True,
        published_at=timezone.now(),
    )
    body = public_views.blog_detail(_pub(), slug=post.slug).content.decode()
    assert '"@type":"BlogPosting"' in body and "Herbst-Pflege" in body
