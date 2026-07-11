# syntax=docker/dockerfile:1
# Production image: Django (gunicorn) + Celery worker/beat используют один образ.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    DJANGO_SETTINGS_MODULE=config.settings.production

WORKDIR /app

# curl — для healthcheck; gettext — compilemessages (L4, переводы писем);
# остальное тянется бинарными wheels (psycopg[binary], pillow).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gettext \
    && rm -rf /var/lib/apt/lists/*

# uv для установки зависимостей.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Сначала зависимости (слой кэшируется), затем код.
COPY pyproject.toml ./
COPY . .

# Ставит зависимости из pyproject. PYTHONPATH=/app гарантирует, что
# приоритет у исходников в /app (templates/static/locale рядом с кодом).
RUN uv pip install --system --no-cache .

# T1-b: .mo не в git — компилируем В ОБРАЗ. Раньше deploy.sh делал compilemessages
# через `compose run --rm` → .mo умирали вместе с временным контейнером, и в проде
# переводы молча не работали. msgfmt settings-free (gettext установлен выше).
RUN for po in locale/*/LC_MESSAGES/django.po; do msgfmt -o "${po%.po}.mo" "$po"; done

EXPOSE 8000

# Дефолтная команда — web; worker/beat переопределяют command в compose.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]
