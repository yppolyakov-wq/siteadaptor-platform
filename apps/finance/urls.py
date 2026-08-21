from django.urls import path

from . import views

app_name = "finance"

urlpatterns = [
    path("", views.journal, name="journal"),
    # MX-1: расходы и сводный результат — «Finanzen» больше не только выручка.
    path("ausgaben/", views.expenses, name="expenses"),
    path("ergebnis/", views.ergebnis, name="ergebnis"),
    # Экспорты журнала (D4c).
    path("export.csv", views.journal_export_csv, name="export-csv"),
    path("datev.csv", views.journal_export_datev, name="export-datev"),
    # Rechnungen (D4b).
    path("rechnungen/", views.invoices, name="invoices"),
    path("rechnungen/<uuid:pk>/", views.invoice_detail, name="invoice-detail"),
    path("rechnungen/<uuid:pk>/pdf/", views.invoice_pdf, name="invoice-pdf"),
]
