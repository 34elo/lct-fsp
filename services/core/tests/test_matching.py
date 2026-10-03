"""Подбор: жёсткие фильтры, скоринг, объяснения — примеры из ml.md §6, matching.md §3–4,
skills.md §8.3."""

import subprocess
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from app.candidates.models import Candidate
from app.companies.models import Company
from app.config import Settings
from app.graph.models import CandidateSkill, Evidence
from app.graph.team_signals import TeamConfig, k_soft
from app.graph.trust import TrustConfig
from app.identity.models import User
from app.matching.models import Match
from app.matching.scoring import (
    EVIDENCE_REQUIRED,
    CandidateView,
    FspProof,
    HeldSkill,
    MatchConfig,
    Requirement,
    VacancyView,
    grade_component,
    salary_component,
    score_candidate,
    semantic_component,
)
from app.matching.service import match_candidate, match_vacancy, match_vacancy_candidates
from app.taxonomy.models import Skill, SkillRelation
from app.vacancies.models import Vacancy, VacancySkill
from app.worker import Worker
from fsp_contracts import new_envelope
from fsp_contracts.commands import CoreMatchCandidate, CoreMatchVacancy
from fsp_platform.db import make_engine, make_session_factory, session_scope
from fsp_platform.outbox import OutboxRecord
from sqlalchemy import func, select

CORE = Path(__file__).resolve().parents[1]
CFG = MatchConfig.load()
TRUST = TrustConfig.load()
TODAY = date(2026, 6, 1)

PY, FASTAPI, KAFKA, RABBIT, DOCKER = (uuid.uuid4() for _ in range(5))
COMPANY = uuid.uuid4()


def _req(sid, slug, required=True, min_level=2, weight=1.0):
    return Requirement(sid, slug, slug.capitalize(), required, min_level, weight)


def _vac(**kw):
    base = dict(
        id=uuid.uuid4(), version=1, company_id=COMPANY, grade_min="middle", grade_max="middle",
        formats=("remote",), salary_from=200_000, salary_to=300_000,
        skills=(_req(PY, "python", min_level=3), _req(KAFKA, "kafka")),
    )  # fmt: skip
    return VacancyView(**{**base, **kw})


def _held(name, conf, level, sources=("github",), claimed=False):
    return HeldSkill(name, conf, level, sources, (f"ev-{name}",), claimed)


def _cand(**kw):
    base = dict(
        id=uuid.uuid4(), profile_version=3, grade="middle", formats=("remote", "hybrid"),
        salary_min=None, status="open",
        skills={PY: _held("Python", 0.7, 3), KAFKA: _held("Kafka", 0.5, 2)},
        grade_evidence=("ev-grade",),
    )  # fmt: skip
    return CandidateView(**{**base, **kw})


ADJ = {KAFKA: [(RABBIT, 0.8)], RABBIT: [(KAFKA, 0.8)]}


def _all_ev(c: CandidateView) -> set[str]:
    out = {e for h in c.skills.values() for e in h.evidence_ids} | set(c.grade_evidence)
    out |= {p.evidence_id for p in c.fsp.values()}
    return out | {e for es in c.team_evidence.values() for e in es}


# --- конфиг и компоненты ----------------------------------------------------------------


def test_config_from_scoring_yaml():
    assert (CFG.w_skills, CFG.w_semantic, CFG.w_grade, CFG.w_salary, CFG.w_fsp) == (
        0.45, 0.20, 0.15, 0.10, 0.10,
    )  # fmt: skip
    assert CFG.target(2) == 0.4 and CFG.target(3) == 0.6  # ml.md §6.2: 2 → 0.4, 3 → 0.6
    assert CFG.salary_grace == 1.10 and CFG.max_failed_required == 2
    assert CFG.team == TeamConfig.load()


def test_semantic_clip():
    assert semantic_component([1, 0], [1, 0], CFG) == 1.0  # cos 1 → 1
    assert semantic_component([1, 0], [0, 1], CFG) == 0.0  # cos 0 → 0
    assert semantic_component(None, [1, 0], CFG) == 0.0
    # cos = 0.575 → (0.575 − 0.30) / 0.55 = 0.5
    a, b = [1.0, 0.0], [0.575, (1 - 0.575**2) ** 0.5]
    assert semantic_component(a, b, CFG) == pytest.approx(0.5)


def test_grade_fit():
    assert grade_component("middle", "middle", "senior", CFG) == 1.0
    assert grade_component("junior_plus", "middle", "senior", CFG) == 0.5
    assert grade_component("junior", "middle", "senior", CFG) == 0.0
    assert grade_component(None, "middle", "senior", CFG) == 0.0


def test_salary_fit_linear_from_mid_to_top():
    assert salary_component(None, 200_000, 300_000) == 1.0
    assert salary_component(250_000, 200_000, 300_000) == 1.0  # ≤ середины вилки
    assert salary_component(275_000, 200_000, 300_000) == pytest.approx(0.5)
    assert salary_component(300_000, 200_000, 300_000) == 0.0
    assert salary_component(320_000, 200_000, 300_000) == 0.0


def test_skills_coverage_weights_required_double():
    # Python обяз. (W=2): 0.7 ≥ 0.6 → 1; Docker желат. (W=1): 0.2 / 0.4 → 0.5
    v = _vac(skills=(_req(PY, "python", min_level=3), _req(DOCKER, "docker", required=False)))
    c = _cand(skills={PY: _held("Python", 0.7, 3), DOCKER: _held("Docker", 0.2, 1)})
    r = score_candidate(v, c, {}, CFG)
    assert r.breakdown["skills"] == pytest.approx((2 * 1 + 1 * 0.5) / 3, abs=1e-4)


def test_full_score_formula():
    # skills 1, semantic 0 (нет векторов), grade 1, salary 1, fsp 0.5; «активно ищу» × 1.03
    c = _cand(status="active", salary_min=240_000, fsp={PY: FspProof("ev-fsp", 0.5, "Кубок")})
    r = score_candidate(_vac(), c, ADJ, CFG)
    base = 0.45 * 1 + 0.20 * 0 + 0.15 * 1 + 0.10 * 1 + 0.10 * 0.5
    assert r.breakdown["base"] == pytest.approx(base)
    assert r.score == pytest.approx(base * 1.03, abs=1e-4)


def test_k_soft_example_from_skills_md():
    # Middle, L = 0.47, T = 0.6, R = 0.6 → K_soft ≈ 1.039; скор только растёт
    team = {"leadership": 0.47, "teamwork": 0.6, "results": 0.6}
    assert k_soft(team, "middle", CFG.team) == pytest.approx(1.0394)
    plain = score_candidate(_vac(), _cand(grade_evidence=()), ADJ, CFG)
    boosted = score_candidate(
        _vac(),
        _cand(grade_evidence=(), team=team, team_evidence={"leadership": ("ev-cap",)}),
        ADJ,
        CFG,
    )
    assert boosted.breakdown["k_soft"] == pytest.approx(1.0394, abs=1e-4)
    assert boosted.score == pytest.approx(min(1, plain.score * 1.0394), abs=1e-4)
    items = [i for i in boosted.explanation if i.code == "team_signal"]
    # T и R без доказательств не показываются; L = 0.47 — «есть подтверждение»
    assert [i.text.split(" (")[0] for i in items] == ["Лидерство — есть подтверждение"]
    assert items[0].evidence_ids == ["ev-cap"]


# --- жёсткие фильтры -------------------------------------------------------------------


@pytest.mark.parametrize(
    "kw",
    [
        {"status": "dnd"},
        {"deleted": True},
        {"stoplist": frozenset({str(COMPANY)})},
        {"formats": ("office",)},
        {"formats": ()},
        {"salary_min": 331_000},  # > 300 000 × 1.10
        {"grade": "junior"},  # две ступени от middle
        {"skills": {}},  # не закрыты 2 обязательных навыка
    ],
)
def test_hard_filters_cut(kw):
    assert score_candidate(_vac(), _cand(**kw), ADJ, CFG) is None


def test_salary_grace_passes_with_warning():
    r = score_candidate(_vac(), _cand(salary_min=320_000), ADJ, CFG)
    assert r is not None and r.breakdown["salary_over"]
    (w,) = [i for i in r.explanation if i.code == "salary_below_min"]
    assert w.kind == "warn" and "выше вилки на 7%" in w.text


def test_one_missing_required_kept_with_minus():
    c = _cand(skills={PY: _held("Python", 0.7, 3)})
    r = score_candidate(_vac(), c, {}, CFG)
    assert r is not None
    (m,) = [i for i in r.explanation if i.code == "skill_missing"]
    assert m.kind == "minus" and m.text == "Нет подтверждения Kafka" and m.weight < 0


def test_adjacent_skill_closes_requirement():
    # RabbitMQ 0.5 × adj 0.8 = 0.4 ≥ target(2) → Kafka закрыт через смежное
    c = _cand(skills={PY: _held("Python", 0.7, 3), RABBIT: _held("RabbitMQ", 0.5, 2)})
    r = score_candidate(_vac(), c, ADJ, CFG)
    (a,) = [i for i in r.explanation if i.code == "skill_adjacent"]
    assert a.text == "Нет подтверждения Kafka (есть смежное: RabbitMQ ●●○○)"
    assert a.kind == "warn" and a.evidence_ids == ["ev-RabbitMQ"]
    assert r.breakdown["skills"] == pytest.approx(1.0)
    # без смежности тот же кандидат теряет Kafka
    assert score_candidate(_vac(), c, {}, CFG).breakdown["skills"] < 1


def test_semantic_only_skips_skill_filter():
    c = _cand(skills={}, embedding=[1.0, 0.0])
    v = _vac(embedding=[1.0, 0.0])
    assert score_candidate(v, c, ADJ, CFG) is None
    r = score_candidate(v, c, ADJ, CFG, semantic_only=True)
    assert r.breakdown["semantic"] == 1.0
    assert any(i.code == "semantic_only" for i in r.explanation)


# --- объяснения ------------------------------------------------------------------------


def test_every_experience_item_references_evidence():
    c = _cand(
        status="active",
        salary_min=240_000,
        skills={
            PY: _held("Python", 0.85, 4, ("github", "test")),
            RABBIT: _held("RabbitMQ", 0.5, 2),
            DOCKER: _held("Docker", 0.3, 1, ("resume",), claimed=True),
        },
        fsp={PY: FspProof("ev-fsp", 0.7, "Кубок России 2025, финал, 2 место")},
        team={"leadership": 0.7},
        team_evidence={"leadership": ("ev-cap",)},
    )
    v = _vac(skills=(_req(PY, "python", 3), _req(KAFKA, "kafka"), _req(DOCKER, "docker", False)))
    r = score_candidate(v, c, ADJ, CFG)
    known = _all_ev(c)
    for i in r.explanation:
        if i.code in EVIDENCE_REQUIRED:
            assert i.evidence_ids, i
        assert set(i.evidence_ids) <= known
    plus = [i for i in r.explanation if i.kind == "plus"]
    assert len(plus) == 3 and plus == sorted(plus, key=lambda i: -i.weight)
    texts = {i.code: i.text for i in r.explanation}
    assert texts["skill_confirmed"] == "Python — подтверждено кодом и тестом (●●●●)"


def test_items_without_evidence_hidden():
    c = _cand(grade_evidence=())  # грейд без доказательств — пункт «грейд» не показываем
    r = score_candidate(_vac(), c, ADJ, CFG)
    assert r.breakdown["grade"] == 1.0
    assert not [i for i in r.explanation if i.code == "grade_fit"]


def test_claimed_only_is_warning():
    c = _cand(skills={PY: _held("Python", 0.7, 3), KAFKA: _held("Kafka", 0.3, 1, ("resume",),
                                                                 claimed=True)})  # fmt: skip
    r = score_candidate(_vac(), c, ADJ, CFG)
    (w,) = [i for i in r.explanation if i.code == "skill_claimed_only"]
    assert w.kind == "warn" and w.text.startswith("Kafka — только заявлено")


# --- БД: отбор SQL + скоринг ------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'm.db'}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"url={url}", "upgrade", "head"],
        cwd=CORE,
        check=True,
        capture_output=True,
    )
    return url


@pytest.fixture
def factory(db):
    return make_session_factory(make_engine(db))


async def _seed(factory):
    now = datetime(2026, 5, 1, tzinfo=UTC)
    async with session_scope(factory) as s:
        sk = {}
        for slug in ("python", "kafka", "rabbitmq"):
            sk[slug] = Skill(slug=f"{slug}-{uuid.uuid4().hex[:4]}", name=slug.capitalize(),
                             kind="hard", source="core")  # fmt: skip
            s.add(sk[slug])
        co = Company(name="ООО Вымысел", status="verified")
        s.add(co)
        await s.flush()
        for a, b in (("kafka", "rabbitmq"), ("rabbitmq", "kafka")):
            s.add(SkillRelation(skill_a=sk[a].id, skill_b=sk[b].id, kind="adjacent", weight=0.8,
                                source="seed"))  # fmt: skip
        v = Vacancy(company_id=co.id, title="Backend", role="backend", grade_min="middle",
                    grade_max="senior", formats=["remote"], employment_type="full",
                    salary_from=200_000, salary_to=300_000, status="published",
                    important_qualities=[])  # fmt: skip
        s.add(v)
        await s.flush()
        s.add(VacancySkill(vacancy_id=v.id, skill_id=sk["python"].id, required=True, min_level=3))
        s.add(VacancySkill(vacancy_id=v.id, skill_id=sk["kafka"].id, required=True, min_level=2))

        async def cand(name, skills, **kw):
            uid = uuid.uuid4()
            s.add(User(id=uid, email=f"{uid.hex}@x.io", password_hash="x", role="candidate"))
            await s.flush()
            c = Candidate(user_id=uid, pseudonym=name, pseudo_id=uid.hex[:12],
                          formats=kw.pop("formats", ["remote"]), grade=kw.pop("grade", "middle"),
                          **kw)  # fmt: skip
            s.add(c)
            await s.flush()
            for slug, conf, lvl, src in skills:
                ev = Evidence(
                    candidate_id=uid, skill_id=sk[slug].id, source=src, strength=conf,
                    observed_at=TODAY, fact_type="fact", fact_id=uuid.uuid4(),
                )  # fmt: skip
                s.add(ev)
                await s.flush()
                s.add(CandidateSkill(candidate_id=uid, skill_id=sk[slug].id, confidence=conf,
                                     level=lvl, sources=[src], top_evidence=[str(ev.id)],
                                     claimed_only=src in ("resume", "self")))  # fmt: skip
            return uid

        ids = {
            "strong": await cand("A", [("python", 0.85, 4, "github"), ("kafka", 0.6, 3, "test")],
                                 search_status="active", active_until=now + timedelta(days=400)),
            "adjacent": await cand("B", [("python", 0.7, 3, "github"),
                                         ("rabbitmq", 0.5, 2, "github")]),
            "one_missing": await cand("C", [("python", 0.65, 3, "github")]),
            "none": await cand("D", [("rabbitmq", 0.2, 1, "resume")]),
            "dnd": await cand("E", [("python", 0.9, 4, "github"), ("kafka", 0.9, 4, "github")],
                              search_status="dnd"),
            "office": await cand("F", [("python", 0.9, 4, "github"), ("kafka", 0.9, 4, "github")],
                                 formats=["office"]),
            "stoplist": await cand("G", [("python", 0.9, 4, "github"),
                                         ("kafka", 0.9, 4, "github")],
                                   stoplist_company_ids=[str(co.id)]),
            "expensive": await cand("H", [("python", 0.9, 4, "github"),
                                          ("kafka", 0.9, 4, "github")], salary_min=400_000),
        }  # fmt: skip
        return v.id, ids


async def test_match_vacancy_end_to_end(factory):
    vid, ids = await _seed(factory)
    async with session_scope(factory) as s:
        res = await match_vacancy_candidates(s, vid, CFG, TrustConfig.load(), today=TODAY)
        got = [r.candidate_id for r in res]
        assert set(got) == {ids["strong"], ids["adjacent"], ids["one_missing"]}
        assert got[0] == ids["strong"]
        assert [r.score for r in res] == sorted((r.score for r in res), reverse=True)
        for r in res:
            mine = set(
                map(str, await s.scalars(select(Evidence.id).where(
                    Evidence.candidate_id == r.candidate_id)))
            )  # fmt: skip
            for i in r.explanation:
                assert set(i.evidence_ids) <= mine
                if i.code in EVIDENCE_REQUIRED:
                    assert i.evidence_ids
        by = {r.candidate_id: r for r in res}
        assert any(i.code == "skill_adjacent" for i in by[ids["adjacent"]].explanation)
        assert any(i.code == "skill_missing" for i in by[ids["one_missing"]].explanation)
        assert by[ids["strong"]].breakdown["active"] is True


async def test_unknown_vacancy_empty(factory):
    async with session_scope(factory) as s:
        assert await match_vacancy_candidates(s, uuid.uuid4(), CFG, TrustConfig.load()) == []


# --- таблица matches (E7-2) ----------------------------------------------------------------


async def _rows(s, vid) -> dict:
    return {
        m.candidate_id: m for m in await s.scalars(select(Match).where(Match.vacancy_id == vid))
    }


async def _count(s, type_) -> int:
    return await s.scalar(select(func.count()).select_from(OutboxRecord).where(
        OutboxRecord.type == type_))  # fmt: skip


async def test_match_vacancy_writes_rows_and_is_stable(factory):
    vid, ids = await _seed(factory)
    async with session_scope(factory) as s:
        assert await match_vacancy(s, vid, CFG, TRUST, today=TODAY) == 3
    async with session_scope(factory) as s:
        rows = await _rows(s, vid)
        assert set(rows) == {ids["strong"], ids["adjacent"], ids["one_missing"]}
        top = rows[ids["strong"]]
        assert top.score == max(m.score for m in rows.values())
        assert top.explanation and all(i["text"] for i in top.explanation)
        assert (top.vacancy_version, top.candidate_version) == (1, 0)
        first = {k: m.score for k, m in rows.items()}
        assert await _count(s, "matches.ready") == 1
    async with session_scope(factory) as s:  # повторный пересчёт не плодит строки
        await match_vacancy(s, vid, CFG, TRUST, today=TODAY)
    async with session_scope(factory) as s:
        rows = await _rows(s, vid)
        assert {k: m.score for k, m in rows.items()} == first


async def test_recompute_drops_candidates_that_no_longer_fit_and_resets_rationale(factory):
    vid, ids = await _seed(factory)
    async with session_scope(factory) as s:
        await match_vacancy(s, vid, CFG, TRUST, today=TODAY)
        (await _rows(s, vid))[ids["strong"]].rationale = "обоснование"
    async with session_scope(factory) as s:
        (await s.get(Candidate, ids["adjacent"])).search_status = "dnd"
        (await s.get(Vacancy, vid)).version = 2
    async with session_scope(factory) as s:
        assert await match_vacancy(s, vid, CFG, TRUST, version=2, today=TODAY) == 2
    async with session_scope(factory) as s:
        rows = await _rows(s, vid)
        assert ids["adjacent"] not in rows
        assert rows[ids["strong"]].rationale is None  # версия вакансии сменилась
        assert rows[ids["strong"]].vacancy_version == 2


async def test_stale_unpublished_and_unknown_are_skipped(factory):
    vid, _ = await _seed(factory)
    async with session_scope(factory) as s:
        (await s.get(Vacancy, vid)).version = 3
    async with session_scope(factory) as s:
        assert await match_vacancy(s, vid, CFG, TRUST, version=2, today=TODAY) is None
        assert await match_vacancy(s, uuid.uuid4(), CFG, TRUST) is None
        assert await _rows(s, vid) == {}
        (await s.get(Vacancy, vid)).status = "closed"
    async with session_scope(factory) as s:
        assert await match_vacancy(s, vid, CFG, TRUST, version=3, today=TODAY) is None


async def test_match_candidate_upserts_and_removes(factory):
    vid, ids = await _seed(factory)
    async with session_scope(factory) as s:
        assert await match_candidate(s, ids["strong"], CFG, TRUST, today=TODAY) == 1
        assert await match_candidate(s, ids["none"], CFG, TRUST, today=TODAY) == 0
        assert await match_candidate(s, uuid.uuid4(), CFG, TRUST) is None
    async with session_scope(factory) as s:
        rows = await _rows(s, vid)
        assert set(rows) == {ids["strong"]}
        by_vacancy = rows[ids["strong"]].score
    async with session_scope(factory) as s:  # тот же скор, что и в подборке по вакансии
        await match_vacancy(s, vid, CFG, TRUST, today=TODAY)
    async with session_scope(factory) as s:
        assert (await _rows(s, vid))[ids["strong"]].score == by_vacancy
        (await s.get(Candidate, ids["strong"])).search_status = "dnd"
    async with session_scope(factory) as s:
        assert await match_candidate(s, ids["strong"], CFG, TRUST, today=TODAY) == 0
    async with session_scope(factory) as s:
        assert ids["strong"] not in await _rows(s, vid)
    async with session_scope(factory) as s:
        (await s.get(Candidate, ids["adjacent"])).profile_version = 5
    async with session_scope(factory) as s:  # устаревшая команда
        assert await match_candidate(s, ids["adjacent"], CFG, TRUST, version=4) is None


async def test_handlers_chain_and_redelivery(db, factory):
    vid, ids = await _seed(factory)
    worker = Worker(Settings(database_url=db))
    pub = new_envelope("vacancy.published", "core", {"vacancy_id": str(vid), "version": 1})
    await worker.consumers["core.handlers"].dispatch(pub)
    await worker.consumers["core.handlers"].dispatch(pub)  # повторная доставка
    async with session_scope(factory) as s:
        assert await _count(s, "core.match.vacancy") == 1
    cmd = new_envelope("core.match.vacancy", "core", CoreMatchVacancy(vacancy_id=vid, version=1))
    await worker.consumers["core.match"].dispatch(cmd)
    await worker.consumers["core.match"].dispatch(cmd)
    async with session_scope(factory) as s:
        assert len(await _rows(s, vid)) == 3
        assert await _count(s, "matches.ready") == 1

    prof = new_envelope(
        "skills.profile.updated", "core",
        {"candidate_id": str(ids["strong"]), "profile_version": 1},
    )  # fmt: skip
    await worker.consumers["core.handlers"].dispatch(prof)
    await worker.consumers["core.handlers"].dispatch(prof)
    async with session_scope(factory) as s:
        assert await _count(s, "core.match.candidate") == 1
        (await s.get(Candidate, ids["strong"])).profile_version = 1
    one = CoreMatchCandidate(candidate_id=ids["strong"], profile_version=1)
    ccmd = new_envelope("core.match.candidate", "core", one)
    await worker.consumers["core.match"].dispatch(ccmd)
    async with session_scope(factory) as s:
        assert ids["strong"] in await _rows(s, vid)

    closed = new_envelope("vacancy.closed", "core", {"vacancy_id": str(vid), "version": 2})
    await worker.consumers["core.handlers"].dispatch(closed)
    async with session_scope(factory) as s:
        assert await _rows(s, vid) == {}
    await worker.engine.dispose()
