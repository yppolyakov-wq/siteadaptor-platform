"""T-8.10f F-4e: демо-засев пишет адреса только в зарезервированные домены (RFC 2606).

`example.de` — настоящий домен третьего лица: письмо владельцу демо или «клиенту» из
засева (напоминания, отзывы, сделки из ассистента) ушло бы постороннему."""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCES = [
    ROOT / "apps/tenants/demo_kits.py",
    ROOT / "apps/tenants/management/commands/seed_demo_tenants.py",
    *sorted((ROOT / "apps/tenants/demo_city").glob("*.py")),
]
_EMAIL = re.compile(r"[\w.+{}-]+@([\w.-]+\.[a-z]{2,})", re.I)
_RESERVED = ("example.com", "example.org", "example.net")


def _domains():
    for path in SOURCES:
        for match in _EMAIL.finditer(path.read_text(encoding="utf-8")):
            yield path.name, match.group(1).lower().rstrip(".")


def test_demo_seed_uses_only_reserved_mail_domains():
    bad = sorted(
        {
            (name, domain)
            for name, domain in _domains()
            if domain not in _RESERVED and not domain.endswith(".example")
        }
    )
    assert bad == []


def _string_parts(path):
    """Все строковые куски файла (включая куски f-строк) — только строки, не декораторы."""
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value


def test_no_address_with_domain_from_a_variable():
    """`f"{x}@{DOMAIN}"`: домен не виден регэкспу — такой адрес в засеве запрещён."""
    bad = []
    for path in SOURCES:
        for part in _string_parts(path):
            for at in re.finditer(r"@", part):
                tail = part[at.end() :]
                if not tail or not re.match(r"[\w-]", tail):
                    bad.append((path.name, part[:60]))
    assert bad == []


def test_scan_actually_sees_addresses():
    assert any(domain == "example.com" for _name, domain in _domains())
