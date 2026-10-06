"""E26-4: конвейер LLM-заданий → `draft` в очереди допуска; LLM как кандидат → ai_solvable."""

import uuid
from pathlib import Path

import httpx
import pytest
from app.assessment import constructor, llm_bank
from app.assessment.attempts import family_of
from app.assessment.config import load_config
from app.assessment.families import check
from app.assessment.families.spec import FamilySpec, SpecFamily
from app.assessment.models import FamilyRow
from app.config import Settings
from app.taxonomy import service as tax
from app.taxonomy.loader import load_taxonomy
from fsp_contracts.ml import (
    FamilyGenerateResponse,
    FamilyKeyDraft,
    FamilySolveAnswer,
)
from fsp_platform.db import session_scope
from sqlalchemy import select

CFG = load_config()
TAXONOMY = Path(__file__).resolve().parents[3] / "data" / "taxonomy"
RIGHT = "верно"

CHOICE = {
    "title": "Бинарный поиск",
    "kind": "choice",
    "stem": "Сколько сравнений нужно бинарному поиску в массиве из {{n}} элементов?",
    "params": {"n": {"values": [1000, 10000]}},
    "options": [RIGHT, "O(n)", "O(1)"],
    "correct": 0,
}
NO_KEY = {
    **CHOICE,
    "stem": "Какая сложность у вставки в хеш-таблицу {{n}} в среднем?",
    "correct": None,
}
BAD_SCHEMA = {**CHOICE, "options": None}
DUP_OPTIONS = {**CHOICE, "stem": "Дубли вариантов в задании {{n}}", "options": ["a", "a", RIGHT]}


class FakeBank:
    """Генератор отдаёт заготовки; решатель выбирает вариант «верно»; черновик — индекс «верно»."""

    def __init__(self, specs, *, draft_correct: int | None = 0, solver: bool = True):
        self.specs, self.draft_correct, self.solver = specs, draft_correct, solver
        self.solved = 0

    async def generate(self, req):
        return FamilyGenerateResponse(
            specs=[{**s, "kind": req.kind} for s in self.specs], model="fake"
        )

    async def key_draft(self, spec: FamilySpec):
        if self.draft_correct is None:
            return None
        return FamilyKeyDraft(correct=self.draft_correct, model="fake")

    async def solve(self, req):
        self.solved += 1
        if not self.solver:
            return None
        return FamilySolveAnswer(answer=req.options.index(RIGHT) if RIGHT in req.options else 0)


@pytest.fixture
async def taxonomy_loaded(factory):
    async with session_scope(factory) as s:
        await tax.sync(s, load_taxonomy(TAXONOMY))


def test_digest_ignores_title_and_solve_seeds_are_own():
    a = FamilySpec.model_validate({**CHOICE, "skill": "python", "level": 3})
    b = FamilySpec.model_validate({**CHOICE, "skill": "python", "level": 3, "title": "Другое"})
    assert llm_bank.digest(a) == llm_bank.digest(b)
    assert not set(llm_bank.solve_seeds(50)) & set(check.seeds(1000))


def test_key_agrees_by_kind():
    spec = FamilySpec.model_validate({**CHOICE, "skill": "python", "level": 3})
    fam = SpecFamily(spec, slug="x", skill_type="hard")
    assert llm_bank.key_agrees(spec, fam, FamilyKeyDraft(correct=0)) is True
    assert llm_bank.key_agrees(spec, fam, FamilyKeyDraft(correct=2)) is False
    assert llm_bank.key_agrees(spec, fam, None) is None
    exact = FamilySpec.model_validate(
        {
            "title": "Счёт",
            "kind": "exact",
            "skill": "python",
            "level": 2,
            "stem": "Сколько будет {{a}} * 3?",
            "params": {"a": {"min": 1, "max": 9}},
            "answer": "a * 3",
            "precision": 0,
        }
    )
    ef = SpecFamily(exact, slug="e", skill_type="hard")
    key = check.build(ef, 0).key
    assert llm_bank.key_agrees(exact, ef, FamilyKeyDraft(answer=key)) is True
    assert llm_bank.key_agrees(exact, ef, FamilyKeyDraft(answer=key + 1)) is False


async def test_propose_checks_and_lands_in_draft(factory, taxonomy_loaded):
    bank = FakeBank([CHOICE, NO_KEY, BAD_SCHEMA, DUP_OPTIONS, CHOICE])
    targets = [llm_bank.Target("python", "choice", 3, n=5)]
    async with session_scope(factory) as s:
        rep = await llm_bank.propose(s, bank, CFG, targets, k=3)
    assert rep.proposed == 5 and rep.passed == 2
    assert rep.rejected == {"schema": 1, "autocheck": 1, "duplicate": 1}
    assert rep.flags["key_from_draft"] == 1
    async with session_scope(factory) as s:
        rows = (await s.scalars(select(FamilyRow).where(FamilyRow.source == "llm"))).all()
        assert len(rows) == 2
        for row in rows:
            assert (row.status, row.key_status, row.kind) == ("draft", "draft", "choice")
            assert row.b == CFG.prior_b(3) and row.ai_solvable == 1.0
            assert row.spec["llm"]["solver"] == {"score": 1.0, "k": 3}
            assert family_of(row) is not None  # семейство собирается как у конструктора
        # админ: ключ генератора → утверждён, в банк → pilot; K в пилоте растёт
        row = next(r for r in rows if r.spec["author"]["correct"] == 0)
        await constructor.approve_key(s, row.id, uuid.uuid4(), "author")
        await constructor.to_bank(s, row.id, uuid.uuid4(), CFG)
        assert (row.key_status, row.status) == ("approved", "pilot")
        rep = await llm_bank.bank_counts(s, llm_bank.Report())
        assert (rep.in_pilot, rep.in_draft) == (1, 1)
    async with session_scope(factory) as s:  # повтор того же заказа ничего не дублирует
        again = await llm_bank.propose(s, FakeBank([CHOICE]), CFG, targets, k=3)
    assert again.passed == 0 and again.rejected == {"duplicate": 1}


async def test_no_key_without_draft_is_rejected(factory, taxonomy_loaded):
    async with session_scope(factory) as s:
        rep = await llm_bank.propose(
            s,
            FakeBank([NO_KEY], draft_correct=None),
            CFG,
            [llm_bank.Target("python", "choice", 3)],
            k=2,
        )
    assert rep.passed == 0 and rep.rejected == {"no_key": 1}


async def test_disagreeing_key_is_flagged_not_rejected(factory, taxonomy_loaded):
    wrong = {**CHOICE, "correct": 1}  # генератор ошибся: «верно» — нулевой вариант
    async with session_scope(factory) as s:
        rep = await llm_bank.propose(
            s, FakeBank([wrong]), CFG, [llm_bank.Target("python", "choice", 2)], k=3
        )
        row = (await s.scalars(select(FamilyRow).where(FamilyRow.source == "llm"))).one()
    assert rep.passed == 1
    assert set(row.spec["llm"]["flags"]) == {"key_draft_disagrees", "key_doubtful"}
    assert row.ai_solvable == 0.0


async def test_measure_ai_solvable_is_idempotent_and_skips_when_down(factory, taxonomy_loaded):
    async with session_scope(factory) as s:
        await llm_bank.propose(
            s, FakeBank([CHOICE], solver=False), CFG, [llm_bank.Target("sql", "choice", 3)]
        )
        row = (await s.scalars(select(FamilyRow).where(FamilyRow.source == "llm"))).one()
        assert row.ai_solvable == 0.0 and row.spec["llm"]["solver"]["score"] is None
        down = await llm_bank.measure_ai_solvable(s, FakeBank([], solver=False), k=2)
        assert (down.ai_measured, down.ai_skipped) == (0, 1) and row.ai_solvable == 0.0
        rep = await llm_bank.measure_ai_solvable(s, FakeBank([]), k=4)
        assert rep.ai_measured == 1 and rep.ai_mean == 1.0 and row.ai_solvable == 1.0
        again = await llm_bank.measure_ai_solvable(s, FakeBank([]), k=4)
        assert again.ai_top == rep.ai_top
        assert "1 предложено" not in rep.markdown() and "ai_solvable" in rep.markdown()


async def test_llm_disabled_proposes_nothing(factory, taxonomy_loaded):
    bank = llm_bank.HttpBank(Settings(llm_enabled=False, ml_api_url="http://ml"))
    try:
        async with session_scope(factory) as s:
            rep = await llm_bank.propose(s, bank, CFG, [llm_bank.Target("python", "choice", 3)])
            await llm_bank.measure_ai_solvable(s, bank, report=rep)
            n = len((await s.scalars(select(FamilyRow))).all())
    finally:
        await bank.aclose()
    assert not rep.llm_available and rep.proposed == 0 and n == 0


async def test_end_to_end_with_ml_fake(factory, taxonomy_loaded):
    """core → ml-api (ML_FAKE=true) по HTTP: шаблоны заглушки проходят автопроверку."""
    pytest.importorskip("fsp_ml")
    from fsp_ml.config import Settings as MlSettings
    from fsp_ml.main import build_app

    transport = httpx.ASGITransport(app=build_app(MlSettings(ml_fake=True)))
    bank = llm_bank.HttpBank(
        Settings(llm_enabled=True, ml_api_url="http://ml"), transport=transport
    )
    kinds = ["exact", "estimate", "choice", "find_bug", "order", "sjt", "open"]
    try:
        async with session_scope(factory) as s:
            rep = await llm_bank.propose(
                s, bank, CFG, llm_bank.targets_of(["python"], kinds, [3], 2), k=3
            )
            await llm_bank.measure_ai_solvable(s, bank, k=3, report=rep)
            await llm_bank.bank_counts(s, rep)
    finally:
        await bank.aclose()
    assert rep.llm_available and rep.proposed == 14
    assert rep.passed + sum(rep.rejected.values()) == rep.proposed
    assert rep.passed >= 9 and rep.in_draft == rep.passed and rep.in_pilot == 0
    assert rep.ai_measured >= 1 and 0.0 <= (rep.ai_mean or 0.0) <= 1.0
