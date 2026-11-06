"""AIS A-3b: техподдержка доходит в обе стороны.

Найдено планом A-3: ответ платформы из админки сохранялся инлайном мимо
`services.add_message` → `unread_for_owner` не ставился, владелец ответа не видел; о новом
обращении платформа не узнавала (только список в админке). Теперь:
* ответ из админки — роль platform (подделать «owner» нельзя), флаги треда, письмо владельцу;
* новое обращение/ответ владельца — письмо на SUPPORT_NOTIFY_EMAIL без текста обращения
  (в админке он есть), не чаще одного письма на тред в окно;
* письма — через notify(dedupe_key=…), повтор не шлёт второе.
"""

import pytest
from django.contrib.admin.sites import site
from django.test import RequestFactory, override_settings

from apps.notifications.models import Notification
from apps.support import services
from apps.support.admin import SupportThreadAdmin
from apps.support.models import SupportMessage, SupportThread
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _immediate_on_commit(monkeypatch):
    from django.db import transaction

    monkeypatch.setattr(transaction, "on_commit", lambda fn, using=None: fn())
    from apps.notifications import tasks

    monkeypatch.setattr(tasks.send_notification, "delay", lambda **kw: None)


def _tenant():
    return TenantFactory(name="Bäckerei Krume", contact_email="chef@krume.test")


@override_settings(SUPPORT_NOTIFY_EMAIL="support@platform.test")
def test_new_thread_notifies_platform_without_body():
    thread = services.open_thread(tenant=_tenant(), subject="Kasse", body="GEHEIMTEXT 123")
    note = Notification.objects.get(recipient="support@platform.test")
    assert "Bäckerei Krume" in note.subject and "Kasse" in note.subject
    assert "GEHEIMTEXT" not in note.subject + str(note.payload)
    assert f"/admin/support/supportthread/{thread.pk}/change/" in note.payload["body"]


@override_settings(SUPPORT_NOTIFY_EMAIL="support@platform.test")
def test_owner_follow_ups_do_not_spam_the_platform():
    thread = services.open_thread(tenant=_tenant(), subject="Kasse", body="eins")
    services.add_message(thread, body="zwei", author_role=SupportMessage.AUTHOR_OWNER)
    services.add_message(thread, body="drei", author_role=SupportMessage.AUTHOR_OWNER)
    assert Notification.objects.filter(recipient="support@platform.test").count() == 1


def test_platform_reply_notifies_owner_with_link():
    tenant = _tenant()
    thread = services.open_thread(tenant=tenant, subject="Kasse", body="Frage")
    msg = services.add_message(thread, body="Antwort", author_role=SupportMessage.AUTHOR_PLATFORM)
    note = Notification.objects.get(recipient="chef@krume.test")
    assert "Kasse" in note.subject
    assert f"/dashboard/help/{thread.pk}/" in note.payload["body"]
    # повтор того же сообщения не шлёт второе письмо
    services.notify_owner(thread, msg)
    assert Notification.objects.filter(recipient="chef@krume.test").count() == 1


def _admin_save(thread, rows):
    """Сохранить инлайн админки так, как это делает форма (через save_formset)."""
    from django.contrib.auth import get_user_model

    admin = SupportThreadAdmin(SupportThread, site)
    request = RequestFactory().post("/admin/")
    request.user = get_user_model().objects.create_superuser("root-a3", "r@t.de", "pw12345678")
    inline = admin.get_inline_instances(request, thread)[0]
    FormSet = inline.get_formset(request, thread)
    prefix = FormSet.get_default_prefix()
    existing = list(thread.messages.order_by("pk"))
    data = {
        f"{prefix}-TOTAL_FORMS": str(len(existing) + len(rows)),
        f"{prefix}-INITIAL_FORMS": str(len(existing)),
        f"{prefix}-MIN_NUM_FORMS": "0",
        f"{prefix}-MAX_NUM_FORMS": "1000",
    }
    for i, msg in enumerate(existing):
        data.update({f"{prefix}-{i}-id": str(msg.pk), f"{prefix}-{i}-body": msg.body})
        data[f"{prefix}-{i}-thread"] = str(thread.pk)
    for j, row in enumerate(rows, start=len(existing)):
        for key, value in row.items():
            data[f"{prefix}-{j}-{key}"] = value
    formset = FormSet(data=data, instance=thread, prefix=prefix)
    assert formset.is_valid(), formset.errors
    form = admin.get_form(request, thread)(instance=thread)
    admin.save_formset(request, form, formset, change=True)


def test_admin_reply_is_platform_and_marks_unread_for_owner():
    tenant = _tenant()
    thread = services.open_thread(tenant=tenant, subject="Kasse", body="Frage")
    _admin_save(thread, [{"body": "Bitte neu starten", "author_role": "owner"}])
    thread.refresh_from_db()
    reply = thread.messages.order_by("-pk").first()
    assert reply.author_role == SupportMessage.AUTHOR_PLATFORM  # «owner» из POST не прошёл
    assert thread.unread_for_owner and not thread.unread_for_platform
    assert Notification.objects.filter(recipient="chef@krume.test").exists()


def test_notification_failure_does_not_break_the_thread(monkeypatch):
    from apps.notifications import services as nsvc

    def boom(**kw):
        raise RuntimeError("mail down")

    monkeypatch.setattr(nsvc, "notify", boom)
    thread = services.open_thread(tenant=_tenant(), subject="Kasse", body="Frage")
    assert thread.pk and thread.messages.count() == 1


def test_support_open_in_lite_package_and_mini_app():
    from apps.core import packages, tg_login

    assert {"support:help", "support:thread"} <= set(tg_login.TG_LITE_VIEWS)
    assert {"support:help", "support:thread"} <= set(packages._AKTIONEN_VIEWS)


# ── ревью A-3b (silent-failure + security) ──


@override_settings(SUPPORT_NOTIFY_EMAIL="support@platform.test")
def test_newline_in_subject_or_company_does_not_kill_the_email():
    tenant = TenantFactory(name="Krume\nBcc: evil@x.test", contact_email="chef@krume.test")
    thread = services.open_thread(tenant=tenant, subject="Kasse\r\nhängt", body="x")
    assert "\n" not in thread.subject and "\r" not in thread.subject
    note = Notification.objects.get(recipient="support@platform.test")
    assert "\n" not in note.subject and "\r" not in note.subject


def test_admin_does_not_rewrite_sent_messages():
    tenant = _tenant()
    thread = services.open_thread(tenant=tenant, subject="Kasse", body="Original vom Inhaber")
    first = thread.messages.get()
    from django.contrib.auth import get_user_model

    admin = SupportThreadAdmin(SupportThread, site)
    request = RequestFactory().post("/admin/")
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.contrib.sessions.middleware import SessionMiddleware

    SessionMiddleware(lambda r: None).process_request(request)
    request._messages = FallbackStorage(request)
    request.user = get_user_model().objects.create_superuser("root-a3b", "r2@t.de", "pw12345678")
    inline = admin.get_inline_instances(request, thread)[0]
    FormSet = inline.get_formset(request, thread)
    prefix = FormSet.get_default_prefix()
    data = {
        f"{prefix}-TOTAL_FORMS": "1",
        f"{prefix}-INITIAL_FORMS": "1",
        f"{prefix}-MIN_NUM_FORMS": "0",
        f"{prefix}-MAX_NUM_FORMS": "1000",
        f"{prefix}-0-id": str(first.pk),
        f"{prefix}-0-thread": str(thread.pk),
        f"{prefix}-0-body": "UMGESCHRIEBEN",
    }
    formset = FormSet(data=data, instance=thread, prefix=prefix)
    assert formset.is_valid(), formset.errors
    admin.save_formset(request, admin.get_form(request, thread)(instance=thread), formset, True)
    first.refresh_from_db()
    assert first.body == "Original vom Inhaber"
