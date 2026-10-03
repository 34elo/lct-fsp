"""Синтетический рынок для стенда оценки (evaluation.md §3).

Правило честности: генератор устроен иначе, чем подбор. «Настоящие» уровни навыков порождает
собственная латентная модель (роль, стаж, талант τ, склонность приукрашивать π); формулы доверия,
грейда и скоринга (data/scoring.yaml, services/*) здесь не используются.

У каждого кандидата две части: `truth` (скрытое — только для подсчёта метрик) и `observed`
(то, что увидел бы продукт: резюме, ФСП, GitHub, тесты). Подбор должен получать только `observed`.

Запуск:
    uv run python tools/synth/synth.py --split dev --out reports/synth/dev
    uv run python tools/synth/synth.py --seed 7 --candidates 200 --out /tmp/m
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path(__file__).with_name("config.yaml")
ROLES_PATH = ROOT / "data/taxonomy/roles.yaml"
SKILLS_PATH = ROOT / "data/taxonomy/skills.yaml"


# ---------- справочники и конфиг ----------


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class Taxonomy:
    role_skills: dict[str, dict[str, float]]  # роль → {навык: типичность 0..1}
    skill_names: dict[str, str]
    testable: list[str]


def load_taxonomy() -> Taxonomy:
    roles = yaml.safe_load(ROLES_PATH.read_text(encoding="utf-8"))["roles"]
    skills = yaml.safe_load(SKILLS_PATH.read_text(encoding="utf-8"))["skills"]
    return Taxonomy(
        role_skills={r["slug"]: dict(r["skills"]) for r in roles},
        skill_names={s["slug"]: s["name"] for s in skills},
        testable=sorted(s["slug"] for s in skills if s.get("testable")),
    )


# ---------- математика ----------


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def p_3pl(theta: float, a: float, b: float, c: float) -> float:
    """Вероятность верного ответа в модели 3PL (D = 1.7)."""
    return c + (1.0 - c) * sigmoid(1.7 * a * (theta - b))


def theta_of(t: float) -> float:
    """Способность в шкале IRT по настоящему уровню навыка: θ = 4·(t − 0.5)."""
    return 4.0 * (t - 0.5)


def _weighted(rng: random.Random, weights: dict[str, float]) -> str:
    keys = sorted(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


def _sample_weighted_distinct(rng: random.Random, weights: dict[str, float], k: int) -> list[str]:
    pool = dict(weights)
    out: list[str] = []
    while pool and len(out) < k:
        s = _weighted(rng, pool)
        out.append(s)
        del pool[s]
    return out


def _uniform(rng: random.Random, lo_hi: list[float]) -> float:
    return rng.uniform(lo_hi[0], lo_hi[1])


def _randint(rng: random.Random, lo_hi: list[int]) -> int:
    return rng.randint(lo_hi[0], lo_hi[1])


# ---------- сущности ----------


@dataclass
class Market:
    seed: int
    params: dict[str, Any]
    candidates: list[dict[str, Any]] = field(default_factory=list)
    vacancies: list[dict[str, Any]] = field(default_factory=list)
    employers: list[dict[str, Any]] = field(default_factory=list)
    competitions: list[dict[str, Any]] = field(default_factory=list)
    item_bank: dict[str, list[dict[str, float]]] = field(default_factory=dict)

    def meta(self) -> dict[str, Any]:
        """Параметры генератора — для страницы качества (evaluation.md §3.5)."""
        blob = json.dumps(self.params, sort_keys=True, ensure_ascii=False).encode()
        return {
            "seed": self.seed,
            "params_hash": hashlib.sha256(blob).hexdigest()[:12],
            "counts": {
                "candidates": len(self.candidates),
                "vacancies": len(self.vacancies),
                "employers": len(self.employers),
                "competitions": len(self.competitions),
            },
            "params": self.params,
        }


class Generator:
    def __init__(self, config: dict[str, Any], taxonomy: Taxonomy, seed: int) -> None:
        self.cfg = config
        self.tax = taxonomy
        self.seed = seed
        self.rng = random.Random(seed)
        self.roles = sorted(r for r in config["role_share"] if r in taxonomy.role_skills)
        # Параметры навыков a_s, b_s — свои для каждого навыка, фиксируются seed'ом
        all_skills = sorted({s for r in self.roles for s in taxonomy.role_skills[r]})
        lat = config["latent"]
        self.skill_ab = {
            s: (_uniform(self.rng, lat["skill_a"]), _uniform(self.rng, lat["skill_b"]))
            for s in all_skills
        }

    # --- банк вопросов и соревнования ---

    def item_bank(self) -> dict[str, list[dict[str, float]]]:
        t = self.cfg["tests"]
        n = self.cfg["counts"]["test_items_per_skill"]
        return {
            s: [
                {
                    "item_id": f"{s}-q{i}",
                    "a": round(_uniform(self.rng, t["irt_a"]), 3),
                    "b": round(_uniform(self.rng, t["irt_b"]), 3),
                    "c": round(_uniform(self.rng, t["irt_c"]), 3),
                }
                for i in range(n)
            ]
            for s in self.tax.testable
        }

    def competitions(self) -> list[dict[str, Any]]:
        f = self.cfg["fsp"]
        disciplines = sorted(f["discipline_skills"])
        out = []
        for i in range(self.cfg["counts"]["competitions"]):
            level = _weighted(self.rng, f["level_share"])
            out.append(
                {
                    "id": f"comp-{i:03d}",
                    "discipline": self.rng.choice(disciplines),
                    "level": level,
                    "participants": _randint(self.rng, f["participants"][level]),
                }
            )
        return out

    # --- кандидаты ---

    def true_skills(self, role: str, years: float, tau: float) -> dict[str, float]:
        lat = self.cfg["latent"]
        profile = self.tax.role_skills[role]
        pw = lat["skill_presence_pow"]
        chosen = [s for s in sorted(profile) if self.rng.random() < profile[s] ** pw]
        adjacent = [r for r in self.cfg["adjacent_roles"].get(role, []) if r in self.roles]
        extra_pool = sorted({s for r in adjacent for s in self.tax.role_skills[r]} - set(chosen))
        n_extra = min(_randint(self.rng, lat["extra_skills"]), len(extra_pool))
        chosen += self.rng.sample(extra_pool, n_extra)
        out = {}
        for s in chosen:
            a, b = self.skill_ab[s]
            z = (
                a * tau
                + b * math.log1p(years)
                + lat["skill_intercept"]
                + self.rng.gauss(0, lat["skill_noise_sd"])
            )
            out[s] = round(sigmoid(z), 4)
        return out

    def true_grade(self, years: float, tau: float) -> str:
        lat = self.cfg["latent"]
        eff = years * math.exp(lat["grade_talent_mult"] * tau)
        idx = sum(1 for th in lat["grade_years"] if eff >= th)
        return self.cfg["grades"][idx]

    def resume(
        self, role: str, skills: dict[str, float], months: int, embellisher: bool
    ) -> tuple[dict[str, Any], list[str]]:
        r = self.cfg["resume"]
        listed = [
            s
            for s in sorted(skills)
            if skills[s] > r["include_min_t"] and self.rng.random() < r["include_p"]
        ]
        embellished: list[str] = []
        shown_months = months
        if embellisher:
            # Слабые свои навыки или навыки соседних ролей, которых нет вовсе (t = 0)
            weak = [s for s in sorted(skills) if skills[s] < r["embellish_max_t"]]
            foreign = sorted(
                {s for rr in self.roles for s in self.tax.role_skills[rr]} - set(skills)
            )
            pool = sorted(set(weak + self.rng.sample(foreign, min(10, len(foreign)))))
            k = min(_randint(self.rng, r["embellish_count"]), len(pool))
            embellished = self.rng.sample(pool, k)
            listed = sorted(set(listed) | set(embellished))
            shown_months = months + _randint(self.rng, r["experience_inflate_months"])
        names = [self.tax.skill_names.get(s, s) for s in listed]
        text = (
            f"Роль: {role}. Опыт: {shown_months // 12} г. {shown_months % 12} мес. "
            f"Навыки: {', '.join(names)}."
        )
        return {"skills": listed, "experience_months": shown_months, "text": text}, embellished

    def discipline_strength(self, skills: dict[str, float], discipline: str) -> float:
        vals = sorted(
            (skills.get(s, 0.0) for s in self.cfg["fsp"]["discipline_skills"][discipline]),
            reverse=True,
        )
        top = vals[:3]
        return sum(top) / len(top)

    def fsp(
        self, skills: dict[str, float], tau: float, comps: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        f = self.cfg["fsp"]
        strength = {d: self.discipline_strength(skills, d) for d in sorted(f["discipline_skills"])}
        # Участвует чаще там, где сильнее
        by_disc = {d: [c for c in comps if c["discipline"] == d] for d in strength}
        weights = {d: strength[d] + 0.05 for d in strength if by_disc[d]}
        n = _randint(self.rng, f["competitions_per_candidate"])
        results = []
        used: set[str] = set()
        for _ in range(n):
            d = _weighted(self.rng, weights)
            options = [c for c in by_disc[d] if c["id"] not in used]
            if not options:
                continue
            comp = self.rng.choice(options)
            used.add(comp["id"])
            mean, sd = f["opponent_strength"][comp["level"]]
            me = strength[d] + self.rng.gauss(0, f["noise_sd"])
            better = sum(
                1
                for _ in range(comp["participants"] - 1)
                if self.rng.gauss(mean, sd) + self.rng.gauss(0, f["noise_sd"]) > me
            )
            captain = d == "product" and self.rng.random() < sigmoid(
                f["captain_base"] + f["captain_tau"] * tau
            )
            results.append(
                {
                    "competition_id": comp["id"],
                    "discipline": d,
                    "level": comp["level"],
                    "place": better + 1,
                    "participants": comp["participants"],
                    "captain": captain,
                }
            )
        return results

    def github(self, skills: dict[str, float]) -> list[dict[str, Any]]:
        g = self.cfg["github"]
        strong = [s for s in sorted(skills) if skills[s] > g["tech_min_t"]]
        everything = sorted({s for r in self.roles for s in self.tax.role_skills[r]})
        repos = []
        for i in range(_randint(self.rng, g["repos"])):
            if self.rng.random() < g["fake_repo_p"]:
                techs = sorted(self.rng.sample(everything, self.rng.randint(1, 3)))
                repos.append(
                    {
                        "repo": f"repo-{i}",
                        "technologies": techs,
                        "authorship_share": round(self.rng.uniform(0.0, 0.1), 3),
                        "fake": True,
                        "fake_kind": self.rng.choice(g["fake_kinds"]),
                    }
                )
                continue
            techs = [s for s in strong if self.rng.random() < g["tech_p"]]
            repos.append(
                {
                    "repo": f"repo-{i}",
                    "technologies": techs,
                    "authorship_share": round(self.rng.betavariate(5, 2), 3),
                    "fake": False,
                    "fake_kind": None,
                }
            )
        return repos

    def tests(self, skills: dict[str, float], bank: dict[str, list[dict[str, float]]]) -> list:
        t = self.cfg["tests"]
        # Тест проходят по заявленным/своим навыкам; навыка нет — t = 0 (честно проваливает)
        own = [s for s in sorted(skills) if s in bank]
        pool = own or sorted(bank)
        out = []
        for s in self.rng.sample(pool, min(_randint(self.rng, t["skills"]), len(pool))):
            theta = theta_of(skills.get(s, 0.0))
            items = self.rng.sample(bank[s], min(_randint(self.rng, t["items"]), len(bank[s])))
            answers = [
                {
                    "item_id": it["item_id"],
                    "correct": self.rng.random() < p_3pl(theta, it["a"], it["b"], it["c"]),
                }
                for it in items
            ]
            out.append({"skill": s, "answers": answers})
        return out

    def salary(self, grade: str) -> int:
        base = self.cfg["salary_by_grade"][grade]
        val = base * math.exp(self.rng.gauss(0, self.cfg["salary_noise_sd"]))
        return int(round(val / 5000) * 5000)

    def candidate(self, i: int, comps: list, bank: dict) -> dict[str, Any]:
        lat = self.cfg["latent"]
        role = _weighted(self.rng, {r: self.cfg["role_share"][r] for r in self.roles})
        g = lat["experience_years_gamma"]
        years = self.rng.gammavariate(g["shape"], g["scale"])
        tau = self.rng.gauss(0, 1)
        embellisher = self.rng.random() < lat["embellish_p"]
        skills = self.true_skills(role, years, tau)
        months = int(round(years * 12))
        grade = self.true_grade(years, tau)
        resume, embellished = self.resume(role, skills, months, embellisher)
        observed: dict[str, Any] = {
            "role": role,
            "resume": resume,
            "fsp": self.fsp(skills, tau, comps)
            if self.rng.random() < self.cfg["fsp"]["share"]
            else None,
            "github": self.github(skills)
            if self.rng.random() < self.cfg["github"]["share"]
            else None,
            "tests": self.tests(skills, bank)
            if self.rng.random() < self.cfg["tests"]["share"]
            else None,
            "salary_expectation": self.salary(grade),
            "work_format": _weighted(self.rng, self.cfg["formats"]),
        }
        return {
            "id": f"c-{i:05d}",
            "truth": {
                "role": role,
                "experience_months": months,
                "talent": round(tau, 4),
                "embellisher": embellisher,
                "grade": grade,
                "skills": skills,
                "embellished_skills": sorted(embellished),
            },
            "observed": observed,
        }

    # --- вакансии и работодатели ---

    def vacancy(self, i: int) -> dict[str, Any]:
        v = self.cfg["vacancies"]
        grades = self.cfg["grades"]
        role = _weighted(self.rng, {r: self.cfg["role_share"][r] for r in self.roles})
        profile = self.tax.role_skills[role]
        must = _sample_weighted_distinct(self.rng, profile, _randint(self.rng, v["must"]))
        rest = {s: w for s, w in profile.items() if s not in must}
        nice = _sample_weighted_distinct(self.rng, rest, _randint(self.rng, v["nice"]))
        gi = self.rng.randrange(len(grades))
        gj = min(gi + 1, len(grades) - 1) if self.rng.random() < v["grade_span_p"] else gi
        market_lo = self.cfg["salary_by_grade"][grades[gi]]
        market_hi = self.cfg["salary_by_grade"][grades[gj]]
        lo = int(round(market_lo * _uniform(self.rng, v["fork_low"]) / 5000) * 5000)
        hi = int(round(market_hi * _uniform(self.rng, v["fork_high"]) / 5000) * 5000)
        return {
            "id": f"v-{i:04d}",
            "role": role,
            "grade_min": grades[gi],
            "grade_max": grades[gj],
            "must_skills": sorted(must),
            "nice_skills": sorted(nice),
            "salary_min": lo,
            "salary_max": max(hi, lo),
            "work_format": _weighted(self.rng, self.cfg["formats"]),
        }

    def employer(self, i: int, vacancies: list[dict[str, Any]]) -> dict[str, Any]:
        e = self.cfg["employers"]
        prefs = {f: round(_uniform(self.rng, e["pref_weight"]), 3) for f in e["pref_features"]}
        return {"id": f"e-{i:03d}", "vacancy_id": self.rng.choice(vacancies)["id"], "prefs": prefs}

    def build(self, n_candidates: int | None = None, n_vacancies: int | None = None) -> Market:
        counts = self.cfg["counts"]
        bank = self.item_bank()
        comps = self.competitions()
        nc = n_candidates if n_candidates is not None else counts["candidates"]
        nv = n_vacancies if n_vacancies is not None else counts["vacancies"]
        candidates = [self.candidate(i, comps, bank) for i in range(nc)]
        vacancies = [self.vacancy(i) for i in range(nv)]
        employers = [self.employer(i, vacancies) for i in range(counts["employers"])] if nv else []
        return Market(
            seed=self.seed,
            params=self.cfg,
            candidates=candidates,
            vacancies=vacancies,
            employers=employers,
            competitions=comps,
            item_bank=bank,
        )


def generate_market(
    seed: int | None = None,
    split: str = "dev",
    config: dict[str, Any] | None = None,
    n_candidates: int | None = None,
    n_vacancies: int | None = None,
) -> Market:
    cfg = config or load_config()
    s = seed if seed is not None else cfg["seeds"][split]
    return Generator(cfg, load_taxonomy(), s).build(n_candidates, n_vacancies)


# ---------- истинная релевантность (§3.3) ----------


def relevance(candidate: dict[str, Any], vacancy: dict[str, Any], config: dict[str, Any]) -> int:
    """2 — все обязательные навыки на уровне, грейд в диапазоне, вилка совместима;
    1 — не хватает ровно одного обязательного ИЛИ грейд на ступень рядом; иначе 0.
    Считается только по настоящим уровням (`truth`)."""
    truth = candidate["truth"]
    grades = config["grades"]
    if candidate["observed"]["salary_expectation"] > vacancy["salary_max"]:
        return 0
    threshold = config["required_level"][vacancy["grade_min"]]
    missing = sum(1 for s in vacancy["must_skills"] if truth["skills"].get(s, 0.0) < threshold)
    g = grades.index(truth["grade"])
    lo, hi = grades.index(vacancy["grade_min"]), grades.index(vacancy["grade_max"])
    grade_gap = max(lo - g, g - hi, 0)
    if missing == 0 and grade_gap == 0:
        return 2
    if (missing == 1 and grade_gap == 0) or (missing == 0 and grade_gap == 1):
        return 1
    return 0


def relevance_matrix(market: Market) -> dict[str, dict[str, int]]:
    """vacancy_id → {candidate_id: rel} только для rel > 0 (разреженно)."""
    out: dict[str, dict[str, int]] = {}
    for v in market.vacancies:
        row = {}
        for c in market.candidates:
            r = relevance(c, v, market.params)
            if r:
                row[c["id"]] = r
        out[v["id"]] = row
    return out


# ---------- симулированные работодатели (§3.4) ----------


def employer_features(candidate: dict[str, Any], vacancy: dict[str, Any]) -> dict[str, float]:
    obs = candidate["observed"]
    fsp = obs["fsp"] or []
    mid = (vacancy["salary_min"] + vacancy["salary_max"]) / 2
    return {
        "captain": float(any(r["captain"] for r in fsp)),
        "fsp": float(bool(fsp)),
        "github": float(obs["github"] is not None),
        "tests": float(obs["tests"] is not None),
        "remote": float(obs["work_format"] == "remote"),
        "cheap": float(obs["salary_expectation"] < mid),
    }


def true_utility(
    employer: dict[str, Any],
    candidate: dict[str, Any],
    vacancy: dict[str, Any],
    config: dict[str, Any],
) -> float:
    """Скрытая полезность: истинная релевантность + вкусы работодателя («любит капитанов»)."""
    e = config["employers"]
    feats = employer_features(candidate, vacancy)
    taste = sum(employer["prefs"].get(f, 0.0) * x for f, x in feats.items())
    return (
        e["utility_rel_weight"] * relevance(candidate, vacancy, config) + taste + e["utility_bias"]
    )


def simulate_session(
    employer: dict[str, Any],
    ranking: list[str],
    market: Market,
    rng: random.Random,
) -> list[dict[str, Any]]:
    """Каскадная модель кликов: P(клик на k) = decay^k · σ(полезность).
    Показов 20–40, действий 3–8 (останавливаемся, когда набрали лимит действий)."""
    e = market.params["employers"]
    by_id = {c["id"]: c for c in market.candidates}
    vacancy = next(v for v in market.vacancies if v["id"] == employer["vacancy_id"])
    shows = min(_randint(rng, e["session_shows"]), len(ranking))
    max_actions = _randint(rng, e["session_actions"])
    actions = []
    for pos, cid in enumerate(ranking[:shows]):
        if len(actions) >= max_actions:
            break
        if rng.random() >= e["view_decay"] ** pos:
            continue
        u = true_utility(employer, by_id[cid], vacancy, market.params)
        if rng.random() < sigmoid(u):
            actions.append({"candidate_id": cid, "position": pos, "action": "click"})
    return actions


# ---------- CLI ----------


def write_market(market: Market, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)

    def dump(name: str, rows: list[dict[str, Any]]) -> None:
        with (out / name).open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    dump("candidates.jsonl", market.candidates)
    dump("vacancies.jsonl", market.vacancies)
    dump("employers.jsonl", market.employers)
    dump("competitions.jsonl", market.competitions)
    rel = relevance_matrix(market)
    dump("relevance.jsonl", [{"vacancy_id": v, "labels": rel[v]} for v in sorted(rel)])
    (out / "item_bank.json").write_text(
        json.dumps(market.item_bank, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    (out / "meta.json").write_text(
        json.dumps(market.meta(), ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Синтетический рынок (evaluation.md §3)")
    p.add_argument("--split", choices=["dev", "test"], default="dev")
    p.add_argument("--seed", type=int, default=None, help="перекрывает seed split'а")
    p.add_argument("--candidates", type=int, default=None)
    p.add_argument("--vacancies", type=int, default=None)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)
    m = generate_market(a.seed, a.split, None, a.candidates, a.vacancies)
    write_market(m, a.out)
    meta = m.meta()
    print(f"seed={meta['seed']} params={meta['params_hash']} {meta['counts']} → {a.out}")


if __name__ == "__main__":
    main()
