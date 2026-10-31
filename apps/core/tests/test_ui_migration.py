"""KA-12 E9.8: экраны кабинета собраны из деталей ui-* (поле, основная кнопка, карточка).

Замок: в кабинете нет рукописного поля во всю ширину, основной кнопки и карточки, которые
можно заменить на `ui-input` / `ui-btn ui-btn-primary` / `ui-card`. Студия и мастер настройки
вне объёма (там JS переключает эти классы), публичные страницы — не кабинет.
"""

import re
from pathlib import Path

from django.conf import settings

TEMPLATES = Path(settings.BASE_DIR) / "templates"
SKIP_PREFIX = (
    "storefront/",
    "aggregator/",
    "email",
    "pdf/",
    "public/",
    "platform/",
    "account/",
    "konto/",
    "admin/",
    "tenants/",
    "tenant/setup",
)
SKIP_FILES = {
    "tenant/site_home.html",
    "tenant/site_preview.html",
    "tenant/_cb_row.html",
    "tenant/_section_fields.html",
    "tenant/_builtin_list_fields.html",
    "tenant/_output_axis.html",
}
_CLASS = re.compile(r'<(?P<tag>[a-z]+)\b[^>]*?\bclass="(?P<cls>[^"]*)"[^>]*>')


def hand_rolled(text):
    out = []
    for m in _CLASS.finditer(text):
        tag, cls = m["tag"], m["cls"]
        if "{" in cls or "ui-" in cls:
            continue
        s = set(cls.split())
        rounded = any(t.startswith("rounded") for t in s)
        if tag in ("input", "select", "textarea") and {"w-full", "border"} <= s and rounded:
            if not re.search(r'type="(file|checkbox|radio|range|color)"', m[0]):
                out.append(("input", m[0][:90]))
        elif tag in ("button", "a") and s & {"bg-indigo-600", "bg-gray-900"} and "text-white" in s:
            out.append(("button", m[0][:90]))
        elif (
            "bg-white" in s
            and any(re.match(r"rounded-(xl|2xl)$", t) for t in s)
            and (any(t.startswith("shadow") for t in s) or "border" in s)
            and not any(re.match(r"border-(?!gray-|black/)\S", t) for t in s)
        ):
            out.append(("card", m[0][:90]))
    return out


def _cabinet_templates():
    for path in sorted(TEMPLATES.rglob("*.html")):
        rel = path.relative_to(TEMPLATES).as_posix()
        if not rel.startswith(SKIP_PREFIX) and rel not in SKIP_FILES:
            yield rel, path.read_text()


def test_cabinet_uses_ui_parts():
    found = [
        (rel, kind, snippet)
        for rel, text in _cabinet_templates()
        for kind, snippet in hand_rolled(text)
    ]
    assert not found, found[:10]


def test_detector_sees_each_pattern():
    assert hand_rolled(
        '<input name="a" class="w-full rounded-lg border border-gray-300 px-3 py-2">'
    )
    assert hand_rolled('<button class="bg-indigo-600 text-white px-4 py-2 rounded-lg">x</button>')
    assert hand_rolled('<div class="bg-white rounded-2xl shadow p-5">x</div>')
    assert not hand_rolled('<input type="file" class="w-full rounded-lg border">')
    assert not hand_rolled('<div class="ui-card p-5">x</div>')
