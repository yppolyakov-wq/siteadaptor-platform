"""Реестр демо-бизнесов Золингена по разделам справочника (по модулю на раздел)."""

from __future__ import annotations

from . import essen, lebensmittel, tiere

SECTIONS = (lebensmittel, essen, tiere)
BUSINESSES = tuple(b for mod in SECTIONS for b in mod.BUSINESSES)
