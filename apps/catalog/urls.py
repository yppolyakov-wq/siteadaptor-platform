from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("products/", views.product_list, name="product-list"),
    path("products/new/", views.product_create, name="product-create"),
    path("products/<uuid:pk>/edit/", views.product_edit, name="product-edit"),
    path("products/<uuid:pk>/delete/", views.product_delete, name="product-delete"),
]
