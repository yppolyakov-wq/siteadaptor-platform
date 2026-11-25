"""FB-33 стопка 15 K0: тестовый urlconf — кабинетный префикс без своего корня.

Сегодня у каждого из `CABINET_PREFIXES` есть корень, и страница витрины `<slug>/` под ними
не разбирается. Здесь `/crm/` уходит в `storefront-content-page`, как ушёл бы будущий
префикс без пути `""`: замок проверяет запасную ветку `CabinetOwnerAccessMiddleware`.
"""

from django.urls import path

from apps.core import content_page_views
from config import urls_tenant

handler404 = urls_tenant.handler404

urlpatterns = [
    path(
        "crm/",
        content_page_views.storefront_page,
        {"slug": "crm"},
        name="storefront-content-page",
    ),
    *urls_tenant.urlpatterns,
]
