"""Единая точка чтения табличных файлов импорта (CSV и Excel).

Формат определяется по расширению имени файла. Для CSV учитывается
выбранный разделитель (delimiter_key), для Excel он игнорируется.
"""

from . import csvutil, xlsxutil
from .csvutil import apply_mapping  # noqa: F401 — реэкспорт для tasks.py

EXCEL_SUFFIXES = (".xlsx", ".xlsm")
CSV_SUFFIXES = (".csv",)


def is_excel(django_file) -> bool:
    name = (getattr(django_file, "name", "") or "").lower()
    return name.endswith(EXCEL_SUFFIXES)


def read_headers(django_file, delimiter_key: str | None = None) -> list[str]:
    if is_excel(django_file):
        return xlsxutil.read_headers(django_file)
    return csvutil.read_headers(django_file, delimiter_key)


def read_rows(django_file, delimiter_key: str | None = None):
    if is_excel(django_file):
        return xlsxutil.read_rows(django_file)
    return csvutil.read_rows(django_file, delimiter_key)
