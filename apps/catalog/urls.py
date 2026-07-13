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
    # Модификаторы / Extras (A4 Gastro): группы + опции.
    path(
        "products/<uuid:pk>/modifiers/add/",
        views.modifier_group_add,
        name="modifier-group-add",
    ),
    path(
        "products/<uuid:pk>/modifiers/<uuid:gid>/update/",
        views.modifier_group_update,
        name="modifier-group-update",
    ),
    path(
        "products/<uuid:pk>/modifiers/<uuid:gid>/delete/",
        views.modifier_group_delete,
        name="modifier-group-delete",
    ),
    path(
        "products/<uuid:pk>/modifiers/<uuid:gid>/options/add/",
        views.modifier_option_add,
        name="modifier-option-add",
    ),
    path(
        "products/<uuid:pk>/modifiers/<uuid:gid>/options/<uuid:oid>/update/",
        views.modifier_option_update,
        name="modifier-option-update",
    ),
    path(
        "products/<uuid:pk>/modifiers/<uuid:gid>/options/<uuid:oid>/delete/",
        views.modifier_option_delete,
        name="modifier-option-delete",
    ),
    # Фаза 1 (inline-content): правка текста товара прямо на канве витрины.
    path("products/inline-edit/", views.product_inline_edit, name="product-inline-edit"),
    # M4: замена главного фото товара на канве (multipart).
    path("products/photo-edit/", views.product_photo_edit, name="product-photo-edit"),
    path("categories/", views.category_list, name="category-list"),
    path("categories/new/", views.category_create, name="category-create"),
    path("categories/inline-edit/", views.category_inline_edit, name="category-inline-edit"),
    path("categories/<uuid:pk>/edit/", views.category_edit, name="category-edit"),
    # FB-6: фото категории — удалить/сделать главной (паттерн product-image-*)
    path(
        "categories/<uuid:pk>/images/<str:image_id>/delete/",
        views.category_image_delete,
        name="category-image-delete",
    ),
    path(
        "categories/<uuid:pk>/images/<str:image_id>/primary/",
        views.category_image_primary,
        name="category-image-primary",
    ),
    path("categories/<uuid:pk>/delete/", views.category_delete, name="category-delete"),
    # Комбо-наборы (A4 Gastro): набор + группы выбора + опции.
    path("combos/", views.combo_list, name="combo-list"),
    path("combos/new/", views.combo_create, name="combo-create"),
    path("combos/<uuid:pk>/edit/", views.combo_edit, name="combo-edit"),
    path("combos/<uuid:pk>/delete/", views.combo_delete, name="combo-delete"),
    path("combos/<uuid:pk>/groups/add/", views.combo_group_add, name="combo-group-add"),
    path(
        "combos/<uuid:pk>/groups/<uuid:gid>/update/",
        views.combo_group_update,
        name="combo-group-update",
    ),
    path(
        "combos/<uuid:pk>/groups/<uuid:gid>/delete/",
        views.combo_group_delete,
        name="combo-group-delete",
    ),
    path(
        "combos/<uuid:pk>/groups/<uuid:gid>/options/add/",
        views.combo_option_add,
        name="combo-option-add",
    ),
    path(
        "combos/<uuid:pk>/groups/<uuid:gid>/options/<uuid:oid>/update/",
        views.combo_option_update,
        name="combo-option-update",
    ),
    path(
        "combos/<uuid:pk>/groups/<uuid:gid>/options/<uuid:oid>/delete/",
        views.combo_option_delete,
        name="combo-option-delete",
    ),
]
