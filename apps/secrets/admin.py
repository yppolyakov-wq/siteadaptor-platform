"""Unfold-админка платформенных секретов (только public, config/urls_public).

Значение write-only: вводится в маскированное поле, в БД хранится зашифрованным,
в UI не показывается (только признак «задан» + дата). Пустой ввод не затирает.
"""

from django import forms
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from .models import PlatformSecret


class PlatformSecretForm(forms.ModelForm):
    value = forms.CharField(
        required=False,
        # autocomplete=new-password: браузер не подставляет сохранённый пароль админки
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        label=_("Value"),
        help_text=_("Enter to set/replace. Leave blank to keep the current value."),
    )

    class Meta:
        model = PlatformSecret
        fields = ("key", "description")

    def save(self, commit=True):
        obj = super().save(commit=False)
        raw = self.cleaned_data.get("value")
        if raw:
            obj.set_value(raw)
        if commit:
            obj.save()
        return obj


@admin.register(PlatformSecret)
class PlatformSecretAdmin(ModelAdmin):
    form = PlatformSecretForm
    list_display = ("key", "is_set_display", "description", "updated_at")
    search_fields = ("key", "description")
    ordering = ("key",)

    # Секреты (токены ботов, ключи OAuth/ИИ) — только суперпользователю: обычный staff с
    # правом change мог бы подменить токен бота платформы или отключить секрет вебхука.
    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    @admin.display(description=_("Set"), boolean=True)
    def is_set_display(self, obj):
        return obj.is_set
