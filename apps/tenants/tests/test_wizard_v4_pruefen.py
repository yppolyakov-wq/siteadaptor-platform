"""AIS-W W4-2 срез 2: шаг v4 «Angebot prüfen» — проверка строк и создание пачкой."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import offer_batch
from apps.core import views as core_views
from apps.core.models import Membership
from apps.tenants import onboarding
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
V4 = {"onboarding": {"v": 2, "flow": "v4"}}


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


class Owner:
    """Один владелец с одной сессией на несколько запросов (черновик живёт в сессии)."""

    def __init__(self, tenant, role=Membership.ROLE_OWNER):
        self.tenant = tenant
        tag = uuid.uuid4().hex[:8]
        self.user = get_user_model().objects.create_user(
            username=f"o-{tag}",
            email=f"o-{tag}@test.de",
            password="pw12345678",
            first_name="Anna",
            last_name="Muster",
        )
        Membership.objects.create(user=self.user, role=role)
        self.session = None
        self.messages = []

    def __call__(self, method="get", data=None):
        request = getattr(RequestFactory(), method)("/dashboard/setup/", data or {})
        SessionMiddleware(lambda r: None).process_request(request)
        if self.session is not None:
            request.session.update(self.session)
        MessageMiddleware(lambda r: None).process_request(request)
        request.tenant = self.tenant
        request.user = self.user
        response = core_views.setup_view(request)
        self.session = dict(request.session.items())
        self.messages = [str(m) for m in get_messages(request)]
        return response


def _v4(**kw):
    kw.setdefault("schema_name", "public")
    kw.setdefault("slug", "pr")
    kw.setdefault("business_type", "bakery")
    kw.setdefault("site_config", dict(V4))
    tenant = TenantFactory(published_at=None, **kw)
    onboarding.goto(tenant, "pruefen")
    return tenant


def _confirm_data(owner, rows):
    data = {"action": "offer_confirm", "batch": owner.session[offer_batch.SESSION_KEY]["batch"]}
    data["row_count"] = str(len(rows))
    for i, row in enumerate(rows):
        for key, value in row.items():
            data[f"row_{i}_{key}"] = value
    return data


def test_v4_rail_uses_pruefen_and_v3_keeps_offer():
    tenant = TenantFactory.build(business_type="bakery", site_config=dict(V4), published_at=None)
    assert onboarding.visible_keys(tenant) == ["company", "pruefen", "recht", "done"]
    v3 = TenantFactory.build(business_type="bakery")
    assert "offer" in onboarding.visible_keys(v3) and "pruefen" not in onboarding.visible_keys(v3)


def test_preview_creates_nothing_and_shows_table():
    from apps.catalog.models import Product

    owner = Owner(_v4())
    owner("post", {"action": "offer_preview", "kind": "waren", "offer_text": "Brot — 3,50\nX"})
    assert Product.objects.count() == 0
    html = owner().content.decode()
    assert "data-pruefen-review" in html and "data-pruefen-error" in html
    assert 'name="row_0_name" value="Brot"' in html


def test_examples_fill_text_only():
    from apps.catalog.models import Product

    owner = Owner(_v4())
    owner("post", {"action": "offer_examples", "kind": "waren"})
    assert Product.objects.count() == 0
    assert "Roggenbrot" in owner().content.decode()


def test_confirm_creates_valid_rows_once_even_on_double_submit():
    from apps.catalog.models import Product

    tenant = _v4()
    owner = Owner(tenant)
    owner("post", {"action": "offer_preview", "kind": "waren", "offer_text": "Brot — 3,50"})
    rows = [
        {"on": "1", "name": "Brot", "price": "3,50"},
        {"on": "1", "name": "Torte", "price": ""},  # подделка/правка: без цены → skipped
        {"name": "Kuchen", "price": "2"},  # не отмечена
    ]
    data = _confirm_data(owner, rows)
    session = dict(owner.session)
    owner("post", data)
    assert list(Product.objects.values_list("base_price", flat=True)) == [pytest.approx(3.5)]
    assert any("Angelegt: 1" in m and "Torte" in m for m in owner.messages)
    product = Product.objects.get()
    assert product.slug and str(product.vat_rate) == "7.00"  # еда: 7 %
    owner.session = session  # вторая вкладка / двойной клик с прежней сессией
    owner("post", data)
    assert Product.objects.count() == 1


def test_stale_batch_creates_nothing():
    from apps.catalog.models import Product

    owner = Owner(_v4())
    owner("post", {"action": "offer_preview", "kind": "waren", "offer_text": "Brot — 3"})
    data = _confirm_data(owner, [{"on": "1", "name": "Brot", "price": "3"}])
    data["batch"] = "alt"
    owner("post", data)
    assert Product.objects.count() == 0 and owner.messages


def test_existing_name_is_skipped():
    from apps.catalog.models import Product

    Product.objects.create(name={"de": "Brot"}, base_price=3)
    owner = Owner(_v4())
    owner("post", {"action": "offer_preview", "kind": "waren", "offer_text": "brot — 4"})
    owner("post", _confirm_data(owner, [{"on": "1", "name": "brot", "price": "4"}]))
    assert Product.objects.count() == 1
    assert any("gibt es schon" in m for m in owner.messages)


def test_too_many_rows_are_capped():
    from apps.catalog.models import Product

    owner = Owner(_v4())
    owner("post", {"action": "offer_preview", "kind": "waren", "offer_text": "A — 1"})
    rows = [{"on": "1", "name": f"Artikel {i}", "price": "1"} for i in range(80)]
    owner("post", _confirm_data(owner, rows))
    assert Product.objects.count() == 50


def test_db_failure_rolls_back_whole_batch(monkeypatch):
    from apps.catalog.models import Product

    owner = Owner(_v4())
    owner("post", {"action": "offer_preview", "kind": "waren", "offer_text": "A — 1"})
    calls = []
    real = offer_batch._create

    def flaky(tenant, kind, line):
        calls.append(line.name)
        if len(calls) == 3:
            raise RuntimeError("db down")
        real(tenant, kind, line)

    monkeypatch.setattr(offer_batch, "_create", flaky)
    rows = [{"on": "1", "name": f"A{i}", "price": "1"} for i in range(4)]
    owner("post", _confirm_data(owner, rows))
    assert Product.objects.count() == 0
    assert any("Nichts angelegt" in m for m in owner.messages)
    assert offer_batch.SESSION_KEY in owner.session  # черновик цел — можно повторить


def test_termine_creates_service_and_one_staff_named_after_owner():
    from apps.booking.availability import service_pool
    from apps.booking.models import Resource, Service

    owner = Owner(_v4(business_type="friseur"))
    owner("post", {"action": "offer_preview", "kind": "termine", "offer_text": "S — 30 Min — 25"})
    rows = [{"on": "1", "name": "Schnitt", "duration": "30", "price": "25"}]
    owner("post", _confirm_data(owner, rows))
    service = Service.objects.get()
    assert service.duration_minutes == 30 and service.price_cents == 2500
    staff = Resource.objects.get(type=Resource.TYPE_STAFF)
    assert staff.name == "Anna Muster" and list(service_pool(service))
    owner("post", {"action": "offer_preview", "kind": "termine", "offer_text": "F — 60 Min — 60"})
    rows = [{"on": "1", "name": "Färben", "duration": "60", "price": "60"}]
    owner("post", _confirm_data(owner, rows))
    assert Resource.objects.filter(type=Resource.TYPE_STAFF).count() == 1


def test_staff_without_permission_cannot_confirm():
    from apps.catalog.models import Product

    owner = Owner(_v4(), role="nobody")
    owner("post", {"action": "offer_preview", "kind": "waren", "offer_text": "Brot — 3"})
    assert offer_batch.SESSION_KEY not in owner.session
    assert Product.objects.count() == 0


def test_onboarding_key_survives_normalize_and_keeps_other_keys():
    from apps.tenants import siteconfig

    tenant = _v4(site_config={**V4, "seo": {"allow_ai": False}})
    owner = Owner(tenant)
    owner("post", {"action": "offer_preview", "kind": "waren", "offer_text": "Brot — 3"})
    owner("post", _confirm_data(owner, [{"on": "1", "name": "Brot", "price": "3"}]))
    tenant.refresh_from_db()
    assert tenant.site_config["seo"] == {"allow_ai": False}
    normalized = siteconfig.normalize(tenant.site_config)
    assert normalized["onboarding"]["offer_batches"]
