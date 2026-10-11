"""Валидация подбора.

Пары «потребность – кандидат»: потребность — вакансия синтетического рынка (обязательные и
желательные навыки, вилка грейдов, зарплата), истинная релевантность `rel` считается по скрытым
уровням (`truth`, tools/synth). Подбор видит только `observed`.

Методы:
- `bm25` — поиск по ключевым словам по тексту резюме (базовое решение);
- `bm25_filtered` — то же с жёсткими фильтрами грейда и зарплаты (усиленная база);
- `ours` — `score_candidate` из core (формулы `data/scoring.yaml`) на уверенностях из доказательств;
- `ours_no_github|no_tests|no_fsp` — абляции источников.

Метрики на потребность (среднее по потребностям, где есть хоть один релевантный кандидат):
precision@10, nDCG@10 (gain = rel), доля «приукрашенных» в топ-10, плюс попадание настоящей
роли в категории, которые предлагает `needs.recommend`.
"""

from __future__ import annotations

import importlib.util
import math
import sys
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
for _p in (ROOT / "services/core", ROOT / "tools/eval"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from app.matching import needs as needs_mod  # noqa: E402
from app.matching import scoring as sc  # noqa: E402
from bm25 import BM25, tokenize  # noqa: E402
from fsp_contracts.ml import SearchFilters, SkillRequirement  # noqa: E402

_spec = importlib.util.spec_from_file_location("synth", ROOT / "tools/synth/synth.py")
synth = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
sys.modules.setdefault("synth", synth)
_spec.loader.exec_module(synth)  # type: ignore[union-attr]

K = 10
METHODS = ("bm25", "bm25_filtered", "ours", "ours_no_github", "ours_no_tests", "ours_no_fsp")
GRADES = sc.GRADES
# Грубая оценка грейда по заявленному стажу (мес): порог каждой ступени, кроме последней.
_GRADE_MONTHS = (6, 14, 24, 42, 60, 96)
_MIN_LEVEL = {"intern": 1, "junior": 2, "junior_plus": 2, "middle": 3, "middle_plus": 3,
              "senior": 4, "lead": 4}  # fmt: skip
# Дисциплина ФСП → навыки, которые подтверждает результат (по смыслу дисциплины).
_FSP_SKILLS = {
    "algorithmic": ("algorithms", "data_structures", "math", "cpp", "python"),
    "product": ("backend", "frontend", "git", "teamwork"),
    "security": ("security", "networks", "linux", "pentest", "cryptography"),
    "uav": ("embedded", "control_systems", "computer_vision"),
    "robotics": ("embedded", "control_systems", "electronics"),
}  # fmt: skip
_LEVEL_W = {"regional": 0.5, "interregional": 0.65, "national": 0.8, "international": 0.9}
CLAIM_CONF = 0.25  # навык, заявленный в резюме, без других источников
GITHUB_CONF = 0.5  # коэффициент при доле авторства
TEST_CONF = 0.9
FSP_CONF = 0.6
MIN_TEST_ANSWERS = 5


def sid(slug: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"skill:{slug}")


def grade_from_months(months: int) -> str:
    for g, lim in zip(GRADES, _GRADE_MONTHS, strict=False):
        if months < lim:
            return g
    return GRADES[-1]


def noisy_or(values: Sequence[float]) -> float:
    out = 1.0
    for v in values:
        out *= 1.0 - v
    return 1.0 - out


def evidence_conf(
    observed: Mapping[str, Any], *, github: bool = True, tests: bool = True, fsp: bool = True
) -> tuple[dict[str, float], dict[str, tuple[str, ...]], dict[str, float]]:
    """Уверенность в навыке по `observed`: ({slug: conf}, {slug: источники}, {slug: сила ФСП})."""
    parts: dict[str, list[tuple[str, float]]] = {}
    for s in observed["resume"]["skills"]:
        parts.setdefault(s, []).append(("resume", CLAIM_CONF))
    if github:
        per: dict[str, list[float]] = {}
        for repo in observed.get("github") or ():
            if repo.get("fake"):
                continue  # подделки отсекает проверка кода
            for t in repo["technologies"]:
                per.setdefault(t, []).append(GITHUB_CONF * repo["authorship_share"])
        for t, vs in per.items():
            parts.setdefault(t, []).append(("github", min(0.7, noisy_or(vs))))
    if tests:
        for blk in observed.get("tests") or ():
            ans = blk["answers"]
            if len(ans) >= MIN_TEST_ANSWERS:
                share = sum(1 for a in ans if a["correct"]) / len(ans)
                parts.setdefault(blk["skill"], []).append(("test", TEST_CONF * share))
    fsp_strength: dict[str, float] = {}
    if fsp:
        for r in observed.get("fsp") or ():
            pct = 1.0 - (r["place"] - 1) / max(1, r["participants"])
            strength = round(pct * _LEVEL_W.get(r["level"], 0.5), 4)
            for s in _FSP_SKILLS.get(r["discipline"], ()):
                fsp_strength[s] = max(fsp_strength.get(s, 0.0), strength)
        for s, st in fsp_strength.items():
            parts.setdefault(s, []).append(("fsp", FSP_CONF * st))
    conf = {s: round(noisy_or([c for _, c in ps]), 4) for s, ps in parts.items()}
    sources = {s: tuple(dict.fromkeys(src for src, _ in ps)) for s, ps in parts.items()}
    return conf, sources, fsp_strength


def candidate_view(c: Mapping[str, Any], **flags: bool) -> sc.CandidateView:
    obs = c["observed"]
    conf, sources, fsp = evidence_conf(obs, **flags)
    skills = {
        sid(s): sc.HeldSkill(
            name=s,
            confidence=v,
            level=max(1, min(5, round(v * 5))),
            sources=sources[s],
            evidence_ids=(f"{c['id']}:{s}",),
            claimed_only=sources[s] == ("resume",),
        )
        for s, v in conf.items()
    }
    proofs = {
        sid(s): sc.FspProof(evidence_id=f"{c['id']}:fsp:{s}", strength=st) for s, st in fsp.items()
    }
    return sc.CandidateView(
        id=uuid.uuid5(uuid.NAMESPACE_URL, c["id"]),
        profile_version=1,
        grade=grade_from_months(obs["resume"]["experience_months"]),
        formats=("remote", "hybrid", "office"),  # истина релевантности формат не учитывает
        salary_min=obs["salary_expectation"],
        status="open",
        skills=skills,
        fsp=proofs,
    )


def vacancy_view(v: Mapping[str, Any]) -> sc.VacancyView:
    lvl = _MIN_LEVEL[v["grade_min"]]
    reqs = [sc.Requirement(sid(s), s, s, True, min_level=lvl) for s in v["must_skills"]] + [
        sc.Requirement(sid(s), s, s, False, min_level=lvl) for s in v["nice_skills"]
    ]
    return sc.VacancyView(
        id=uuid.uuid5(uuid.NAMESPACE_URL, v["id"]),
        version=1,
        company_id=uuid.uuid5(uuid.NAMESPACE_URL, "company"),
        grade_min=v["grade_min"],
        grade_max=v["grade_max"],
        formats=("remote", "hybrid", "office"),
        salary_from=v["salary_min"],
        salary_to=v["salary_max"],
        skills=tuple(reqs),
    )


def need_filters(v: Mapping[str, Any]) -> SearchFilters:
    return SearchFilters(
        skills_must=[SkillRequirement(slug=s) for s in v["must_skills"]],
        skills_nice=list(v["nice_skills"]),
        grade_min=v["grade_min"],
        grade_max=v["grade_max"],
    )


# ---------- метрики ----------


def precision_at_k(ranked: Sequence[str], rel: Mapping[str, int], k: int = K) -> float:
    return sum(1 for c in ranked[:k] if rel.get(c, 0) > 0) / k


def ndcg_at_k(ranked: Sequence[str], rel: Mapping[str, int], k: int = K) -> float:
    dcg = sum(rel.get(c, 0) / math.log2(i + 2) for i, c in enumerate(ranked[:k]))
    ideal = sorted(rel.values(), reverse=True)[:k]
    idcg = sum(g / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def embellished_share(ranked: Sequence[str], embellished: set[str], k: int = K) -> float:
    top = ranked[:k]
    return sum(1 for c in top if c in embellished) / len(top) if top else 0.0


def _rank(scores: Mapping[str, float]) -> list[str]:
    return [c for c, s in sorted(scores.items(), key=lambda x: (-x[1], x[0])) if s > 0]


def _mean(xs: Sequence[float]) -> float:
    return round(sum(xs) / len(xs), 4) if xs else 0.0


def _ratio(a: float, b: float) -> float | None:
    return round(a / b - 1, 4) if b else None


def run_matching(market: Any, *, max_needs: int | None = None) -> dict[str, Any]:
    cfg = sc.MatchConfig.load()
    ncfg = needs_mod.NeedsConfig.load()
    taxonomy = synth.load_taxonomy()
    relmat = synth.relevance_matrix(market)
    cands = market.candidates
    ids = [c["id"] for c in cands]
    embellished = {c["id"] for c in cands if c["truth"]["embellisher"]}
    bm = BM25([tokenize(c["observed"]["resume"]["text"]) for c in cands])
    names = taxonomy.skill_names
    views = {
        "ours": [candidate_view(c) for c in cands],
        "ours_no_github": [candidate_view(c, github=False) for c in cands],
        "ours_no_tests": [candidate_view(c, tests=False) for c in cands],
        "ours_no_fsp": [candidate_view(c, fsp=False) for c in cands],
    }
    graded = [grade_from_months(c["observed"]["resume"]["experience_months"]) for c in cands]
    adjacency: sc.Adjacency = {}
    vacancies = [v for v in market.vacancies if relmat.get(v["id"])]
    if max_needs is not None:
        vacancies = vacancies[:max_needs]

    acc: dict[str, dict[str, list[float]]] = {
        m: {"p10": [], "ndcg10": [], "embellished10": []} for m in METHODS
    }
    cat_hits: list[float] = []
    for v in vacancies:
        rel = relmat[v["id"]]
        query = tokenize(" ".join(names.get(s, s) for s in [*v["must_skills"], *v["nice_skills"]]))
        raw = bm.scores(query)
        passes = []
        for c, g in zip(cands, graded, strict=True):
            d = sc.grade_distance(g, v["grade_min"], v["grade_max"])
            passes.append(
                (d is None or d <= cfg.grade_margin)
                and c["observed"]["salary_expectation"] <= v["salary_max"] * cfg.salary_grace
            )
        rankings: dict[str, list[str]] = {
            "bm25": _rank(dict(zip(ids, raw, strict=True))),
            "bm25_filtered": _rank({i: s for i, s, ok in zip(ids, raw, passes, strict=True) if ok}),
        }
        vv = vacancy_view(v)
        for m, vs in views.items():
            res: dict[str, float] = {}
            for cv, cid in zip(vs, ids, strict=True):
                r = sc.score_candidate(vv, cv, adjacency, cfg)
                if r is not None:
                    res[cid] = r.score
            rankings[m] = _rank(res)
        for m in METHODS:
            acc[m]["p10"].append(precision_at_k(rankings[m], rel))
            acc[m]["ndcg10"].append(ndcg_at_k(rankings[m], rel))
            acc[m]["embellished10"].append(embellished_share(rankings[m], embellished))
        picked = needs_mod.recommend(
            needs_mod.need_weights(need_filters(v), ncfg), taxonomy.role_skills, ncfg
        )
        cat_hits.append(1.0 if v["role"] in {p for p, _ in picked} else 0.0)

    table = {m: {k: _mean(x) for k, x in a.items()} for m, a in acc.items()}
    lift = {
        k: {
            "vs_bm25": _ratio(table["ours"][k], table["bm25"][k]),
            "vs_bm25_filtered": _ratio(table["ours"][k], table["bm25_filtered"][k]),
        }
        for k in ("p10", "ndcg10")
    }
    vs = lift["ndcg10"]["vs_bm25"]
    return {
        "k": K,
        "needs": len(vacancies),
        "candidates": len(cands),
        "embellished_candidates": len(embellished),
        "table": table,
        "lift": lift,
        "fsp_delta_ndcg10": round(table["ours"]["ndcg10"] - table["ours_no_fsp"]["ndcg10"], 4),
        "category_hit": _mean(cat_hits),
        "target": {"lift_vs_bm25": 0.2},
        "meets_target": vs is not None and vs >= 0.2,
    }
