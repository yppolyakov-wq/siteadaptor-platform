# Caddy с DNS-плагином для wildcard-TLS (*.siteadaptor.de требует DNS-01 challenge).
# По умолчанию — Hetzner DNS. Если домен на другом провайдере, замени модуль:
#   Cloudflare:  github.com/caddy-dns/cloudflare
#   и т.д. — список: https://github.com/caddy-dns
FROM caddy:2-builder AS builder
RUN xcaddy build --with github.com/caddy-dns/hetzner

FROM caddy:2
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
