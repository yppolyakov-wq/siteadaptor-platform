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
    vary = hit.get("Vary", "")
    assert "Accept-Language" in vary  # Vary из вьюхи пережил хит…
    assert "Cookie" in vary  # …и хит объявляет ключевание по куке (симметрично промаху)


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


# --- P0-1, по ревью скептика: паритет двух декораторов + ветки, которых не было ---

_DECORATORS = [pagecache.cache_storefront_page, pagecache.cache_public_page]


@pytest.mark.parametrize("decorator", _DECORATORS)
@override_settings(CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=60)
def test_real_request_without_personal_data_is_cached(decorator):
    """Позитивный замок на НАСТОЯЩЕМ HttpRequest (с META): гейт не задушил кэш."""
    cache.clear()
    calls = {"n": 0}

    @decorator
    def view(request):
        calls["n"] += 1
        return HttpResponse("x")

    view(_real_req())
    hit = view(_real_req())
    assert calls["n"] == 1
    assert "Cookie" in hit.get("Vary", "")  # хит честно объявляет Vary: Cookie


@pytest.mark.parametrize("decorator", _DECORATORS)
@override_settings(CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=60)
def test_csrf_token_with_existing_cookie_branch_is_not_cached(decorator):
    """Вторая ветка get_token (кука уже есть, csrf.py:107-111) — тоже персональна."""
    from django.middleware.csrf import CsrfViewMiddleware, get_token

    cache.clear()
    calls = {"n": 0}

    @decorator
    def view(request):
        calls["n"] += 1
        return HttpResponse(f"token={get_token(request)}")

    for _ in range(2):
        request = _real_req()
        request.COOKIES["csrftoken"] = "a" * 32
        CsrfViewMiddleware(lambda r: None).process_request(request)
        view(request)
    assert calls["n"] == 2


@pytest.mark.parametrize("decorator", _DECORATORS)
@override_settings(CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=60)
def test_session_modified_during_render_is_not_cached(decorator):
    """Куку sessionid ставит middleware ПОСЛЕ декоратора — виден только флаг modified."""
    cache.clear()
    calls = {"n": 0}

    @decorator
    def view(request):
        calls["n"] += 1
        request.session["visitor"] = 1
        return HttpResponse("x")

    view(_real_req())
    view(_real_req())
    assert calls["n"] == 2


@pytest.mark.parametrize("decorator", _DECORATORS)
@override_settings(CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=60)
def test_set_cookie_not_cached_for_both_decorators(decorator):
    cache.clear()
    calls = {"n": 0}

    @decorator
    def view(request):
        calls["n"] += 1
        response = HttpResponse("x")
        response.set_cookie("visitor", "1")
        return response

    view(_real_req())
    assert "visitor" in view(_real_req()).cookies
    assert calls["n"] == 2


@pytest.mark.parametrize("decorator", _DECORATORS)
@override_settings(CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=60)
def test_unrendered_template_response_is_not_cached_and_does_not_raise(decorator):
    from django.template import engines
    from django.template.response import TemplateResponse

    cache.clear()
    calls = {"n": 0}
    template = engines["django"].from_string("lazy")

    @decorator
    def view(request):
        calls["n"] += 1
        return TemplateResponse(request, template)

    view(_real_req())
    view(_real_req())
    assert calls["n"] == 2


@override_settings(CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=60)
def test_legacy_two_tuple_cache_entry_is_treated_as_miss():
    """Старый формат записи (кортеж из двух) новый код не распаковывает."""
    cache.clear()
    calls = {"n": 0}

    @pagecache.cache_storefront_page
    def view(request):
        calls["n"] += 1
        return HttpResponse("fresh")

    cache.set("sfpage2:acme:/:de:v0", (b"old", "text/html"), 60)
    assert view(_real_req()).content == b"fresh"
    assert calls["n"] == 1


@pytest.mark.parametrize("decorator", _DECORATORS)
@override_settings(CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=60)
def test_flash_message_from_cookie_rendered_in_body_is_not_cached(decorator):
    """Ревью плана (P0-1 регрессии): сообщение пришло с cookie ПРЕДЫДУЩЕГО ответа
    (added_new=False), шаблон его отрисовал (итерация → used=True). Тело содержит
    личный текст первого посетителя — второму его отдавать нельзя."""
    from django.contrib.messages import constants
    from django.contrib.messages.storage.base import Message
    from django.contrib.messages.storage.cookie import CookieStorage

    cache.clear()
    calls = {"n": 0}

    def req_with_flash():
        request = _real_req()
        request.COOKIES["messages"] = CookieStorage(request)._encode(
            [Message(constants.INFO, "Ihr Angebot 4711 wurde gesendet")]
        )
        request._messages = CookieStorage(request)
        return request

    @decorator
    def view(request):
        calls["n"] += 1
        return HttpResponse(", ".join(m.message for m in request._messages) or "leer")

    first = view(req_with_flash())
    assert b"4711" in first.content
    plain = _real_req()
    plain._messages = CookieStorage(plain)  # у второго посетителя своих сообщений нет
    second = view(plain)
    assert calls["n"] == 2
    assert b"4711" not in second.content


@pytest.mark.parametrize("decorator", _DECORATORS)
@override_settings(CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=60)
def test_cache_hit_does_not_touch_csrf_or_session(decorator):
    """На хите вьюха не зовётся: флаг CSRF не выставлен, сессия не тронута —
    иначе middleware поставил бы куки поверх общего тела."""
    cache.clear()

    @decorator
    def view(request):
        return HttpResponse("shared")

    view(_real_req())
    request = _real_req()
    assert view(request).content == b"shared"
    assert "CSRF_COOKIE_NEEDS_UPDATE" not in request.META
    assert not request.session.modified
