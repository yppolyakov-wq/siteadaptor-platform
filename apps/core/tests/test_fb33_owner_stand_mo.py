"""Стенд владельца не стартует на устаревших `.mo` (стопка 11: ложные 806 ✗ «немецкое в ru»)."""

import importlib.util
import os
import pathlib
import time

ROOT = pathlib.Path(__file__).resolve().parents[3]


def _stand():
    spec = importlib.util.spec_from_file_location(
        "owner_stand", ROOT / "scripts" / "fb33_m3_9_owner_stand.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tree(tmp_path, mo_newer):
    d = tmp_path / "locale" / "ru" / "LC_MESSAGES"
    d.mkdir(parents=True)
    po, mo = d / "django.po", d / "django.mo"
    po.write_text("")
    mo.write_bytes(b"")
    now = time.time()
    os.utime(po, (now, now))
    os.utime(mo, (now + (10 if mo_newer else -10),) * 2)
    return tmp_path


def test_stale_mo_detected(tmp_path):
    assert _stand().stale_mo(str(_tree(tmp_path, mo_newer=False))) == ["ru"]


def test_fresh_mo_passes(tmp_path):
    assert _stand().stale_mo(str(_tree(tmp_path, mo_newer=True))) == []


def test_missing_mo_detected(tmp_path):
    root = _tree(tmp_path, mo_newer=True)
    (root / "locale" / "ru" / "LC_MESSAGES" / "django.mo").unlink()
    assert _stand().stale_mo(str(root)) == ["ru"]
