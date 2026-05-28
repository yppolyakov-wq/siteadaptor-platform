# Hetzner setup + Claude Code: пошаговый гайд

Проект: minimarket-platform (Django + django-tenants + HTMX + Postgres).
Стек серверов: CPX21 (app, ~€7/мес) + CCX13 (db, ~€17/мес), оба в одной локации (Nürnberg или Falkenstein), связаны Private Network.

---

## 0. Перед началом: какой сценарий выбираешь

| | Сценарий A: локальная разработка | Сценарий B: dev-сервер на Hetzner |
|---|---|---|
| Где Claude Code | На твоём MacBook/PC | На отдельном dev-сервере |
| Что на app/db серверах | Только прод-код (через CI/CD) | То же самое |
| Когда поднимать app/db | Sprint 6, как было в плане | Sprint 6 |
| Стоимость | €0 локально + €24/мес прод (со Sprint 6) | +€5/мес dev-сервер сейчас |
| Когда выбрать | Default. Всегда, если есть нормальный ноут | Слабая локальная машина, кочевая работа, Windows без WSL |

**В обоих сценариях app и db серверы — это прод, и Claude Code на них не ставится.**

Дальше документ покрывает оба пути. Начни с раздела 1 (общая часть), потом выбери 4A (локально) или 4B (dev-сервер).

---

## 1. Структура проекта в Hetzner Console

Зайди на https://console.hetzner.com/projects.

**Создай два проекта** (не один общий — это нужно для изоляции billing и доступов):

1. `minimarket-platform-staging` — здесь будут staging-серверы, тесты, эксперименты
2. `minimarket-platform-prod` — только прод, со строгим доступом

**Внутри каждого проекта** в разделе Security сразу добавь:
- **SSH Keys** — твой публичный ключ (см. раздел 2)
- **Firewalls** — заготовки правил (раздел 3)

**Не создавай серверы сейчас**, пока не дойдёшь до Sprint 6 (для prod). Для dev-сервера (сценарий B) — создавай в `staging` проекте.

---

## 2. SSH ключи

На локальной машине (один раз):

```bash
# Создать отдельный ключ для Hetzner — не используй общий id_rsa
ssh-keygen -t ed25519 -C "hetzner-minimarket" -f ~/.ssh/hetzner_minimarket

# Посмотреть публичную часть для вставки в Hetzner Console
cat ~/.ssh/hetzner_minimarket.pub
```

Добавь содержимое `.pub` в Hetzner Console → Security → SSH Keys в обоих проектах.

В `~/.ssh/config` добавь алиасы (заполнишь IP после создания серверов):

```
Host hetzner-app
    HostName <APP_PUBLIC_IP>
    User deploy
    IdentityFile ~/.ssh/hetzner_minimarket
    IdentitiesOnly yes

Host hetzner-db
    HostName <DB_PUBLIC_IP>
    User deploy
    IdentityFile ~/.ssh/hetzner_minimarket
    IdentitiesOnly yes

Host hetzner-dev
    HostName <DEV_PUBLIC_IP>
    User deploy
    IdentityFile ~/.ssh/hetzner_minimarket
    IdentitiesOnly yes
```

---

## 3. Firewall правила (заранее в Hetzner Console)

В разделе Firewalls создай три набора правил:

### `fw-app` (для app-сервера, CPX21)
Inbound:
- TCP 22 — только с твоих IP (узнай через `curl ifconfig.me`)
- TCP 80 — `0.0.0.0/0, ::/0`
- TCP 443 — `0.0.0.0/0, ::/0`
- ICMP — `0.0.0.0/0, ::/0` (для ping)

Outbound — всё открыто (default).

### `fw-db` (для db-сервера, CCX13)
Inbound:
- TCP 22 — только с твоих IP
- TCP 5432 — только из Private Network subnet (например `10.0.0.0/16`)
- ICMP — из Private Network

**Никаких публичных портов кроме SSH.** Postgres только через private network.

### `fw-dev` (для dev-сервера, если сценарий B)
Inbound:
- TCP 22 — только с твоих IP

---

## 4A. Сценарий A: установка Claude Code локально

На твоём MacBook/PC.

### macOS / Linux

```bash
# Node.js 20+ через nvm (если нет)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
nvm install 20
nvm use 20

# Claude Code
npm install -g @anthropic-ai/claude-code

# Проверить
claude --version
```

Запуск в проекте:

```bash
cd ~/projects/minimarket-platform
claude
```

При первом запуске Claude Code попросит залогиниться через браузер (Anthropic Console / Claude.ai Pro/Max). Готово.

### Windows
Поставь WSL2 (Ubuntu) и в нём всё то же самое. Запускать Claude Code в нативном Windows возможно, но WSL надёжнее для Python/Docker стека.

**Дальше работаешь локально**, как было в плане Sprint 1–5. Серверы поднимешь в Sprint 6.

Если ты идёшь по сценарию A — переходи к разделу 6 (когда дойдёшь до деплоя).

---

## 4B. Сценарий B: dev-сервер с Claude Code

### 4B.1 Создание dev-сервера

В проекте `minimarket-platform-staging` создай сервер:
- **Тип:** CPX21 (3 vCPU AMD, 4 GB RAM, 80 GB NVMe) — этого хватит на Django dev-сервер + Postgres + Claude Code
- **Локация:** Nürnberg или Falkenstein
- **Образ:** Ubuntu 24.04 LTS
- **SSH Key:** твой `hetzner-minimarket`
- **Firewall:** `fw-dev`
- **Backups:** включить (+20% к цене, ~€1/мес — стоит того)
- **Имя:** `minimarket-dev`

### 4B.2 Первоначальная настройка сервера

Подключись как root (Hetzner показывает IP сразу после создания):

```bash
ssh root@<DEV_PUBLIC_IP>
```

Базовое усиление:

```bash
# Обновить систему
apt update && apt upgrade -y

# Создать пользователя deploy
adduser --disabled-password --gecos "" deploy
usermod -aG sudo deploy
mkdir -p /home/deploy/.ssh
cp ~/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys

# Sudo без пароля для deploy (удобно для Claude Code workflow)
echo "deploy ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/deploy
chmod 440 /etc/sudoers.d/deploy

# Запретить SSH под root и парольный вход
sed -i 's/#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl reload ssh

# Установить базовые утилиты
apt install -y git curl build-essential unzip htop tmux ufw fail2ban
```

Выйди и перелогинься как `deploy`:

```bash
exit
ssh hetzner-dev
```

### 4B.3 Docker + Postgres + Redis (для dev окружения)

```bash
# Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker deploy
# Перелогинься чтобы группа применилась
exit
ssh hetzner-dev

# Проверить
docker --version
docker compose version
```

### 4B.4 Python окружение

```bash
# uv для Python (как в плане Sprint 1)
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc

# Проверить
uv --version
```

### 4B.5 Node.js и Claude Code

```bash
# nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.bashrc
nvm install 20
nvm use 20
nvm alias default 20

# Claude Code
npm install -g @anthropic-ai/claude-code
claude --version
```

### 4B.6 Git и клонирование проекта

```bash
# Сгенерировать ключ для GitHub на этом сервере
ssh-keygen -t ed25519 -C "dev-server-minimarket" -f ~/.ssh/github_dev -N ""
cat ~/.ssh/github_dev.pub
# → добавь содержимое в GitHub → Settings → SSH and GPG keys

# Настроить SSH для GitHub
cat >> ~/.ssh/config <<EOF
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/github_dev
    IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config

# Git глобальные настройки
git config --global user.name "Твоё Имя"
git config --global user.email "твой@email"

# Клонировать проект
mkdir -p ~/projects && cd ~/projects
git clone git@github.com:<твой-юзер>/minimarket-platform.git
cd minimarket-platform
```

### 4B.7 Запуск Claude Code

```bash
# Лучше в tmux чтобы сессия не прерывалась при разрыве SSH
tmux new -s claude

cd ~/projects/siteadaptor-platform
claude
```

Первый запуск — авторизация через браузер. Claude Code даст URL, скопируешь его в локальный браузер, залогинишься на Claude.ai/Anthropic Console, вернёшь токен.

Отсоединиться от tmux: `Ctrl+B`, потом `D`. Вернуться: `tmux attach -t claude`.

### 4B.8 Удобный SSH-туннель для Django dev-сервера

Чтобы открывать локально в браузере Django, который крутится на dev-сервере:

```bash
# На локальной машине
ssh -L 8000:localhost:8000 siteadaptor-dev
```

Теперь `http://baeckerei-test.localhost:8000` на твоём ноуте идёт на dev-сервер.

Для поддоменов (django-tenants) добавь в `/etc/hosts` локально:
```
127.0.0.1  baeckerei-test.localhost
127.0.0.1  fleischerei-test.localhost
```

---

## 5. Production: app-сервер (CPX21) — для Sprint 6

В проекте `minimarket-platform-prod`. **Не делай этого сейчас.**

### 5.1 Создание

- Тип: **CPX21**
- Локация: та же, что и dev/db
- Образ: Ubuntu 24.04 LTS
- SSH Key: `hetzner-minimarket`
- Firewall: `fw-app`
- Backups: включить
- **Private Network:** создать новую сеть `minimarket-net` (10.0.0.0/16) и подключить сервер
- Имя: `minimarket-app-prod`

### 5.2 Hardening (то же что 4B.2)

Те же шаги: deploy user, отключить root SSH, отключить password auth, fail2ban.

### 5.3 Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker deploy
```

### 5.4 Caddy (reverse proxy с auto-SSL)

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy
```

Минимальный `/etc/caddy/Caddyfile` для старта:

```
*.minimarkt.de, minimarkt.de {
    reverse_proxy localhost:8000
}
```

Caddy сам получит wildcard-сертификат через Let's Encrypt DNS challenge (для wildcard нужен DNS plugin — потом настроишь).

### 5.5 Деплой Django (через docker compose)

В проекте уже есть `docker-compose.yml` (из Sprint 1). На prod-сервере:

```bash
cd ~/projects
git clone git@github.com:<твой-юзер>/minimarket-platform.git
cd minimarket-platform

# .env с прод-значениями (DATABASE_URL указывает на private IP db-сервера)
cp .env.example .env
nano .env

docker compose -f docker-compose.prod.yml up -d
```

`docker-compose.prod.yml` для прода не запускает Postgres (он на отдельной машине) — только Django, Celery worker, Redis (если совсем нет ресурсов на отдельный — иначе тоже на db-сервер).

---

## 6. Production: db-сервер (CCX13) — для Sprint 6

### 6.1 Создание

- Тип: **CCX13** (2 dedicated vCPU, 8 GB RAM, 80 GB NVMe) — dedicated CPU критично для Postgres
- Локация: та же
- Образ: Ubuntu 24.04 LTS
- SSH Key: `hetzner-minimarket`
- Firewall: `fw-db`
- Backups: включить
- **Private Network:** подключить к той же `minimarket-net`
- Имя: `minimarket-db-prod`

### 6.2 Hardening (то же)

### 6.3 PostgreSQL 16 (нативно, не в Docker)

```bash
sudo apt install -y postgresql-16 postgresql-contrib-16
sudo systemctl enable --now postgresql

# Создать БД и пользователя
sudo -u postgres psql <<EOF
CREATE USER minimarket WITH PASSWORD '<strong-password>';
CREATE DATABASE minimarket_prod OWNER minimarket;
\c minimarket_prod
GRANT ALL ON SCHEMA public TO minimarket;
EOF
```

### 6.4 Слушать только private network

В `/etc/postgresql/16/main/postgresql.conf`:
```
listen_addresses = 'localhost,10.0.0.3'  # private IP db-сервера
```

В `/etc/postgresql/16/main/pg_hba.conf` (в самый конец):
```
host    minimarket_prod    minimarket    10.0.0.0/16    scram-sha-256
```

```bash
sudo systemctl restart postgresql
```

### 6.5 pg_dump backup в Hetzner Object Storage

Создай bucket в Hetzner Object Storage. Скрипт `/home/deploy/backup-db.sh`:

```bash
#!/bin/bash
set -e
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="/tmp/minimarket_${TIMESTAMP}.sql.gz"

PGPASSWORD='<password>' pg_dump -h localhost -U minimarket minimarket_prod | gzip > "$BACKUP_FILE"

# Загрузить в Hetzner Object Storage (через rclone или s3cmd)
rclone copy "$BACKUP_FILE" hetzner-s3:minimarket-backups/

# Удалить локально
rm "$BACKUP_FILE"

# Ротация: оставить 7 последних
rclone delete --min-age 7d hetzner-s3:minimarket-backups/
```

Cron: `0 3 * * * /home/deploy/backup-db.sh >> /var/log/backup-db.log 2>&1`

---

## 7. Workflow разработки через Claude Code

Независимо от сценария A или B:

1. **Узкий scope.** Одна задача = одна сессия Claude Code. Между задачами — `/clear` или новая сессия.
2. **Контекст обязательно.** Каждая новая сессия начинается с того, что Claude Code читает `docs/architecture.md` и `docs/phase1-plan.md`.
3. **`git diff` перед каждым commit.** Не доверяй "всё работает" — смотри что изменено.
4. **Не давай переписывать архитектуру.** Стек зафиксирован — django-tenants, HTMX, uv, Caddy. Если Claude Code предлагает альтернативу — отказывай.
5. **Tests параллельно с кодом.** Если "забыл написать тесты" — сигнал что и код плохой.
6. **Запускай локально/на dev сам.** Не верь "проверил, работает" без своего запуска.

---

## 8. Что НЕ делать

- **Не ставить Claude Code на app-prod или db-prod серверы.** Это прод. На них только задеплоенный код через CI/CD.
- **Не открывать Postgres в публичный интернет.** Только private network.
- **Не использовать root по SSH в постоянной работе.** Только deploy user.
- **Не хранить production API keys/секреты в коде.** Через `.env` на сервере, не в git.
- **Не поднимать prod в Sprint 1.** Сначала локальная разработка (или dev-сервер), prod — Sprint 6.

---

## 9. Чек-лист, что сделать сейчас vs позже

**Сейчас (до начала Sprint 1):**
- [ ] Зарегистрироваться на Hetzner, пройти верификацию (1-24 часа)
- [ ] Создать оба проекта в Console
- [ ] Добавить SSH ключи и firewall заготовки в обоих проектах
- [ ] Выбрать сценарий A или B
- [ ] Если B — создать dev-сервер, пройти разделы 4B.1–4B.7
- [ ] Если A — поставить Claude Code локально (раздел 4A)

**В Sprint 6 (деплой):**
- [ ] Создать app-prod и db-prod в `minimarket-platform-prod` проекте
- [ ] Настроить private network
- [ ] Развернуть Django через docker compose
- [ ] Caddy + Let's Encrypt для домена
- [ ] pg_dump backup в Object Storage по cron
- [ ] Sentry + UptimeRobot на `/health/`
