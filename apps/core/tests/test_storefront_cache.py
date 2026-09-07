"""SE-5a: кэш HTML витрины тенанта + сброс при публикации (версия в ключе)."""

from types import SimpleNamespace

import pytest
from django.core.cache import cache
from django.http import HttpResponse
from django.test import override_settings

from apps.core import pagecache
from apps.tenants.tests.factories import TenantFactory

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


def _req(*, method="GET", get=None, session_empty=True, schema="acme", path="/"):
    return SimpleNamespace(
        method=method,
        GET=get or {},
        session=SimpleNamespace(is_empty=lambda: session_empty),
        tenant=SimpleNamespace(schema_name=schema),
        LANGUAGE_CODE="de",
        path=path,
    )


@override_settings(CACHES=LOCMEM)
def test_bump_increments_version():
    cache.clear()
    assert pagecache._sf_version("acme") == 0
    pagecache.bump_storefront_cache("acme")
    assert pagecache._sf_version("acme") == 1
    pagecache.bump_storefront_cache("acme")
    assert pagecache._sf_version("acme") == 2


@override_settings(CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=60)
def test_decorator_serves_second_request_from_cache():
    cache.clear()
    calls = {"n": 0}

    @pagecache.cache_storefront_page
    def view(request):
        calls["n"] += 1
        return HttpResponse(f"render-{calls['n']}")

    first = view(_req())
    second = view(_req())
    assert first.content == b"render-1"
    assert second.content == b"render-1"  # из кэша — вьюха не вызвана повторно
    assert calls["n"] == 1


@override_settings(CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=60)
def test_bump_invalidates_cache():
    cache.clear()
    calls = {"n": 0}

    @pagecache.cache_storefront_page
    def view(request):
        calls["n"] += 1
        return HttpResponse(f"render-{calls['n']}")

    view(_req())  # закэшировали render-1
    pagecache.bump_storefront_cache("acme")  # публикация → версия++
    after = view(_req())
    assert after.content == b"render-2"  # ключ сменился → свежий рендер
    assert calls["n"] == 2


@override_settings(CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=60)
def test_bypass_for_session_query_and_method():
    cache.clear()
    calls = {"n": 0}

    @pagecache.cache_storefront_page
    def view(request):
        calls["n"] += 1
        return HttpResponse("x")

    view(_req(session_empty=False))  # непустая сессия (владелец/корзина) → мимо
    view(_req(get={"preview": "1"}))  # query-параметр → мимо
    view(_req(method="POST"))  # не-GET → мимо
    view(_req(schema=None))  # public/без тенанта → мимо
    assert calls["n"] == 4  # ни один не закэширован


@override_settings(CACHES=LOCMEM)
def test_ttl_zero_disables_cache():
    cache.clear()
    calls = {"n": 0}

    @pagecache.cache_storefront_page
    def view(request):
        calls["n"] += 1
        return HttpResponse("x")

    view(_req())
    view(_req())
    assert calls["n"] == 2  # TTL=0 (дефолт тестов) → кэш выключен


@override_settings(CACHES=LOCMEM)
@pytest.mark.django_db
def test_signal_bumps_version_on_site_config_save():
    cache.clear()
    tenant = TenantFactory(schema_name="public", slug="sfsig", name="SFSIG")
    before = pagecache._sf_version(tenant.schema_name)
    tenant.site_config = {"hero_title": "Neu"}
    tenant.save(update_fields=["site_config", "updated_at"])
    assert pagecache._sf_version(tenant.schema_name) == before + 1


@override_settings(CACHES=LOCMEM)
@pytest.mark.django_db
def test_signal_skips_when_site_config_not_in_update_fields():
    cache.clear()
    tenant = TenantFactory(schema_name="public", slug="sfsig2", name="SFSIG2")
    before = pagecache._sf_version(tenant.schema_name)
    tenant.name = "Renamed"
    tenant.save(update_fields=["name"])
    assert pagecache._sf_version(tenant.schema_name) == before  # не сброшен


# --- P0-1 (аудит 2026-09-03 §9.3): CSRF-токен и куки НЕ попадают в общий кэш ---


def _real_req(path="/", schema="acme"):
    """Настоящий HttpRequest (нужен META для get_token), с атрибутами витрины."""
    from importlib import import_module

    from django.conf import settings as dj_settings
    from django.test import RequestFactory

    request = RequestFactory().get(path)
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = SimpleNamespace(schema_name=schema)
    request.LANGUAGE_CODE = "de"
    return request


@override_settings(CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=60)
def test_page_with_csrf_token_is_never_served_from_cache():
    """Страница, использовавшая {% csrf_token %}, не кэшируется: второй посетитель
    получает СВОЙ токен, а не токен первого (воспроизведённая утечка)."""
    from django.middleware.csrf import get_token

    cache.clear()
    calls = {"n": 0}

    @pagecache.cache_storefront_page
    def view(request):
        calls["n"] += 1
        return HttpResponse(f"token={get_token(request)}")

    first = view(_real_req()).content
    second = view(_real_req()).content
    assert calls["n"] == 2, "ответ с CSRF-токеном попал в кэш"
    assert first != second, "второй посетитель получил чужой токен"


@override_settings(CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=60)
def test_response_with_set_cookie_is_not_cached_and_keeps_cookie():
    cache.clear()
    calls = {"n": 0}

    @pagecache.cache_storefront_page
    def view(request):
        calls["n"] += 1
        response = HttpResponse("x")
        response.set_cookie("visitor", "1")
        return response

    view(_real_req())
    second = view(_real_req())
    assert calls["n"] == 2
    assert "visitor" in second.cookies  # своя кука, а не пустой Set-Cookie с хита


@override_settings(CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=60)
def test_cache_hit_preserves_vary_header():
    cache.clear()

    @pagecache.cache_storefront_page
    def view(request):
        response = HttpResponse("x")
        response["Vary"] = "Accept-Language"
        return response

    view(_real_req())
    hit = view(_real_req())
    assert hit.get("Vary") == "Accept-Language"


@override_settings(CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=60)
def test_public_page_with_csrf_token_is_never_served_from_cache():
    """Тот же класс дефекта у cache_public_page (агрегатор/порталы)."""
    from django.middleware.csrf import get_token

    cache.clear()
    calls = {"n": 0}

    @pagecache.cache_public_page
    def view(request):
        calls["n"] += 1
        return HttpResponse(f"token={get_token(request)}")

    first = view(_real_req()).content
    second = view(_real_req()).content
    assert calls["n"] == 2
    assert first != second
