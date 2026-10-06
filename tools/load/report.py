"""Проверка порогов нагрузочного прогона (E29-2) по CSV `locust --csv`.

Запуск: `python tools/load/report.py reports/load/load_stats.csv [--out reports/load/load.md]`.
Код выхода 1, если порог нарушен. Зависит только от стандартной библиотеки.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# Пороги (metrics.md, «Техника»): p95 подборки и поиска при 50 пользователях ≤ 1 с; ошибки ≤ 1 %.
P95_LIMITS_MS: dict[str, float] = {"search": 1000.0, "matches": 1000.0}
MAX_ERROR_RATE = 0.01
P95_COLUMN = "95%"


def load_stats(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def check(rows: list[dict[str, str]]) -> tuple[list[str], list[str]]:
    """Вернуть (строки таблицы отчёта, нарушения)."""
    lines: list[str] = []
    violations: list[str] = []
    seen: set[str] = set()
    for row in rows:
        name = row["Name"]
        reqs = int(row["Request Count"])
        fails = int(row["Failure Count"])
        p95 = float(row[P95_COLUMN]) if reqs else 0.0
        lines.append(
            f"| {name} | {reqs} | {fails} | {row['Median Response Time']} | {p95:.0f} "
            f"| {row['Requests/s']} |"
        )
        if reqs:
            seen.add(name)
        limit = P95_LIMITS_MS.get(name)
        if limit is not None and reqs and p95 > limit:
            violations.append(f"{name}: p95 {p95:.0f} мс > {limit:.0f} мс")
        if name == "Aggregated" and reqs and fails / reqs > MAX_ERROR_RATE:
            violations.append(f"ошибки {fails}/{reqs} > {MAX_ERROR_RATE:.0%}")
    for name in P95_LIMITS_MS:
        if name not in seen:
            violations.append(f"{name}: нет запросов в прогоне")
    return lines, violations


def render(lines: list[str], violations: list[str]) -> str:
    head = [
        "| Запрос | Запросов | Ошибок | p50, мс | p95, мс | RPS |",
        "|---|---|---|---|---|---|",
    ]
    verdict = "Пороги выполнены." if not violations else "Нарушено: " + "; ".join(violations)
    return "\n".join([*head, *lines, "", verdict, ""])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stats", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    lines, violations = check(load_stats(args.stats))
    text = render(lines, violations)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
