# Sprint 1: стартовые промпты для Claude Code

## Как использовать этот документ

1. **Перед стартом** — создай пустой Git репозиторий локально и инициализируй его. Промпт ниже предполагает, что Claude Code работает в этом репо.
2. **Открой Claude Code** в директории репозитория (`claude` в терминале).
3. **Скопируй артефакт архитектуры** (`platform-core-architecture`) и артефакт Phase 1 (`phase1-implementation-guide`) в контекст: положи их в файлы `docs/architecture.md` и `docs/phase1-plan.md` соответственно.
4. **Дай Claude Code Bootstrap промпт ниже** — это первое сообщение в сессии.
5. **После Bootstrap** — последовательно прогоняй Task 1.1, 1.2, 1.3, 1.4, 1.5 в **отдельных сессиях** или с явным `/clear` между ними.
6. **Между задачами** — запускай локально, проверяй, что работает, делай commit.

---

## Перед первой сессией: подготовка локально

```bash
# 1. Создать репозиторий
mkdir minimarket-platform && cd minimarket-platform
git init
git branch -m main

# 2. Скопировать архитектурные документы
mkdir docs
# Скопируй сюда содержимое артефактов:
#   docs/architecture.md      (артефакт platform-core-architecture)
#   docs/phase1-plan.md       (артефакт phase1-implementation-guide)
#   docs/monetization.md      (артефакт monetization-unit-economics, опционально)

# 3. Создать базовый .gitignore
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
.venv/
venv/
env/

# Django
*.log
local_settings.py
db.sqlite3
db.sqlite3-journal
media/
staticfiles/

# Environment
.env
.env.local
.env.*.local

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Docker
.docker/

# Coverage
htmlcov/
.coverage
.coverage.*
.cache
.pytest_cache/
coverage.xml

# Compiled translations
*.mo
EOF

# 4. Создать README placeholder
cat > README.md << 'EOF'
# Minimarket Platform

SaaS-платформа для малых офлайн-бизнесов (мини-маркеты, пекарни, специалитет-магазины, рестораны).
Свой сайт + база клиентов + акции с бронированием + локальный агрегатор + уведомления.

## Status
Phase 1 in development.

## Tech stack
Django 5, PostgreSQL, Redis, Celery, HTMX, Tailwind. Multi-tenant via django-tenants.

## Documentation
- `docs/architecture.md` — общая архитектура
- `docs/phase1-plan.md` — план разработки Phase 1
EOF

# 5. Первый commit
git add .
git commit -m "Initial: docs and gitignore"

# 6. Запустить Claude Code в этой директории
claude
```

---

## Bootstrap Prompt (первое сообщение в сессии Sprint 1)

```
Привет. Я начинаю Phase 1 разработки SaaS-платформы для мини-маркетов (мини-маркет = малый офлайн-бизнес: пекарня, мясная, продуктовый, Bioladen, специалитет-магазин, маленький ресторан/кафе).

Контекст проекта:
- Полная архитектура: docs/architecture.md
- План Phase 1 со спринтами: docs/phase1-plan.md  
- Монетизация: docs/monetization.md

Прочитай оба docs/architecture.md и docs/phase1-plan.md полностью, прежде чем что-либо делать. Это критично — без полного контекста ты сделаешь не то.

Стек (фиксирован, не предлагай альтернативы):
- Django 5.x + django-tenants (schema-per-tenant)
- PostgreSQL 16
- Redis + Celery
- HTMX + Alpine.js + Tailwind CSS
- Tenant routing через subdomain

Принципы работы со мной:
1. Один спринт за раз. Сейчас — Sprint 1.
2. Внутри спринта — одна задача за раз. Я скажу когда переходить к следующей.
3. После каждой задачи я локально проверяю результат и делаю git commit. Не делай commit сам.
4. Если предлагаешь отклониться от спецификации (изменить поле модели, добавить библиотеку, поменять подход) — СПРОСИ меня сначала, не делай молча.
5. Tests пиши параллельно с кодом, не "потом". Использую pytest + pytest-django + factory-boy.
6. Не пиши длинных комментариев в коде. Код должен быть самоочевидным. Комментарии только там, где есть нетривиальное решение.
7. Не используй emoji в коде, коммитах, выводе.

Что мы делаем в Sprint 1: Foundation & Multi-tenancy.
Цель спринта: работающий Django-проект с настроенным django-tenants. Можно создать tenant через admin или management command, зайти на его subdomain в браузере, увидеть пустой dashboard. Auth работает (регистрация/логин/logout).

Sprint 1 разбит на 5 задач, которые мы будем делать последовательно:
Task 1.1: Инициализация проекта (структура, зависимости, settings, docker-compose)
Task 1.2: Модели Tenant и Domain, миграции, management command для создания тестового tenant
Task 1.3: Django-tenants middleware и routing (urls_public.py, urls_tenant.py)  
Task 1.4: Django-allauth для email-based auth
Task 1.5: Onboarding flow (форма создания бизнеса = создание tenant + первого user)

Подтверди что прочитал документацию и готов. Не начинай Task 1.1 пока я не скажу "поехали Task 1.1".
```

После того как Claude Code подтвердит, что прочитал документацию, переходи к Task 1.1.

---

## Task 1.1: Инициализация проекта

```
Поехали Task 1.1: Инициализация проекта.

Создай следующую структуру согласно docs/architecture.md и docs/phase1-plan.md (раздел "Часть 1: Project Setup"):

1. pyproject.toml со всеми зависимостями из спецификации (Django 5.1+, django-tenants, psycopg, redis, celery, django-allauth, django-htmx, django-storages, dj-stripe, django-import-export, anymail, gunicorn, whitenoise, sentry-sdk, и dev зависимости: pytest, pytest-django, factory-boy, ruff, ipython, debug-toolbar, django-extensions).

2. Структура директорий:
   - config/ (Django project)
     - __init__.py
     - settings/ (__init__.py, base.py, development.py)
     - urls_public.py (пустой пока)
     - urls_tenant.py (пустой пока)
     - celery.py
     - wsgi.py
     - asgi.py
   - apps/ (с __init__.py)
   - templates/
   - static/
   - locale/

3. config/settings/base.py — точно по спецификации в docs/phase1-plan.md, с django-tenants config (SHARED_APPS, TENANT_APPS, TENANT_MODEL, TENANT_DOMAIN_MODEL, DATABASE_ROUTERS, middleware order). Важно: middleware django_tenants.middleware.main.TenantMainMiddleware должен быть первым.

4. config/settings/development.py — DEBUG=True, ALLOWED_HOSTS=['*'], console email, local FileSystemStorage для медиа.

5. .env.example точно по спецификации.

6. docker-compose.yml с postgres:16-alpine и redis:7-alpine.

7. manage.py.

8. config/celery.py с базовой конфигурацией.

9. config/wsgi.py и asgi.py стандартные.

10. README.md с инструкциями setup и запуска.

11. pytest.ini или pyproject.toml [tool.pytest.ini_options] с pytest-django настройкой.

Важные детали:
- Использую uv для управления зависимостями (не poetry, не pip-tools)
- Python 3.12+
- Не создавай apps пока — это сделаем в Task 1.2
- Не пиши миграции пока — нет моделей

После того как создашь файлы, опиши мне команды которые я должен выполнить локально:
1. Создание venv и установка зависимостей
2. Запуск docker compose
3. Что должно сработать без ошибок (например python manage.py check)

Не делай git commit. Я сделаю сам после проверки.
```

### Локальная проверка после Task 1.1

```bash
# Установить uv если ещё нет
curl -LsSf https://astral.sh/uv/install.sh | sh

# Создать venv и установить зависимости
uv venv
source .venv/bin/activate  # или .venv\Scripts\activate на Windows
uv pip install -e ".[dev]"

# Запустить БД и Redis
docker compose up -d db redis

# Скопировать env
cp .env.example .env
# отредактировать .env (поменять SECRET_KEY на любую строку)

# Проверка
python manage.py check
# Должно: System check identified no issues (0 silenced).
```

Если всё OK:
```bash
git add .
git commit -m "Sprint 1 / Task 1.1: project bootstrap, settings, dependencies"
```

Если есть ошибки — копируй вывод обратно в Claude Code, проси исправить.

---

## Task 1.2: Tenant модели и тестовый tenant

```
Task 1.1 проверен и закоммичен. Поехали Task 1.2: модели Tenant и Domain.

1. Создай app apps/tenants/:
   - __init__.py
   - apps.py с правильным name='apps.tenants'
   - models.py с моделями Tenant и Domain ТОЧНО по спецификации в docs/phase1-plan.md раздел "Часть 2: apps/tenants/models.py". Не отступай от полей, не добавляй своего, не убирай.
   - admin.py с Django Admin регистрацией обеих моделей. Используй unfold для современного вида (ModelAdmin from unfold.admin). Покажи в list_display: name, schema_name, business_type, city, subscription_status, created_at. Сделай search_fields на name, slug, schema_name. List_filter на business_type, subscription_status, country.
   - migrations/__init__.py (пустой)
   - management/commands/create_test_tenant.py — точно по спецификации (создаёт public tenant если нет, потом создаёт тестовый tenant "baeckerei-test" в Hilden, привязывает domain baeckerei-test.localhost)
   - tests/__init__.py
   - tests/test_models.py — базовые тесты на создание Tenant, что schema создаётся автоматически
   - tests/factories.py — factory-boy TenantFactory и DomainFactory
   - tests/conftest.py если нужно

2. Создай миграции:
   - Объясни мне как правильно сгенерировать миграции для tenants app (команда python manage.py makemigrations tenants)
   - Создай миграцию в файле и положи в migrations/

3. Не запускай миграции сам — я сделаю.

После того как создашь, опиши:
- Команды для создания миграции и её применения (migrate_schemas --shared)
- Команду создания тестового tenant
- Что я должен увидеть в Django Admin
- Как локально настроить /etc/hosts если нужно для *.localhost (на Linux/Mac обычно не нужно, на Windows может понадобиться)

Не делай git commit.
```

### Локальная проверка после Task 1.2

```bash
# Создать миграции
python manage.py makemigrations tenants

# Применить SHARED schema
python manage.py migrate_schemas --shared

# Создать суперюзера в public
python manage.py createsuperuser
# email: admin@platform.local
# password: какой-нибудь

# Создать тестовый tenant
python manage.py create_test_tenant
# Должно: Created tenant: baeckerei-test.localhost:8000

# Запустить сервер
python manage.py runserver 0.0.0.0:8000

# В браузере: http://localhost:8000/admin/
# Залогиниться. В Tenants → Tenants должен быть public и baeckerei_test.

# Тесты
pytest apps/tenants/tests/
# Должно: все зелёные
```

Если всё OK:
```bash
git add .
git commit -m "Sprint 1 / Task 1.2: Tenant and Domain models, admin, test tenant command"
```

---

## Task 1.3: Routing и базовый layout

```
Task 1.2 закоммичен. Tenants работают. Поехали Task 1.3: routing.

1. Создай config/urls_public.py:
   - urls для public schema (агрегатор, главная)
   - admin/ (Django admin)
   - api/v1/ (заготовка под DRF, пока заглушка)
   - / → редирект на временную главную страницу "platform.com — для бизнесов и потребителей"

2. Создай config/urls_tenant.py:
   - urls для tenant schema (когда зашли на subdomain)
   - admin/ (Django admin для tenant в его контексте)
   - accounts/ (для allauth, добавим в Task 1.4 — пока заглушку)
   - / → tenant_dashboard view (placeholder)

3. Создай app apps/core/ (TENANT app):
   - __init__.py
   - apps.py
   - models.py с TimestampedModel абстрактным классом и I18nMixin по спецификации
   - views.py с TenantDashboardView (LoginRequired, простая HTML страница "Welcome, {tenant.name}!")
   - urls.py с маршрутом для dashboard
   - templates/core/dashboard.html (минимальный, чистый Tailwind layout)
   - tests/__init__.py

4. Создай базовый template templates/base.html:
   - HTML5 шаблон
   - Tailwind CSS через CDN (для разработки, в production будет build)
   - HTMX через CDN
   - Alpine.js через CDN
   - Блоки {% block title %}, {% block content %}, {% block scripts %}
   - Минимальный header с логотипом текстом "Minimarket Platform"
   - Footer с copyright

5. Создай templates/tenant/_layout.html который extends base.html:
   - Sidebar с навигацией: Dashboard, Catalog (placeholder), Promotions (placeholder), Settings (placeholder)
   - Top bar с email пользователя (когда залогинен) и logout link
   - Block content для основного контента

6. Создай health check endpoint /health/ в urls_public.py:
   - Возвращает {"status": "ok", "version": "0.1.0"} как JSON
   - Не требует auth

7. Тесты:
   - tests на TenantDashboardView (требует auth, редиректит неавторизованных)
   - test на health endpoint
   - test на правильный routing public vs tenant (запрос на baeckerei-test.localhost → tenant context, запрос на localhost → public)

Опиши команды для проверки локально. Не делай commit.
```

### Локальная проверка после Task 1.3

```bash
python manage.py runserver 0.0.0.0:8000

# Public:
# http://localhost:8000/ — заглушка главной
# http://localhost:8000/admin/ — Django admin (public)
# http://localhost:8000/health/ — {"status": "ok"}

# Tenant:
# http://baeckerei-test.localhost:8000/ — placeholder dashboard (но требует auth, поэтому редирект на login)
# http://baeckerei-test.localhost:8000/admin/ — Django admin (tenant context)

# Тесты
pytest
```

Если работает:
```bash
git add .
git commit -m "Sprint 1 / Task 1.3: routing, base layout, tenant dashboard placeholder, health check"
```

---

## Task 1.4: Email-based auth через django-allauth

```
Task 1.3 закоммичен. Routing работает. Поехали Task 1.4: auth.

Подключаем django-allauth для email-based аутентификации.

1. Настрой allauth в config/settings/base.py:
   - Уже добавлен в SHARED_APPS (проверь)
   - AUTHENTICATION_BACKENDS включает allauth.account.auth_backends.AuthenticationBackend
   - ACCOUNT_LOGIN_METHODS = {'email'}
   - ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
   - ACCOUNT_EMAIL_VERIFICATION = 'mandatory' (но в development можно сделать 'optional' или 'none' для скорости разработки — добавь это в development.py)
   - LOGIN_REDIRECT_URL = '/' (на tenant subdomain пойдёт в dashboard)
   - LOGOUT_REDIRECT_URL = '/accounts/login/'

2. Добавь allauth URLs в config/urls_tenant.py:
   - path('accounts/', include('allauth.urls'))

3. Создай кастомные templates для allauth (templates/account/):
   - login.html — extends base.html, минималистичная форма
   - signup.html — но пометь что это пока внутренний signup (внешний signup для нового бизнеса будет в Task 1.5)
   - logout.html
   - password_reset.html
   - password_reset_done.html
   - password_reset_from_key.html
   - email_confirm.html
   Все используют Tailwind. Не usai allauth дефолтные templates.

4. Сделай миграции для allauth:
   - python manage.py migrate_schemas --shared (allauth модели идут в SHARED)
   - Объясни мне команду

5. Создай первого пользователя в тестовом tenant:
   - Расширь management command create_test_tenant: создавать также первого user в схеме tenant'а с email=owner@baeckerei-test.local, password='testpass123'
   - Использовать with schema_context(tenant.schema_name) для создания user в правильной схеме

6. Tests:
   - test_login_works
   - test_logout_works  
   - test_password_reset_email_sent
   - test_unauthenticated_redirected_to_login

Важно: User модель идёт в TENANT_APPS contrib.auth (уже там), значит каждый tenant имеет свой набор пользователей. Это правильно для нашего use case.

Не делай commit.
```

### Локальная проверка после Task 1.4

```bash
# Применить новые миграции
python manage.py migrate_schemas --shared

# Пересоздать тестовый tenant с user
python manage.py create_test_tenant
# Должно: создан tenant + user owner@baeckerei-test.local / testpass123

# Запустить
python manage.py runserver 0.0.0.0:8000

# В браузере:
# http://baeckerei-test.localhost:8000/ → редирект на /accounts/login/
# Login с owner@baeckerei-test.local / testpass123 → попадает в dashboard
# Logout → редирект на login

# В development email идёт в консоль — проверь password reset:
# http://baeckerei-test.localhost:8000/accounts/password/reset/ → ввести email → в консоли увидишь email с ссылкой

# Тесты
pytest
```

Если всё работает:
```bash
git add .
git commit -m "Sprint 1 / Task 1.4: django-allauth email-based auth with custom templates"
```

---

## Task 1.5: Onboarding нового бизнеса

```
Task 1.4 закоммичен. Auth работает. Поехали Task 1.5 — последняя задача Sprint 1.

Onboarding flow: внешний посетитель приходит на главную, нажимает "Register your business", заполняет форму, и в результате:
- Создаётся новый Tenant с уникальным schema_name и slug
- Создаётся Domain ({slug}.localhost для dev)
- В схеме нового tenant'а создаётся первый User (owner)
- Пользователь автоматически логинится
- Редирект на dashboard нового tenant'а

1. Создай форму OnboardingForm в apps/tenants/forms.py:
   - business_name (CharField)
   - slug (SlugField, с валидацией уникальности по Tenant.slug)
   - business_type (ChoiceField из Tenant.BUSINESS_TYPES, default 'other')
   - city (CharField, hint: "город где находится бизнес")
   - country (ChoiceField, на старте только 'DE')
   - owner_email (EmailField)
   - owner_password1, owner_password2 (PasswordField, валидация совпадения и django password validators)
   - Метод clean_slug проверяет что schema_name (slug с дефисами заменёнными на подчёркивания) ещё не существует
   - Метод save создаёт Tenant, Domain, User в правильной схеме, возвращает (tenant, user, domain)

2. Создай OnboardingView в apps/tenants/views.py:
   - GET: рендерит форму
   - POST: валидирует, если OK — создаёт всё, логинит user, редиректит на http://{slug}.localhost:8000/
   - При ошибке валидации — снова форма с ошибками

3. Создай URL в config/urls_public.py:
   - path('signup/', OnboardingView.as_view(), name='onboarding')

4. Создай template templates/tenants/onboarding.html:
   - Чистый Tailwind, центрированная форма на белом фоне
   - Поля сгруппированы: "About your business" и "Your account"
   - Кнопка "Create my business" в primary цвете
   - После создания — splash страница "Welcome! Your dashboard is being prepared..." с JS-редиректом через 2 секунды на новый subdomain (чтобы успело создаться)

5. Обнови главную страницу (заглушка из Task 1.3):
   - Сделай простой landing с двумя CTA: "For businesses → Register" и "For consumers → Browse promotions (coming soon)"
   - Заменить временную заглушку

6. Tests:
   - test_onboarding_creates_tenant_domain_and_user
   - test_onboarding_slug_uniqueness (попытка взять занятый slug → ошибка)
   - test_onboarding_invalid_email
   - test_onboarding_password_mismatch
   - test_onboarding_redirects_after_creation

7. Edge case: что если в процессе создания упадёт ошибка после создания Tenant, но до создания User? Заверни всё в transaction.atomic. Но: создание schema через django-tenants — это DDL, оно не откатывается транзакцией. Подумай как обработать это правильно. Самый простой вариант: использовать try/except, и при ошибке после создания schema — программно удалить schema. Объясни мне подход который ты выберешь.

Не делай commit.
```

### Локальная проверка после Task 1.5

```bash
python manage.py runserver 0.0.0.0:8000

# В браузере:
# http://localhost:8000/ — landing с CTA
# http://localhost:8000/signup/ → заполни форму:
#   - business_name: Bäckerei Müller
#   - slug: mueller
#   - business_type: bakery
#   - city: Düsseldorf
#   - country: DE
#   - email: max@mueller.local
#   - password: SecurePass123!
# → должен создаться tenant mueller, домен mueller.localhost, ты залогинен
# → редирект на http://mueller.localhost:8000/ → dashboard
#
# В админке localhost:8000/admin/ должны быть видны два tenant'а: baeckerei_test и mueller

# Тесты
pytest

# Демо для финала Sprint 1:
# 1. Создать через UI третий бизнес "Metzgerei Schmidt" в Hilden
# 2. Зайти на schmidt.localhost:8000/, увидеть dashboard
# 3. Logout, login снова — работает
# 4. Зайти на mueller.localhost:8000/admin/ как owner — видна только своя схема
```

Если работает:
```bash
git add .
git commit -m "Sprint 1 / Task 1.5: business onboarding flow with tenant + user creation"
git tag sprint-1-complete
```

---

## Definition of Done для Sprint 1

После завершения всех 5 задач у тебя должно работать:

- [ ] Локально запускается через `docker compose up -d && python manage.py runserver`
- [ ] `manage.py check` без ошибок
- [ ] `migrate_schemas --shared` применяется чисто
- [ ] Можно создать superuser, зайти в admin localhost:8000/admin/
- [ ] Можно создать тестовый tenant командой `create_test_tenant`
- [ ] Через UI можно зарегистрировать новый бизнес — создаётся schema, domain, user
- [ ] `{slug}.localhost:8000/` открывается, требует auth, после auth показывает dashboard placeholder
- [ ] Health check на `/health/` возвращает 200
- [ ] Все тесты зелёные: `pytest`
- [ ] Git: 5 коммитов (по одному на задачу), tag `sprint-1-complete`

---

## Что делать если Claude Code "сломал" что-то

Если после задачи проект не работает:

1. **Не паникуй, не пиши "всё сломал, начни заново".** Claude Code тогда переписывает всё и теряет правильные части.

2. **Скопируй точный traceback или error message** в чат с Claude Code.

3. **Скажи конкретно:** "После Task 1.X команда X выдаёт ошибку Y. Найди причину и исправь. Не трогай ничего кроме того что вызывает ошибку."

4. **Если Claude Code крутится на одной проблеме** больше двух итераций — останови. Сам посмотри код, скажи Claude Code "проблема скорее всего в X, проверь это место".

5. **Используй `git diff`** перед каждым commit'ом. Если видишь что Claude Code изменил файл который не должен был трогать — `git checkout file.py` и попроси не трогать.

---

## Что делать если Claude Code предлагает альтернативный подход

Например: "вместо django-tenants могу использовать django-tenant-schemas (более новая библиотека)..."

**Ответ:** "Нет. Стек зафиксирован в docs/architecture.md. Следуй спецификации точно. Если у тебя есть аргументация против выбранного подхода — изложи её, но не меняй код без моего согласия."

Не давай Claude Code переписывать архитектурные решения. Он часто предлагает "более современный" подход, который ломает совместимость с остальной системой.

---

## После Sprint 1

Когда tag `sprint-1-complete` поставлен:

1. **Сделай паузу.** Не лезь сразу в Sprint 2. День-два, прежде чем продолжить.
2. **Зайди в проект как пользователь.** Зарегистрируй 3-5 разных бизнесов через onboarding. Убедись что это реально удобно.
3. **Перечитай Sprint 2 в docs/phase1-plan.md.** Возможно после Sprint 1 поймёшь что что-то стоит переформулировать.
4. **Запусти deploy на staging-сервер Hetzner** (даже не для пользователей, чисто чтобы проверить что production setup работает на минимальных мощностях).

Только после этого — открывай новую сессию Claude Code, давай Bootstrap прочитать docs снова, и переходи к Sprint 2.

---

## Принципы работы с Claude Code, которые я понял на этом проекте

1. **Контекст — это всё.** Если docs/architecture.md не загружены — Claude Code будет придумывать архитектуру с нуля каждую сессию.
2. **Узкий scope = качество.** Одна задача за сессию даёт лучший результат, чем "сделай весь спринт".
3. **Между задачами — `/clear` или новая сессия.** Длинный контекст накапливает старые ошибки.
4. **Code review каждого PR.** Перед commit'ом — `git diff` и беглый просмотр. 80% багов ловится так.
5. **Tests параллельно с кодом.** Если Claude Code "забыл написать тесты" — это сигнал что и код может быть плохим.
6. **Не доверяй "и проверил, всё работает"** без локального запуска. Запускай сам.
