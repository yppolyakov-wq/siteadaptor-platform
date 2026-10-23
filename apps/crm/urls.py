from django.urls import path

from . import views

app_name = "crm"

urlpatterns = [
    path("", views.customer_list, name="customer-list"),
    # CSV-экспорт текущей выборки (D1c).
    path("export.csv", views.customer_export_csv, name="customer-export"),
    path("new/", views.customer_create, name="customer-create"),
    # CO-1: справочник компаний (корпоративный контур v1).
    path("firmen/", views.company_list, name="company-list"),
    path("firmen/neu/", views.company_create, name="company-create"),
    path("firmen/<uuid:pk>/", views.company_detail, name="company-detail"),
    path("firmen/<uuid:pk>/loeschen/", views.company_delete, name="company-delete"),
    path("<uuid:pk>/", views.customer_detail, name="customer-detail"),
    path("<uuid:pk>/notes/", views.note_add, name="note-add"),
    # KA-12 E6.1: запрос клиента по DSGVO (Art. 15/17/20) — только владелец.
    path("<uuid:pk>/datenschutz/", views.customer_dsgvo, name="customer-dsgvo"),
    path(
        "<uuid:pk>/datenschutz/export.zip",
        views.customer_dsgvo_export,
        name="customer-dsgvo-export",
    ),
    path(
        "<uuid:pk>/datenschutz/loeschen/",
        views.customer_dsgvo_erase,
        name="customer-dsgvo-erase",
    ),
]
