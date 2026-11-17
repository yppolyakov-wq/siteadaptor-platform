"""Страницы с формами не отдают `Referrer-Policy: no-referrer` (фидбэк владельца 2026-11-17).

При «no-referrer» браузер шлёт у отправки формы `Origin: null`, и CSRF-проверка Django
отклоняет запрос («Origin checking failed - null does not match any trusted origins») —
так ломалась подписка на портале (/folgen/auswahl/). Токен в адресе от утечки бережёт и
«same-origin»: Referer не уходит на чужие сайты.
"""

import pathlib
import re


def test_no_page_response_uses_no_referrer():
    bad = []
    for path in pathlib.Path("apps").rglob("*.py"):
        if "tests" in path.parts or "migrations" in path.parts:
            continue
        if re.search(r"""\["Referrer-Policy"\]\s*=\s*["']no-referrer["']""", path.read_text()):
            bad.append(str(path))
    assert not bad, f"no-referrer ломает формы (Origin: null): {bad}"
