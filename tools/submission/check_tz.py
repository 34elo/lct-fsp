"""AU-4: сверка 8 обязательных пунктов ТЗ (`docs/case.md`) с `docs/submission.md`.

Берёт список из case.md («Документация должна включать»), для каждого пункта требует
в submission.md строку таблицы «Соответствие ТЗ» со ссылкой на существующий раздел `## N.`
с непустым текстом. Код возврата 1, если что-то не закрыто.
Запуск: `python tools/submission/check_tz.py [--case docs/case.md] [--src docs/submission.md]`.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

MARK = "Документация должна включать"


def tz_items(case_md: str) -> list[str]:
    after = case_md.split(MARK, 1)[1]
    items: list[str] = []
    for line in after.splitlines()[1:]:
        if line.startswith("- "):
            items.append(line[2:].strip().rstrip(";.").strip())
        elif items and not line.strip():
            break
    return items


def sections(sub_md: str) -> dict[int, str]:
    """Номер раздела `## N.` → его текст без заголовка."""
    parts = re.split(r"^## (\d+)\.[^\n]*\n", sub_md, flags=re.M)
    return {int(parts[k]): parts[k + 1].strip() for k in range(1, len(parts) - 1, 2)}


def check(case_md: str, sub_md: str) -> list[str]:
    errors: list[str] = []
    items = tz_items(case_md)
    if len(items) != 8:
        errors.append(f"в case.md найдено {len(items)} пунктов вместо 8")
    secs = sections(sub_md)
    parts = sub_md.split("## Соответствие ТЗ", 1)
    if len(parts) < 2:
        return [*errors, "нет раздела «Соответствие ТЗ»"]
    body = parts[1].split("\n## ", 1)[0]
    rows = [r for r in body.splitlines() if r.startswith("|")][2:]
    mapped = {r.split("|")[1].strip().lower(): r for r in rows}
    for item in items:
        row = mapped.get(item.lower())
        if row is None:
            errors.append(f"пункта нет в таблице соответствия: {item}")
            continue
        refs = [int(n) for n in re.findall(r"§(\d+)", row)]
        if not refs:
            errors.append(f"нет ссылки на раздел: {item}")
        for n in refs:
            if len(secs.get(n, "")) < 80:
                errors.append(f"раздел §{n} пуст или отсутствует: {item}")
    return errors


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", type=Path, default=Path("docs/case.md"))
    ap.add_argument("--src", type=Path, default=Path("docs/submission.md"))
    args = ap.parse_args()
    errors = check(args.case.read_text(encoding="utf-8"), args.src.read_text(encoding="utf-8"))
    for e in errors:
        print("ОШИБКА:", e)
    if errors:
        sys.exit(1)
    print("ТЗ: все 8 пунктов закрыты")


if __name__ == "__main__":
    main()
