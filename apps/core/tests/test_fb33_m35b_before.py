"""FB-33 M3-5b-0: замки ДО кода «FAQ-вопросы и плашки Schnellzugriff в окне блока».

План — scratchpad `m35b-plan.md` / `docs/fb33-editor-model-2026-11-19.md` §«План M3» (FAQ M3-5b).
- L1 витрина плашек: все наборы × модули вкл/выкл × живая акция есть/нет — байт-в-байт снимок
  ДО среза (скрытие и подписи по умолчанию ничего не добавляют, ни пробела).
- L2 витрина FAQ: виды × de/ru (перевод позиционный) — снимок держит
  `test_fb33_m2b2a_before.py` (de); здесь — что перевод на ru рисуется тем же шаблоном.
Пересъёмка (осознанно): FB33M35B_GOLDEN=update uv run pytest <этот файл>
"""

import json
import os
import uuid
from pathlib import Path

import pytest
from django.template import Context, Template
from django.test import RequestFactory

from apps.core import hero_tiles
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
GOLDEN = Path(__file__).parent / "golden_fb33m35b" / "quick_links.json"
UPDATE = os.environ.get("FB33M35B_GOLDEN") == "update"
DEAL_PK = uuid.UUID("00000000-0000-4000-8000-00000000d3a1")
FLAGS = (
    "storefront_booking_enabled",
    "storefront_orders_enabled",
    "storefront_jobs_enabled",
    "storefront_gift_enabled",
)


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def make_deal():
    from apps.promotions.tests.factories import PromotionFactory

    return PromotionFactory(
        pk=DEAL_PK, title={"de": "Brezel-Tag", "en": "Pretzel day"}, available_quantity=None
    )


def modules_on(monkeypatch, on: bool):
    from apps.core import modules

    monkeypatch.setattr(modules, "is_module_active", lambda tenant, key, **kw: on)
    monkeypatch.setitem(hero_tiles._EXTRA_GATES, "gift", lambda tenant: on)


def block_html(data, on: bool, extra=None):
    """Блок «Schnellzugriff» так, как его рисует витрина (`render_block`)."""
    req = RequestFactory().get("/")
    req.tenant = TenantFactory.build(business_type="online_shop", disabled_modules=[])
    tpl = Template("{% load siteui %}{% render_block b %}")
    ctx = {"request": req, "site": siteconfig.normalize({}), "modules": {}}
    ctx.update({flag: on for flag in FLAGS})
    ctx.update(extra or {})
    block = {"key": "quick_links", "id": "q1", "data": data}
    return tpl.render(Context({**ctx, "b": block}))


def _cases():
    for name in hero_tiles.QUICK_LINK_SETS:
        for on in (True, False):
            for deal in (True, False):
                yield (
                    f"{name}|{'on' if on else 'off'}|{'deal' if deal else 'nodeal'}",
                    name,
                    on,
                    deal,
                )


def snapshot(monkeypatch, data_for=lambda name: {"set": name}):
    from apps.promotions.models import Promotion

    if not Promotion._base_manager.filter(pk=DEAL_PK).exists():
        make_deal()
    got = {}
    for case, name, on, deal in _cases():
        modules_on(monkeypatch, on)
        Promotion._base_manager.filter(pk=DEAL_PK).update(status="active" if deal else "draft")
        got[case] = block_html(data_for(name), on)
    return got


def test_quick_links_storefront_byte_for_byte(monkeypatch):
    got = snapshot(monkeypatch)
    if UPDATE or not GOLDEN.exists():
        if not UPDATE:
            pytest.fail(f"нет снимка {GOLDEN.name}: FB33M35B_GOLDEN=update")
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(got, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
        return
    want = json.loads(GOLDEN.read_text())
    assert sorted(got) == sorted(want)
    for case in want:
        assert got[case] == want[case], f"плашки изменились: {case}"


def test_every_set_draws_tiles_with_modules_and_a_deal(monkeypatch):
    """Снимок не пустой: у каждого набора при включённых модулях и живой акции есть плитки."""
    got = snapshot(monkeypatch)
    for name in hero_tiles.QUICK_LINK_SETS:
        assert "data-block-quick-links" in got[f"{name}|on|deal"], name


FAQ = [
    {"q": "Wann haben Sie offen?", "a": "Mo–Fr 8–18 Uhr."},
    {"q": "Kann ich vorbestellen?", "a": "Ja, bis 18 Uhr."},
]
FAQ_RU = [{"q": "Когда открыто?", "a": "Пн–Пт 8–18."}, {"q": "Можно заказать заранее?"}]


@pytest.mark.parametrize("style", ("", "list", "twocol", "cards", "numbered"))
def test_faq_translation_is_drawn_by_position(style):
    """Перевод FAQ на витрине — позиционный оверлей (`localize`): частичный перевод берёт
    немецкий ответ своей позиции. Срез меняет только писателей, не витрину."""
    cfg = siteconfig.normalize({"faq": FAQ, "i18n": {"ru": {"faq": FAQ_RU}}})
    site = siteconfig.localize(cfg, "ru")
    assert [f["q"] for f in site["faq"]] == ["Когда открыто?", "Можно заказать заранее?"]
    assert site["faq"][1]["a"] == "Ja, bis 18 Uhr."
    req = RequestFactory().get("/")
    row = {"key": "faq", **({"style": style} if style else {})}
    tpl = Template("{% load siteui %}{% render_block b %}")
    html = tpl.render(Context({"request": req, "site": site, "b": row, "sample_wrapped": set()}))
    assert "Когда открыто?" in html and "Ja, bis 18 Uhr." in html
