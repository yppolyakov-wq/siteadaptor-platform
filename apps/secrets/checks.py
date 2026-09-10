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

import re

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.checks import Error, Tags, Warning, register


def _key() -> str:
    return getattr(settings, "SECRETS_ENCRYPTION_KEY", "") or ""


#: Ключ целиком = base64-токен. ОБА алфавита законны: Fernet принимает и
#: urlsafe («-_», как у Fernet.generate_key()), и стандартный («+/», как у
#: `openssl rand -base64 32`). Всё, что вне этого набора (запятая, пробел,
#: комментарий, кавычки, префикс b'), — хвост, а не ключ.
_TOKEN_RE = re.compile(rb"[A-Za-z0-9+/_-]+={0,2}\Z")


def _key_problem(value) -> str:
    """Причина непригодности ключа или '' — если ключ годен.

    Помимо конструктора Fernet ловим «хвост после base64-паддинга»: декодер
    останавливается на `=`, поэтому `Fernet("KEY2,KEY1")` побайтово равен
    `Fernet("KEY2")` — перечислить оба ключа через запятую (соседняя переменная
    именно список!) или оставить хвостовой комментарий значило бы молча
    использовать только первый, а чек рапортовал бы «годен».

    Проверяем именно ХВОСТ, а не канонический алфавит: сравнение с
    `urlsafe_b64encode(urlsafe_b64decode(...))` отвергало РАБОЧИЕ ключи из
    `openssl rand -base64 32` (в них «+»/«/» примерно в трёх случаях из четырёх),
    причём с ложным диагнозом «лишнее после ключа» — и владелец, следуя подсказке,
    обрезал бы рабочий ключ, потеряв доступ ко всем шифротекстам.
    """
    raw = value.encode() if isinstance(value, str) else value
    try:
        Fernet(raw)
    except (ValueError, TypeError) as exc:
        return str(exc)
    if not isinstance(raw, bytes) or not _TOKEN_RE.fullmatch(raw.strip()):
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

    previous_keys = crypto._previous_keys()
    if previous_keys and not key:
        issues.append(
            Error(
                "SECRETS_ENCRYPTION_KEY_PREVIOUS задан, а SECRETS_ENCRYPTION_KEY пуст.",
                hint=(
                    "Прежние ключи — только для чтения. Без актуального ключа новые "
                    "секреты шифровались бы производным из SECRET_KEY, а смена ключа "
                    "выглядела бы выполненной. Задайте SECRETS_ENCRYPTION_KEY."
                ),
                id="secrets.E004",
            )
        )
    for i, previous in enumerate(previous_keys, 1):
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
