#!/usr/bin/env bash
# Вайбкодинг без открытого чата (запасной вариант к /vibe).
# контекстом: диспетчер берёт одну задачу, отдаёт её сабагенту, проверяет и ставит статус.
# Если упёрлись в лимит, ждём и повторяем.
# Использование: tools/agents/vibe.sh [сколько задач, по умолчанию 6] [модель диспетчера, по умолчанию sonnet]
set -uo pipefail
MAX="${1:-6}"
MODEL="${2:-sonnet}"
cd "$(git rev-parse --show-toplevel)"
mkdir -p reports
LOG="reports/vibe-$(date +%F).log"

if [ -n "$(git status --porcelain)" ]; then
  echo "Рабочее дерево не чистое — закоммить или убери изменения." | tee -a "$LOG"; exit 1
fi

for i in $(seq 1 "$MAX"); do
  echo "=== задача $i/$MAX, $(date +%T) ===" >>"$LOG"
  for attempt in 1 2 3 4 5 6; do
    claude -p "Выполни инструкции из .claude/commands/vibe.md с лимитом 1 задача. Вопросов не задавай." \
      --permission-mode acceptEdits --model "$MODEL" >>"$LOG" 2>&1
    code=$?
    if [ $code -eq 0 ]; then break; fi
    if tail -n 30 "$LOG" | grep -qiE "usage limit|rate limit|limit reached|429|overloaded"; then
      echo "лимит или перегрузка — жду 30 минут (попытка $attempt)" >>"$LOG"; sleep 1800
    else
      echo "ошибка запуска (код $code) — останавливаюсь" >>"$LOG"; exit $code
    fi
  done
  if tail -n 40 "$LOG" | grep -q "ОЧЕРЕДЬ ПУСТА"; then echo "очередь пуста" >>"$LOG"; break; fi
done
echo "=== конец смены $(date +%T) ===" >>"$LOG"
