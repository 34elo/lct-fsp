# VPS: HTTPS и внешняя проверка

VPS `2.26.52.44` принимает трафик доменов `*.fsp.patissons.tech`, выпускает сертификаты Let's Encrypt (Caddy) и через Tailscale проксирует на домашний сервер `100.78.22.33:28080` (gateway стенда).

## DNS

A-записи на `2.26.52.44`: `fsp.patissons.tech`, `www.fsp.patissons.tech`, `dashboard.`, `api.`, `s3.`, `mock.fsp.patissons.tech`.

## Caddy

1. Скопировать блоки из [Caddyfile](Caddyfile) в `/etc/caddy/Caddyfile` VPS (блоки других проектов не трогать).
2. `sudo mkdir -p /var/log/caddy && sudo chown caddy:caddy /var/log/caddy`
3. `sudo caddy validate --config /etc/caddy/Caddyfile && sudo systemctl reload caddy`
4. Проверка: `curl -sI https://dashboard.fsp.patissons.tech/api/v1/healthz` → 200, `curl -sI https://fsp.patissons.tech` → 308 на dashboard.

## Ретранслятор Telegram

С домашнего сервера `api.telegram.org` недоступен. Блок `http://100.66.64.126:28443` в [Caddyfile](Caddyfile) пересылает Bot API в Telegram и слушает только Tailscale-адрес VPS (`100.66.64.126`). Проверка с домашнего сервера: `docker run --rm curlimages/curl -s http://100.66.64.126:28443/` → ответ Telegram (404 на корень — нормально).

## Внешняя проверка

Уже есть: сторож пульса `hostwatch-watchdog` на этом VPS (`/opt/hostwatch`) пишет в `@patissons_alerts_bot`, если домашняя машина пропала больше чем на 4 минуты. Отдельная проверка для стенда не нужна.
