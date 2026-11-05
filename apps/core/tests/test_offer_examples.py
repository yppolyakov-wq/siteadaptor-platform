"""AIS-W W4-2 срез 1: образцы «Beispiele einfügen» — на каждый тип × вид, все разбираются."""

from datetime import date

import pytest

from apps.core import directions, offer_examples, offer_lines
from apps.tenants.models import Tenant

TODAY = date(2026, 11, 5)
PAIRS = sorted(
    {
        (btype, kind)
        for btype, _label in Tenant.BUSINESS_TYPES
        for kind in (directions.defaults_for(btype) or offer_lines.KINDS)
        if kind in offer_lines.KINDS
    }
)


@pytest.mark.parametrize(("btype", "kind"), PAIRS)
def test_every_type_and_kind_has_parseable_examples(btype, kind):
    lines = offer_examples.lines_for(btype, kind, today=TODAY)
    assert len(lines) >= 5, (btype, kind)
    parsed = offer_lines.parse_lines("\n".join(lines), kind, today=TODAY)
    bad = [(x.raw, x.errors) for x in parsed.lines if x.errors]
    assert not bad, bad
    assert len(parsed.lines) == len(lines)


def test_ticket_examples_are_always_in_the_future():
    text = offer_examples.examples_for("events", "tickets", today=TODAY)
    lines = offer_lines.parse_lines(text, "tickets", today=TODAY).lines
    assert all(x.starts_at.date() > TODAY for x in lines)


def test_unknown_kind_has_no_examples():
    assert offer_examples.lines_for("bakery", "tisch") == ()
