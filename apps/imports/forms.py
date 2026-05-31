"""Формы импорта.

Маппинг колонок обрабатывается во view из POST (динамические заголовки),
поэтому отдельного Form-класса для него нет.
"""

from django import forms


class ImportUploadForm(forms.Form):
    source_file = forms.FileField(label="CSV-файл")

    def clean_source_file(self):
        f = self.cleaned_data["source_file"]
        name = (f.name or "").lower()
        if not name.endswith(".csv"):
            raise forms.ValidationError("Только файлы .csv поддерживаются.")
        return f
