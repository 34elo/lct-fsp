import importlib.util
import json
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("synth", ROOT / "tools/synth/synth.py")
synth = importlib.util.module_from_spec(spec)
sys.modules["synth"] = synth  # dataclasses ищут модуль по имени
spec.loader.exec_module(synth)

CFG = synth.load_config()


@pytest.fixture(scope="module")
def market():
    return synth.generate_market(split="dev", n_candidates=1000, n_vacancies=120)


def test_defaults_from_doc():
    assert CFG["counts"]["candidates"] == 1000
    assert CFG["counts"]["vacancies"] == 120
    assert CFG["seeds"]["dev"] != CFG["seeds"]["test"]


def test_deterministic_by_seed():
    a = synth.generate_market(seed=5, n_candidates=50, n_vacancies=10)
    b = synth.generate_market(seed=5, n_candidates=50, n_vacancies=10)
    c = synth.generate_market(seed=6, n_candidates=50, n_vacancies=10)
    dump = lambda m: json.dumps([m.candidates, m.vacancies, m.employers], sort_keys=True)  # noqa: E731
    assert dump(a) == dump(b)
    assert dump(a) != dump(c)
    assert a.meta()["params_hash"] == c.meta()["params_hash"]


def test_independent_from_scoring():
    """Правило честности: генератор не читает scoring.yaml и не импортирует код сервисов."""
    src = (ROOT / "tools/synth/synth.py").read_text(encoding="utf-8")
    assert "scoring" not in src.replace("скоринг", "").split('"""', 2)[2]
    assert "services" not in src.split('"""', 2)[2]
    assert "fsp_contracts" not in src


def test_shares(market):
    cs = market.candidates
    n = len(cs)
    assert 0.20 < sum(c["truth"]["embellisher"] for c in cs) / n < 0.30
    assert 0.35 < sum(c["observed"]["fsp"] is not None for c in cs) / n < 0.45
    assert 0.45 < sum(c["observed"]["github"] is not None for c in cs) / n < 0.55
    assert 0.25 < sum(c["observed"]["tests"] is not None for c in cs) / n < 0.35
    roles = [c["truth"]["role"] for c in cs]
    assert roles.count("backend") > roles.count("frontend") > roles.count("security")


def test_resume_distortions(market):
    listed = total = 0
    for c in market.candidates:
        t = c["truth"]
        resume = c["observed"]["resume"]
        strong = [s for s, v in t["skills"].items() if v > CFG["resume"]["include_min_t"]]
        total += len(strong)
        listed += sum(1 for s in strong if s in resume["skills"])
        if t["embellisher"]:
            assert 1 <= len(t["embellished_skills"]) <= 4
            assert set(t["embellished_skills"]) <= set(resume["skills"])
            assert all(t["skills"].get(s, 0.0) < 0.15 for s in t["embellished_skills"])
            assert 0 <= resume["experience_months"] - t["experience_months"] <= 12
        else:
            assert t["embellished_skills"] == []
            assert resume["experience_months"] == t["experience_months"]
    assert 0.82 < listed / total < 0.88


def test_fsp_place_tracks_hidden_strength(market):
    gen = synth.Generator(CFG, synth.load_taxonomy(), 0)
    pairs = [
        (
            gen.discipline_strength(c["truth"]["skills"], r["discipline"]),
            r["place"] / r["participants"],
        )
        for c in market.candidates
        for r in c["observed"]["fsp"] or []
    ]
    strong = [p for s, p in pairs if s > 0.6]
    weak = [p for s, p in pairs if s < 0.3]
    assert strong and weak
    assert sum(strong) / len(strong) < sum(weak) / len(weak)  # сильные ближе к первым местам


def test_github_fakes(market):
    repos = [r for c in market.candidates for r in c["observed"]["github"] or []]
    share = sum(r["fake"] for r in repos) / len(repos)
    assert 0.06 < share < 0.14
    assert all(r["fake_kind"] for r in repos if r["fake"])


def test_3pl():
    assert synth.theta_of(0.5) == 0
    assert synth.theta_of(1.0) == 2
    assert synth.p_3pl(0.0, 1.0, 0.0, 0.2) == pytest.approx(0.6)
    assert synth.p_3pl(-10, 1.0, 0.0, 0.2) == pytest.approx(0.2, abs=1e-6)
    assert synth.p_3pl(10, 1.0, 0.0, 0.2) == pytest.approx(1.0, abs=1e-6)


def _cand(skills, grade="middle", salary=150_000):
    return {
        "truth": {"skills": skills, "grade": grade},
        "observed": {
            "salary_expectation": salary,
            "fsp": None,
            "github": None,
            "tests": None,
            "work_format": "remote",
        },
    }


VAC = {
    "must_skills": ["python", "sql", "docker"],
    "grade_min": "middle",
    "grade_max": "middle",
    "salary_min": 150_000,
    "salary_max": 200_000,
}


@pytest.mark.parametrize(
    ("skills", "grade", "salary", "expected"),
    [
        ({"python": 0.8, "sql": 0.8, "docker": 0.8}, "middle", 150_000, 2),
        ({"python": 0.8, "sql": 0.8}, "middle", 150_000, 1),  # нет одного обязательного
        ({"python": 0.8, "sql": 0.8, "docker": 0.1}, "middle", 150_000, 1),  # ниже порога
        ({"python": 0.8, "sql": 0.8, "docker": 0.8}, "middle_plus", 150_000, 1),  # грейд рядом
        ({"python": 0.8, "sql": 0.8, "docker": 0.8}, "senior", 150_000, 0),  # грейд на 2 ступени
        ({"python": 0.8}, "middle", 150_000, 0),  # не хватает двух
        ({"python": 0.8, "sql": 0.8}, "junior_plus", 150_000, 0),  # и навык, и грейд
        ({"python": 0.8, "sql": 0.8, "docker": 0.8}, "middle", 250_000, 0),  # вилка
    ],
)
def test_relevance(skills, grade, salary, expected):
    assert synth.relevance(_cand(skills, grade, salary), VAC, CFG) == expected


def test_relevance_has_positives(market):
    rel = synth.relevance_matrix(market)
    with_ideal = sum(1 for row in rel.values() if 2 in row.values())
    assert with_ideal > len(market.vacancies) / 2


def test_employer_session(market):
    emp = market.employers[0]
    ranking = [c["id"] for c in market.candidates[:60]]
    actions = synth.simulate_session(emp, ranking, market, random.Random(1))
    assert len(actions) <= 8
    assert all(a["position"] < 40 for a in actions)
    # Предпочтения сдвигают полезность: «любит капитанов»
    vac = next(v for v in market.vacancies if v["id"] == emp["vacancy_id"])
    cand = _cand({})
    cand["observed"]["fsp"] = [{"captain": True}]
    loves = {"prefs": {"captain": 0.3}}
    neutral = {"prefs": {"captain": 0.0}}
    assert synth.true_utility(loves, cand, vac, CFG) - synth.true_utility(
        neutral, cand, vac, CFG
    ) == pytest.approx(0.3)


def test_cli_writes_files(tmp_path):
    synth.main(["--seed", "3", "--candidates", "20", "--vacancies", "5", "--out", str(tmp_path)])
    for name in (
        "candidates.jsonl",
        "vacancies.jsonl",
        "employers.jsonl",
        "relevance.jsonl",
        "item_bank.json",
        "meta.json",
    ):
        assert (tmp_path / name).exists()
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert meta["seed"] == 3 and meta["counts"]["candidates"] == 20
