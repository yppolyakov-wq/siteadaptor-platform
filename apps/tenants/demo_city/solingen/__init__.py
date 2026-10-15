"""Реестр демо-бизнесов Золингена по разделам справочника (по модулю на раздел)."""

from __future__ import annotations

from . import (
    auto,
    beauty,
    dienstleistungen,
    elektronik,
    essen,
    freizeit,
    gesundheit,
    handwerk,
    haus,
    kinder,
    kunst,
    lebensmittel,
    mode,
    reisen,
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
    handwerk,
    dienstleistungen,
    reisen,
    tiere,
    kunst,
)
BUSINESSES = tuple(b for mod in SECTIONS for b in mod.BUSINESSES)
