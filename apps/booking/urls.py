from django.urls import path

from . import views

app_name = "booking"

urlpatterns = [
    path("", views.calendar, name="calendar"),
    path("new/", views.booking_create, name="booking-create"),
    # Фидбэк 2026-08-05: карточка брони услуги (зеркало stays booking-detail).
    path("termin/<uuid:pk>/", views.booking_detail, name="booking-detail"),
    path("<uuid:pk>/action/", views.booking_action, name="booking-action"),
    path("ressourcen/", views.resources, name="resources"),
    # HF-4: визуальный календарь доступности (закрыть/открыть продажи на день).
    path("verfuegbarkeit/", views.availability_calendar, name="availability"),
    path("leistungen/", views.services_view, name="services"),
    # Фидбэк 2026-07-30: у каждой услуги своя страница (паттерн stays:unit-edit) —
    # «Bearbeiten» из хаба «Angebote» больше не высаживает в общий список.
    path("leistungen/<uuid:pk>/", views.services_view, name="service-edit"),
    path("karten/", views.passes_view, name="passes"),
    path("nichterscheinen/", views.no_show_rule_save, name="no-show-rule"),
    # KA-12 GA-6: «Tischplan» — столы по зонам на момент времени.
    path("tische/plan/", views.tischplan, name="tischplan"),
    path("tische/regeln/", views.table_rules_save, name="table-rules"),
    path("services/inline-edit/", views.service_inline_edit, name="service-inline-edit"),
    path("services/photo-edit/", views.service_photo_edit, name="service-photo-edit"),
]
