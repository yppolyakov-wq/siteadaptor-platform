from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("products/", views.product_list, name="product-list"),
    path("products/new/", views.product_create, name="product-create"),
    path("products/<uuid:pk>/edit/", views.product_edit, name="product-edit"),
    path("products/<uuid:pk>/delete/", views.product_delete, name="product-delete"),
    path(
        "products/<uuid:pk>/images/<str:image_id>/delete/",
        views.product_image_delete,
        name="product-image-delete",
    ),
    path(
        "products/<uuid:pk>/images/<str:image_id>/primary/",
        views.product_image_primary,
        name="product-image-primary",
    ),
    # Варианты товара (R1).
    path("products/<uuid:pk>/variants/add/", views.variant_add, name="variant-add"),
    path(
        "products/<uuid:pk>/variants/<uuid:vid>/update/",
        views.variant_update,
        name="variant-update",
    ),
    path(
        "products/<uuid:pk>/variants/<uuid:vid>/delete/",
        views.variant_delete,
        name="variant-delete",
    ),
    path("categories/", views.category_list, name="category-list"),
    path("categories/new/", views.category_create, name="category-create"),
    path("categories/<uuid:pk>/edit/", views.category_edit, name="category-edit"),
    path("categories/<uuid:pk>/delete/", views.category_delete, name="category-delete"),
]
