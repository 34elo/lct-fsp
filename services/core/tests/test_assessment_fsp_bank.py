"""E32-6: задачи соревнований ФСП в банке без преимущества участников."""

import dataclasses
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.assessment import engine, fsp_bank, lifecycle, psychometrics_db
from app.assessment.attempts import family_of
from app.assessment.config import load_config
from app.assessment.lifecycle import FamilyStats, admission_failures
from app.assessment.models import Attempt, FamilyRow, Response
from app.graph import service as graph
from app.graph.fsp_models import FspResultRow, FspTeamMember, FspTeamRow
from app.taxonomy import service as tax
from app.taxonomy.loader import load_taxonomy
from fsp_contracts.assessment import TestGrade
from fsp_platform.db import session_scope
from sqlalchemy import select

CFG = load_config()
TAXONOMY = Path(__file__).resolve().parents[3] / "data" / "taxonomy"

FORM = {
    "title": "Сумма до N",
    "kind": "exact",
    "skill": "algorithms",
    "level": 3,
    "stem": "Чему равна сумма чисел от 1 до {{n}}?",
    "params": {"n": {"min": 10, "max": 90, "step": 5}},
    "answer": "n * (n + 1) / 2",
    "precision": 0,
}
COMP = {
    "id": "c-777",
    "title": "Кубок (демо)",
    "year": 2025,
    "url": "https://example.test/cup",
    "license": "author",
}


def bank(**over):
    return {
        "schema": 1,
        "competition": {**COMP, **over.pop("competition", {})},
        "tasks": [{"form": FORM}],
        **over,
    }


@pytest.fixture
async def taxonomy_loaded(factory):
    async with session_scope(factory) as s:
        await tax.sync(s, load_taxonomy(TAXONOMY))


# --- проверка банка ---------------------------------------------------------------------------


def test_valid_bank_passes():
    assert fsp_bank.check_bank(bank()) == []


def test_provenance_is_required():
    assert fsp_bank.check_bank(bank(competition={"license": "all-rights-reserved"}))
    errs = fsp_bank.check_bank(bank(competition={"license": "fsp-permission"}))
    assert any("permission" in e for e in errs)
    assert (
        fsp_bank.check_bank(
            bank(competition={"license": "fsp-permission", "permission": "письмо ФСП от 01.10"})
        )
        == []
    )
    assert fsp_bank.check_bank(bank(competition={"url": ""}))
    assert fsp_bank.check_bank({"schema": 2, "tasks": []})


def test_tasks_need_key_and_test_kind():
    no_key = {k: v for k, v in FORM.items() if k != "answer"} | {
        "kind": "choice",
        "options": ["a", "b"],
    }
    errs = fsp_bank.check_bank({**bank(), "tasks": [{"form": no_key}]})
    assert any("нет ключа" in e for e in errs)
    open_ = {**FORM, "kind": "open", "rubric": ["a"], "answer": None}
    assert any(
        "не идёт в тест" in e for e in fsp_bank.check_bank({**bank(), "tasks": [{"form": open_}]})
    )
    dup = {**bank(), "tasks": [{"slug": "x", "form": FORM}, {"slug": "x", "form": FORM}]}
    assert any("повтор" in e for e in fsp_bank.check_bank(dup))
    assert any("справочнике" in e for e in fsp_bank.check_bank(bank(), taxonomy_skills={"python"}))


def test_repo_banks_and_families_check_hook():
    assert fsp_bank.check_files(fsp_bank.bank_files()) == []
    from app.assessment.families import check

    assert check.check_fsp_banks() == []


# --- импорт ----------------------------------------------------------------------------------


async def test_import_is_idempotent_and_builds_family(factory, taxonomy_loaded):
    async with session_scope(factory) as s:
        out = await fsp_bank.import_bank(s, bank(), CFG)
    assert out["created"] == 1
    async with session_scope(factory) as s:
        row = (await s.scalars(select(FamilyRow).where(FamilyRow.source == "fsp"))).one()
        assert (row.status, row.key_status, row.competition_id) == ("draft", "approved", "c-777")
        assert row.b == CFG.prior_b(3) and not row.anchor
        assert row.spec["fsp"]["license"] == "author"
        assert family_of(row) is not None
        again = await fsp_bank.import_bank(s, bank(), CFG)
        assert again["unchanged"] == 1 and again["created"] == 0
        changed = await fsp_bank.import_bank(s, bank(competition={"title": "Другое"}), CFG)
        assert changed["kept"] == 1
        bad = {**bank(), "tasks": [{"form": {**FORM, "skill": "no-such-skill"}}]}
        assert (await fsp_bank.import_bank(s, bad, CFG))["failed_check"] == 1
        with pytest.raises(fsp_bank.BankError):
            await fsp_bank.import_bank(s, bank(competition={"license": "x"}), CFG)


async def test_import_to_pilot(factory, taxonomy_loaded):
    async with session_scope(factory) as s:
        await fsp_bank.import_bank(s, bank(), CFG, to_pilot=True)
        row = (await s.scalars(select(FamilyRow).where(FamilyRow.source == "fsp"))).one()
        assert row.status == "pilot"


# --- участнику соревнования задача не выдаётся --------------------------------------------------


async def test_participant_never_sees_own_competition(factory, taxonomy_loaded):
    me, member, other = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with session_scope(factory) as s:
        await fsp_bank.import_bank(s, bank(), CFG)
        row = (await s.scalars(select(FamilyRow).where(FamilyRow.source == "fsp"))).one()
        row.status = "active"
        row.level = 3
        s.add(FspResultRow(id=uuid.uuid4(), candidate_id=me, participant_id="p1",
                           competition_id="c-777", stage="final"))  # fmt: skip
        s.add(FspResultRow(id=uuid.uuid4(), candidate_id=other, participant_id="p3",
                           competition_id="c-other", stage="final"))  # fmt: skip
        s.add(FspTeamRow(id="t1", name="T", competition_id="c-777"))
        await s.flush()
        s.add(FspTeamMember(team_id="t1", participant_id="p2", candidate_id=member))
        await s.flush()
        assert await graph.fsp_competitions_of(s, me) == {"c-777"}
        assert await graph.fsp_competitions_of(s, member) == {"c-777"}

        async def seen(cid):
            pool = await engine.eligible(s, cid, ["algorithms"], TestGrade.middle, CFG)
            return any(r.slug == row.slug for rows in pool.values() for r in rows)

        assert not await seen(me)  # результат соревнования
        assert not await seen(member)  # состав команды
        assert await seen(other)  # другое соревнование — можно
        assert await seen(uuid.uuid4())  # без ФСП — можно


# --- калибровка не берёт ответы «своих» ---------------------------------------------------------


async def _answered_attempt(s, family: FamilyRow, candidate_id, score: float) -> Attempt:
    att = Attempt(candidate_id=candidate_id, profession="backend", declared_grade="middle",
                  status="passed", plan={})  # fmt: skip
    s.add(att)
    await s.flush()
    s.add(Response(attempt_id=att.id, seq=1, family_id=family.id, seed=1, score=score,
                   answered_at=datetime.now(UTC)))  # fmt: skip
    await s.flush()
    return att


async def test_rasch_calibration_ignores_fsp_candidates_on_fsp_tasks(
    factory, taxonomy_loaded, monkeypatch
):
    async with session_scope(factory) as s:
        await fsp_bank.import_bank(s, bank(), CFG)
        row = (await s.scalars(select(FamilyRow).where(FamilyRow.source == "fsp"))).one()
        b0, n0 = row.b, row.n
        row2 = FamilyRow(
            id=uuid.uuid4(), slug="plain", kind="exact", source="spec", skill_id=row.skill_id,
            skill_type="hard", level=3, b=0.0, status="active", stats={},
        )  # fmt: skip
        s.add(row2)
        await s.flush()

        async def has(_s, _c, source):
            return source == "fsp" and has.flag

        monkeypatch.setattr(graph, "has_source", has)
        has.flag = True  # участник ФСП: задача ФСП не калибруется, обычная — да
        att = await _answered_attempt(s, row, uuid.uuid4(), 1.0)
        await psychometrics_db.finalize_attempt(s, att, CFG)
        assert (row.b, row.n) == (b0, n0)
        att2 = await _answered_attempt(s, row2, uuid.uuid4(), 1.0)
        await psychometrics_db.finalize_attempt(s, att2, CFG)
        assert row2.n == 1 and row2.b != 0.0
        has.flag = False  # остальная аудитория задаёт шкалу
        att3 = await _answered_attempt(s, row, uuid.uuid4(), 1.0)
        await psychometrics_db.finalize_attempt(s, att3, CFG)
        assert row.n == n0 + 1 and row.b < b0


# --- допуск только с измеренным DIF ----------------------------------------------------------


def test_fsp_admission_requires_dif():
    good = FamilyStats(n=40, p=0.5, r_pb=0.4, seed_spread=0.05, dif=None, leak=None, appeals=0)
    assert admission_failures(good, 0.0, CFG) == []
    assert admission_failures(good, 0.0, CFG, need_dif=True) == ["dif_unmeasured"]
    ok = dataclasses.replace(good, dif=0.05)
    assert admission_failures(ok, 0.0, CFG, need_dif=True) == []
    bad = dataclasses.replace(good, dif=0.3)
    assert admission_failures(bad, 0.0, CFG, need_dif=True) == ["dif"]
    assert lifecycle.admission_failures is admission_failures
