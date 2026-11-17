"""T-8.35: реквизиты оператора портала — одна точка истины для «Rechtliches».

План — docs/t8-35-portal-legal-plan-2026-11-17.md. Страницы портала (Impressum, Datenschutz,
Nutzungsbedingungen, хаб) берут оператора ТОЛЬКО отсюда. Пока реквизиты неполные или тексты не
вычитаны юристом (`reviewed_at`), страницы — «Entwurf» (не выдаём заглушки за готовый текст).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

#: обязательные сведения § 5 Abs. 1 DDG (имя, ladungsfähige Anschrift, быстрый контакт)
REQUIRED = (
    ("name", "Name / Firma"),
    ("street", "Straße und Hausnummer"),
    ("zip_city", "PLZ und Ort"),
    ("email", "E-Mail"),
    ("phone", "Telefon"),
)
#: правовые формы, для которых нужен представитель (§ 5 Abs. 1 Nr. 1 DDG)
_WITHOUT_REPRESENTATIVE = {"", "einzelunternehmen", "einzelunternehmer", "freiberufler"}


@dataclass(frozen=True)
class Info:
    operator: object | None
    missing: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_complete(self) -> bool:
        return self.operator is not None and not self.missing

    @property
    def is_final(self) -> bool:
        """Реквизиты полные И тексты вычитаны — плашка «Entwurf» снимается."""
        return self.is_complete and bool(getattr(self.operator, "reviewed_at", None))

    @property
    def contact_email(self) -> str:
        return getattr(self.operator, "email", "") or ""

    @property
    def dsa_email(self) -> str:
        op = self.operator
        return (getattr(op, "dsa_email", "") or self.contact_email) if op else ""

    @property
    def responsible_mstv(self) -> str:
        op = self.operator
        if op is None:
            return ""
        return op.responsible_mstv or "\n".join(x for x in (op.name, op.street, op.zip_city) if x)


def missing(operator) -> tuple[str, ...]:
    if operator is None:
        return tuple(label for _f, label in REQUIRED)
    out = [label for name, label in REQUIRED if not (getattr(operator, name, "") or "").strip()]
    form = (operator.legal_form or "").strip().casefold()
    if form not in _WITHOUT_REPRESENTATIVE and not (operator.representative or "").strip():
        out.append("Vertretungsberechtigt")
    return tuple(out)


def info(portal) -> Info:
    operator = getattr(portal, "operator", None) if portal is not None else None
    gaps = missing(operator)
    if gaps and portal is not None:
        logger.info(
            "portal legal pages are a draft: operator data missing",
            extra={"portal": getattr(portal, "host", ""), "missing": list(gaps)},
        )
    return Info(operator=operator, missing=gaps)
