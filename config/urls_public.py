"""URL routes для SHARED schema (агрегатор, public-сайт, admin).

Эти урлы доступны на основном домене platform.com и aggregator.platform.com.
"""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("health/", health, name="health"),
]
