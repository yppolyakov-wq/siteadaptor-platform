"""CSV formula/DDE-инъекция: csv_safe (MEDIUM-3)."""

from apps.core.csv_safe import csv_safe


def test_neutralizes_formula_prefixes():
    for bad in ("=cmd|'/c calc'!A1", "+1+1", "-2+3", "@SUM(A1)", "\ttab", "\rcr"):
        out = csv_safe(bad)
        assert out.startswith("'"), bad


def test_passes_plain_text_unchanged():
    for ok in ("Alice", "alice@example.com", "Notiz zum Auftrag", "Straße 5", ""):
        assert csv_safe(ok) == ok


def test_none_is_empty():
    assert csv_safe(None) == ""
