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
    conditional = decorator_from_middleware(ConditionalGetMiddleware)(view)

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        response = conditional(request, *args, **kwargs)
        if response.status_code == 200:
            patch_cache_control(
                response, public=True, max_age=getattr(settings, "PUBLIC_PAGE_CACHE_TTL", 0)
            )
        return response

    return wrapped
