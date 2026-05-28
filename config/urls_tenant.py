"""URL routes для TENANT schema ({slug}.platform.com и custom domains).

Эти урлы видны на subdomain'ах конкретного бизнеса.
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
