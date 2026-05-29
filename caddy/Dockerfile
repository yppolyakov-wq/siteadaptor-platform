# Стоковый Caddy: для HTTP-01 challenge (см. Caddyfile) DNS-плагин не нужен.
#
# Если в будущем перейдёшь на wildcard через DNS-01 (напр. Cloudflare), верни
# сборку через xcaddy с нужным плагином:
#   FROM caddy:2-builder AS builder
#   RUN xcaddy build --with github.com/caddy-dns/cloudflare
#   FROM caddy:2
#   COPY --from=builder /usr/bin/caddy /usr/bin/caddy
# Список плагинов: https://github.com/caddy-dns
FROM caddy:2
