"""Конструктор заданий — вычислитель, интерпретаторы `spec`, автопроверка, API, ключ LLM."""

import sqlite3
import uuid
from pathlib import Path
from random import Random

import httpx
import pytest
from app.assessment import constructor, expr, key_draft
from app.assessment.attempts import family_of
from app.assessment.config import load_config
from app.assessment.families.base import Kind
from app.assessment.families.spec import FamilySpec, SpecFamily, render, score_open
from app.assessment.models import FamilyRow
from app.assessment.world import World
from app.config import Settings
from app.taxonomy import service as tax
from app.taxonomy.loader import load_taxonomy
from core_helpers import PASSWORD, register
from fsp_contracts.assessment import FamilyStatusChanged
from fsp_contracts.ml import FamilyKeyDraft
from fsp_platform.db import session_scope
from fsp_platform.outbox import OutboxRecord
from pydantic import ValidationError
from sqlalchemy import select

CFG = load_config()
TAXONOMY = Path(__file__).resolve().parents[3] / "data" / "taxonomy"
INN = "7707083893"

# --- безопасный вычислитель -------------------------------------------------------------------


def test_expr_arithmetic_and_functions():
    assert expr.evaluate("a * b + 2", {"a": 3, "b": 4}) == 14
    assert expr.evaluate("round(rps * 86400 / 1e6, 1)", {"rps": 120}) == 10.4
    assert expr.evaluate("max(a, b) if a > 1 else -1", {"a": 2, "b": 5}) == 5
    assert expr.evaluate("log10(1000) + sqrt(16) + pi * 0") == 7.0
    assert expr.names("x * y + sqrt(z) + pi") == {"x", "y", "z"}


@pytest.mark.parametrize(
    "src",
    [
        "__import__('os').system('id')",
        "a.__class__",
        "(lambda: 1)()",
        "[1, 2][0]",
        "'x' * 3",
        "open('f')",
        "9 ** 9 ** 9",
        "1 / 0",
        "unknown + 1",
        "exp(1000)",
        "x" * 400,
        "True",
    ],
)
def test_expr_rejects_unsafe_and_bad(src):
    with pytest.raises(expr.ExprError):
        expr.evaluate(src, {"a": 1})


def test_render_templates_keep_single_braces():
    env = {"a": 2, "b": 0.5, "company": "Корзинка"}
    assert render("{{company}}: {{a}} × {{= a * 3}}, d = {}", env) == "Корзинка: 2 × 6, d = {}"
    assert render("{{= b * 3}}", env) == "1.5"


# --- интерпретаторы по kind -------------------------------------------------------------------

BASE = {"title": "Задание", "skill": "python", "level": 3}
SPECS = {
    "exact": {
        **BASE,
        "kind": "exact",
        "stem": "Сервис {{service}} обрабатывает {{n}} запросов по {{k}} мс. Сколько секунд всего?",
        "params": {"n": {"min": 10, "max": 90, "step": 10}, "k": {"values": [100, 200, 500]}},
        "derived": {"total_ms": "n * k"},
        "answer": "total_ms / 1000",
    },
    "estimate": {
        **BASE,
        "kind": "estimate",
        "stem": "У {{company}} {{users}} пользователей в сутки, по {{r}} запросов. Оцените RPS.",
        "params": {"users": {"values": [100000, 1000000, 5000000]}, "r": {"min": 5, "max": 50}},
        "answer": "users * r / 86400",
    },
    "choice": {
        **BASE,
        "kind": "choice",
        "stem": "Чему равно {{a}} // {{b}} в Python?",
        "params": {"a": {"min": 10, "max": 99}, "b": {"min": 2, "max": 9}},
        "options": ["{{= a // b}}", "{{= a / b + 0.5}}", "{{= a % b + 100}}", "{{= a * b + 1000}}"],
        "correct": 0,
    },
    "find_bug": {
        **BASE,
        "kind": "find_bug",
        "stem": "Функция должна вернуть сумму первых {{n}} элементов. Найдите ошибку.",
        "params": {"n": {"min": 2, "max": 9}},
        "lines": [
            "def head_sum(xs):",
            "    total = 0",
            "    for i in range(1, {{n}}):",
            "        total += xs[i]",
            "    return total",
        ],
        "bug_lines": [3],
    },
    "order": {
        **BASE,
        "kind": "order",
        "skill": "production_support",
        "stem": "Сервис {{service}} упал после релиза. Расставьте шаги по порядку.",
        "steps": ["Взять инцидент", "Оценить масштаб", "Откатить релиз", "Найти причину"],
    },
    "sjt": {
        **BASE,
        "kind": "sjt",
        "skill": "code_review",
        "level": 2,
        "stem": "Коллега прислал PR на 3000 строк в {{service}}. Расставьте действия.",
        "actions": [
            {"text": "Попросить разбить PR на части", "score": 4},
            {"text": "Посмотреть бегло и одобрить", "score": 1},
            {"text": "Созвониться и обсудить план", "score": 3},
            {"text": "Молча отложить", "score": 0},
        ],
    },
    "open": {
        **BASE,
        "kind": "open",
        "stem": "Опишите, как вы ускорите медленный отчёт в {{service}}.",
        "rubric": ["Найдено узкое место", "Предложено измерение до и после"],
    },
}


def _fam(raw: dict) -> SpecFamily:
    return SpecFamily(FamilySpec.model_validate(raw), slug="t", skill_type="hard")


@pytest.mark.parametrize("kind", list(SPECS))
def test_every_kind_passes_autocheck_and_key_scores_one(kind):
    fam = _fam(SPECS[kind])
    assert constructor.autocheck(fam, n=60) == []
    item = fam.generate(Random(7), World.from_seed(7))
    assert item.kind == Kind(kind)
    assert "{{" not in item.stem
    if kind == "open":
        assert fam.score(item, [True, False]) == 0.5
    else:
        assert fam.score(item, item.key) == 1.0


def test_variants_differ_by_seed_and_are_deterministic():
    fam = _fam(SPECS["exact"])
    a = fam.generate(Random(1), World.from_seed(1))
    assert a == fam.generate(Random(1), World.from_seed(1))
    stems = {fam.generate(Random(s), World.from_seed(s)).stem for s in range(30)}
    assert len(stems) > 5


def test_exact_and_estimate_keys_from_formula():
    fam = _fam(SPECS["exact"])
    item = fam.generate(Random(3), World.from_seed(3))
    assert fam.score(item, str(item.key)) == 1.0 and fam.score(item, item.key + 1) == 0.0
    est = _fam(SPECS["estimate"])
    item = est.generate(Random(3), World.from_seed(3))
    assert est.score(item, item.key * 1.5) == 1.0 and est.score(item, item.key * 3) == 0.5


def test_choice_shuffles_and_tracks_key():
    fam = _fam(SPECS["choice"])
    keys = {fam.generate(Random(s), World.from_seed(s)).key for s in range(40)}
    assert len(keys) > 1  # верный вариант не всегда первый


def test_autocheck_catches_ambiguous_choice_and_bad_sjt():
    dup = {**SPECS["choice"], "options": ["{{= a // b}}", "{{= a // b}}", "1000"]}
    assert any("повтор" in e for e in constructor.autocheck(_fam(dup), n=10))
    ties = {
        **SPECS["sjt"],
        "actions": [{"text": t, "score": 1} for t in ("Первое", "Второе", "Третье")],
    }
    assert constructor.autocheck(_fam(ties), n=5)
    bad = {**SPECS["exact"], "answer": "n / (k - k)"}
    assert any("не вычисляется" in e for e in constructor.autocheck(_fam(bad), n=5))


def test_spec_validation():
    with pytest.raises(ValidationError):
        FamilySpec.model_validate({**SPECS["choice"], "correct": 9})
    with pytest.raises(ValidationError):
        FamilySpec.model_validate({**SPECS["exact"], "answer": "__import__('os')"})
    with pytest.raises(ValidationError):
        FamilySpec.model_validate({**SPECS["exact"], "params": {"company": {"min": 1, "max": 2}}})
    with pytest.raises(ValidationError):
        FamilySpec.model_validate({**SPECS["find_bug"], "bug_lines": [42]})
    no_key = FamilySpec.model_validate({**SPECS["choice"], "correct": None})
    assert no_key.missing_key() == ["correct"]


def test_score_open_rubric():
    assert score_open(["a", "b", "c", "d"], {"marks": [True, True, False, True]}) == 0.75
    assert score_open(["a"], "текст") == 0.0


# --- черновик ключа ---------------------------------------------------------------------------


def test_key_draft_apply_and_fits():
    spec = FamilySpec.model_validate(
        {**SPECS["sjt"], "actions": [{"text": a["text"]} for a in SPECS["sjt"]["actions"]]}
    )
    assert spec.missing_key() == ["actions.score"]
    assert not key_draft.fits(spec, FamilyKeyDraft(scores=[1, 2]))
    assert not key_draft.fits(spec, FamilyKeyDraft(scores=[1, 1, 2, 3]))
    full = key_draft.apply(spec, FamilyKeyDraft(scores=[4, 1, 3, 0]))
    assert full.missing_key() == [] and [a.score for a in full.actions] == [4, 1, 3, 0]
    req = key_draft.example_request(spec)
    assert req.kind == "sjt" and len(req.actions) == 4 and "{{" not in req.stem


async def test_request_draft_offline_and_via_ml_api():
    spec = FamilySpec.model_validate({**SPECS["choice"], "correct": None})
    off = Settings(llm_enabled=False, ml_api_url="http://ml")
    assert await key_draft.request_draft(off, spec) is None
    assert await key_draft.request_draft(Settings(ml_api_url=""), spec) is None

    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        return httpx.Response(200, json={"correct": 0, "model": "m"})

    on = Settings(llm_enabled=True, ml_api_url="http://ml")
    got = await key_draft.request_draft(on, spec, transport=httpx.MockTransport(handler))
    assert got is not None and got.correct == 0 and seen["path"] == "/v1/families/key-draft"
    oob = httpx.MockTransport(lambda r: httpx.Response(200, json={"correct": 9, "model": "m"}))
    assert await key_draft.request_draft(on, spec, transport=oob) is None
    down = httpx.MockTransport(lambda r: httpx.Response(503, json={"code": "llm_disabled"}))
    assert await key_draft.request_draft(on, spec, transport=down) is None


# --- API --------------------------------------------------------------------------------------


@pytest.fixture
async def taxonomy_loaded(factory):
    async with session_scope(factory) as s:
        await tax.sync(s, load_taxonomy(TAXONOMY))


def _admin(api) -> dict[str, str]:
    email = f"root-{uuid.uuid4().hex[:6]}@example.test"
    r = api.post("/auth/register", json={"email": email, "password": PASSWORD, "role": "candidate"})
    with sqlite3.connect(api.db_path) as con:
        con.execute("update users set role='fsp_admin' where email=?", (email,))
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _employer(api, inn: str = INN) -> dict[str, str]:
    h = register(api, "employer")
    assert (
        api.post("/companies", json={"name": "Acme Labs", "inn": inn}, headers=h).status_code < 300
    )
    return h


async def _status_events(factory, fid) -> list[tuple[str, str]]:
    async with session_scope(factory) as s:
        rows = await s.scalars(
            select(OutboxRecord).where(OutboxRecord.type == "assessment.family.status_changed")
        )
        evs = [FamilyStatusChanged.model_validate(r.payload["payload"]) for r in rows]
        return [(e.from_, e.to) for e in evs if str(e.family_id) == str(fid)]


async def test_admin_family_goes_to_pilot(api, factory, taxonomy_loaded):
    adm = _admin(api)
    r = api.post("/families", json=SPECS["exact"], headers=adm)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "pilot" and body["source"] == "spec"
    assert body["key_status"] == "approved" and body["autocheck"]["ok"] is True
    assert body["company_id"] is None and len(body["examples"]) == 3
    assert body["skill_type"] == "hard" and body["slug"].startswith("c-")
    assert await _status_events(factory, body["id"]) == [("draft", "pilot")]
    async with session_scope(factory) as s:
        row = await s.get(FamilyRow, uuid.UUID(body["id"]))
        assert row.b == CFG.prior_b(3) and row.author_id is not None
        fam = family_of(row)  # попытка пересобирает вариант из spec
        assert fam is not None and fam.generate(Random(1), World.from_seed(1)).key is not None


async def test_company_family_stays_draft_until_admin(api, factory, taxonomy_loaded):
    emp, adm = _employer(api), _admin(api)
    r = api.post("/families", json=SPECS["sjt"], headers=emp)
    assert r.status_code == 201, r.text
    fam = r.json()
    assert fam["status"] == "draft" and fam["company_id"] is not None
    assert [f["id"] for f in api.get("/families", headers=emp).json()] == [fam["id"]]

    # чужая компания и кандидат: 404 / 403
    other = _employer(api, inn="7736050003")
    assert api.get(f"/families/{fam['id']}", headers=other).status_code == 404
    assert api.get("/families", headers=other).json() == []
    cand = register(api)
    assert api.post("/families", json=SPECS["exact"], headers=cand).status_code == 403
    assert api.get(f"/families/{fam['id']}", headers=emp).json()["examples"]

    r = api.post(f"/admin/families/{fam['id']}/pilot", headers=adm)
    assert r.status_code == 200 and r.json()["status"] == "pilot"
    assert r.json()["log"][-1]["reason"] == "admin" and r.json()["spec"]["form"]["kind"] == "sjt"
    assert api.post(f"/admin/families/{fam['id']}/pilot", headers=emp).status_code == 403


async def test_open_task_never_in_bank(api, taxonomy_loaded):
    adm = _admin(api)
    fam = api.post("/families", json=SPECS["open"], headers=adm).json()
    assert fam["status"] == "draft"
    r = api.post(f"/admin/families/{fam['id']}/pilot", headers=adm)
    assert r.status_code == 409 and r.json()["code"] == "open_not_in_bank"


async def test_validation_errors(api, taxonomy_loaded):
    adm = _admin(api)
    r = api.post("/families", json={**SPECS["exact"], "skill": "no_such_skill"}, headers=adm)
    assert r.status_code == 422 and r.json()["code"] == "unknown_skill"
    dup = {**SPECS["choice"], "options": ["{{= a // b}}", "{{= a // b}}", "1000"]}
    r = api.post("/families", json=dup, headers=adm)
    assert r.status_code == 422 and r.json()["code"] == "autocheck_failed"
    r = api.post("/families", json={**SPECS["exact"], "answer": "a.__class__"}, headers=adm)
    assert r.status_code == 422
    emp_nocompany = register(api, "employer")
    assert api.post("/families", json=SPECS["exact"], headers=emp_nocompany).status_code == 404


async def test_without_llm_key_is_required(api, taxonomy_loaded):
    """LLM_ENABLED=false / нет ml-api: без ключа автора — 422 key_required, с ключом — работает."""
    emp = _employer(api)
    r = api.post("/families", json={**SPECS["choice"], "correct": None}, headers=emp)
    assert r.status_code == 422 and r.json()["code"] == "key_required"
    assert api.post("/families", json=SPECS["choice"], headers=emp).status_code == 201


async def test_llm_key_is_draft_until_admin_approves(api, factory, taxonomy_loaded, monkeypatch):
    async def fake_draft(settings, spec, **kw):
        return FamilyKeyDraft(scores=[4, 1, 3, 0], rationale="r", model="fake")

    monkeypatch.setattr(key_draft, "request_draft", fake_draft)
    adm = _admin(api)
    raw = {**SPECS["sjt"], "actions": [{"text": a["text"]} for a in SPECS["sjt"]["actions"]]}
    r = api.post("/families", json=raw, headers=adm)
    assert r.status_code == 201, r.text
    fam = r.json()
    assert fam["key_status"] == "draft" and fam["status"] == "pilot"
    assert fam["key_draft"]["scores"] == [4, 1, 3, 0]
    assert fam["author_form"]["actions"][0]["score"] is None

    # ключ не утверждён — в active не пустит даже при выполненных порогах
    r = api.post(f"/admin/families/{fam['id']}/approve", headers=adm)
    assert r.status_code == 409 and r.json()["code"] == "key_not_approved"
    r = api.post(f"/admin/families/{fam['id']}/key", json={"source": "author"}, headers=adm)
    assert r.status_code == 409 and r.json()["code"] == "no_author_key"
    r = api.post(f"/admin/families/{fam['id']}/key", json={"source": "llm"}, headers=adm)
    assert r.status_code == 200 and r.json()["key_status"] == "approved"

    custom = {**SPECS["sjt"]}
    r = api.post(
        f"/admin/families/{fam['id']}/key", json={"source": "custom", "spec": custom}, headers=adm
    )
    assert r.status_code == 200 and r.json()["spec"]["form"]["actions"][0]["score"] == 4
    bad = {**SPECS["sjt"], "level": 5}
    r = api.post(
        f"/admin/families/{fam['id']}/key", json={"source": "custom", "spec": bad}, headers=adm
    )
    assert r.status_code == 422 and r.json()["code"] == "spec_mismatch"
    async with session_scope(factory) as s:
        row = await s.get(FamilyRow, uuid.UUID(fam["id"]))
        assert [e["source"] for e in row.spec["key_log"]] == ["llm", "custom"]


async def test_admission_card_fields(api, taxonomy_loaded):
    """В очереди допуска — грейд, профессии и пример варианта с ответом решателя."""
    adm = _admin(api)
    fam = api.post("/families", json=SPECS["exact"], headers=adm).json()
    items = api.get("/admin/families", params={"status": "pilot"}, headers=adm).json()
    card = next(x for x in items if x["id"] == fam["id"])
    assert card["grade"] == "middle" and card["skill"] == SPECS["exact"]["skill"]
    assert card["example"]["stem"] and card["example"]["answer"]
    assert all(p["slug"] and p["title"] for p in card["professions"])


def test_admission_helpers():
    from app.assessment import admission
    from app.assessment.families.base import Item
    from fsp_contracts.assessment import ProfessionInfo

    assert [admission.grade_of_level(n) for n in (1, 2, 3, 4, 5)] == [
        "junior", "junior", "middle", "senior", "senior",
    ]  # fmt: skip
    profs = [
        ProfessionInfo(slug="backend", title="A", skill_weights={"py": 0.9}),
        ProfessionInfo(slug="qa", title="B", skill_weights={"py": 0.3}),
        ProfessionInfo(slug="ml", title="C", skill_weights={"go": 1.0}),
    ]
    assert [p.slug for p in admission.professions_of("py", profs)] == ["backend"]
    assert [p.slug for p in admission.professions_of("zzz", profs)] == []
    only_weak = [profs[1]]
    assert [p.slug for p in admission.professions_of("py", only_weak)] == ["qa"]
    item = Item(kind=Kind.choice, stem="q", key=1, options=["x", "y"])
    assert admission.answer_text(item) == "y"
    assert admission.answer_text(Item(kind=Kind.find_bug, stem="q", key=[2, 5])) == "строки 2, 5"
    assert admission.answer_text(Item(kind=Kind.exact, stem="q", key=42)) == "42"


# --- «Готово» без допуска админа, задание в приглашении ------------------------------


async def test_company_family_ready_without_admin(api, factory, taxonomy_loaded):
    from app.assessment import invite_bank

    emp, adm = _employer(api), _admin(api)
    fam = api.post("/families", json=SPECS["exact"], headers=emp).json()
    assert fam["status"] == "draft" and fam["ready"] is False
    # не в очереди допуска админа
    queue = api.get("/admin/families?status=draft", headers=adm).json()
    assert fam["id"] not in {f["id"] for f in queue}

    async with session_scope(factory) as s:  # черновик нельзя прикрепить к приглашению
        row = await s.get(FamilyRow, uuid.UUID(fam["id"]))
        with pytest.raises(Exception, match="Готово"):
            await invite_bank.describe(s, row.id, company_id=row.company_id, user_id=row.author_id)

    r = api.put(f"/families/{fam['id']}/ready", json={"ready": True}, headers=emp)
    assert r.status_code == 200 and r.json()["ready"] is True and r.json()["status"] == "draft"
    assert api.get(f"/families/{fam['id']}", headers=emp).json()["ready"] is True

    async with session_scope(factory) as s:
        row = await s.get(FamilyRow, uuid.UUID(fam["id"]))
        info = await invite_bank.describe(
            s, row.id, company_id=row.company_id, user_id=row.author_id
        )
        assert info.kind == "exact" and info.minutes >= 1
        cand = uuid.uuid4()
        it = await invite_bank.item(s, row.id, candidate_id=cand, offer_id=uuid.uuid4())
        assert "key" not in it
        # чужая компания: 404
        with pytest.raises(Exception, match="не найдено"):
            await invite_bank.describe(s, row.id, company_id=uuid.uuid4(), user_id=uuid.uuid4())

    # чужой и кандидат
    other = _employer(api, inn="7736050003")
    assert (
        api.put(f"/families/{fam['id']}/ready", json={"ready": False}, headers=other).status_code
        == 404
    )
    back = api.put(f"/families/{fam['id']}/ready", json={"ready": False}, headers=emp)
    assert back.json()["ready"] is False


async def test_admin_family_ready_is_bank_status(api, taxonomy_loaded):
    adm = _admin(api)
    fam = api.post("/families", json=SPECS["exact"], headers=adm).json()
    assert fam["ready"] is True  # pilot
    assert (
        api.put(f"/families/{fam['id']}/ready", json={"ready": True}, headers=adm).status_code
        == 409
    )


async def test_invite_submit_writes_task_evidence_once(api, factory, taxonomy_loaded):
    from app.assessment import invite_bank
    from app.assessment.attempts import build_item, item_seed
    from app.graph.models import Evidence

    emp = _employer(api)
    fam = api.post("/families", json=SPECS["exact"], headers=emp).json()
    api.put(f"/families/{fam['id']}/ready", json={"ready": True}, headers=emp)
    cand, offer = uuid.uuid4(), uuid.uuid4()
    async with session_scope(factory) as s:
        row = await s.get(FamilyRow, uuid.UUID(fam["id"]))
        key = build_item(family_of(row), item_seed(cand, offer, row.id), None).key
        for _ in range(2):  # повтор не плодит доказательств
            score = await invite_bank.submit(
                s, row.id, candidate_id=cand, offer_id=offer, answer=str(key)
            )
            assert score == 1.0
        ev = list(await s.scalars(select(Evidence).where(Evidence.candidate_id == cand)))
        assert len(ev) == 1 and ev[0].source == "task" and ev[0].fact_id == offer
        assert ev[0].fact_type == "invite_task" and 0 < ev[0].strength <= 0.5
        wrong = await invite_bank.submit(
            s, row.id, candidate_id=cand, offer_id=uuid.uuid4(), answer="-1"
        )
        assert wrong == 0.0
