"""SE-5a: кэш HTML витрины тенанта + сброс при публикации (версия в ключе)."""

import re
from types import SimpleNamespace

import pytest
from django.core.cache import cache
from django.http import HttpResponse
from django.test import override_settings

from apps.core import pagecache
from apps.tenants.tests.factories import TenantFactory

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


def _req(*, method="GET", get=None, session_empty=True, schema="acme", path="/", host="acme.test"):
    return SimpleNamespace(
        method=method,
        GET=get or {},
        session=SimpleNamespace(is_empty=lambda: session_empty),
        tenant=SimpleNamespace(schema_name=schema),
        LANGUAGE_CODE="de",
        path=path,
        # Настоящий HttpRequest это умеет; ключ кэша витрины включает хост
        # (у тенанта одновременно живут субдомен и кастом-домен).
        get_host=lambda: host,
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

    # Ветка `is_rendered` заперта ПРЯМО: без неё ContentNotRenderedError глотался
    # бы общим except вокруг cache.set, тест остался бы зелёным, и отказ
    # кэшировать стал бы побочным эффектом, а не решением.
    unrendered = TemplateResponse(_real_req(), "storefront/home.html", {})
    assert pagecache._cacheable(_real_req(), unrendered) is False


@override_settings(CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=60)
def test_legacy_two_tuple_cache_entry_is_treated_as_miss():
    """Старый формат записи (кортеж из двух) новый код не распаковывает."""
    cache.clear()
    calls = {"n": 0}

    @pagecache.cache_storefront_page
    def view(request):
        calls["n"] += 1
        return HttpResponse("fresh")

    # Ключ собираем ТЕМ ЖЕ выражением, что и декоратор: посеянный вручную
    # «sfpage2:acme:/:de:v0» после добавления хоста в ключ не читался никогда,
    # и замок стал холостым — зелёным при любом поведении `_unpack`.
    request = _real_req()
    key = pagecache._sf_key(request, "acme", "de", pagecache._cache_host(request))
    cache.set(key, (b"old", "text/html"), 60)
    assert cache.get(key) is not None, "замок сеет ключ, которого декоратор не ищет"
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


@override_settings(CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=60)
def test_storefront_cache_is_per_host():
    """Ревью диффа: у тенанта одновременно живут субдомен провижининга и
    подтверждённый кастом-домен — оба идут в тот же Django. Тело главной несёт
    абсолютный URL (LocalBusiness JSON-LD), поэтому общий на два хоста кэш отдавал
    посетителю кастом-домена разметку с адресом субдомена."""
    from django.test import RequestFactory

    cache.clear()

    @pagecache.cache_storefront_page
    def view(request):
        return HttpResponse(f'"url":"https://{request.get_host()}/"')

    def req(host):
        request = RequestFactory().get("/", HTTP_HOST=host)
        request.session = _real_req().session
        request.tenant = SimpleNamespace(schema_name="acme")
        request.LANGUAGE_CODE = "de"
        return request

    first = view(req("baeckerei.siteadaptor.de")).content.decode()
    second = view(req("www.baeckerei.de")).content.decode()
    assert "baeckerei.siteadaptor.de" in first
    assert "www.baeckerei.de" in second

    # оба хоста по-прежнему кэшируются (второй визит — без вызова вьюхи)
    calls = {"n": 0}

    @pagecache.cache_storefront_page
    def counted(request):
        calls["n"] += 1
        return HttpResponse("x")

    counted(req("shop.siteadaptor.de"))
    counted(req("shop.siteadaptor.de"))
    assert calls["n"] == 1


# --- Ревью диффа: позитивный замок на РЕАЛЬНОЙ главной, а не на HttpResponse("x") ---


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=60, ROOT_URLCONF="config.urls_tenant")
def test_real_storefront_home_is_still_cached_by_default():
    """Цена P0-1 измерена на живой странице, а не на синтетической вьюхе.

    Опасение ревью: с дефолтным `quick_add` главная всегда несёт форму с токеном,
    значит кэш витрины умер целиком и молча (все прежние позитивные замки —
    `HttpResponse("x")`). Замер: дефолтный конфиг + активный orders + товар в
    наличии → токена в теле НЕТ, страница кэшируется. Замок фиксирует именно это:
    если главная начнёт рендерить форму, тест покраснеет и цена станет видимой.
    """
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.catalog.models import Product
    from apps.promotions import public_views
    from apps.tenants.tests.factories import TenantFactory

    cache.clear()
    tenant = TenantFactory(
        schema_name="public", slug="sfcache", name="SF", disabled_modules=[], site_config={}
    )
    Product.objects.create(
        name={"de": "Brot"}, base_price="2.00", is_active=True, is_featured=True, stock_quantity=5
    )

    def req():
        request = RequestFactory().get("/")
        SessionMiddleware(lambda r: None).process_request(request)
        request.tenant = tenant
        return request

    body = public_views.storefront_home(req()).content.decode()
    assert "Brot" in body  # товар реально отрисован, страница не пустая
    assert "csrfmiddlewaretoken" not in body
    assert cache.get("sfpage2:testserver:public:/:de:v0") is not None

    # и хит действительно обслуживается кэшем — без повторного рендера
    from unittest.mock import patch

    with patch.object(
        public_views, "_capture_channel", side_effect=AssertionError("вьюха вызвана")
    ):
        assert "Brot" in public_views.storefront_home(req()).content.decode()


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=60, ROOT_URLCONF="config.urls_tenant")
def test_real_storefront_home_with_a_form_is_not_cached():
    """Обратная сторона того же замка на живой странице: как только на главной
    появляется форма с токеном (C-блок подписки), страница становится
    персональной и в общий кэш не попадает."""
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.promotions import public_views
    from apps.tenants.tests.factories import TenantFactory

    cache.clear()
    tenant = TenantFactory(
        schema_name="public",
        slug="sfcache2",
        name="SF2",
        disabled_modules=[],
        # C-блок подписки рендерит форму БЕЗУСЛОВНО (GK-8) — надёжный носитель
        # токена на главной, не зависящий от гейтов архетипа.
        site_config={"sections": [{"key": "newsletter", "enabled": True}]},
    )

    def req():
        request = RequestFactory().get("/")
        SessionMiddleware(lambda r: None).process_request(request)
        request.tenant = tenant
        return request

    body = public_views.storefront_home(req()).content.decode()
    assert "csrfmiddlewaretoken" in body, "секция заявки не отрисовала форму — замок бессмыслен"
    assert cache.get("sfpage2:testserver:public:/:de:v0") is None


@pytest.mark.parametrize("decorator", _DECORATORS)
@override_settings(CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=60)
def test_host_with_port_does_not_mint_cache_entries(decorator):
    """Ревью раунда 2: сырой `get_host()` в ключе — способ засорить Redis.

    ALLOWED_HOSTS проверяет домен БЕЗ порта, `TenantMainMiddleware` порт срезает,
    поэтому аноним доходит до вьюхи, меняя только `Host: shop.example.de:1`,
    `:2`, `:31337` — и каждая проба минтила бы свою запись в том же Redis, где
    сессии. Порт отбрасывается: все пробы схлопываются в одну запись по домену.
    """
    from django.test import RequestFactory

    cache.clear()

    @decorator
    def view(request):
        return HttpResponse("x")

    def req(host):
        request = RequestFactory().get("/", HTTP_HOST=host)
        request.session = _real_req().session
        request.tenant = SimpleNamespace(schema_name="acme")
        request.LANGUAGE_CODE = "de"
        return request

    for port in ("1", "2", "31337", "0000009"):
        view(req(f"shop.example.de:{port}"))
    view(req("shop.example.de"))
    # Все пробы схлопнулись в ОДНУ запись по домену: минта нет, а кэш при этом
    # продолжает работать (отказ кэшировать хост с портом выключал бы кэш целиком
    # в локальной разработке и на стенде, где адрес — `…:8000`).
    keys = [str(k) for k in cache._cache]
    assert len(keys) == 1, keys
    # Порт в ключ не попал. Проверяем формой ключа, а не игрой с подстроками:
    # прежние две ассерции были декоративными (одна — заведомо ложная под
    # `or True`), и работу делала только проверка количества.
    assert not re.search(r"shop\.example\.de:\d", keys[0]), keys

    view(req("anderer.example.de"))  # другой домен — своя запись
    assert len(cache._cache) == 2
