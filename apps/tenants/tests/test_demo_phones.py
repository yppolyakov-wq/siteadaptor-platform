"""KA-12 E7.10: в демо только телефоны «Drama Numbers» Bundesnetzagentur."""

import glob
import re
from pathlib import Path

from apps.tenants import demo_phones

ROOT = Path(__file__).resolve().parents[3]
PHONE = re.compile(r'"(\+49 [1-9][0-9]{1,4} [0-9]{4,8}|0[1-9][0-9]{1,4}[ /][0-9][0-9 ]{3,10})"')


def test_reserved_ranges_from_mitteilung_148_2021():
    assert demo_phones.is_reserved("+49 221 4710123")
    assert demo_phones.is_reserved("030 23125999")
    assert demo_phones.is_reserved("+49 171 3920042")
    assert demo_phones.is_reserved("0152 28817386")
    assert not demo_phones.is_reserved("+49 212 5552001")  # «555» — не вымышленная серия
    assert not demo_phones.is_reserved("+49 221 47101234")  # лишняя цифра


def test_every_phone_in_demo_sources_is_a_drama_number():
    files = [ROOT / "apps/tenants/demo_kits.py", ROOT / "apps/tenants/demo.py"]
    files += [Path(p) for p in glob.glob(str(ROOT / "apps/tenants/demo_city/solingen/*.py"))]
    bad = []
    for f in files:
        for m in PHONE.finditer(f.read_text(encoding="utf-8")):
            if not demo_phones.is_reserved(m.group(1)):
                bad.append(f"{f.name}: {m.group(1)}")
    assert not bad, bad
