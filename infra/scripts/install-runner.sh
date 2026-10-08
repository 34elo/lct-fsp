#!/bin/sh
# Ставит self-hosted раннер GitHub Actions для деплоя стенда (docs/deploy.md «CI/CD») как службу systemd.
# Запускать на сервере стенда под пользователем, который состоит в группе docker.
# Токен регистрации: GitHub → репозиторий → Settings → Actions → Runners → New self-hosted runner (живёт 1 час).
#   sh infra/scripts/install-runner.sh      — спросит токен (ввод скрыт)
set -eu
REPO_URL="${REPO_URL:-https://github.com/34elo/lct-fsp}"
DIR="${RUNNER_DIR:-$HOME/actions-runner-fsp}"
NAME="${RUNNER_NAME:-$(hostname)-fsp-stand}"

id -nG | grep -qw docker || { echo "пользователь $(id -un) не в группе docker" >&2; exit 1; }

mkdir -p "$DIR" && cd "$DIR"
if [ ! -x ./config.sh ]; then
  VER=$(curl -fsSL https://api.github.com/repos/actions/runner/releases/latest | sed -n 's/.*"tag_name": *"v\([^"]*\)".*/\1/p')
  curl -fsSL -o runner.tgz "https://github.com/actions/runner/releases/download/v$VER/actions-runner-linux-x64-$VER.tar.gz"
  tar xzf runner.tgz && rm runner.tgz
fi

if [ -z "${RUNNER_TOKEN:-}" ]; then
  printf 'Токен регистрации раннера: '; stty -echo; read -r RUNNER_TOKEN; stty echo; echo
fi
./config.sh --unattended --url "$REPO_URL" --token "$RUNNER_TOKEN" --name "$NAME" --labels fsp-stand --work _work --replace

sudo ./svc.sh install "$(id -un)"
sudo ./svc.sh start
echo "Раннер $NAME запущен. Проверьте: Settings → Actions → Runners (статус Idle)."
