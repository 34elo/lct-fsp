# VPS: HTTPS и внешняя проверка

VPS `2.26.52.44` принимает трафик доменов `*.fsp.patissons.tech`, выпускает сертификаты Let's Encrypt (Caddy) и через Tailscale проксирует на домашний сервер `100.78.22.33:28080` (gateway стенда).

## DNS

A-записи на `2.26.52.44`: `fsp.patissons.tech`, `dashboard.`, `api.`, `s3.`, `mock.fsp.patissons.tech` (заведены).

## Caddy

Конфиг стенда — [fsp.caddy](fsp.caddy), на VPS `/etc/caddy/fsp.caddy` (подключён `import` в конце основного `/etc/caddy/Caddyfile`). Обновление с домашнего сервера, из корня репозитория:

```bash
scp infra/vps/fsp.caddy root@2.26.52.44:/tmp/fsp.caddy.new
ssh root@2.26.52.44 'cd /etc/caddy && cp -p fsp.caddy fsp.caddy.bak-$(date +%Y%m%d-%H%M) && install -m 644 /tmp/fsp.caddy.new fsp.caddy && caddy validate --config Caddyfile --adapter caddyfile && systemctl reload caddy'
```

Если `validate` упал — вернуть копию: `cp -p $(ls -t /etc/caddy/fsp.caddy.bak-* | head -1) /etc/caddy/fsp.caddy`.

Проверка: `curl -sI https://dashboard.fsp.patissons.tech/api/v1/healthz` → 200, `curl -sI https://fsp.patissons.tech` → лендинг (200); `curl -sI https://fsp.patissons.tech/me` → 302 на dashboard, `curl -sI https://mock.fsp.patissons.tech` → ответ мока.

## Ретранслятор Telegram

С домашнего сервера `api.telegram.org` недоступен. Блок `http://100.66.64.126:28443` в [fsp.caddy](fsp.caddy) пересылает Bot API в Telegram и слушает только Tailscale-адрес VPS (`100.66.64.126`). Проверка с домашнего сервера: `docker run --rm curlimages/curl -s http://100.66.64.126:28443/` → ответ Telegram (404 на корень — нормально). Если не отвечает — фаервол VPS: `ufw allow in on tailscale0 to any port 28443 proto tcp`.

## Внешняя проверка

Уже есть: сторож пульса `hostwatch-watchdog` на этом VPS (`/opt/hostwatch`) пишет в `@patissons_alerts_bot`, если домашняя машина пропала больше чем на 4 минуты. Отдельная проверка для стенда не нужна.
