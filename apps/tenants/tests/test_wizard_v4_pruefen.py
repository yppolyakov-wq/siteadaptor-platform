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


def test_too_many_ticked_rows_are_refused_not_cut():
    from apps.catalog.models import Product

    owner = Owner(_v4())
    owner("post", {"action": "offer_preview", "kind": "waren", "offer_text": "A — 1"})
    rows = [{"on": "1", "name": f"Artikel {i}", "price": "1"} for i in range(80)]
    owner("post", _confirm_data(owner, rows))
    assert Product.objects.count() == 0 and any("50" in m for m in owner.messages)


def test_forged_low_row_count_does_not_hide_ticked_rows():
    from apps.catalog.models import Product

    owner = Owner(_v4())
    owner("post", {"action": "offer_preview", "kind": "waren", "offer_text": "A — 1"})
    data = _confirm_data(owner, [{"on": "1", "name": f"A{i}", "price": "1"} for i in range(3)])
    data["row_count"] = "1"
    owner("post", data)
    assert Product.objects.count() == 3


def test_failing_row_is_reported_and_others_are_created(monkeypatch):
    from django.db import DatabaseError

    from apps.catalog.models import Product

    owner = Owner(_v4())
    owner("post", {"action": "offer_preview", "kind": "waren", "offer_text": "A — 1"})
    real = offer_batch._create

    def flaky(tenant, kind, line):
        if line.name == "A2":
            raise DatabaseError("value too long")
        real(tenant, kind, line)

    monkeypatch.setattr(offer_batch, "_create", flaky)
    rows = [{"on": "1", "name": f"A{i}", "price": "1"} for i in range(4)]
    owner("post", _confirm_data(owner, rows))
    assert Product.objects.count() == 3
    assert any("A2" in m and "Übersprungen: 1" in m for m in owner.messages)


def test_nothing_ticked_keeps_draft_and_says_so():
    owner = Owner(_v4())
    owner("post", {"action": "offer_preview", "kind": "waren", "offer_text": "A — 1"})
    owner("post", _confirm_data(owner, [{"name": "A", "price": "1"}]))
    assert offer_batch.SESSION_KEY in owner.session and owner.messages


def test_all_skipped_keeps_draft_and_writes_no_batch():
    from apps.catalog.models import Product

    Product.objects.create(name={"de": "Brot"}, base_price=3)
    tenant = _v4()
    owner = Owner(tenant)
    owner("post", {"action": "offer_preview", "kind": "waren", "offer_text": "Brot — 3"})
    owner("post", _confirm_data(owner, [{"on": "1", "name": "Brot", "price": "3"}]))
    tenant.refresh_from_db()
    assert offer_batch.SESSION_KEY in owner.session
    assert not tenant.site_config["onboarding"].get("offer_batches")


def test_replay_clears_draft_and_says_already_added():
    owner = Owner(_v4())
    owner("post", {"action": "offer_preview", "kind": "waren", "offer_text": "Brot — 3"})
    data = _confirm_data(owner, [{"on": "1", "name": "Brot", "price": "3"}])
    session = dict(owner.session)
    owner("post", data)
    owner.session = session
    owner("post", data)
    assert offer_batch.SESSION_KEY not in owner.session
    assert any("Schon angelegt: 1" in m for m in owner.messages)


def test_batch_ring_survives_later_wizard_steps():
    tenant = _v4()
    owner = Owner(tenant)
    owner("post", {"action": "offer_preview", "kind": "waren", "offer_text": "Brot — 3"})
    owner("post", _confirm_data(owner, [{"on": "1", "name": "Brot", "price": "3"}]))
    stale = type(tenant).objects.get(pk=tenant.pk)
    stale.site_config = {**stale.site_config, "onboarding": {"v": 2, "flow": "v4"}}
    onboarding.save_state(stale, onboarding.get_state(stale))  # запрос со старым тенантом
    onboarding.advance(type(tenant).objects.get(pk=tenant.pk))
    tenant.refresh_from_db()
    assert tenant.site_config["onboarding"]["offer_batches"]


def test_staff_member_needs_settings_permission(monkeypatch):
    from apps.booking.models import Resource, Service
    from apps.core import permissions

    real = permissions.has_perm
    monkeypatch.setattr(
        permissions, "has_perm", lambda user, key: key != "einstellungen.edit" and real(user, key)
    )
    owner = Owner(_v4(business_type="friseur"))
    owner("post", {"action": "offer_preview", "kind": "termine", "offer_text": "S — 30 Min — 2"})
    rows = [{"on": "1", "name": "Schnitt", "duration": "30", "price": "25"}]
    owner("post", _confirm_data(owner, rows))
    assert Service.objects.count() == 1 and not Resource.objects.exists()
    assert any("Mitarbeiter" in m for m in owner.messages)


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


def _png():
    import io

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "blue").save(buf, "PNG")
    return SimpleUploadedFile("zimmer.png", buf.getvalue(), content_type="image/png")


def test_rooms_get_created_and_a_photo_makes_them_ready(settings, tmp_path):
    from apps.core import readiness
    from apps.stays.models import StayUnit

    settings.MEDIA_ROOT = str(tmp_path)
    tenant = _v4(business_type="hotel")
    owner = Owner(tenant)
    owner("post", {"action": "offer_preview", "kind": "zimmer", "offer_text": "DZ — 89 €"})
    owner("post", _confirm_data(owner, [{"on": "1", "name": "DZ", "guests": "2", "price": "89"}]))
    unit = StayUnit.objects.get()
    assert unit.max_guests == 2 and unit.price_cents == 8900
    html = owner().content.decode()
    assert "data-pruefen-photo" in html and 'enctype="multipart/form-data"' in html
    readiness.invalidate(tenant)
    assert readiness.is_done(tenant, "zimmer.room") is False
    owner("post", {"action": "offer_photo", "unit": str(unit.pk), "photo": _png()})
    unit.refresh_from_db()
    assert unit.images and any("Foto gespeichert" in m for m in owner.messages)
    readiness.invalidate(tenant)
    assert readiness.is_done(tenant, "zimmer.room") is True


def test_broken_photo_is_reported_not_swallowed(settings, tmp_path):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.stays.models import StayUnit
    from apps.stays.photos import add_unit_photos

    settings.MEDIA_ROOT = str(tmp_path)
    unit = StayUnit.objects.create(name="DZ", price_cents=8900)
    saved, failed = add_unit_photos(unit, [SimpleUploadedFile("x.png", b"nope")])
    assert saved == 0 and failed
    tenant = _v4(business_type="hotel", slug="ph")
    owner = Owner(tenant)
    owner(
        "post",
        {
            "action": "offer_photo",
            "unit": str(unit.pk),
            "photo": SimpleUploadedFile("x.png", b"nope"),
        },
    )
    unit.refresh_from_db()
    assert not unit.images and owner.messages


def test_other_type_asks_how_you_sell_and_enables_only_what_was_ticked():
    from apps.core import directions

    tenant = _v4(business_type="other", disabled_modules=["booking", "events", "stays", "jobs"])
    owner = Owner(tenant)
    html = owner().content.decode()
    assert (
        "data-pruefen-directions" in html
        and "open" in html.split("data-pruefen-directions")[0][-40:]
    )
    owner("post", {"action": "offer_directions", "direction": ["waren", "termine"]})
    tenant.refresh_from_db()
    assert "booking" not in tenant.disabled_modules and "stays" in tenant.disabled_modules
    assert directions.is_active(tenant, "termine")
    assert offer_batch.offer_kinds(tenant, owner.user)[:2] == ["waren", "termine"]
    # Снятая галочка модуль не выключает.
    owner("post", {"action": "offer_directions", "direction": ["waren"]})
    tenant.refresh_from_db()
    assert "booking" not in tenant.disabled_modules


def test_waren_choice_does_not_open_online_ordering():
    tenant = _v4(business_type="other", slug="ow", disabled_modules=["orders"])
    owner = Owner(tenant)
    owner("post", {"action": "offer_directions", "direction": ["waren"]})
    tenant.refresh_from_db()
    assert "orders" in tenant.disabled_modules
    assert "waren" in offer_batch.offer_kinds(tenant, owner.user)


def test_bakery_shows_directions_collapsed():
    owner = Owner(_v4(slug="bk"))
    html = owner().content.decode()
    head = html.split("data-pruefen-directions")[0][-60:]
    assert "data-pruefen-directions" in html and " open" not in head


def test_directions_need_functions_permission(monkeypatch):
    from apps.core import permissions

    real = permissions.has_perm
    monkeypatch.setattr(
        permissions, "has_perm", lambda user, key: key != "funktionen.edit" and real(user, key)
    )
    tenant = _v4(business_type="other", slug="np", disabled_modules=["booking"])
    owner = Owner(tenant)
    owner("post", {"action": "offer_directions", "direction": ["termine"]})
    tenant.refresh_from_db()
    assert "booking" in tenant.disabled_modules


# --- W4-6b: Handwerk — «Leistungen auf Anfrage» -------------------------------------------


def _handwerker():
    tenant = _v4(business_type="handwerker", slug="hw")
    tenant.enabled_modules = list({*(tenant.enabled_modules or []), "jobs"})
    tenant.save(update_fields=["enabled_modules"])
    return tenant


def test_handwerker_gets_anfragen_input_not_nothing_to_enter():
    owner = Owner(_handwerker())
    html = owner().content.decode()
    assert "data-pruefen-none" not in html and "data-pruefen-form" in html
    assert 'value="anfragen"' in html


def test_anfragen_lines_become_request_products_with_optional_price():
    from apps.catalog.models import Product

    owner = Owner(_handwerker())
    text = "Dachreparatur — auf Anfrage\nRinnenreinigung — 89"
    owner("post", {"action": "offer_preview", "kind": "anfragen", "offer_text": text})
    rows = [
        {"on": "1", "name": "Dachreparatur", "price": ""},
        {"on": "1", "name": "Rinnenreinigung", "price": "89"},
    ]
    data = _confirm_data(owner, rows)
    owner("post", data)
    got = {p.name["de"]: p for p in Product.objects.all()}
    assert set(got) == {"Dachreparatur", "Rinnenreinigung"}, owner.messages
    assert all(p.primary_action == "request" for p in got.values())
    assert got["Dachreparatur"].price_on_request and not got["Rinnenreinigung"].price_on_request
    owner("post", data)  # повтор той же пачки — без дублей
    assert Product.objects.count() == 2


def test_without_jobs_there_is_no_anfragen_input(monkeypatch):
    from apps.tenants.models import Tenant

    tenant = _v4(business_type="handwerker", slug="hw2")
    real = Tenant.is_module_active
    monkeypatch.setattr(Tenant, "is_module_active", lambda self, k: k != "jobs" and real(self, k))
    from apps.core import modules

    real_mod = modules.is_module_active
    monkeypatch.setattr(modules, "is_module_active", lambda t, k: k != "jobs" and real_mod(t, k))
    user = get_user_model().objects.create_user(username="x-hw2", password="pw12345678")
    Membership.objects.create(user=user, role=Membership.ROLE_OWNER)
    assert "anfragen" not in offer_batch.offer_kinds(tenant, user)
