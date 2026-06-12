from django.urls import path

from . import views

app_name = "finance"

urlpatterns = [
    path("", views.journal, name="journal"),
    # Экспорты журнала (D4c).
    path("export.csv", views.journal_export_csv, name="export-csv"),
    path("datev.csv", views.journal_export_datev, name="export-datev"),
    # Rechnungen (D4b).
    path("rechnungen/", views.invoices, name="invoices"),
    path("rechnungen/<uuid:pk>/", views.invoice_detail, name="invoice-detail"),
    path("rechnungen/<uuid:pk>/pdf/", views.invoice_pdf, name="invoice-pdf"),
]
