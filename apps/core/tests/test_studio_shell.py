"""ST-3 → STU-12a: Studio-оболочка.

ST-3 (2026-07-19) переупаковал хром в рейку уровней + page-ленту; STU-12a
(2026-09-09, решение владельца «Убрать») снёс рейку, ленту страниц и вкладки
областей: страницу выбирает «Seite ▾» в верхней строке, глобальный дизайн —
ссылка «Design des Shops →» на экран кабинета, колонка настроек одна и открыта
по умолчанию. Существующие id билдера НЕ переименованы (их держат замки
test_home_builder); брендинг «Studio» и кросс-фейд свопа остались.
"""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views as core_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _html(tenant):
    request = RequestFactory().get("/dashboard/site/home/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    o = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
    )
    request.tenant = tenant
    return core_views.home_builder_view(request).content.decode()


def test_studio_shell_without_rail_renders():
    tenant = TenantFactory(slug="stsh", name="StSh", business_type="bakery")
    html = _html(tenant)
    # STU-12a: рейки уровней и ленты страниц нет — их работу несут верхняя строка
    # («Seite ▾» + «Design des Shops →») и клик по канве.
    assert 'id="st-rail"' not in html and "data-st-level=" not in html
    assert 'id="st-pages"' not in html
    assert 'id="st-page-switch"' in html and 'id="st-design-link"' in html
    assert ">Studio</span>" in html  # брендинг в топ-баре
    # кросс-фейд врезан в swapPreview
    assert "transition:opacity" in html
    # существующие якоря хрома целы (замки старого билдера)
    assert 'id="bld-root"' in html and 'id="bld-editor-pane"' in html
    assert 'id="bld-area-tabs"' not in html  # вкладок областей тоже нет
    assert 'id="home-prev-frame"' in html
