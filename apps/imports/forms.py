"""Формы импорта.

Маппинг колонок обрабатывается во view из POST (динамические заголовки),
поэтому отдельного Form-класса для него нет.
"""

from django import forms

ALLOWED_SUFFIXES = (".csv", ".xlsx", ".xlsm")


class ImportUploadForm(forms.Form):
    source_file = forms.FileField(label="CSV- oder Excel-Datei")

    def clean_source_file(self):
        f = self.cleaned_data["source_file"]
        name = (f.name or "").lower()
        if not name.endswith(ALLOWED_SUFFIXES):
            raise forms.ValidationError("Nur .csv, .xlsx oder .xlsm werden unterstützt.")
        return f
