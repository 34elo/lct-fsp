"""E16-5: применение решений конвейера, слияние и откат, «точно разные», стоп-лист."""

import datetime as dt
import uuid
from pathlib import Path

import pytest
from app.graph.models import CandidateSkill, Evidence
from app.taxonomy import decisions
from app.taxonomy.models import (
    Skill,
    SkillAlias,
    SkillMention,
    SkillRelation,
)
from app.vacancies.models import VacancySkill
from core_helpers import upgrade_head
from fsp_platform.app import ProblemError
from fsp_platform.db import make_engine, make_session_factory, session_scope
from fsp_platform.outbox import OutboxRecord
from sqlalchemy import func, select

CORE = Path(__file__).resolve().parents[1]
TODAY = dt.date(2026, 10, 1)


@pytest.fixture
def db_url(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'd.db'}"
    upgrade_head(url)
    return url


def _skill(slug: str, status: str = "active", name: str | None = None) -> Skill:
    return Skill(
        id=uuid.uuid4(),
        slug=slug,
        name=name or slug.title(),
        kind="hard",
        status=status,
        source="seed" if status == "active" else "pipeline",
        skill_type="hard",
    )


@pytest.fixture
async def session(db_url):
    engine = make_engine(db_url)
    async with session_scope(make_session_factory(engine)) as s:
        s.add_all([_skill("java"), _skill("javascript"), _skill("postgresql")])
        await s.flush()
        yield s
    await engine.dispose()


async def _id(s, slug: str) -> uuid.UUID:
    return (await s.scalar(select(Skill).where(Skill.slug == slug))).id


def _item(**kw) -> dict:
    base = {"raw": "Helmfile", "norm": "helmfile", "kind": "hard"}
    return {**base, **kw}


async def _events(s) -> int:
    return await s.scalar(select(func.count()).select_from(OutboxRecord))


async def test_new_vertex_provisional_with_alias_and_relation(session):
    out = await decisions.apply_decisions(
        session,
        [
            _item(
                decision="new",
                skill_slug="helmfile",
                relation={"type": "narrower", "to_slug": "java", "confidence": 0.8},
            )
        ],
        context="resume",
    )
    a = out[0]
    assert a.created and not a.alias_added and a.relation == "parent"  # norm == slug
    sk = await session.scalar(select(Skill).where(Skill.slug == "helmfile"))
    assert (sk.status, sk.source) == ("provisional", "pipeline")
    rel = await session.get(SkillRelation, (sk.id, await _id(session, "java"), "parent"))
    assert rel.weight == 0.6
    assert await _events(session) == 1  # taxonomy.updated


async def test_apply_is_idempotent(session):
    item = _item(
        decision="new",
        skill_slug="helmfile",
        relation={"type": "related", "to_slug": "postgresql", "confidence": 0.75},
    )
    await decisions.apply_decisions(session, [item])
    again = await decisions.apply_decisions(session, [item])
    assert not again[0].created and not again[0].alias_added and again[0].relation is None
    count = await session.scalar(
        select(func.count()).select_from(Skill).where(Skill.slug == "helmfile")
    )
    assert count == 1
    rel = await session.get(
        SkillRelation,
        (await _id(session, "postgresql"), await _id(session, "helmfile"), "adjacent"),
    )
    assert rel.weight == 0.6  # 0.75 × 0.8
    assert await _events(session) == 1  # повтор не меняет снимок


async def test_alias_and_fuzzy_add_synonym_only(session):
    out = await decisions.apply_decisions(
        session,
        [
            {
                "raw": "Постгрес",
                "norm": "постгрес",
                "kind": "hard",
                "decision": "alias",
                "skill_slug": "postgresql",
                "reason": "new_synonym",
            },
            {
                "raw": "Javascrpt",
                "norm": "javascrpt",
                "kind": "hard",
                "decision": "fuzzy",
                "skill_slug": "javascript",
            },
        ],
    )
    assert all(o.alias_added and not o.created for o in out)
    assert (await session.get(SkillAlias, "постгрес")).skill_id == await _id(session, "postgresql")
    assert await session.scalar(select(func.count()).select_from(Skill)) == 3


async def test_same_pending_creates_vertex_and_queues(session):
    await decisions.apply_decisions(
        session,
        [
            _item(
                raw="Postgres SQL",
                norm="postgres sql",
                decision="same_pending",
                skill_slug="postgres-sql",
                relation={"type": "same", "to_slug": "postgresql", "confidence": 0.8},
            )
        ],
    )
    sk = await session.scalar(select(Skill).where(Skill.slug == "postgres-sql"))
    assert sk.status == "provisional"
    assert await session.scalar(select(func.count()).select_from(SkillRelation)) == 0
    q = await decisions.pending_merges(session)
    assert q == [
        {"skill": "postgres-sql", "into": "postgresql", "confidence": 0.8, "norm": "postgres sql"}
    ]


async def test_rejected_moderation_goes_to_blocklist_pii_does_not(session):
    out = await decisions.apply_decisions(
        session,
        [
            {
                "raw": "плохоеслово",
                "norm": "плохоеслово",
                "kind": "not_skill",
                "decision": "rejected",
                "reason": "moderation",
            },
            {
                "raw": "[скрыто]",
                "norm": "[скрыто]",
                "kind": "not_skill",
                "decision": "rejected",
                "reason": "pii",
            },
        ],
    )
    assert out[0].decision == "rejected"
    assert await decisions.is_blocked(session, "плохоеслово")
    assert not await decisions.is_blocked(session, "[скрыто]")
    assert await session.scalar(select(func.count()).select_from(SkillMention)) == 1
    # заблокированное упоминание вершину не создаёт
    res = await decisions.apply_decisions(
        session, [_item(raw="плохоеслово", norm="плохоеслово", decision="new", skill_slug="x")]
    )
    assert res[0].blocked and await session.scalar(select(Skill).where(Skill.slug == "x")) is None
    assert await decisions.remove_blocklist(session, "плохоеслово")


async def test_distinct_pairs_crud_and_ordering(session):
    assert await decisions.add_distinct(session, "javascript", "java")
    assert not await decisions.add_distinct(session, "java", "javascript")
    assert await decisions.list_distinct(session) in (
        [("java", "javascript")],
        [("javascript", "java")],
    )
    with pytest.raises(ProblemError) as e:
        await decisions.add_distinct(session, "java", "java")
    assert e.value.code == "distinct_same_skill"
    assert await decisions.remove_distinct(session, "java", "javascript")
    assert await decisions.list_distinct(session) == []


async def _seed_candidates(session, from_slug: str, into_slug: str):
    f, i = await _id(session, from_slug), await _id(session, into_slug)
    c1, c2, c3 = (uuid.uuid4() for _ in range(3))
    shared_fact = uuid.uuid4()

    def ev(cid, sid, strength, fact):
        return Evidence(
            candidate_id=cid,
            skill_id=sid,
            source="resume",
            strength=strength,
            observed_at=TODAY,
            fact_type="experience",
            fact_id=fact,
        )

    # c1: только у from; c2: тот же факт у обоих (дубль, сильнее у from); c3: только у into
    session.add_all(
        [
            ev(c1, f, 0.4, uuid.uuid4()),
            ev(c2, f, 0.7, shared_fact),
            ev(c2, i, 0.3, shared_fact),
            ev(c3, i, 0.5, uuid.uuid4()),
        ]
    )
    session.add(
        CandidateSkill(
            candidate_id=c1,
            skill_id=f,
            confidence=0.4,
            level=2,
            sources=[],
            top_evidence=[],
            claimed_only=False,
        )
    )
    v1, v2 = uuid.uuid4(), uuid.uuid4()
    session.add_all(
        [
            VacancySkill(vacancy_id=v1, skill_id=f, required=True, min_level=3, weight=1.0),
            VacancySkill(vacancy_id=v2, skill_id=f, required=False, min_level=2, weight=0.5),
            VacancySkill(vacancy_id=v2, skill_id=i, required=True, min_level=2, weight=1.0),
        ]
    )
    await session.flush()
    return f, i, (c1, c2, c3), (v1, v2)


async def _ev_rows(session):
    rows = await session.scalars(select(Evidence).execution_options(populate_existing=True))
    return sorted((str(r.candidate_id), str(r.skill_id), r.strength) for r in rows)


async def test_merge_moves_everything_and_revert_restores(session):
    await decisions.apply_decisions(
        session,
        [_item(raw="Postgres SQL", norm="postgres sql", decision="new", skill_slug="postgres-sql")],
    )
    f, i, (c1, c2, c3), (v1, v2) = await _seed_candidates(session, "postgres-sql", "postgresql")
    session.add(
        SkillRelation(
            skill_a=f,
            skill_b=await _id(session, "java"),
            kind="adjacent",
            weight=0.5,
            source="pipeline",
        )
    )
    await session.flush()
    before_ev = await _ev_rows(session)
    events = await _events(session)

    rec = await decisions.merge(session, "postgres-sql", "postgresql", actor="admin:1")
    frm = await session.get(Skill, f)
    assert (frm.status, frm.merged_into) == ("merged", i)
    ev = await session.scalars(
        select(Evidence).where(Evidence.skill_id == f).execution_options(populate_existing=True)
    )
    assert list(ev) == []
    into_ev = {
        (r.candidate_id, r.strength)
        for r in await session.scalars(
            select(Evidence).where(Evidence.skill_id == i).execution_options(populate_existing=True)
        )
    }
    assert into_ev == {(c1, 0.4), (c2, 0.7), (c3, 0.5)}  # дубль схлопнут, остался сильнейший
    vs = {
        r.vacancy_id: r
        for r in await session.scalars(
            select(VacancySkill).execution_options(populate_existing=True)
        )
    }
    assert set(vs) == {v1, v2} and vs[v2].required and vs[v2].weight == 1.0
    assert vs[v1].skill_id == i
    assert await session.get(SkillAlias, "postgres sql") is not None  # синоним слитого
    assert (await session.get(SkillAlias, "postgres sql")).skill_id == i
    assert (
        await session.scalar(
            select(func.count()).select_from(CandidateSkill).where(CandidateSkill.skill_id == f)
        )
        == 0
    )
    assert await session.get(SkillRelation, (i, await _id(session, "java"), "adjacent"))
    ev_changed = await _events(session)
    assert ev_changed == events + 1
    out = (
        await session.scalars(select(OutboxRecord).order_by(OutboxRecord.id.desc()).limit(1))
    ).one()
    assert set(map(str, out.payload["payload"]["changed_skill_ids"])) == {str(f), str(i)}

    await decisions.revert_merge(session, rec.id)
    assert (await session.get(Skill, f)).status == "provisional"
    assert (await session.get(Skill, f)).merged_into is None
    assert await _ev_rows(session) == before_ev
    vs = {
        (r.vacancy_id): r
        for r in await session.scalars(
            select(VacancySkill).execution_options(populate_existing=True)
        )
    }
    assert vs[v1].skill_id == f
    rows2 = {
        r.skill_id: (r.required, r.weight)
        for r in await session.scalars(
            select(VacancySkill)
            .where(VacancySkill.vacancy_id == v2)
            .execution_options(populate_existing=True)
        )
    }
    assert rows2 == {f: (False, 0.5), i: (True, 1.0)}
    assert {
        r.skill_id
        for r in await session.scalars(select(VacancySkill).where(VacancySkill.vacancy_id == v2))
    } == {f, i}
    assert await session.get(SkillAlias, "postgres sql") is None  # добавлен слиянием
    assert await session.get(SkillAlias, "postgres-sql") is None
    assert await session.get(SkillRelation, (f, await _id(session, "java"), "adjacent"))
    assert await session.get(SkillRelation, (i, await _id(session, "java"), "adjacent")) is None
    with pytest.raises(ProblemError) as e:
        await decisions.revert_merge(session, rec.id)
    assert e.value.code == "merge_reverted"


async def test_merge_forbidden_for_distinct_pairs(session):
    await decisions.add_distinct(session, "java", "javascript")
    with pytest.raises(ProblemError) as e:
        await decisions.merge(session, "javascript", "java")
    assert e.value.code == "merge_forbidden_distinct"
    assert (
        await session.scalar(select(Skill).where(Skill.slug == "javascript"))
    ).status == "active"
    # транзитивно: слитый во «from» наследует запрет
    session.add(_skill("js-es6", "provisional"))
    await session.flush()
    await decisions.merge(session, "js-es6", "javascript")
    with pytest.raises(ProblemError):
        await decisions.merge(session, "js-es6", "java")  # js-es6 уже слит
    with pytest.raises(ProblemError) as e2:
        await decisions.merge(session, "java", "javascript")
    assert e2.value.code == "merge_forbidden_distinct"


async def test_merge_guards(session):
    session.add(_skill("pg", "provisional"))
    await session.flush()
    with pytest.raises(ProblemError) as e:
        await decisions.merge(session, "postgresql", "pg")
    assert e.value.code == "merge_into_provisional"
    with pytest.raises(ProblemError) as e:
        await decisions.merge(session, "pg", "pg")
    assert e.value.code == "merge_same_skill"


async def test_approve_and_reject(session):
    session.add_all([_skill("a-new", "provisional"), _skill("b-new", "provisional")])
    await session.flush()
    assert (await decisions.approve(session, "a-new")).status == "active"
    assert (await decisions.reject(session, "b-new")).status == "rejected"
    with pytest.raises(ProblemError):
        await decisions.reject(session, "java")
