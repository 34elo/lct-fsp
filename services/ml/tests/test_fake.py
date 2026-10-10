from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from fsp_contracts import Envelope, new_command, parse_payload
from fsp_contracts import commands as cmd
from fsp_contracts.commands import COMMANDS
from fsp_contracts.enums import TrustLevel
from fsp_contracts.ml import InterviewAnswer, KitGap, KitSkill, MatchToExplain, SkillMention
from fsp_ml.config import Settings
from fsp_ml.handlers import HANDLERS, handle
from fsp_ml.main import build_app

U = uuid4


def _commands() -> dict[str, object]:
    ans = InterviewAnswer(
        question_id="q1",
        question="?",
        rubric=["a", "b", "c"],
        snippet="x",
        answer="слово " * 30,
        seconds=60,
    )
    return {
        "ml.resume.parse": cmd.MlResumeParse(
            resume_id=U(),
            candidate_id=U(),
            object_key="r/1.pdf",
            mime="application/pdf",
            sha256="0" * 64,
            taxonomy_version=1,
        ),
        "ml.interview.grade": cmd.MlInterviewGrade(
            interview_id=U(), candidate_id=U(), answers=[ans]
        ),
        "ml.interview.generate": cmd.MlInterviewGenerate(
            interview_id=U(),
            candidate_id=U(),
            github_login="demo",
            repo_full_name="demo/api",
            questions=3,
        ),
        "ml.interview_kit.generate": cmd.MlInterviewKitGenerate(
            kit_id=U(),
            vacancy_id=U(),
            vacancy_version=1,
            candidate_id=U(),
            profile_version=2,
            requirements=["python"],
            skills=[KitSkill(slug="python", level=TrustLevel.l3)],
            gaps=[KitGap(slug="kafka", kind="claimed_only")],
        ),
        "ml.skills.resolve": cmd.MlSkillsResolve(
            request_id=U(),
            mentions=[SkillMention(raw="Питон"), SkillMention(raw="Zig")],
            taxonomy_version=1,
        ),
        "ml.matches.explain": cmd.MlMatchesExplain(
            vacancy_id=U(),
            vacancy_version=1,
            requirements=["python"],
            items=[MatchToExplain(candidate_id=U(), profile_version=1, score=0.8, explanation=[])],
        ),
        "ml.questions.generate": cmd.MlQuestionsGenerate(skill_slug="python", count=4),
        "ml.families.generate": cmd.MlFamiliesGenerate(
            order_id=U(), skill="python", kind="choice", level=3, n=7
        ),
        "ml.code.analyze": cmd.MlCodeAnalyze(
            analysis_id=U(), candidate_id=U(), github_login="demo"
        ),
    }


def test_every_ml_command_has_handler():
    ml_cmds = {t for t, s in COMMANDS.items() if s.consumer == "ml"}
    assert ml_cmds == set(HANDLERS) == set(_commands())


@pytest.mark.parametrize("type_", sorted(_commands()))
def test_handler_returns_valid_events_and_is_idempotent(type_):
    env, _ = new_command(type_, "core", _commands()[type_], correlation_id="c1")
    first = handle(env)
    assert first and all(e.producer == "ml" and e.correlation_id == "c1" for e in first)
    for e in first:
        parse_payload(e)  # результат соответствует контракту
    again = handle(Envelope.model_validate(env.model_dump(mode="json")))
    # повторная доставка: те же message_id и содержимое → inbox получателя отбросит дубль
    assert [(e.message_id, e.type, e.payload) for e in first] == [
        (e.message_id, e.type, e.payload) for e in again
    ]


def test_resume_failure_scenario():
    p = _commands()["ml.resume.parse"].model_copy(update={"object_key": "r/1.scanned"})
    env, _ = new_command("ml.resume.parse", "core", p)
    (out,) = handle(env)
    assert out.type == "ml.resume.failed" and out.payload["error"] == "scanned_pdf"


def test_resume_without_llm_is_unavailable_not_fixture():
    env, _ = new_command("ml.resume.parse", "core", _commands()["ml.resume.parse"])
    (out,) = handle(env)
    assert out.type == "ml.resume.failed" and out.payload["error"] == "llm_unavailable"


def test_resume_has_quotes_for_every_skill():
    p = _commands()["ml.resume.parse"].model_copy(update={"object_key": "r/1.fixture"})
    env, _ = new_command("ml.resume.parse", "core", p)
    parsed = parse_payload(handle(env)[0]).parsed
    assert parsed.skills and all(s.quote for s in parsed.skills)


def test_skills_resolve_keeps_java_javascript_distinct():
    env, _ = new_command(
        "ml.skills.resolve",
        "core",
        cmd.MlSkillsResolve(
            request_id=U(),
            mentions=[SkillMention(raw="Java"), SkillMention(raw="JavaScript")],
            taxonomy_version=1,
        ),
    )
    items = parse_payload(handle(env)[0]).items
    assert [i.skill_slug for i in items] == ["java", "javascript"]


@pytest.fixture
def client():
    return TestClient(build_app(Settings(ml_fake=True)))


def test_api_embeddings_deterministic(client):
    body = {"texts": ["a", "b"], "kind": "query"}
    r1 = client.post("/v1/embeddings", json=body).json()
    r2 = client.post("/v1/embeddings", json=body).json()
    assert r1 == r2 and r1["dim"] == 1024 and len(r1["vectors"]) == 2
    assert len(r1["vectors"][0]) == 1024 and r1["vectors"][0] != r1["vectors"][1]


def test_api_skills_resolve(client):
    r = client.post(
        "/v1/skills/resolve",
        json={"mentions": [{"raw": "Postgres"}, {"raw": "etc"}], "taxonomy_version": 1},
    )
    assert r.status_code == 200
    items = r.json()
    assert items[0]["decision"] == "alias" and items[0]["skill_slug"] == "postgresql"
    assert items[1]["decision"] == "rejected"


def test_api_query_parse(client):
    r = client.post(
        "/v1/query/parse",
        json={"text": "Senior бэкенд на Python удалённо до 300 тыс", "taxonomy_version": 1},
    )
    f = r.json()["filters"]
    assert f["roles"] == ["backend"] and f["grade_min"] == "senior" and f["formats"] == ["remote"]
    assert f["salary_max"] == 300000 and f["skills_must"][0]["slug"] == "python"


def test_api_validation_error_is_problem(client):
    r = client.post("/v1/embeddings", json={"texts": [], "kind": "query"})
    assert r.status_code == 422 and r.json()["code"] == "validation_error"


def test_embeddings_without_model_use_fallback_not_503():
    c = TestClient(build_app(Settings(ml_fake=False, llm_enabled=True)))
    r = c.post("/v1/embeddings", json={"texts": ["a"], "kind": "query"})
    assert r.status_code == 200 and r.json()["dim"] == 1024
    again = c.post("/v1/embeddings", json={"texts": ["a"], "kind": "query"}).json()
    assert again["vectors"] == r.json()["vectors"]  # детерминированно
    assert c.get("/healthz").json()["embedder"] == "fallback"
