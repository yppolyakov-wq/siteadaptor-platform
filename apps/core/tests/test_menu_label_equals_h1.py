"""KA-12 E8.5: подпись пункта меню = заголовок страницы `<h1>` (правило глоссария).

Обход всех беспараметрных экранов реестра (`nav_registry.ENTRIES` без query) у тенанта
со всеми модулями: первый `<h1>` обязан совпадать с подписью записи в DE и в RU (ru
ловит страницы, где заголовок забит литералом без перевода).
"""

import re
from uuid import uuid4

import pytest
from django.urls import NoReverseMatch, reverse
from django.utils import translation

from apps.core import modules, nav_registry
from apps.core.models import Membership
from apps.core.tests.test_staff_walk import _open, _user
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

# Осознанные исключения (причина обязательна). Долга нет — H1_DEBT пуст.
EXEMPT = {
    "verkaeufe": "Verkäufe с одним направлением показывает h1 вкладки (KA-4 прил. A)",
    "site-home": "Studio — полноэкранный редактор без h1 кабинета",
    "dashboard": "Übersicht — приветствие с именем бизнеса",
    "promotion-quick": "ассистент акции — заголовок шага",
}
H1_DEBT: dict[str, str] = {}

_H1 = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S)
_TAG = re.compile(r"<[^>]+>")


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _clean(raw: str) -> str:
    import html

    text = html.unescape(_TAG.sub(" ", raw))
    text = re.sub(r"^[^\wÄÖÜäöüА-Яа-яЁё]+", "", text.strip())
    return re.sub(r"\s+", " ", text).strip()


def _tenant():
    slug = f"h1-{uuid4().hex[:6]}"
    return TenantFactory(
        schema_name=slug.replace("-", "_"),
        slug=slug,
        business_type="restaurant",
        disabled_modules=[],
        enabled_modules=[m.key for m in modules.REGISTRY],
        bank_iban="DE89370400440532013000",
    )


def _entries(tenant):
    seen = set()
    for e in nav_registry.ENTRIES:
        if e.query or e.url_name in seen or e.url_name in EXEMPT:
            continue
        if not nav_registry.entry_visible(e, tenant, frozenset()):
            continue
        seen.add(e.url_name)
        yield e


def test_menu_label_equals_h1():
    tenant = _tenant()
    owner = _user(Membership.ROLE_OWNER)
    checked, bad = 0, []
    for e in _entries(tenant):
        try:
            path = reverse(e.url_name)
        except NoReverseMatch:
            continue
        for lang in ("de", "ru"):
            with translation.override(lang):
                resp = _open(path, tenant, owner)
                if resp.status_code != 200:
                    bad.append(f"{e.url_name}: HTTP {resp.status_code}")
                    break
                body = resp.content.decode() if not getattr(resp, "streaming", False) else ""
                m = _H1.search(body)
                got = _clean(m.group(1)) if m else "<kein h1>"
                want = str(e.label)
                if got != want and e.url_name not in H1_DEBT:
                    bad.append(f"{e.url_name} [{lang}]: h1={got!r} ≠ menu={want!r}")
        checked += 1
    assert checked >= 40, checked
    assert not bad, "\n".join(bad)
