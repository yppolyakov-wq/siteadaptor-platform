"""W9-7/W9-8 (аудит кабинета 2026-08-05): «Abläufe» + пресеты уведомлений.

- «Abläufe» сводит панели статусов/переходов/колонок доски в один экран
  (раньше — разбросаны: копия формы в списке заказов, у stays — мёртвый контекст).
- kind-селектор гейтится по активным модулям; неизвестный ?kind= → первый.
- Легаси-копия формы статусов в списке заказов удалена (остался мостик).
- W9-7: пресеты «Alle Kanäle aktivieren»/«Nur E-Mail» (JS по чекбоксам, серверная
  механика прежняя) + read-only статус бизнес-бота на экране уведомлений.
"""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


class _User:
    is_authenticated = True
    is_active = True
    username = "owner"


def _req(path="/dashboard/ablaeufe/", method="get", data=None, tenant=None):
    req = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = tenant or TenantFactory(business_type="restaurant")
    return req


# --- W9-8: экран «Abläufe» ----------------------------------------------------
def test_ablaeufe_renders_all_three_panels():
    body = views.ablaeufe_view(_req()).content.decode()
    assert "Status-Namen anpassen" in body  # FB-4a/b панель
    assert "Statusübergänge anpassen" in body  # FB-3 панель
    assert 'action="/dashboard/board/settings/"' in body  # W5 колонки доски
    assert "Eigene Status verwalten" in body  # вход в status-manager (Вариант B)


def test_ablaeufe_panels_post_to_active_kind_with_next_back():
    body = views.ablaeufe_view(_req("/dashboard/ablaeufe/?kind=order")).content.decode()
    assert 'action="/dashboard/status-labels/order/"' in body
    assert 'action="/dashboard/status-transitions/order/"' in body
    # next= возвращает на этот же экран (с выбранным kind)
    assert 'name="next" value="/dashboard/ablaeufe/?kind=order"' in body


def test_ablaeufe_kind_gating_and_fallback():
    # У отеля активен stays → вкладка Übernachtungen и панель stay.
    hotel = TenantFactory(business_type="hotel")
    body = views.ablaeufe_view(
        _req("/dashboard/ablaeufe/?kind=stay", tenant=hotel)
    ).content.decode()
    assert 'action="/dashboard/status-labels/stay/"' in body
    # Неизвестный kind → первый активный (не 500, не пустая страница).
    body = views.ablaeufe_view(_req("/dashboard/ablaeufe/?kind=bogus")).content.decode()
    assert 'action="/dashboard/status-labels/' in body


def test_board_settings_returns_to_next_local_path_only():
    tenant = TenantFactory(business_type="restaurant")
    resp = views.board_settings(
        _req(
            "/dashboard/board/settings/",
            "post",
            {"next": "/dashboard/ablaeufe/?kind=order"},
            tenant=tenant,
        )
    )
    assert resp.status_code == 302
    assert resp["Location"] == "/dashboard/ablaeufe/?kind=order"
    # Внешний/протокол-относительный next не принимается — дефолт (доска).
    resp = views.board_settings(
        _req("/dashboard/board/settings/", "post", {"next": "//evil.example/x"}, tenant=tenant)
    )
    assert resp["Location"].startswith("/dashboard/board/")


def test_verkaeufe_links_to_ablaeufe():
    body = views.verkaeufe(_req("/dashboard/verkaeufe/")).content.decode()
    assert "/dashboard/ablaeufe/" in body


def test_order_list_legacy_page_is_redirect():
    """W9-8 убрал копию формы статусов; W10-6 схлопнул страницу целиком —
    легаси-список заказов теперь 302 на Verkäufe (вход в Abläufe — с неё)."""
    from apps.orders import views as orders_views

    resp = orders_views.order_list(_req("/dashboard/orders/"))
    assert resp.status_code == 302
    assert resp["Location"].startswith("/dashboard/verkaeufe/")


# --- W9-7: уведомления — пресеты + статус бота --------------------------------
def test_notifications_has_presets_and_no_bot_line_without_bot():
    body = views.notifications_settings(_req("/dashboard/settings/notifications/")).content.decode()
    assert 'data-notify-preset="all"' in body
    assert 'data-notify-preset="email"' in body
    assert "Aktiver Bot:" not in body  # бота нет — строки статуса нет


def test_notifications_shows_active_bot_readonly():
    from apps.telegram.models import TelegramBot

    TelegramBot.objects.create(token="123:abc", bot_username="demo_bot", is_active=True)
    body = views.notifications_settings(_req("/dashboard/settings/notifications/")).content.decode()
    assert "Aktiver Bot:" in body
    assert "@demo_bot" in body
    assert "/dashboard/telegram/" in body  # ссылка «Bot verwalten»
