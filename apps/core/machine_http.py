"""T-8.8: HTTP-обвязка машинных ресурсов (фид, sitemap): условный GET + Cache-Control.

`ConditionalGetMiddleware` ставит ETag по телу и отвечает 304 на If-None-Match.
Декоратор обязан стоять СНАРУЖИ `cache_public_page`: на кэш-хите вьюха не
вызывается, а кэш хранит только тело, Content-Type и Vary — заголовки, выставленные
внутри, пропали бы. Last-Modified не ставим: max(updated_at) выборки не меняется при
скрытии/истечении записи → был бы ложный 304.
"""

from functools import wraps

from django.conf import settings
from django.middleware.http import ConditionalGetMiddleware
from django.utils.cache import patch_cache_control
from django.utils.decorators import decorator_from_middleware


def machine_resource(view):
    @wraps(view)
    def with_cache_control(request, *args, **kwargs):
        response = view(request, *args, **kwargs)
        if response.status_code == 200:
            patch_cache_control(
                response, public=True, max_age=getattr(settings, "PUBLIC_PAGE_CACHE_TTL", 0)
            )
        return response

    # Cache-Control ставится ДО условного шага: ответ 304 строится из заголовков 200
    # и обязан повторять их (RFC 9110 §15.4.5).
    return decorator_from_middleware(ConditionalGetMiddleware)(with_cache_control)


def static_resource(view):
    """sitemap/robots/llms: содержимое не зависит от query → мусорный `?x=` не должен
    обходить кэш публичных страниц (иначе анонимный cache-bust = бесплатная нагрузка
    на БД). Запрос с параметрами обслуживается как запрос БЕЗ них."""
    from django.http import QueryDict

    from .pagecache import cache_public_page

    cached = cache_public_page(view)

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if request.GET:
            request.GET = QueryDict("", mutable=False)
            request.META["QUERY_STRING"] = ""
        return cached(request, *args, **kwargs)

    return wrapped
