# Production image: Django (gunicorn) + Celery worker/beat используют один образ.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    DJANGO_SETTINGS_MODULE=config.settings.production

WORKDIR /app

# curl — для healthcheck; gettext — compilemessages (L4, переводы писем);
# fonts-dejavu-core — шрифт с кириллицей для PDF (I18N-7b): встроенного в
# reportlab Helvetica хватает только на WinAnsi, ru/uk/tr вышли бы рваными.
# Остальное тянется бинарными wheels (psycopg[binary], pillow).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gettext fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# uv для установки зависимостей. Версия закреплена: `latest` сверялся по сети
# на каждой сборке (T-10).
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv

# T-10: сначала ТОЛЬКО зависимости — строго по uv.lock (как в CI), отдельным слоем.
# Раньше `COPY . .` стоял до установки, и любая правка кода переустанавливала все
# пакеты на каждом деплое. Теперь слой пересобирается, только когда меняется лок.
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-emit-project --no-hashes -o /tmp/requirements.txt \
    && uv pip install --system --no-cache -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# Затем код. Сам проект ставится без зависимостей (они уже стоят); PYTHONPATH=/app
# гарантирует приоритет исходников в /app (templates/static/locale рядом с кодом).
COPY . .
RUN uv pip install --system --no-cache --no-deps .

# T1-b: .mo не в git — компилируем В ОБРАЗ. Раньше deploy.sh делал compilemessages
# через `compose run --rm` → .mo умирали вместе с временным контейнером, и в проде
# переводы молча не работали. msgfmt settings-free (gettext установлен выше).
RUN for po in locale/*/LC_MESSAGES/django.po; do msgfmt -o "${po%.po}.mo" "$po"; done

EXPOSE 8000

# Дефолтная команда — web; worker/beat переопределяют command в compose.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]
