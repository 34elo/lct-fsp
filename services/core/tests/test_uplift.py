"""Uplift (matching.md §6): релевантные вакансии, симуляция, комбинация, способы подтверждения."""

import subprocess
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest
from app.candidates.models import Candidate
from app.companies.models import Company
from app.graph.fsp_models import FspCompetitionRow
from app.graph.models import CandidateSkill, Evidence
from app.graph.trust import TrustConfig
from app.identity.models import User
from app.matching.scoring import (
    CandidateView,
    HeldSkill,
    MatchConfig,
    Requirement,
    VacancyView,
    score_candidate,
)
from app.matching.uplift import UpliftConfig, is_relevant, raise_skills, simulate, top_roles
from app.matching.uplift_service import compute
from app.taxonomy.models import Discipline, DisciplineSkillRule, Skill
from app.vacancies.models import Vacancy, VacancySkill
from fsp_platform.db import make_engine, make_session_factory, session_scope

CORE = Path(__file__).resolve().parents[1]
CFG, TRUST, UCFG = MatchConfig.load(), TrustConfig.load(), UpliftConfig.load()
PY, DOCKER, KAFKA, CONT = (uuid.uuid4() for _ in range(4))
NAMES = {PY: "Python", DOCKER: "Docker", KAFKA: "Kafka", CONT: "Containers"}
COMPANY = uuid.uuid4()


def _vac(salary_to, *reqs):
    return VacancyView(
        uuid.uuid4(), 1, COMPANY, "middle", "middle", ("remote",), 100_000, salary_to,
        tuple(Requirement(s, NAMES[s], NAMES[s], True, lvl) for s, lvl in reqs),
    )  # fmt: skip


def _cand(**kw):
    base = dict(
        id=uuid.uuid4(), profile_version=1, grade="middle", formats=("remote",), salary_min=None,
        status="open", skills={PY: HeldSkill("Python", 0.7, 3, ("github",), ("e1",))},
    )  # fmt: skip
    return CandidateView(**{**base, **kw})


def _world():
    return [
        _vac(250_000, (PY, 3)),  # подходит сейчас
        _vac(300_000, (PY, 3), (DOCKER, 2)),
        _vac(320_000, (PY, 3), (DOCKER, 2)),
        _vac(340_000, (PY, 3), (DOCKER, 2)),
        _vac(360_000, (DOCKER, 2), (KAFKA, 2)),  # нужны оба навыка
        _vac(380_000, (PY, 3), (KAFKA, 2)),
    ]


def _run(vacs, cand=None):
    return simulate(vacs, cand or _cand(), {}, NAMES, lambda s: (), CFG, TRUST, UCFG)


def test_config_from_scoring_yaml():
    assert (UCFG.score_threshold, UCFG.target_confidence) == (0.6, 0.65)
    assert (UCFG.salary_threshold, UCFG.grade_margin) == (0.90, 1)
    assert (UCFG.top_skills, UCFG.combo_max) == (30, 3)


def test_simulation_gain_combo_and_median():
    res = _run(_world())
    assert (res.relevant_total, res.base) == (6, 1)
    gains = {g.skill_id: g for g in res.items}
    assert gains[DOCKER].extra == 3 and gains[DOCKER].pct == 3.0
    assert gains[KAFKA].extra == 1
    # медиана salary_to: было [250] = 250к, стало [250, 300, 320, 340] = 310к
    assert gains[DOCKER].median_salary_delta == 60_000
    assert res.items[0].skill_id == DOCKER  # сортировка по приросту
    assert res.combo_ids == [DOCKER, KAFKA] and res.combo_extra == 5


def test_prediction_equals_actual_after_confirmation():
    """Критерий E17-6: подтвердил навык — число подходящих вакансий ровно предсказанное."""
    vacs, cand = _world(), _cand()
    res = _run(vacs, cand)
    for g in res.items:
        confirmed, _ = raise_skills(cand, g.skill_id, NAMES, lambda s: (), TRUST, 0.65)
        actual = sum(
            1 for v in vacs
            if (r := score_candidate(v, confirmed, {}, CFG)) and r.score >= UCFG.score_threshold
        )  # fmt: skip
        assert actual - res.base == g.extra


def test_base_zero_uses_absolute_gain():
    res = _run([_vac(300_000, (PY, 3), (DOCKER, 2))], _cand(salary_min=None))
    assert res.base == 0
    assert res.items[0].extra == 1 and res.items[0].pct == 1.0  # Δ / max(base, 1)
    assert res.items[0].median_salary_delta == 0


def test_parent_inheritance_in_simulation():
    parents = {DOCKER: ((CONT, 0.8),)}
    new, changed = raise_skills(_cand(), DOCKER, NAMES, lambda s: parents.get(s, ()), TRUST, 0.65)
    assert changed == {DOCKER, CONT}
    assert new.skills[DOCKER].confidence == 0.65 and new.skills[DOCKER].level == 3
    assert new.skills[CONT].confidence == pytest.approx(0.52)
    assert new.skills[PY].confidence == 0.7  # чужое не трогаем; высокое не понижаем
    kept, ch = raise_skills(new, DOCKER, NAMES, lambda s: (), TRUST, 0.60)
    assert ch == set() and kept.skills[DOCKER].confidence == 0.65


def test_relevance_filters():
    v = _vac(200_000, (PY, 3))
    c = _cand()
    assert is_relevant(v, "backend", {"backend"}, c, UCFG)
    assert not is_relevant(v, "frontend", {"backend", "data"}, c, UCFG)  # роль вне топ-2
    assert is_relevant(v, "frontend", set(), c, UCFG)  # ролей нет — не фильтруем
    assert not is_relevant(v, "backend", set(), _cand(formats=("office",)), UCFG)
    assert not is_relevant(v, "backend", set(), _cand(salary_min=230_000), UCFG)  # 0.9·230k > 200k
    assert is_relevant(v, "backend", set(), _cand(salary_min=220_000), UCFG)
    assert not is_relevant(v, "backend", set(), _cand(grade="lead"), UCFG)  # дальше ±1
    assert is_relevant(v, "backend", set(), _cand(grade="junior_plus"), UCFG)


def test_top_roles():
    roles = [{"role": "data", "weight": 0.2}, {"role": "backend", "weight": 0.5},
             {"role": "devops", "weight": 0.3}]  # fmt: skip
    assert top_roles(roles, "backend") == {"backend", "devops"}
    assert top_roles(None, "backend") == {"backend"}
    assert top_roles(None, None) == set()


# --- сервис с БД ---------------------------------------------------------------------------


@pytest.fixture
def factory(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'u.db'}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"url={url}", "upgrade", "head"],
        cwd=CORE, check=True, capture_output=True,
    )  # fmt: skip
    return make_session_factory(make_engine(url))


async def test_compute_end_to_end_with_how_to_confirm(factory):
    today = date(2026, 6, 1)
    async with session_scope(factory) as s:
        uid = uuid.uuid4()
        s.add(User(id=uid, email="u@x.io", password_hash="x", role="candidate"))
        py = Skill(slug=f"py-{uuid.uuid4().hex[:4]}", name="Python", kind="hard", source="core")
        dk = Skill(slug=f"dk-{uuid.uuid4().hex[:4]}", name="Docker", kind="hard", source="core",
                   testable=True)  # fmt: skip
        s.add_all([py, dk, Company(name="ООО Вымысел", status="verified")])
        await s.flush()
        co = (await s.execute(Company.__table__.select())).first()
        cand = Candidate(user_id=uid, pseudonym="A", pseudo_id="aaaa", formats=["remote"],
                         grade="middle", primary_role="backend",
                         roles=[{"role": "backend", "weight": 1.0}], profile_version=2)  # fmt: skip
        s.add(cand)
        for i, sal in enumerate((300_000, 320_000)):
            v = Vacancy(company_id=co.id, title=f"B{i}", role="backend", grade_min="middle",
                        grade_max="middle", formats=["remote"], employment_type="full",
                        salary_from=200_000, salary_to=sal, status="published",
                        important_qualities=[])  # fmt: skip
            s.add(v)
            await s.flush()
            s.add(VacancySkill(vacancy_id=v.id, skill_id=py.id, required=True, min_level=3))
            s.add(VacancySkill(vacancy_id=v.id, skill_id=dk.id, required=True, min_level=2))
        s.add(
            Vacancy(
                company_id=co.id,
                title="Fe",
                role="frontend",
                grade_min="middle",
                grade_max="middle",
                formats=["remote"],
                employment_type="full",
                salary_from=1,
                salary_to=2,
                status="published",
                important_qualities=[],
            )
        )
        ev = Evidence(candidate_id=uid, skill_id=py.id, source="github", strength=0.7,
                      observed_at=today, fact_type="fact", fact_id=uuid.uuid4())  # fmt: skip
        s.add(ev)
        await s.flush()
        s.add(
            CandidateSkill(
                candidate_id=uid,
                skill_id=py.id,
                confidence=0.7,
                level=3,
                sources=["github"],
                top_evidence=[str(ev.id)],
                claimed_only=False,
            )
        )
        s.add(Discipline(slug="devops-cup", name="DevOps"))
        await s.flush()
        s.add(DisciplineSkillRule(discipline="devops-cup", skill_id=dk.id, weight=0.8))
        soon, late = today + timedelta(days=30), today + timedelta(days=200)
        s.add(FspCompetitionRow(id="c1", title="Кубок DevOps", discipline="devops-cup",
                                start_date=soon, status="registration",
                                registration_url="https://fsp.example/c1"))  # fmt: skip
        s.add(FspCompetitionRow(id="c2", title="Поздний", discipline="devops-cup",
                                start_date=late, status="announced"))  # fmt: skip
    async with session_scope(factory) as s:
        cand = await s.get(Candidate, uid)
        out = await compute(s, None, cand, CFG, TRUST, UCFG, today)
        assert out["relevant_total"] == 2 and out["base"] == 0  # вакансия frontend не релевантна
        (item,) = out["items"]
        assert item["name"] == "Docker" and item["extra"] == 2 and item["pct"] == 2.0
        assert item["current_level"] == 0
        assert item["median_salary_delta"] == 0  # base = 0: сравнивать не с чем
        kinds = [h["kind"] for h in item["how_to_confirm"]]
        assert kinds == ["test", "github", "fsp_competition"]  # c2 дальше 120 дней
        assert item["how_to_confirm"][0]["minutes"] == 10
        comp = item["how_to_confirm"][2]
        assert comp["id"] == "c1" and comp["registration_url"] == "https://fsp.example/c1"
        assert out["combo"] is None  # один навык — комбинации нет
