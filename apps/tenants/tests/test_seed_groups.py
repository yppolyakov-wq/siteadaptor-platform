"""seed_demo_tenants: несколько китов и группы одной командой (2026-10-11)."""

from io import StringIO
from unittest import mock

from django.core.management import call_command

from apps.tenants import demo_kits
from apps.tenants.management.commands import seed_demo_tenants as cmd


def _run(*args):
    seen = []
    out, err = StringIO(), StringIO()

    def fake(self, key, options):
        seen.append(key)
        if key == "hotel":
            raise RuntimeError("boom")
        return True

    with mock.patch.object(cmd.Command, "_seed_one", fake):
        call_command("seed_demo_tenants", *args, stdout=out, stderr=err)
    return seen, out.getvalue(), err.getvalue()


def test_kits_by_space_or_comma_without_duplicates():
    seen, _out, _err = _run("--kit", "cafe,friseur", "cafe")
    assert seen == ["cafe", "friseur"]


def test_group_solingen_covers_all_solingen_kits():
    seen, _out, _err = _run("--group", "solingen")
    expected = [k for k, kit in demo_kits.KITS.items() if kit.city == "Solingen"]
    assert seen == expected and "klingenbrot" in seen and "klingenwerk" in seen


def test_groups_and_kits_combine_and_one_failure_does_not_stop_the_batch():
    seen, out, err = _run("--group", "travel", "--kit", "cafe")
    assert seen[0] == "cafe" and "hotel" in seen  # явные киты — первыми
    assert "✗ hotel: boom" in err and "ошибки: hotel" in out


def test_unknown_group_is_reported_and_every_kit_belongs_to_all():
    _seen, _out, err = _run("--group", "nope")
    assert "неизвестная группа" in err
    assert cmd.kits_for_group("all") == list(demo_kits.KITS)


def test_list_prints_groups():
    out = StringIO()
    call_command("seed_demo_tenants", "--list", stdout=out)
    assert "solingen" in out.getvalue() and "klingenbrot" in out.getvalue()


def test_kit_as_plain_string_still_works():
    seen = []
    with mock.patch.object(cmd.Command, "_seed_one", lambda self, k, o: seen.append(k)):
        call_command("seed_demo_tenants", kit="cafe", stdout=StringIO())
    assert seen == ["cafe"]
