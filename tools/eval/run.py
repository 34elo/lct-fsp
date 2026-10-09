"""`make eval`: раннеры стенда оценки → отчёт (evaluation.md §5).

Раннеры: подбор (E27-2) и разбор резюме hh.ru (E39-19).

    uv run python tools/eval/run.py --split test --out reports/eval
    uv run python tools/eval/run.py --quick          # 200 кандидатов, 30 потребностей
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from report import to_markdown, write_report  # noqa: E402
from runners import matching, resumes  # noqa: E402


def run(split: str, candidates: int | None, vacancies: int | None, max_needs: int | None) -> tuple:
    market = matching.synth.generate_market(
        split=split, n_candidates=candidates, n_vacancies=vacancies
    )
    result = {
        "matching": matching.run_matching(market, max_needs=max_needs),
        "resumes": resumes.run_resumes(),
    }
    return result, market.meta()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--split", choices=["dev", "test"], default="test")
    ap.add_argument("--candidates", type=int)
    ap.add_argument("--vacancies", type=int)
    ap.add_argument("--max-needs", type=int)
    ap.add_argument("--quick", action="store_true", help="быстрый прогон для CI")
    ap.add_argument("--out", type=Path, default=Path("reports/eval"))
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")  # Windows: cp1251 не знает «Δ»
    if a.quick:
        a.candidates, a.vacancies = a.candidates or 200, a.vacancies or 40
    result, meta = run(a.split, a.candidates, a.vacancies, a.max_needs)
    write_report(result, meta, a.out)
    print(to_markdown(result, meta))


if __name__ == "__main__":
    main()
