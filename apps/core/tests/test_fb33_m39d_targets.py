"""FB-33 M3-9d: остаток мелких целей касания витрины (≥ 24×24 px, WCAG 2.2 2.5.8 AA) и кнопки
ручного состава «Liste» в окне блока (≥ 44 px, контракт окна M3-2).

- точки обложки раздела (`_archetype_cover.html`) и шапки категории (`_category_header.html`):
  кнопка 24×24 с видимой точкой 8 px внутри (`<span aria-hidden>` без data-атрибута — селектор
  `[data-cover-dot]` / `[data-cat-dot]` берёт только кнопку), активная — `aria-current`;
  скрипт красит внутреннюю точку, а не кнопку;
- ссылки блока «Kontakt» (`sections/_contact.html`, оба вида), «Alle Fotos →» у примеров работ,
  «Route planen →» у события, «✎» в превью категорий — `min-h-[24px]`;
- ручной состав «Liste» (`templates/tenant/_schema_pick.html`) — 44 px, как у баннеров.

Высоту pytest не видит: здесь замок разметки, приёмка размеров — стенд
`scripts/fb33_m39c_targets_stand.py` (1440/390, de/ru, без JS и с JS).
"""

import importlib.util
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.template.loader import render_to_string
from django.test import RequestFactory

from apps.core.tests.test_fb33_m39c_targets import _ANCHOR, TARGET, _links

ROOT = Path(__file__).resolve().parents[3]
TEMPLATES = ROOT / "templates" / "storefront"
STAND = ROOT / "scripts" / "fb33_m39c_targets_stand.py"

#: кнопка-цель точки: 24×24, точка по центру
DOT_BUTTON = {"inline-flex", "w-6", "h-6", "items-center", "justify-center", "rounded-full"}
#: видимая точка внутри кнопки — 8 px
DOT_MARK = {"w-2", "h-2", "rounded-full"}
_BUTTON = re.compile(r"<button\b([^>]*)>(.*?)</button>", re.S)
_SPAN = re.compile(r'<span aria-hidden="true" class="([^"]*)"></span>')


def _classes(attrs: str) -> set[str]:
    m = re.search(r'class="([^"]*)"', attrs)
    return set(m.group(1).split()) if m else set()


def _dots(html: str, attr: str):
    """Кнопки точек `(атрибуты, внутренность)` по data-атрибуту."""
    return [(a, body) for a, body in _BUTTON.findall(html) if re.search(rf"\s{attr}[\s>]", a)]


def _assert_dots(dots, *, active: str):
    assert len(dots) == 3
    for k, (attrs, body) in enumerate(dots):
        assert DOT_BUTTON <= _classes(attrs), attrs
        # цвет — у точки, не у кнопки (кнопка прозрачная)
        assert not {"bg-white", "bg-white/50", "w-2", "h-2", "shadow"} & _classes(attrs), attrs
        assert "aria-hidden" not in attrs  # фокусируемое не прячем от чтеца
        label = re.search(r'aria-label="([^"]*)"', attrs).group(1)
        assert label.strip() and not label.strip().isdigit()  # не голое «N»
        marks = _SPAN.findall(body)
        assert len(marks) == 1, body
        mark = set(marks[0].split())
        assert DOT_MARK <= mark
        assert "data-" not in body  # селектор стенда и скрипта не попадает во внутреннюю точку
        assert (active in mark) is (k == 0)
        assert ('aria-current="true"' in attrs) is (k == 0)


def test_cover_dots_are_24px_targets_with_an_8px_mark():
    html = render_to_string(
        "storefront/_archetype_cover.html",
        {"archetype_cover": {"intro": "X", "slides": ["/a.svg", "/b.svg", "/c.svg"]}},
    )
    _assert_dots(_dots(html, "data-cover-dot"), active="bg-white")
    row = re.search(r'<div class="([^"]*)">\s*<button', html).group(1).split()
    # шаг точек = ширина кнопки (24 px): без gap, с переносом на узком экране
    assert "flex-wrap" in row and not [c for c in row if c.startswith("gap")]
    assert "bottom-1" in row  # центр точки — 16 px от низа, как раньше (bottom-3 + 4)
    # ряд во всю ширину: absolute + left:50% ужимал ряд до половины (перенос на 390)
    assert "inset-x-0" in row and "left-1/2" not in row and "-translate-x-1/2" not in row


def _script(path: str, start: str) -> str:
    src = (TEMPLATES / path).read_text(encoding="utf-8")
    return src[src.index(start) : src.index("</script>")]


def _assert_show(show: str):
    """`show()` красит внутреннюю точку (берёт её в момент вызова, без span не падает) и
    переносит `aria-current` на активную кнопку (как `_slider_script.html`)."""
    assert "var m = d.firstElementChild || d;" in show
    assert 'm.classList.toggle("bg-white", k === ' in show
    assert not re.search(r"\bd\.classList", show)
    assert 'd.setAttribute("aria-current", "true")' in show
    assert 'd.removeAttribute("aria-current")' in show


def test_cover_script_marks_the_dot_not_the_button():
    body = _script("_archetype_cover.html", "function show(n)")
    _assert_show(body[: body.index("function stop()")])


def test_category_header_dots_are_24px_targets():
    html = render_to_string(
        "storefront/_category_header.html",
        {"category_photos": ["/a.jpg", "/b.jpg", "/c.jpg"], "current_category": "Brot"},
    )
    dots = _dots(html, "data-cat-dot")
    _assert_dots(dots, active="bg-white")
    assert all("shadow" in _SPAN.findall(body)[0].split() for _a, body in dots)
    row = re.search(r'<div class="([^"]*)">\s*<button[^>]*data-cat-dot', html).group(1).split()
    assert "flex-wrap" in row and not [c for c in row if c.startswith("gap")]
    assert "inset-x-0" in row and "bottom-1" in row


def test_category_header_script_marks_the_dot_not_the_button():
    js = _script("_category_header.html", "function show(n)")
    _assert_show(js[: js.index('s.querySelector("[data-cat-prev]")')])


def test_dots_have_a_visible_focus_ring():
    """Точка на фото: кольцо белое с тёмной обводкой — видно на светлом и тёмном снимке."""
    css = (ROOT / "static" / "src" / "app.css").read_text(encoding="utf-8")
    assert (
        "[data-cover-dot]:focus-visible, [data-cat-dot]:focus-visible { outline: 2px solid #fff;"
        " outline-offset: 0; box-shadow: 0 0 0 4px rgba(0,0,0,.55); }"
    ) in css


@pytest.fixture
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _contact(style: str) -> str:
    tenant = SimpleNamespace(
        address="Markt 1, 42781 Haan",
        opening_hours="Mo–Fr 9–18",
        public_phone="+49 2129 1234",
        public_email="hallo@m39d.test",
        open_status=None,
        todays_hours="",
        map_url="https://maps.example/m39d",
        latitude=None,
        longitude=None,
    )
    req = RequestFactory().get("/")
    req.tenant = tenant
    return render_to_string(
        "storefront/sections/_contact.html",
        {"request": req, "section_row": {"style": style}, "storefront_inbox_enabled": True},
    )


@pytest.mark.parametrize("style", ["card", "compact"])
def test_contact_links_are_24px_targets(_urlconf, style):
    links = _links(_contact("" if style == "card" else style))
    texts = [t for _a, t in links]
    assert "+49 2129 1234" in texts and "hallo@m39d.test" in texts
    assert any(t.endswith("→") for t in texts)
    if style == "card":
        assert any(t.startswith("📞") for t in texts)
    small = [
        t
        for a, t in links
        if not {TARGET, "inline-flex", "items-center"} <= set(a["class"].split())
    ]
    assert small == []


#: шаблон → признак ссылки в исходнике (как `SOURCE_LINKS` M3-9c)
SOURCE_LINKS = [
    ("_combo_examples.html", '{% trans "Alle Fotos" %} →'),
    ("_event_thematic.html", '{% trans "Plan route" %} →'),
    ("products.html", "✎"),
]


@pytest.mark.parametrize(("template", "marker"), SOURCE_LINKS)
def test_storefront_link_is_a_24px_target(template, marker):
    src = (TEMPLATES / template).read_text(encoding="utf-8")
    found = [attrs for attrs, body in _ANCHOR.findall(src) if marker in body]
    assert found, f"{template}: ссылка «{marker}» не найдена"
    small = [
        a.strip()[:80] for a in found if not {TARGET, "inline-flex", "items-center"} <= _classes(a)
    ]
    assert small == []


def test_category_edit_pencil_is_a_24px_square():
    src = (TEMPLATES / "products.html").read_text(encoding="utf-8")
    (attrs,) = [a for a, body in _ANCHOR.findall(src) if body.strip() == "✎"]
    cls = set(re.search(r'class="([^"]*)"', attrs).group(1).split())
    assert {"min-w-[24px]", "justify-center"} <= cls
    assert "aria-label=\"{% trans 'Edit category' %}\"" in attrs  # имя не «✎»


def test_schema_pick_buttons_are_44px_squares():
    src = (ROOT / "templates" / "tenant" / "_schema_pick.html").read_text(encoding="utf-8")
    buttons = re.findall(r"<button\b[^>]*name=\"pick_op\"[^>]*>", src)
    assert len(buttons) == 5  # ↑ ↓ ✕ ＋ «Zur Regel zurück»
    for b in buttons:
        assert "min-h-[44px]" in b, b
    squares = [b for b in buttons if 'value="clear:"' not in b]
    assert len(squares) == 4 and all("min-w-[44px]" in b for b in squares)
    (clear,) = [b for b in buttons if 'value="clear:"' in b]
    assert "inline-flex" in clear and "items-center" in clear
    assert "min-h-[32px]" not in src and "min-w-[32px]" not in src


def _stand() -> str:
    return STAND.read_text(encoding="utf-8")


def test_m39c_stand_measures_pick_buttons():
    """Ручной состав «Liste» больше не исключён из проверки окна ≥ 44 px (в таблице — своей
    строкой, как раньше)."""
    src = _stand()
    body = src[src.index("def measure_panel") : src.index("def window_part")]
    assert 't["pick"] or' not in body and 'outside = t["tag"] == "a"\n' in body


def test_m39c_stand_targets_cover_m39d():
    """Стенд мерит новые цели: точки обложки и шапки категории, «📞 Rückruf» (только ссылка
    блока «Kontakt»: плитка quick_links ведёт по тому же адресу, но текст без «📞»), страницы
    «Über uns» магазина, категории и комбо ресторана."""
    spec = importlib.util.spec_from_file_location("m39c_stand", STAND)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(STAND.parent))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(STAND.parent))
    sels = {sel: pat for sel, pat in mod.TARGETS.values()}
    assert "[data-cover-dot]" in sels and "[data-cat-dot]" in sels
    assert sels.get("main a[href*='kind=callback']") == "^📞"
    # точки обложки и шапки категории есть не на каждом ките — цель необязательная
    optional = {mod.TARGETS[name][0] for name in mod.OPTIONAL_TARGETS}
    assert {"[data-cover-dot]", "[data-cat-dot]"} <= optional
    assert "/ueber-uns/" in mod.KIT_PAGES["shop"]
    assert ("/sortiment/", r"^/sortiment/[a-z0-9-]+/$") in mod.KIT_PAGES["shop"]
    assert ("/kombi/", r"^/kombi/[0-9a-f-]{36}/$") in mod.KIT_PAGES["restaurant"]
