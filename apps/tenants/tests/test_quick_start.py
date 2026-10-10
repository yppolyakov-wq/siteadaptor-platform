"""T-8.5 «Aktion in 3 Klicks»: регистрация + первая акция одной страницей.

План — docs/t8-5-quick-start-plan-2026-10-10.md §2.
"""

import json
import re
from importlib import import_module
from unittest import mock

import pytest
from django.conf import settings as dj_settings
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.core import mail, signing
from django.core.cache import cache
from django.db import connection
from django.http import Http404
from django.test import RequestFactory
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.aggregator import tasks as agg_tasks
from apps.aggregator.models import AggregatorListing
from apps.core import owner_login
from apps.core.models import Membership
from apps.promotions import quick
from apps.promotions.models import Promotion
from apps.tenants import quickstart, quickstart_views, tasks
from apps.tenants.models import Domain, Tenant
from apps.tenants.tests.factories import TenantFactory

EMAIL = "inhaber@krume.test"


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def _session(request):
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    MessageMiddleware(lambda r: None).process_request(request)
    return request


def _old_stamp(seconds=30):
    return signing.dumps(timezone.now().timestamp() - seconds, salt=quickstart.FORM_STAMP_SALT)


def _post_data(**kw):
    data = {
        "title": "Feierabendtüte",
        "new_price": "5",
        "old_price": "12",
        "term": "today",
        "customer_response": "reserve",
        "business_name": "Bäckerei Müller & Söhne",
        "business_type": "bakery",
        "city": "Solingen",
        "district": "",
        "email": EMAIL,
        "stamp": _old_stamp(),
    }
    data.update(kw)
    return data


def _post(data, ip="10.85.0.1"):
    request = _session(RequestFactory().post("/aktion-starten/", data))
    request.META["REMOTE_ADDR"] = ip
    return request


def _drop(tenant):
    Domain.objects.filter(tenant=tenant).delete()
    Tenant.objects.filter(pk=tenant.pk).delete()


# --- поддомен -----------------------------------------------------------------------


@pytest.mark.django_db
def test_slug_from_name_transliterates_and_stays_free():
    assert quickstart.suggest_slug("Bäckerei Müller & Söhne") == "baeckerei-mueller-soehne"
    assert quickstart.suggest_slug("Straße 7") == "strasse-7"
    assert quickstart.suggest_slug("") == "aktion"
    assert quickstart.suggest_slug("Admin") == "admin-2"  # резерв
    assert quickstart.suggest_slug("24/7 Kiosk") == "aktion-247-kiosk"
    long = quickstart.suggest_slug("Sehr " * 30)
    assert len(long) <= quickstart.SLUG_MAX and not long.endswith("-")
    TenantFactory(schema_name="krume", slug="krume")
    assert quickstart.suggest_slug("Krume") == "krume-2"


# --- страница -----------------------------------------------------------------------


@pytest.mark.django_db
def test_page_has_both_steps_in_dom_and_no_password():
    request = _session(RequestFactory().get("/aktion-starten/"))
    html = quickstart_views.quick_start(request).content.decode()
    assert 'data-qs-step="1"' in html and 'data-qs-step="2"' in html
    assert 'capture="environment"' in html
    assert 'name="business_name"' in html and 'name="email"' in html
    assert "password" not in html and 'name="slug"' not in html
    for key in ("reserve", "coupon", "show"):
        assert f'data-qs-response="{key}"' in html
    assert 'data-qs-response="buy"' not in html


@pytest.mark.django_db
def test_post_creates_lite_tenant_and_hands_off_token():
    with mock.patch("apps.tenants.tasks.provision_quick.delay"):
        response = quickstart_views.quick_start(request := _post(_post_data(district="wald")))
    tenant = Tenant.objects.get(slug="baeckerei-mueller-soehne")
    try:
        assert response.status_code == 302
        assert response.url == f"/aktion-starten/{tenant.slug}/"
        assert tenant.site_config.get("profile") == "aktionen"
        assert tenant.email_pending is True
        assert tenant.district == "wald" and tenant.city == "Solingen"
        assert tenant.owner_email == EMAIL
        assert tenant.trial_ends_at is None  # бесплатная ступень не истекает (Р-5)
        assert Domain.objects.filter(tenant=tenant, is_primary=True).exists()
        entry = request.session[quickstart_views.SESSION_KEY][tenant.slug]
        assert entry["title"] == "Feierabendtüte"
        assert owner_login.peek_token(tenant.schema_name, entry["token"]) == {"email": EMAIL}
    finally:
        _drop(tenant)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "data",
    [
        {"website": "spam.example"},  # honeypot
        {"stamp": ""},  # без метки времени
        {"stamp": "x"},  # подделка
    ],
)
def test_bots_create_nothing(data):
    stamp_now = signing.dumps(timezone.now().timestamp(), salt=quickstart.FORM_STAMP_SALT)
    for payload in (_post_data(**data), _post_data(stamp=stamp_now)):
        with mock.patch("apps.tenants.tasks.provision_quick.delay"):
            response = quickstart_views.quick_start(_post(payload))
        assert response.status_code == 200
    assert not Tenant.objects.filter(slug__startswith="baeckerei").exists()


@pytest.mark.django_db
def test_invalid_form_returns_errors_without_tenant():
    with mock.patch("apps.tenants.tasks.provision_quick.delay"):
        html = quickstart_views.quick_start(_post(_post_data(email="kein-mail", title=""))).content
    assert b"text-red-600" in html
    assert not Tenant.objects.filter(slug__startswith="baeckerei").exists()


# --- ожидание -----------------------------------------------------------------------


@pytest.mark.django_db
def test_waiting_redirects_with_token_only_when_promo_is_ready():
    with mock.patch("apps.tenants.tasks.provision_quick.delay"):
        quickstart_views.quick_start(request := _post(_post_data()))
    tenant = Tenant.objects.get(slug="baeckerei-mueller-soehne")
    try:
        get = _session(RequestFactory().get(f"/aktion-starten/{tenant.slug}/"))
        get.session = request.session
        html = quickstart_views.quick_waiting(get, slug=tenant.slug).content.decode()
        assert 'http-equiv="refresh"' in html and "Feierabendtüte" in html

        Tenant.objects.filter(pk=tenant.pk).update(provisioning_status=Tenant.PROVISIONING_READY)
        assert quickstart_views.quick_waiting(get, slug=tenant.slug).status_code == 200

        cache.set(f"quick_promo:{tenant.pk}", "abc", 60)
        response = quickstart_views.quick_waiting(get, slug=tenant.slug)
        token = request.session[quickstart_views.SESSION_KEY][tenant.slug]["token"]
        assert response.status_code == 302
        assert "baeckerei-mueller-soehne." in response.url
        assert f"/start/{token}/?next=%2Fpromotions%2Fabc%2Ffertig%2F" in response.url

        stranger = _session(RequestFactory().get(f"/aktion-starten/{tenant.slug}/"))
        response = quickstart_views.quick_waiting(stranger, slug=tenant.slug)
        assert response.url.endswith("/accounts/login/")  # чужой браузер — обычный вход
    finally:
        _drop(tenant)


# --- вход без пароля ----------------------------------------------------------------


@pytest.fixture
def owner(db):
    tenant = TenantFactory(schema_name="public", slug="krume", name="Krume")
    user = get_user_model().objects.create_user(username=EMAIL, email=EMAIL)
    user.set_unusable_password()
    user.save()
    Membership.objects.create(user=user, role=Membership.ROLE_OWNER)
    return tenant, user


def _tenant_request(method, path, tenant, data=None):
    rf = RequestFactory()
    request = rf.post(path, data or {}) if method == "post" else rf.get(path)
    _session(request)
    request.tenant = tenant
    request.user = mock.Mock(is_authenticated=False)
    return request


def test_owner_start_get_does_not_consume_post_logs_in(owner):
    tenant, user = owner
    token = owner_login.issue_token(connection.schema_name, EMAIL)
    html = owner_login.owner_start(
        _tenant_request("get", f"/start/{token}/?next=/promotions/x/fertig/", tenant), token
    ).content.decode()
    assert "data-owner-start" in html and 'value="/promotions/x/fertig/"' in html
    assert owner_login.peek_token(connection.schema_name, token)  # GET не расходует

    post = _tenant_request("post", f"/start/{token}/", tenant, {"next": "//evil.example/"})
    response = owner_login.owner_start(post, token)
    assert response.status_code == 302 and response.url == "/promotions/"
    assert post.session["_auth_user_id"] == str(user.pk)
    with pytest.raises(Http404):  # одноразовый
        owner_login.owner_start(_tenant_request("post", "/start/x/", tenant), token)


def test_owner_start_refuses_unknown_or_foreign_token(owner):
    tenant, _user = owner
    response = owner_login.owner_start(_tenant_request("get", "/start/nope/", tenant), "nope")
    assert response.status_code == 404
    foreign = owner_login.issue_token("andere_schema", EMAIL)
    with pytest.raises(Http404):
        owner_login.owner_start(_tenant_request("post", "/start/f/", tenant), foreign)


def test_login_link_answer_is_the_same_for_any_address(owner):
    tenant, _user = owner
    known = owner_login.owner_link_request(
        _tenant_request("post", "/anmelden/link/", tenant, {"email": EMAIL})
    ).content.decode()
    assert len(mail.outbox) == 1 and "/start/" in mail.outbox[0].body
    unknown = owner_login.owner_link_request(
        _tenant_request("post", "/anmelden/link/", tenant, {"email": "fremd@x.test"})
    ).content.decode()
    assert len(mail.outbox) == 1
    strip = re.compile(r"csrfmiddlewaretoken\" value=\"[^\"]+\"")
    assert strip.sub("", known) == strip.sub("", unknown)


# --- Р-3: каталог после подтверждения ----------------------------------------------


def test_pending_tenant_stays_out_of_city_catalog_until_confirmed(owner):
    tenant, _user = owner
    Tenant.objects.filter(pk=tenant.pk).update(email_pending=True)
    tenant.refresh_from_db()
    promo = Promotion.objects.create(status="active", title={"de": "Brötchen"})
    assert agg_tasks.sync_listing("public", str(promo.pk)) == "removed"
    assert not AggregatorListing.objects.filter(promo_uuid=promo.pk).exists()

    signed = owner_login.confirm_token(tenant, EMAIL)
    # T-8.6: подтверждение выкладывает ВСЮ схему (все виды), а не акции по одной.
    with mock.patch("django.db.transaction.on_commit", side_effect=lambda f: f()):
        with mock.patch("apps.aggregator.tasks.reconcile_aggregator_schema.delay") as delay:
            html = owner_login.owner_confirm_email(
                _tenant_request("get", "/start/bestaetigen/x/", tenant), signed
            ).content.decode()
    assert "data-owner-confirmed" in html
    tenant.refresh_from_db()
    assert tenant.email_pending is False
    delay.assert_called_once_with(tenant.schema_name)
    assert agg_tasks.sync_listing("public", str(promo.pk)) == "upserted"


def test_confirm_link_is_bound_to_its_tenant(owner):
    tenant, _user = owner
    signed = signing.dumps({"t": "fremd", "e": EMAIL}, salt=owner_login.CONFIRM_SALT)
    response = owner_login.owner_confirm_email(
        _tenant_request("get", "/start/bestaetigen/x/", tenant), signed
    )
    assert response.status_code == 404


# --- фоновое создание (настоящая схема) ---------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_provision_quick_builds_owner_promo_and_skips_wizard():
    from apps.tenants.services import start_quick_provisioning

    promo = {
        "title": "Feierabendtüte",
        "new_price": "5",
        "old_price": "12",
        "term": "today",
        "customer_response": "coupon",
        "images": [],
    }
    with mock.patch("apps.tenants.tasks.provision_quick.delay"):
        tenant = start_quick_provisioning(
            business_name="Krume Schnell",
            slug="krume-schnell",
            business_type="bakery",
            city="Solingen",
            district="",
            email=EMAIL,
            promo=promo,
        )
    try:
        with mock.patch("apps.aggregator.tasks.sync_aggregator_listing.delay"):
            pk = tasks.provision_quick_logic(tenant.pk, EMAIL, promo)
            again = tasks.provision_quick_logic(tenant.pk, EMAIL, promo)
        assert pk and again == pk
        tenant.refresh_from_db()
        assert tenant.provisioning_status == Tenant.PROVISIONING_READY
        assert tenant.site_config["onboarding"]["completed"] is True
        with tenant_context(tenant):
            owner = get_user_model().objects.get(username=EMAIL)
            assert not owner.has_usable_password()
            assert Membership.objects.get(user=owner).role == Membership.ROLE_OWNER
            promos = list(Promotion.objects.all())
            assert len(promos) == 1 and promos[0].status == "active"
            assert promos[0].metadata.get("response") == "coupon"
        confirm = [m for m in mail.outbox if "bestätigen" in m.subject]
        assert len(confirm) == 1 and "/start/bestaetigen/" in confirm[0].body
        assert not [m for m in mail.outbox if "bereit" in m.subject]
    finally:
        with connection.cursor() as cur:
            cur.execute(f'DROP SCHEMA IF EXISTS "{tenant.schema_name}" CASCADE')
        _drop(tenant)


def test_links_build_from_celery_public_urlconf(owner, settings):
    """Стенд: письмо подтверждения уходит из Celery, где urlconf публичный."""
    tenant, _user = owner
    settings.ROOT_URLCONF = "config.urls_public"
    from django.urls import clear_url_caches

    clear_url_caches()
    try:
        assert "/start/bestaetigen/" in owner_login.confirm_url(tenant, EMAIL)
        owner_login.send_login_link(tenant, EMAIL)
        assert "/start/" in mail.outbox[-1].body
    finally:
        clear_url_caches()


# --- T-8.5b: свой адрес + проверка, несколько фото ----------------------------------


@pytest.mark.django_db
def test_slug_helpers_normalize_and_refuse():
    assert quickstart.normalize_slug("  Meine Bäckerei!! ") == "meine-baeckerei"
    assert quickstart.slug_problem("ab")  # коротко
    assert quickstart.slug_problem("7-tage")  # схема Postgres начинается с буквы
    assert quickstart.slug_problem("admin")  # резерв
    assert quickstart.slug_problem("adresse")  # путь самой страницы
    assert quickstart.slug_problem("meine-baeckerei") == ""
    TenantFactory(schema_name="belegt", slug="belegt")
    assert quickstart.slug_problem("belegt")


@pytest.mark.django_db
def test_slug_taken_by_portal_domain():
    """Портал города живёт на своём Domain: «solingen» нельзя отдать бизнесу."""
    public = TenantFactory(schema_name="portal_x", slug="portal-x")
    Domain.objects.create(domain=f"solingen.{quickstart.domain_base()}", tenant=public)
    assert quickstart.slug_problem("solingen")
    assert quickstart.suggest_slug("Solingen") == "solingen-2"


@pytest.mark.django_db
def test_chosen_subdomain_is_used_and_taken_one_is_refused():
    with mock.patch("apps.tenants.tasks.provision_quick.delay"):
        quickstart_views.quick_start(_post(_post_data(subdomain="Krume Hilden")))
    tenant = Tenant.objects.get(slug="krume-hilden")
    try:
        with mock.patch("apps.tenants.tasks.provision_quick.delay"):
            resp = quickstart_views.quick_start(
                _post(_post_data(subdomain="krume-hilden"), ip="10.85.0.9")
            )
        assert resp.status_code == 200 and b"schon vergeben" in resp.content
        assert Tenant.objects.filter(slug__startswith="krume-hilden").count() == 1
    finally:
        _drop(tenant)


@pytest.mark.django_db
def test_slug_check_endpoint():
    import json

    def ask(**params):
        request = RequestFactory().get("/aktion-starten/adresse/", params)
        request.META["REMOTE_ADDR"] = "10.85.1.1"
        return json.loads(quickstart_views.slug_check(request).content)

    assert ask(name="Café Rosé") == {"slug": "cafe-rose", "ok": True, "message": ""}
    free = ask(slug="Mein Laden")
    assert free["slug"] == "mein-laden" and free["ok"] is True
    TenantFactory(schema_name="mein_laden", slug="mein-laden")
    taken = ask(slug="mein-laden")
    assert taken["ok"] is False and taken["message"] and taken["suggestion"] == "mein-laden-2"


@pytest.mark.django_db
def test_post_with_several_photos_carries_all_to_the_task():
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    from apps.catalog.images import delete_stored_image

    def png():
        buf = BytesIO()
        Image.new("RGB", (8, 8), "blue").save(buf, "PNG")
        return SimpleUploadedFile("p.png", buf.getvalue(), content_type="image/png")

    data = _post_data()
    data["photo"] = [png(), png()]
    with mock.patch("apps.tenants.tasks.provision_quick.delay") as delay:
        with mock.patch("django.db.transaction.on_commit", side_effect=lambda f: f()):
            quickstart_views.quick_start(_post(data))
    tenant = Tenant.objects.get(slug="baeckerei-mueller-soehne")
    try:
        images = delay.call_args.args[2]["images"]
        assert len(images) == 2 and images[0]["is_primary"] and not images[1]["is_primary"]
        for ref in images:
            delete_stored_image(ref)
    finally:
        _drop(tenant)


# --- T-8.5c: город, затем район этого города ----------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "city,district,want_city,want_district",
    [
        ("solingen", "Ohligs", "Solingen", "ohligs-aufderhoehe-merscheid"),  # алиас + канон
        ("Wuppertal", "wald", "Wuppertal", ""),  # район чужого города отбрасывается
        ("  Haan  ", "", "Haan", ""),
    ],
)
def test_city_first_then_district_of_that_city(city, district, want_city, want_district):
    form = quickstart.QuickStartForm(_post_data(city=city, district=district))
    assert form.is_valid(), form.errors
    assert form.cleaned_data["city"] == want_city
    assert form.cleaned_data["district"] == want_district


@pytest.mark.django_db
def test_city_is_required():
    form = quickstart.QuickStartForm(_post_data(city=""))
    assert not form.is_valid() and "city" in form.errors


@pytest.mark.django_db
def test_page_offers_cities_and_districts_grouped_by_city():
    request = _session(RequestFactory().get("/aktion-starten/"))
    html = quickstart_views.quick_start(request).content.decode()
    assert 'name="city"' in html and 'value="Solingen"' in html
    assert '<option value="Solingen">' in html  # подсказка datalist
    assert 'data-city="solingen"' in html and "data-qs-district" in html


# --- T-8.13a: категория каталога города -------------------------------------------------


@pytest.mark.django_db
def test_category_and_tags_travel_in_promo_payload():
    form = quickstart.QuickStartForm(
        _post_data(city_category="kunst", city_tags=["regional", "zzz"])
    )
    assert not form.is_valid() and "city_tags" in form.errors  # неизвестный признак
    form = quickstart.QuickStartForm(_post_data(city_category="kunst", city_tags=["regional"]))
    assert form.is_valid(), form.errors
    payload = form.promo_payload()
    assert payload["city_category"] == "kunst" and payload["city_tags"] == ["regional"]
    built = quick.QuickPromotionForm(data=payload, tenant=None)
    assert built.is_valid(), built.errors
    promo = built.build()
    assert (promo.city_category, promo.city_tags) == ("kunst", ["regional"])


@pytest.mark.django_db
def test_page_offers_category_select_with_type_suggestions():
    request = _session(RequestFactory().get("/aktion-starten/"))
    html = quickstart_views.quick_start(request).content.decode()
    assert "data-city-category-select" in html and 'id="qs-cat-suggest"' in html
    assert '"bakery": "brot-backwaren"' in html


@pytest.mark.django_db
def test_waiting_polls_quietly_and_never_spins_forever():
    """Фидбэк 2026-10-10: страница ожидания перезагружалась каждые 3 с и могла
    крутиться вечно (ключ акции потерян / задача пропала)."""
    with mock.patch("apps.tenants.tasks.provision_quick.delay"):
        quickstart_views.quick_start(request := _post(_post_data()))
    tenant = Tenant.objects.get(slug="baeckerei-mueller-soehne")
    try:
        get = _session(RequestFactory().get(f"/aktion-starten/{tenant.slug}/"))
        get.session = request.session
        html = quickstart_views.quick_waiting(get, slug=tenant.slug).content.decode()
        assert "?poll=1" in html and "<noscript>" in html  # тихий опрос, без мигания

        poll = _session(RequestFactory().get(f"/aktion-starten/{tenant.slug}/", {"poll": "1"}))
        poll.session = request.session
        data = json.loads(quickstart_views.quick_waiting(poll, slug=tenant.slug).content)
        assert data == {"redirect": "", "stop": False}

        # схема готова, ключ акции пропал — через несколько минут ведём в список акций
        old = timezone.now() - 2 * quickstart_views.READY_GRACE
        Tenant.objects.filter(pk=tenant.pk).update(
            provisioning_status=Tenant.PROVISIONING_READY, created_at=old
        )
        data = json.loads(quickstart_views.quick_waiting(poll, slug=tenant.slug).content)
        assert "next=%2Fpromotions%2F" in data["redirect"]

        # задача пропала: PENDING слишком долго — честное сообщение, опрос стоп
        stale = timezone.now() - 2 * quickstart_views.STALE_AFTER
        Tenant.objects.filter(pk=tenant.pk).update(
            provisioning_status=Tenant.PROVISIONING_PENDING, created_at=stale
        )
        assert (
            json.loads(quickstart_views.quick_waiting(poll, slug=tenant.slug).content)["stop"]
            is True
        )
        html = quickstart_views.quick_waiting(get, slug=tenant.slug).content.decode()
        assert "?poll=1" not in html and "noscript" not in html
    finally:
        _drop(tenant)
