"""Настройка весов подбора: веса match и rank на размеченных парах синтетики.

Настраиваются: `matching_weights` (skills / grade / salary / fsp), множитель обязательного
навыка в покрытии (`skills_coverage.required_weight_multiplier`) и `strength.rank_match`
(`rank_strength = 1 − rank_match`).

Пары «потребность – кандидат» с истинной релевантностью `rel` — синтетический рынок
(tools/synth). Ручной разметки потребностей в репозитории нет, поэтому
настраиваем только на синтетике. Против переобучения рынки разные (фиксированные seed'ы из
tools/synth/config.yaml): **train** — `dev` (seed 1001), **holdout** — `test` (seed 2002, его же
считает `make eval`). Веса выбираются только по train; «после» и решение «менять ли веса» —
по holdout: веса принимаются, только если на holdout выросли и precision@10, и nDCG@10 в обоих
режимах.

Режимы (как в `matching/search.py`):
- **match** — выдача по вакансии без категории: порядок по `score_candidate`;
- **rank** — выбрана категория: у кандидата с действующим грейдом порядок по
  `rank = rank_match·match + rank_strength·strength`, у остальных — по `match`.

Сетка: веса skills / grade / salary / fsp шагом 0.05, каждый ≥ 0.05, сумма 0.80 — вес семантики
(0.20) фиксирован: в синтетике нет эмбеддингов, компонент всегда 0 и на порядок не влияет;
множитель обязательного навыка 2 / 3 / 4; `rank_match` от 0.3 до 1.0 шагом 0.1. Критерий на
train — среднее nDCG@10 двух режимов, при равенстве среднее precision@10, затем близость к
прежним весам.

    uv run python tools/eval/tune.py --out reports/eval-tune
    uv run python tools/eval/tune.py --quick --out reports/eval-tune-quick
"""

from __future__ import annotations

import argparse
import dataclasses
import heapq
import json
import math
import sys
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
for _p in (HERE, HERE.parents[1] / "services/core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from app.matching import scoring as sc  # noqa: E402
from app.matching import strength as st  # noqa: E402
from runners import matching as mt  # noqa: E402

COMPONENTS = ("skills", "grade", "salary", "fsp")
SEMANTIC = 0.20  # фиксирован (см. выше)
STEP = 0.05
FLOOR = 0.05  # каждый компонент остаётся в формуле: объяснения и вклад ФСП не пропадают
REQ_GRID = (2.0, 3.0, 4.0)
RANK_GRID = tuple(round(0.3 + 0.1 * i, 1) for i in range(8))
MODES = ("match", "rank")
METRICS = ("p10", "ndcg10")


@dataclass(frozen=True, slots=True)
class Weights:
    match: Mapping[str, float]  # skills, grade, salary, fsp
    required_mult: float
    rank_match: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "match": {**self.match, "semantic": SEMANTIC},
            "required_mult": self.required_mult,
            "rank_match": self.rank_match,
            "rank_strength": round(1 - self.rank_match, 2),
        }


# «До» — исходные веса подбора и силы профиля.
BEFORE = Weights({"skills": 0.45, "grade": 0.15, "salary": 0.10, "fsp": 0.10}, 2.0, 0.6)


@dataclass(frozen=True, slots=True)
class Row:
    cid: str
    comp: tuple[float, float, float, float]  # skills, grade, salary, fsp
    strength: float | None  # None — нет грейда (теста): в режиме rank порядок по match


@dataclass(frozen=True, slots=True)
class Need:
    rel: Mapping[str, int]
    rows: tuple[Row, ...]


def strength_of(
    c: Mapping[str, Any], need_skills: Sequence[str], cfg: st.StrengthConfig
) -> float | None:
    """Сила профиля по `observed`: как `_attach_strength`, с заменами для синтетики.

    T — доля верных ответов теста (вместо положения θ в полосе грейда); нет теста — нет грейда,
    силы нет. F — лучший результат ФСП; S — среднее доверие по навыкам потребности;
    R = 1 (в синтетике нет даты теста), C = 1 (анкета синтетики полная).
    """
    obs = c["observed"]
    blocks = [
        b["answers"] for b in obs.get("tests") or () if len(b["answers"]) >= mt.MIN_TEST_ANSWERS
    ]
    if not blocks:
        return None
    t = sum(sum(a["correct"] for a in ans) / len(ans) for ans in blocks) / len(blocks)
    conf, _, fsp = mt.evidence_conf(obs)
    s = sum(min(1.0, conf.get(k, 0.0)) for k in need_skills) / len(need_skills)
    inp = st.StrengthInput(
        band_position=t, fsp=max(fsp.values(), default=0.0), skills=s, days_since_test=0,
        completeness=1.0,
    )  # fmt: skip
    return st.strength(inp, cfg).value


def collect(market: Any, *, required_mult: float, max_needs: int | None = None) -> list[Need]:
    """Компоненты скора и сила для пар, прошедших жёсткие фильтры. От весов компонентов они
    не зависят; покрытие навыков зависит от множителя обязательного навыка."""
    cfg = dataclasses.replace(sc.MatchConfig.load(), required_mult=required_mult)
    scfg = st.StrengthConfig.load()
    relmat = mt.synth.relevance_matrix(market)
    cands = market.candidates
    views = [mt.candidate_view(c) for c in cands]
    vacancies = [v for v in market.vacancies if relmat.get(v["id"])]
    if max_needs is not None:
        vacancies = vacancies[:max_needs]
    out = []
    for v in vacancies:
        vv = mt.vacancy_view(v)
        need_skills = [*v["must_skills"], *v["nice_skills"]]
        rows = []
        for c, cv in zip(cands, views, strict=True):
            r = sc.score_candidate(vv, cv, {}, cfg)
            if r is None:
                continue
            b = r.breakdown
            comp = (b["skills"], b["grade"], b["salary"], b["fsp"])
            rows.append(Row(c["id"], comp, strength_of(c, need_skills, scfg)))
        out.append(Need(relmat[v["id"]], tuple(rows)))
    return out


def per_need(
    needs: Sequence[Need], w: Mapping[str, float], rank_match: float | None = None
) -> dict[str, list[float]]:
    """precision@10 и nDCG@10 по каждой потребности. `rank_match=None` — режим match."""
    ws = tuple(w[k] for k in COMPONENTS)
    out: dict[str, list[float]] = {"p10": [], "ndcg10": []}
    for n in needs:
        scored = []
        for r in n.rows:
            # как score_candidate: K_soft = 1 (нет командных сигналов), статус не «активно ищу»
            m = round(min(1.0, sum(a * b for a, b in zip(ws, r.comp, strict=True))), 4)
            if rank_match is not None and r.strength is not None:
                m = round(rank_match * m + (1 - rank_match) * r.strength, 6)
            if m > 0:
                scored.append((-m, r.cid))
        ranked = [cid for _, cid in heapq.nsmallest(mt.K, scored)]
        out["p10"].append(mt.precision_at_k(ranked, n.rel))
        out["ndcg10"].append(mt.ndcg_at_k(ranked, n.rel))
    return out


def evaluate(
    needs: Sequence[Need], w: Mapping[str, float], rank_match: float | None = None
) -> dict[str, float]:
    """Среднее precision@10 и nDCG@10 по потребностям."""
    return {k: mt._mean(v) for k, v in per_need(needs, w, rank_match).items()}


def paired_ci(after: Sequence[float], before: Sequence[float]) -> tuple[float, float]:
    """Средняя разница по потребностям и полуширина 95 % интервала (1.96·SE): шум сравнения."""
    d = [a - b for a, b in zip(after, before, strict=True)]
    n = len(d)
    mean = sum(d) / n if n else 0.0
    var = sum((x - mean) ** 2 for x in d) / (n - 1) if n > 1 else 0.0
    return round(mean, 4), round(1.96 * math.sqrt(var / n), 4) if n else 0.0


def both(needs: Sequence[Need], w: Weights) -> dict[str, dict[str, float]]:
    return {"match": evaluate(needs, w.match), "rank": evaluate(needs, w.match, w.rank_match)}


def grid() -> Iterator[dict[str, float]]:
    units, floor = round((1 - SEMANTIC) / STEP), round(FLOOR / STEP)
    for a in range(floor, units + 1):
        for b in range(floor, units - a + 1):
            for c in range(floor, units - a - b + 1):
                d = units - a - b - c
                if d >= floor:
                    vals = (a, b, c, d)
                    yield {k: round(x * STEP, 2) for k, x in zip(COMPONENTS, vals, strict=True)}


def _dist(w: Weights) -> float:
    return (
        sum(abs(w.match[k] - BEFORE.match[k]) for k in COMPONENTS)
        + abs(w.required_mult - BEFORE.required_mult) / 10
        + abs(w.rank_match - BEFORE.rank_match)
    )


def search(train: Mapping[float, Sequence[Need]]) -> Weights:
    """Лучшие веса на train: среднее nDCG@10 режимов match и rank, затем P@10, затем близость."""
    best, best_key = BEFORE, (-1.0, -1.0, 0.0)
    for rq, needs in train.items():
        for w in [dict(BEFORE.match), *grid()]:
            m = evaluate(needs, w)
            for rm in sorted({BEFORE.rank_match, *RANK_GRID}):
                r = evaluate(needs, w, rm)
                cand = Weights(w, rq, rm)
                key = (
                    round((m["ndcg10"] + r["ndcg10"]) / 2, 6),
                    round((m["p10"] + r["p10"]) / 2, 6),
                    -_dist(cand),
                )
                if key > best_key:
                    best, best_key = cand, key
    return best


def improves(after: Mapping[str, Mapping[str, float]], before: Mapping[str, Any]) -> bool:
    """Все четыре числа (P@10 и nDCG@10 в режимах match и rank) строго выросли."""
    return all(after[m][k] > before[m][k] for m in MODES for k in METRICS)


def current_weights() -> Weights:
    cfg = sc.MatchConfig.load()
    return Weights(
        {"skills": cfg.w_skills, "grade": cfg.w_grade, "salary": cfg.w_salary, "fsp": cfg.w_fsp},
        cfg.required_mult,
        st.StrengthConfig.load().rank_match,
    )


def run(
    n_candidates: int | None = None, n_vacancies: int | None = None, max_needs: int | None = None
) -> dict[str, Any]:
    markets = {
        s: mt.synth.generate_market(split=s, n_candidates=n_candidates, n_vacancies=n_vacancies)
        for s in ("dev", "test")
    }
    cur = current_weights()
    mults = sorted({*REQ_GRID, BEFORE.required_mult, cur.required_mult})
    data = {
        s: {rq: collect(m, required_mult=rq, max_needs=max_needs) for rq in mults}
        for s, m in markets.items()
    }
    tuned = search({rq: data["dev"][rq] for rq in REQ_GRID})
    configs = {"before": BEFORE, "current": cur, "tuned": tuned}
    table = {
        name: {
            split: both(data[s][w.required_mult], w)
            for split, s in (("train", "dev"), ("holdout", "test"))
        }
        for name, w in configs.items()
    }
    bm25 = {}
    for split, s in (("train", "dev"), ("holdout", "test")):
        t = mt.run_matching(markets[s], max_needs=max_needs)["table"]
        bm25[split] = {
            k: {"p10": t[k]["p10"], "ndcg10": t[k]["ndcg10"]} for k in ("bm25", "bm25_filtered")
        }
    return {
        "k": mt.K,
        "markets": {s: m.meta() for s, m in markets.items()},
        "needs": {"train": len(data["dev"][mults[0]]), "holdout": len(data["test"][mults[0]])},
        "candidates": {s: len(m.candidates) for s, m in markets.items()},
        "weights": {name: w.as_dict() for name, w in configs.items()},
        "table": table,
        "bm25": bm25,
        "accept": improves(table["tuned"]["holdout"], table["before"]["holdout"]),
        "noise": {
            mode: dict(
                zip(
                    ("mean", "ci95"),
                    paired_ci(
                        per_need(data["test"][tuned.required_mult], tuned.match, rms[0])["ndcg10"],
                        per_need(data["test"][BEFORE.required_mult], BEFORE.match, rms[1])[
                            "ndcg10"
                        ],
                    ),
                    strict=True,
                )
            )
            for mode, rms in (
                ("match", (None, None)),
                ("rank", (tuned.rank_match, BEFORE.rank_match)),
            )
        },
    }


# ---------- отчёт ----------

LABELS = {
    "before": "До (исходные веса)",
    "current": "Сейчас в scoring.yaml",
    "tuned": "Подобрано на train",
}


def _w(w: Mapping[str, Any]) -> str:
    m = w["match"]
    return (
        f"skills {m['skills']:.2f} · semantic {m['semantic']:.2f} · grade {m['grade']:.2f} · "
        f"salary {m['salary']:.2f} · fsp {m['fsp']:.2f}; обязательный навык ×"
        f"{w['required_mult']:g}; rank = {w['rank_match']:.1f}·match + "
        f"{w['rank_strength']:.1f}·strength"
    )


def _d(a: float, b: float) -> str:
    return f"{(a - b):+.3f}" + (f" ({(a / b - 1) * 100:+.1f} %)" if b else "")


def to_markdown(r: Mapping[str, Any]) -> str:
    k = r["k"]
    mk = r["markets"]
    lines = [
        "# Настройка весов подбора",
        "",
        f"Train — синтетический рынок `dev` (seed {mk['dev']['seed']}, {r['candidates']['dev']} "
        f"кандидатов, {r['needs']['train']} потребностей); holdout — рынок `test` (seed "
        f"{mk['test']['seed']}, {r['candidates']['test']} кандидатов, {r['needs']['holdout']} "
        f"потребностей), хеш параметров `{mk['test']['params_hash']}`. Веса выбраны только по "
        "train; решение принять их — по holdout (растут P@10 и nDCG@10 в обоих режимах).",
        "",
        "Режим match — выдача по вакансии (порядок по `score_candidate`); режим rank — выбрана "
        "категория (у кандидата с грейдом порядок по rank, у остальных — по match).",
        "",
        "## Веса",
        "",
        "| Набор | Веса |",
        "|---|---|",
    ]
    lines += [f"| {LABELS[n]} | {_w(w)} |" for n, w in r["weights"].items()]
    for split in ("train", "holdout"):
        lines += [
            "",
            f"## {split}",
            "",
            f"| Метод | match: P@{k} | match: nDCG@{k} | rank: P@{k} | rank: nDCG@{k} |",
            "|---|---|---|---|---|",
        ]
        for n in ("before", "current", "tuned"):
            t = r["table"][n][split]
            lines.append(
                f"| {LABELS[n]} | {t['match']['p10']:.3f} | {t['match']['ndcg10']:.3f} | "
                f"{t['rank']['p10']:.3f} | {t['rank']['ndcg10']:.3f} |"
            )
        b = r["bm25"][split]
        for name, label in (("bm25", "BM25 по резюме"), ("bm25_filtered", "BM25 + фильтры")):
            x = b[name]
            lines.append(f"| {label} | {x['p10']:.3f} | {x['ndcg10']:.3f} | — | — |")
    hb, ht = r["table"]["before"]["holdout"], r["table"]["tuned"]["holdout"]
    bf = r["bm25"]["holdout"]["bm25_filtered"]
    lines += ["", "## Итог на holdout", ""]
    for mode in MODES:
        lines.append(
            f"- {mode}: P@{k} {_d(ht[mode]['p10'], hb[mode]['p10'])}, nDCG@{k} "
            f"{_d(ht[mode]['ndcg10'], hb[mode]['ndcg10'])}; 95 % интервал разницы nDCG@{k} по "
            f"потребностям ±{r['noise'][mode]['ci95']:.3f}."
        )
    lines += [
        f"- Против BM25 с фильтрами (match): до — nDCG@{k} "
        f"{_d(hb['match']['ndcg10'], bf['ndcg10'])}, после — "
        f"{_d(ht['match']['ndcg10'], bf['ndcg10'])}.",
        "- Решение: "
        + (
            "веса приняты — на holdout выросли все четыре числа."
            if r["accept"]
            else "улучшения на holdout нет — веса не меняем."
        ),
        "",
        "Ограничения: рынок синтетический; ручной разметки потребностей в репозитории нет "
        "(`data/gold/relevance.jsonl` не собран) — настройка только на синтетике. Семантика "
        "(эмбеддинги) в синтетике не моделируется, её вес не настраивался. Сила профиля — по "
        "заменам: T — доля верных ответов теста, R = 1, C = 1. Разница между соседними узлами "
        "сетки мала (тысячные доли), поэтому выбор ограничен узкой сеткой рядом с прежними весами.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--candidates", type=int)
    ap.add_argument("--vacancies", type=int)
    ap.add_argument("--max-needs", type=int)
    ap.add_argument("--quick", action="store_true", help="200 кандидатов, 40 вакансий")
    ap.add_argument("--out", type=Path, default=Path("reports/eval-tune"))
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    if a.quick:
        a.candidates, a.vacancies = a.candidates or 200, a.vacancies or 40
    r = run(a.candidates, a.vacancies, a.max_needs)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "tune.json").write_text(
        json.dumps(r, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    md = to_markdown(r)
    (a.out / "tune.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
