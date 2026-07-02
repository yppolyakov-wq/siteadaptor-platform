from django.urls import path

from . import views

app_name = "collections"

urlpatterns = [
    path("", views.collections_view, name="list"),
]
