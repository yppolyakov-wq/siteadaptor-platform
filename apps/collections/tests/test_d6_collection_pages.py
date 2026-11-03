"""UX-D D6.3: Kollektionen — строки с количествами, «＋» шторкой, страница с вкладками."""

import json
import re
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.http import Http404
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext

from apps.catalog.tests.factories import ProductFactory
from apps.collections import pages, views
from apps.collections.models import Collection
from apps.core.models import Membership
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(path="/dashboard/collections/", method="get", data=None, drawer=False):
    extra = {"HTTP_X_SF_DRAWER": "1"} if drawer else {}
    req = getattr(RequestFactory(), method)(path, data or {}, **extra)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    tag = uuid.uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(username=f"u-{tag}", password="pw12345678")
    Membership.objects.get_or_create(user=req.user, defaults={"role": Membership.ROLE_OWNER})
    req.tenant = TenantFactory.build(business_type="clothing", disabled_modules=[])
    return req


def _page(col, **kw):
    return pages.collection_edit(_req(f"/dashboard/collections/{col.pk}/", **kw), pk=col.pk)


def test_list_rows_with_counts_and_no_checkboxes():
    col = Collection.objects.create(name="Herbst", slug="herbst")
    col.products.add(ProductFactory(), ProductFactory())
    html = views.collections_view(_req()).content.decode()
    rows = re.findall(r"<a [^>]*data-collection-row>.*?</a>", html, re.S)
    assert len(rows) == 1 and "<input" not in rows[0]
    assert "2 Produkte" in rows[0] or "2 " in rows[0]
    assert 'name="products"' not in html
    assert re.search(r'<a href="/dashboard/collections/neu/" data-drawer', html)


def test_list_query_count_does_not_grow_with_collections():
    def run():
        with CaptureQueriesContext(connection) as ctx:
            views.collections_view(_req())
        return len(ctx.captured_queries)

    Collection.objects.create(name="A", slug="a")
    run()  # прогрев
    few = run()
    for i in range(6):
        Collection.objects.create(name=f"B{i}", slug=f"b{i}")
    assert run() <= few


def test_new_in_drawer_navigates_to_content_tab():
    resp = pages.collection_new(
        _req(
            "/dashboard/collections/neu/",
            "post",
            {"name": "Damen", "next": "/dashboard/collections/"},
            drawer=True,
        )
    )
    col = Collection.objects.get()
    data = json.loads(resp.content)
    assert (
        data["navigate"] is True
        and data["location"] == f"/dashboard/collections/{col.pk}/?tab=inhalt"
    )


def test_new_empty_name_is_an_error_at_the_field():
    resp = pages.collection_new(
        _req("/dashboard/collections/neu/", "post", {"name": " "}, drawer=True)
    )
    assert 'id="col-new-name-err"' in resp.content.decode() and not Collection.objects.exists()


def test_content_tab_keeps_members_not_shown():
    col = Collection.objects.create(name="Herbst", slug="herbst")
    shown, hidden = ProductFactory(), ProductFactory(is_active=False)
    col.products.add(shown, hidden)
    html = _page(col, data={"tab": "inhalt"}).content.decode()
    assert f'name="products_shown" value="{shown.pk}"' in html
    assert "bleiben erhalten: 1" in html
    _page(
        col,
        method="post",
        data={
            "action": "members",
            "collection": str(col.pk),
            "products_present": "1",
            "products_shown": [str(shown.pk)],
        },
    )
    assert set(col.products.all()) == {hidden}


def test_basis_tab_rename_and_garbage_order():
    col = Collection.objects.create(name="Herbst", slug="herbst", sort_order=3)
    _page(
        col,
        method="post",
        data={"action": "basis", "collection": str(col.pk), "name": "Winter", "sort_order": "²"},
    )
    col.refresh_from_db()
    assert (col.name, col.sort_order) == ("Herbst", 3)
    _page(
        col,
        method="post",
        data={"action": "basis", "collection": str(col.pk), "name": "Winter", "sort_order": "5"},
    )
    col.refresh_from_db()
    assert (col.name, col.sort_order, col.slug) == ("Winter", 5, "herbst")  # slug стабилен


def test_foreign_pk_in_post_is_404():
    col = Collection.objects.create(name="A", slug="a")
    other = Collection.objects.create(name="B", slug="b")
    with pytest.raises(Http404):
        _page(col, method="post", data={"action": "delete", "collection": str(other.pk)})
    assert Collection.objects.filter(pk=other.pk).exists()


def test_toggle_is_explicit_and_delete_has_confirmation():
    col = Collection.objects.create(name="A", slug="a")
    for _i in range(2):
        _page(
            col, method="post", data={"action": "toggle", "collection": str(col.pk), "active": "0"}
        )
    col.refresh_from_db()
    assert col.is_active is False
    html = _page(col).content.decode()
    delete_form = html.split('value="delete"', 1)[1].split("</form>", 1)[0]
    assert 'data-danger="1"' in delete_form


def test_drawer_and_permissions():
    from apps.core import drawer, view_perms

    code = drawer.drawer_aware(lambda r: r).__code__
    chain = [pages.collection_new]
    while hasattr(chain[-1], "__wrapped__"):
        chain.append(chain[-1].__wrapped__)
    assert chain[-2].__code__ is code
    r = view_perms.RULES
    assert r["collections:new"] == r["collections:edit"] == r["collections:list"]
