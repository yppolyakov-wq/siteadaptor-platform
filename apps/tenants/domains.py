"""Self-service custom-доменов: валидация заявки и подтверждение владения.

Владение доказывается тем, что A-запись домена указывает на наш сервер
(`CUSTOM_DOMAIN_TARGET_IP`). Только после этого создаём django-tenants `Domain`
(роутинг + авторизация TLS у Caddy on-demand). Пока не подтверждено — домен
нигде не маршрутизируется, поэтому занять чужой домен на платформе нельзя.
"""

import re
import socket

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import CustomDomain, Domain

# RFC-1123 hostname без trailing dot, минимум один разделитель (apex или поддомен).
_HOST_RE = re.compile(r"^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+$")


class DomainError(ValueError):
    """Заявка отклонена; текст пригоден для показа владельцу."""


def normalize_domain(raw: str) -> str:
    domain = (raw or "").strip().lower().rstrip(".")
    domain = re.sub(r"^https?://", "", domain).split("/")[0]  # вставили целый URL
    return domain.split(":")[0]  # и порт


def validate_new_domain(raw: str) -> str:
    """Нормализовать + проверить домен заявки; вернуть его или бросить DomainError."""
    domain = normalize_domain(raw)
    if not _HOST_RE.match(domain):
        raise DomainError(_("Ungültiger Domainname."))
    if all(part.isdigit() for part in domain.split(".")):
        raise DomainError(_("Bitte eine Domain angeben, keine IP-Adresse."))
    base = getattr(settings, "TENANT_DOMAIN_BASE", "siteadaptor.de").split(":")[0]
    if domain == base or domain.endswith("." + base):
        raise DomainError(
            _("Subdomains von %(base)s werden automatisch vergeben.") % {"base": base}
        )
    if Domain.objects.filter(domain=domain).exists():
        raise DomainError(_("Diese Domain ist bereits vergeben."))
    if CustomDomain.objects.filter(domain=domain).exists():
        raise DomainError(_("Diese Domain wurde bereits hinzugefügt."))
    return domain


def _resolve_ipv4(domain: str, timeout: float = 5.0) -> list[str]:
    """A-записи домена (или [] при ошибке/таймауте). Системный резолвер, stdlib."""
    socket.setdefaulttimeout(timeout)
    try:
        infos = socket.getaddrinfo(domain, None, family=socket.AF_INET)
    except OSError:
        return []
    finally:
        socket.setdefaulttimeout(None)
    return sorted({info[4][0] for info in infos})


def verify(custom: CustomDomain) -> bool:
    """Проверить A-запись; при совпадении активировать (создать Domain row).

    Не подтвердилось → статус остаётся pending с понятной ошибкой (DNS может
    распространяться). Сервер без CUSTOM_DOMAIN_TARGET_IP → failed.
    """
    target = getattr(settings, "CUSTOM_DOMAIN_TARGET_IP", "").strip()
    if not target:
        return _fail(custom, _("Server nicht konfiguriert. Bitte Support kontaktieren."))

    ips = _resolve_ipv4(custom.domain)
    if not ips:
        return _pending(custom, _("Domain löst noch nicht auf (DNS kann bis 24 h dauern)."))
    if target not in ips:
        return _pending(
            custom,
            _("Domain zeigt auf %(ips)s, erwartet %(target)s.")
            % {"ips": ", ".join(ips), "target": target},
        )

    with transaction.atomic():
        Domain.objects.get_or_create(
            domain=custom.domain,
            defaults={"tenant": custom.tenant, "is_primary": False},
        )
        custom.status = CustomDomain.ACTIVE
        custom.last_check_error = ""
        custom.verified_at = timezone.now()
        custom.save(update_fields=["status", "last_check_error", "verified_at", "updated_at"])
    return True


def remove(custom: CustomDomain) -> None:
    """Отвязать домен: удалить Domain row (роутинг/TLS) и саму заявку."""
    Domain.objects.filter(domain=custom.domain, tenant=custom.tenant).delete()
    custom.delete()


def _pending(custom: CustomDomain, error: str) -> bool:
    custom.status = CustomDomain.PENDING
    custom.last_check_error = error
    custom.save(update_fields=["status", "last_check_error", "updated_at"])
    return False


def _fail(custom: CustomDomain, error: str) -> bool:
    custom.status = CustomDomain.FAILED
    custom.last_check_error = error
    custom.save(update_fields=["status", "last_check_error", "updated_at"])
    return False
