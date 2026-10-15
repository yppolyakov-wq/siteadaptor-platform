"""Реестр демо-бизнесов Золингена по разделам справочника (по модулю на раздел)."""

from __future__ import annotations

from . import beauty, elektronik, essen, gesundheit, haus, lebensmittel, mode, tiere

SECTIONS = (lebensmittel, essen, mode, elektronik, haus, beauty, gesundheit, tiere)
BUSINESSES = tuple(b for mod in SECTIONS for b in mod.BUSINESSES)
