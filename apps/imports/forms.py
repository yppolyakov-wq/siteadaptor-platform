"""Формы импорта.

Маппинг колонок обрабатывается во view из POST (динамические заголовки),
поэтому отдельного Form-класса для него нет.
"""

from django import forms

ALLOWED_SUFFIXES = (".csv", ".xlsx", ".xlsm")
# Лимит размера загрузки: без него аутентиф. staff мог залить zip-bomb .xlsx /
# многосотмегабайтный CSV → OOM общего Celery-воркера (деградация всех тенантов).
# 10 МБ с запасом покрывает реальные каталоги малого бизнеса. MEDIUM-4.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class ImportUploadForm(forms.Form):
    source_file = forms.FileField(label="CSV- oder Excel-Datei")

    def clean_source_file(self):
        f = self.cleaned_data["source_file"]
        name = (f.name or "").lower()
        if not name.endswith(ALLOWED_SUFFIXES):
            raise forms.ValidationError("Nur .csv, .xlsx oder .xlsm werden unterstützt.")
        if f.size and f.size > MAX_UPLOAD_BYTES:
            raise forms.ValidationError("Datei zu groß (max. 10 MB).")
        return f
