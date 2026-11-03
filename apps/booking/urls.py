from django.urls import path

from . import views, views_resources

app_name = "booking"

urlpatterns = [
    path("", views.calendar, name="calendar"),
    path("new/", views.booking_create, name="booking-create"),
    # Фидбэк 2026-08-05: карточка брони услуги (зеркало stays booking-detail).
    path("termin/<uuid:pk>/", views.booking_detail, name="booking-detail"),
    path("<uuid:pk>/action/", views.booking_action, name="booking-action"),
    path("ressourcen/", views.resources, name="resources"),
    # UX-D D3.2: «＋ Ressource» шторкой (до <uuid:pk>/)
    path("ressourcen/neu/", views_resources.resource_new, name="resource-new"),
    # UX-D D3.1: страница ресурса (вкладки рисует сервер, одна форма — W0)
    path("ressourcen/<uuid:pk>/", views_resources.resource_edit, name="resource-edit"),
    # HF-4: визуальный календарь доступности (закрыть/открыть продажи на день).
    path("verfuegbarkeit/", views.availability_calendar, name="availability"),
    path("leistungen/", views.services_view, name="services"),
    path("leistungen/neu/", views.service_new, name="service-new"),
    # Фидбэк 2026-07-30: у каждой услуги своя страница (паттерн stays:unit-edit) —
    # «Bearbeiten» из хаба «Angebote» больше не высаживает в общий список.
    path("leistungen/<uuid:pk>/", views.services_view, name="service-edit"),
    path("karten/", views.passes_view, name="passes"),
    path("nichterscheinen/", views.no_show_rule_save, name="no-show-rule"),
    path("regeln/", views.booking_rules_view, name="booking-rules"),
    # KA-12 GA-6: «Tischplan» — столы по зонам на момент времени.
    path("tische/plan/", views.tischplan, name="tischplan"),
    path("tische/regeln/", views.table_rules_save, name="table-rules"),
    path("services/inline-edit/", views.service_inline_edit, name="service-inline-edit"),
    path("services/photo-edit/", views.service_photo_edit, name="service-photo-edit"),
]
