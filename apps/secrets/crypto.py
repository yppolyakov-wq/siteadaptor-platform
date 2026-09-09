"""Симметричное шифрование секретов (Fernet).

Мастер-ключ — `settings.SECRETS_ENCRYPTION_KEY` (urlsafe-base64 32 байта, как
`Fernet.generate_key()`). Если не задан — детерминированный фолбэк из SECRET_KEY
(для dev/CI; в проде задаём отдельный ключ в .env). Расшифровка чужим ключом
даёт '' (а не падение), чтобы ротация/смена ключа не роняла приложение.
"""

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings


def _derived_key() -> bytes:
    """Производный ключ из SECRET_KEY (детерминированный) — dev/CI и легаси прода."""
    digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def _explicit_key() -> bytes | None:
    key = getattr(settings, "SECRETS_ENCRYPTION_KEY", "") or ""
    if not key:
        return None
    return key.encode() if isinstance(key, str) else key


def _previous_keys() -> list[bytes]:
    """Прежние явные ключи — ТОЛЬКО для чтения (смена ключа KEY1 → KEY2).

    Без них смена ключа означала бы, что всё зашифрованное перестаёт читаться, а
    `rotate_secrets` при этом честно отвечает «нечего ротировать»: ротация ищет
    то, что читается СТАРЫМ ключом, а старого ключа в связке нет.
    """
    raw = getattr(settings, "SECRETS_ENCRYPTION_KEY_PREVIOUS", None) or []
    if isinstance(raw, (str, bytes)):
        raw = [raw]
    out = []
    for key in raw:
        key = (key or "").strip() if isinstance(key, str) else key
        if key:
            out.append(key.encode() if isinstance(key, str) else key)
    return out


@lru_cache(maxsize=1)
def _fernet() -> MultiFernet:
    """P0-3 (аудит 2026-09-03 §9.3): явный ключ ПЕРВЫМ, производный — вторым.

    MultiFernet шифрует первым ключом и читает любым. Поэтому задать
    SECRETS_ENCRYPTION_KEY в проде безопасно: всё, что было зашифровано
    производным ключом (токены ботов, Meldeschein, документы), продолжает
    читаться, а новое уже не зависит от SECRET_KEY. Довести до конца —
    `manage.py rotate_secrets --apply`: перешифровывает старое явным ключом,
    после чего утечка SECRET_KEY ничего не раскрывает.
    """
    keys = []
    explicit = _explicit_key()
    if explicit:
        keys.append(Fernet(explicit))
    keys.extend(Fernet(key) for key in _previous_keys())
    keys.append(Fernet(_derived_key()))
    return MultiFernet(keys)


#: Все токены Fernet начинаются с версии 0x80 → в urlsafe-base64 это «gAAAAA».
_TOKEN_PREFIX = b"gAAAAA"

#: Состояния значения относительно текущей связки ключей.
CURRENT = "current"  # читается АКТУАЛЬНЫМ явным ключом — ротировать нечего
ROTATABLE = "rotatable"  # читается старым (производным/прежним явным) — под ротацию
UNREADABLE = "unreadable"  # похоже на наш шифротекст, но НИ ОДИН ключ его не читает
NOT_OURS = "not_ours"  # пусто или легаси-плейнтекст — не трогаем


def status(token) -> str:
    """Состояние значения. Отдельная функция, потому что «нечего ротировать» и
    «ничего не читается» — разные вещи: при смене ключа без
    SECRETS_ENCRYPTION_KEY_PREVIOUS второе выглядело бы как первое, и команда
    рапортовала бы «0 к перешифровке», пока прод молча читает всё как ''."""
    if not token:
        return NOT_OURS
    data = token.encode() if isinstance(token, str) else token
    explicit = _explicit_key()
    if explicit:
        # Конструктор — ВНЕ try: кривой ключ (hex вместо base64, python-repr)
        # должен падать, а не выдавать «нечего ротировать» или «нечитаемо».
        explicit_fernet = Fernet(explicit)
        try:
            explicit_fernet.decrypt(data)
            return CURRENT
        except (InvalidToken, ValueError, TypeError):
            pass
    # Связка строится ВНЕ try по той же причине, что и явный ключ выше: негодный
    # ПРЕЖНИЙ ключ должен падать ошибкой конфигурации, а не маскироваться под
    # «нечитаемо» (иначе команда сообщила бы про потерянные данные вместо того,
    # чтобы указать на кривую переменную).
    bundle = _fernet()
    try:
        bundle.decrypt(data)
        # Явного ключа нет — ротировать не во что, состояние «актуальное».
        return ROTATABLE if explicit else CURRENT
    except (InvalidToken, ValueError, TypeError):
        pass
    return UNREADABLE if data[: len(_TOKEN_PREFIX)] == _TOKEN_PREFIX else NOT_OURS


def needs_rotation(token) -> bool:
    """True — шифротекст читается старым ключом (производным или прежним явным).

    False — уже актуальным явным, явного ключа нет (ротировать не во что), пусто,
    не наш шифротекст, а также нечитаемое НИ ОДНИМ ключом: последнее — не работа
    для ротации, а сигнал о неверной конфигурации ключей (см. `status`).
    """
    return status(token) == ROTATABLE


def rotate_bytes(token: bytes) -> bytes:
    """Перешифровать явным ключом (MultiFernet.rotate) — для файлов документов."""
    return _fernet().rotate(token)


def encrypt(raw: str) -> str:
    if not raw:
        return ""
    return _fernet().encrypt(raw.encode()).decode()


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return ""


def encrypt_bytes(raw: bytes) -> bytes:
    """Шифротекст для БИНАРНОГО содержимого (MT-2: документы участников).

    Отдельная пара функций, а не encode/decode поверх строковых: файл может быть
    чем угодно, и превращать его в str по пути было бы ошибкой.
    """
    return _fernet().encrypt(raw)


def decrypt_bytes(token: bytes) -> bytes:
    """Расшифровать бинарь; чужой ключ/битый шифротекст → b'' (как decrypt)."""
    if not token:
        return b""
    try:
        return _fernet().decrypt(token)
    except (InvalidToken, ValueError):
        return b""


def try_decrypt(token: str) -> str | None:
    """Расшифровать или None, если значение не является нашим шифротекстом.

    Для прозрачных полей/конфигов: None = легаси-плейнтекст (читаем как есть,
    зашифруем при следующей записи)."""
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None
