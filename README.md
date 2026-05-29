# Platform

Multi-tenant SaaS for small offline businesses (DACH): own mini-site, customer base,
promotions with reservations, auto-publishing to channels, local aggregator.

See `docs/` for full vision and Phase 1 spec.

> 👉 **Start here:** [`docs/DEVELOPMENT-GUIDE.md`](docs/DEVELOPMENT-GUIDE.md) — единая
> пошаговая инструкция: setup, полный чеклист задач по спринтам (план + дополнения),
> git-флоу, деплой и команды.

## Stack

Python 3.12+ · Django 5.1 · django-tenants (schema-per-tenant) · PostgreSQL 16 ·
Redis 7 · Celery 5 · HTMX + Alpine + Tailwind · django-allauth · dj-stripe ·
django-unfold · Hetzner Cloud (EU) · Caddy 2.

## Local setup

```bash
# 1. uv (one-off)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. venv + deps
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# 3. infra
docker compose up -d db redis

# 4. env
cp .env.example .env

# 5. (after apps созданы) миграции
python manage.py makemigrations tenants
python manage.py migrate_schemas --shared
python manage.py createsuperuser

# 6. dev server
python manage.py runserver 0.0.0.0:8000

# В отдельном терминале:
celery -A config worker -l info
```

Admin: http://localhost:8000/admin/

## Project structure

```
platform/
├── config/                     # Django project
│   ├── settings/{base,development,production}.py
│   ├── urls_public.py          # SHARED schema (aggregator, main domain)
│   ├── urls_tenant.py          # TENANT schema (*.platform.com)
│   ├── celery.py
│   └── {wsgi,asgi}.py
├── apps/                       # Django apps (создаются по спринтам)
│   ├── tenants/                # SHARED
│   ├── core/                   # TENANT
│   ├── catalog/                # TENANT
│   ├── promotions/             # TENANT
│   ├── subscriptions/          # TENANT
│   ├── publishing/             # TENANT
│   ├── notifications/          # TENANT
│   ├── billing/                # TENANT
│   ├── aggregator/             # SHARED
│   └── global_categories/      # SHARED
├── templates/
├── static/
├── locale/
├── caddy/Caddyfile
├── docker-compose.yml
├── pyproject.toml
└── manage.py
```

## Phase 1 sprints

См. `docs/phase1-implementation-guide.md` и `docs/phase1-plan-additions.md`.

1. Foundation & multi-tenancy
2. Catalog & tenant dashboard
3. Promotions & reservations
4. Publishing engine & landing pages
5. Aggregator & customer experience
6. Notifications, billing & launch
