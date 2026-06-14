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
        widget=forms.PasswordInput(render_value=False),
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

    @admin.display(description=_("Set"), boolean=True)
    def is_set_display(self, obj):
        return obj.is_set
