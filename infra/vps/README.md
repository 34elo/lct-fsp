# VPS: HTTPS и внешняя проверка

VPS `2.26.52.44` принимает трафик доменов `*.fsp.patissons.tech`, выпускает сертификаты Let's Encrypt (Caddy) и через Tailscale проксирует на домашний сервер `100.78.22.33:28080` (gateway стенда).

## DNS

A-записи на `2.26.52.44`: `fsp.patissons.tech`, `www.fsp.patissons.tech`, `dashboard.`, `api.`, `s3.`, `mock.fsp.patissons.tech`.

## Caddy

1. Скопировать блоки из [Caddyfile](Caddyfile) в `/etc/caddy/Caddyfile` VPS (блоки других проектов не трогать).
2. `sudo mkdir -p /var/log/caddy && sudo chown caddy:caddy /var/log/caddy`
3. `sudo caddy validate --config /etc/caddy/Caddyfile && sudo systemctl reload caddy`
4. Проверка: `curl -sI https://dashboard.fsp.patissons.tech/api/v1/healthz` → 200, `curl -sI https://fsp.patissons.tech` → 308 на dashboard.

## Внешняя проверка (алерты, если упал домашний ПК или Tailscale)

1. `sudo install -m 755 uptime.sh /usr/local/bin/fsp-uptime.sh`
2. `/etc/fsp-uptime.env` (права 600): `ALERT_BOT_TOKEN=…`, `ALERT_CHAT_ID=…`, при теме в группе — `ALERT_THREAD_ID=…` (те же значения, что в окружении GitHub `prod`).
3. `crontab -e`: `*/5 * * * * /usr/local/bin/fsp-uptime.sh`
