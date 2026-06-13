from django.urls import path

from . import views

app_name = "jobs"

urlpatterns = [
    path("", views.job_list, name="list"),
    path("<uuid:pk>/", views.job_detail, name="detail"),
    path("<uuid:pk>/delete/", views.job_delete, name="delete"),
    path("<uuid:pk>/angebot.pdf", views.job_pdf, name="pdf"),
]
