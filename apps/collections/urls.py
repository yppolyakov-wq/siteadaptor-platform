from django.urls import path

from . import pages, views

app_name = "collections"

urlpatterns = [
    path("", views.collections_view, name="list"),
    path("neu/", pages.collection_new, name="new"),  # UX-D D6.3
    path("<uuid:pk>/", pages.collection_edit, name="edit"),
]
