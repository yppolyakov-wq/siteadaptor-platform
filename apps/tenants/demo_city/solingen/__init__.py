"""Реестр демо-бизнесов Золингена по разделам справочника (по модулю на раздел)."""

from __future__ import annotations

from . import (
    auto,
    beauty,
    elektronik,
    essen,
    freizeit,
    gesundheit,
    haus,
    kinder,
    lebensmittel,
    mode,
    tiere,
)

SECTIONS = (
    lebensmittel,
    essen,
    mode,
    elektronik,
    haus,
    beauty,
    gesundheit,
    freizeit,
    kinder,
    auto,
    tiere,
)
BUSINESSES = tuple(b for mod in SECTIONS for b in mod.BUSINESSES)
