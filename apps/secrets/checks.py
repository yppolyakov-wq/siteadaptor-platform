"""Django-чеки боевого конфига шифрования секретов.

Их два, и они отвечают на РАЗНЫЕ вопросы:

* `secrets_encryption_key_set` (deploy-only) — ключ вообще задан? В dev/CI
  фолбэк из SECRET_KEY допустим намеренно, поэтому шуметь там нечем; в проде
  отсутствие отдельного ключа — риск: утечка SECRET_KEY раскрывает все секреты.
* `secrets_encryption_key_valid` (обычный чек, ЛЮБОЕ окружение) — заданный ключ
  пригоден? Негодное значение ломает приложение везде и молча: чтение отдаёт ''
  (decrypt глотает ValueError), запись падает 500 (encrypt не глотает). Ждать
  деплоя, чтобы это заметить, нельзя — `manage.py check` и старт runserver
  обязаны краснеть сразу.
"""

import base64

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.checks import Error, Tags, Warning, register


def _key() -> str:
    return getattr(settings, "SECRETS_ENCRYPTION_KEY", "") or ""


def _key_problem(value) -> str:
    """Причина непригодности ключа или '' — если ключ годен.

    Помимо конструктора Fernet ловим «хвост после base64-паддинга»: декодер
    останавливается на `=`, поэтому `Fernet("KEY2,KEY1")` побайтово равен
    `Fernet("KEY2")` — перечислить оба ключа через запятую (соседняя переменная
    именно список!) или оставить хвостовой комментарий значило бы молча
    использовать только первый, а чек рапортовал бы «годен».
    """
    raw = value.encode() if isinstance(value, str) else value
    try:
        Fernet(raw)
    except (ValueError, TypeError) as exc:
        return str(exc)
    try:
        canonical = base64.urlsafe_b64encode(base64.urlsafe_b64decode(raw))
    except Exception:  # noqa: BLE001 — Fernet уже принял, до сюда не доходит
        return ""
    if canonical != (raw.strip() if isinstance(raw, bytes) else raw):
        return (
            "значение содержит лишнее после ключа (запятая, пробел, комментарий) — "
            "использовалась бы только первая часть"
        )
    return ""


@register(Tags.security)
def secrets_encryption_key_valid(app_configs, **kwargs):
    """Ключ задан, но не является ключом Fernet → Error в любом окружении.

    Естественные способы «сгенерировать ключ» дают непригодное значение:
    `openssl rand -hex 32` (64 hex = 32 байта ПОСЛЕ hex-декода, но Fernet ждёт
    base64), скопированный python-repr `b'…='`, плейсхолдер CHANGE-ME из шаблона
    окружения. Прежний гейт проверял только непустоту — деплой рапортовал успех,
    а в проде интеграции молча умирали.
    """
    hint = (
        "Нужны 32 байта в urlsafe-base64, ОДНО значение. Сгенерировать: python -c "
        '"from cryptography.fernet import Fernet; '
        "print(Fernet.generate_key().decode())\". Значение без префикса b'…' и без "
        "хвоста. Старый ключ при смене — в SECRETS_ENCRYPTION_KEY_PREVIOUS (список "
        "через запятую). Не нужен ключ в dev? Оставьте переменную ПУСТОЙ — тогда "
        "работает производный ключ из SECRET_KEY."
    )
    issues = []
    key = _key()
    if key:  # «не задан» — вопрос другого чека (deploy-only)
        problem = _key_problem(key)
        if problem:
            issues.append(
                Error(
                    f"SECRETS_ENCRYPTION_KEY непригоден: {problem}",
                    hint=hint,
                    id="secrets.E002",
                )
            )
    # Прежние ключи — тот же класс значения и тот же способ ошибиться. Без этой
    # проверки негодный прежний ключ проходил деплой зелёным, а потом каждый
    # вызов `_fernet()` бросал ValueError: гостевой Online-Checkin, сохранение
    # токена бота и загрузка документа падали 500, чтение молча отдавало пусто.
    from apps.secrets import crypto

    for i, previous in enumerate(crypto._previous_keys(), 1):
        problem = _key_problem(previous)
        if problem:
            issues.append(
                Error(
                    f"SECRETS_ENCRYPTION_KEY_PREVIOUS[{i}] непригоден: {problem}",
                    hint=hint,
                    id="secrets.E003",
                )
            )
    return issues


@register(Tags.security, deploy=True)
def secrets_encryption_key_set(app_configs, **kwargs):
    if _key():
        return []
    msg = (
        "SECRETS_ENCRYPTION_KEY не задан — ключ шифрования секретов выводится из "
        "SECRET_KEY (детерминированный фолбэк)."
    )
    hint = (
        "В проде задайте отдельный SECRETS_ENCRYPTION_KEY (Fernet.generate_key()) "
        "в .env.prod: иначе утечка SECRET_KEY раскрывает все зашифрованные секреты "
        "(токены ботов, OAuth-токены, ключи интеграций)."
    )
    # Fail-closed в проде (DEBUG=False): `manage.py check --deploy` завершится с
    # ошибкой → деплой-пайплайн ловит отсутствие ключа. В dev/CI фолбэк намеренно
    # допустим, поэтому там — предупреждение.
    if settings.DEBUG:
        return [Warning(msg, hint=hint, id="secrets.W001")]
    return [Error(msg, hint=hint, id="secrets.E001")]
