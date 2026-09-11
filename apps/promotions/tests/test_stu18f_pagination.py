"""STU-18f: пагинация обзора акций (решение владельца 2026-09-11).

«Пагинация нужна только на странице с каталогами / акциями» — у каталога она есть
(keyset, размер из «Pro Seite»), у `/aktionen/` не было. План — §12
`docs/stu18-panel-ia-plan-2026-09-10.md`.

Замки написаны ДО кода и краснеют на текущем: выдача уходит в шаблон целиком.
Главный из них — первый: без ключа `page_size` живая витрина не меняется.
"""

import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.promotions import public_views
from apps.promotions.models import Promotion
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(page_size=None, **cfg_extra):
    tenant = TenantFactory(
        schema_name="public", slug=f"stu18f{uuid.uuid4().hex[:6]}", disabled_modules=[]
    )
    cfg = dict(tenant.site_config or {})
    if page_size:
        cfg["promo_index_layout"] = {"preset": "cols3", "page_size": page_size}
    cfg.update(cfg_extra)
    tenant.site_config = cfg
    tenant.save(update_fields=["site_config"])
    return tenant


def _promos(n, group=""):
    now = timezone.now()
    for i in range(n):
        Promotion.objects.create(
            title={"de": f"Deal {i}"},
            status="active",
            group=group,
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=10),
        )


def _page(tenant, query=""):
    req = RequestFactory().get(f"/aktionen/{query}")
    req.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.9"
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=False)
    req.tenant = tenant
    resp = public_views.promotion_list(req)
    assert resp.status_code == 200
    return resp.content.decode()


def test_without_the_key_nothing_changes():
    """Инвариант волны LAY: нет «Pro Seite» — показываем всё и без разметки страниц."""
    tenant = _tenant()
    _promos(5)
    body = _page(tenant, "?q=Deal")  # плоский вид (поиск активен)
    for i in range(5):
        assert f"Deal {i}" in body
    assert "data-promo-pages" not in body


def test_page_size_slices_the_flat_list():
    tenant = _tenant(page_size=6)
    _promos(9)
    body = _page(tenant, "?q=Deal")
    assert "data-promo-pages" in body, "нет разметки страниц"
    shown = [i for i in range(9) if f"Deal {i}" in body]
    assert len(shown) == 6, f"на странице {len(shown)} акций вместо 6"
    second = _page(tenant, "?q=Deal&seite=2")
    shown2 = [i for i in range(9) if f"Deal {i}" in second]
    assert len(shown2) == 3, f"на второй странице {len(shown2)} вместо 3"
    assert not set(shown) & set(shown2), "страницы пересекаются"


def test_switching_a_facet_returns_to_the_first_page():
    """Посетитель применил фильтр на 3-й странице — он не должен попасть в пустоту."""
    tenant = _tenant(page_size=6)
    _promos(9)
    body = _page(tenant, "?q=Deal&seite=2")
    assert "seite=2" not in body.split("data-promo-pages")[0], (
        "ссылки фасетов/сорта тащат номер страницы"
    )


def test_sections_view_is_not_paginated():
    """Вид секциями — витрина-обзор: у каждой секции свой вход на страницу группы.

    Размер берём ДОПУСТИМЫЙ (нормализатор клампит «Pro Seite» в 6..96): с меньшим
    ключ не сохраняется вовсе, и замок был бы холостым — поймано на соседнем тесте.
    """
    tenant = _tenant(page_size=6)
    _promos(8, group="Wochenangebote")
    body = _page(tenant)
    assert "data-promo-pages" not in body
    shown = [i for i in range(8) if f"Deal {i}" in body]
    assert len(shown) == 8, "секции обрезаны пагинацией"


def test_panel_offers_page_size_on_the_promotions_page():
    """STU-9 в обе стороны: страница пагинируется ⇒ «Pro Seite» обязана быть в панели.

    Ключ у обзора и у страницы группы один (`promo_index_layout`), поэтому строка
    одна — но она обязана нести маркер пагинации, иначе поле скрыто скриптом.
    """
    markup = open("templates/tenant/site_home.html", encoding="utf-8").read()
    row = markup[markup.index('field="promo_index_preset"') :][:200]
    assert "paginates=1" in row, "ось акций не помечена как пагинируемая"
    # у листингов, которые НЕ пагинируются, маркера быть не должно
    for field in ("combos_preset", "tours_preset", "blog_index_preset", "service_preset"):
        other = markup[markup.index(f'field="{field}"') :][:200]
        assert "paginates=1" not in other, f"{field}: обещание пагинации без исполнения"


def test_group_page_is_paginated():
    """Обещание плана §12: у секции есть вход «Alle anzeigen →» на страницу группы —
    и она плоская, значит режется на страницы тем же ключом."""
    tenant = _tenant(page_size=6)
    _promos(9, group="Wochenangebote")
    body = _page(tenant, "?gruppe=Wochenangebote")
    assert "data-promo-pages" in body
    shown = [i for i in range(9) if f"Deal {i}" in body]
    assert len(shown) == 6, f"на странице группы {len(shown)} акций вместо 6"


def test_counters_show_the_whole_result_not_the_page():
    """Находка стенда: с «Pro Seite» = 6 и девятью акциями страница писала «6 offers».

    Счётчик — про всю выдачу; иначе посетитель не знает, что на второй странице
    ждут ещё три.
    """
    tenant = _tenant(page_size=6)
    _promos(9)
    body = _page(tenant, "?q=Deal")
    assert "data-promo-pages" in body
    count = body.split("data-result-count>")[1].split("<")[0].strip()
    assert count.startswith("9"), f"счётчик показывает «{count}» вместо всей выдачи"
