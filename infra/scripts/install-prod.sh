#!/bin/sh
# Таймер продового стенда (systemd --user): fsp-backup — бэкап каждую ночь в 03:30. Мониторинг и алерты —
# бот hostwatch (docs/deploy.md «Мониторинг»). Идемпотентно: deploy.sh вызывает при каждом деплое прода.
#   sh infra/scripts/install-prod.sh   (из каталога стенда)
set -eu
STAND="$(pwd)"
UNITS="$HOME/.config/systemd/user"
mkdir -p "$UNITS"
# таймеры работают без входа пользователя в систему
loginctl show-user "$(id -un)" -p Linger 2>/dev/null | grep -q yes || loginctl enable-linger "$(id -un)" \
  || echo "install-prod: не удалось включить linger — выполните: sudo loginctl enable-linger $(id -un)" >&2

unit() { # имя, описание, команда
  cat > "$UNITS/$1.service" <<UNIT
[Unit]
Description=$2
[Service]
Type=oneshot
WorkingDirectory=$STAND
Environment=PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/bin/sh $3
UNIT
}
unit fsp-backup "ФСП Карьера: ночной бэкап" "infra/scripts/backup.sh nightly"
cat > "$UNITS/fsp-backup.timer" <<'UNIT'
[Unit]
Description=ФСП Карьера: ночной бэкап
[Timer]
OnCalendar=*-*-* 03:30
Persistent=true
[Install]
WantedBy=timers.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now fsp-backup.timer
echo "install-prod: таймер бэкапа включён"; systemctl --user list-timers 'fsp-*' --no-pager | head -5
