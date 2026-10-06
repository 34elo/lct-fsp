"""Контракты стыка блоков (blocks.md §4.1, §4.3, §4.4)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fsp_contracts import new_event, parse_payload
from fsp_contracts.analytics import ANALYTICS_EVENTS
from fsp_contracts.analytics_assessment import ASSESSMENT_ANALYTICS_EVENTS
from fsp_contracts.analytics_hiring import HIRING_ANALYTICS_EVENTS
from fsp_contracts.assessment import (
    ASSESSMENT_EVENTS,
    TEST_GRADE_ORDER,
    AttemptFinished,
    CandidateGrade,
    CategoryChanged,
    CategoryRef,
    ClaimedVsConfirmed,
    FamilyStatusChanged,
    ProfessionInfo,
    SkillType,
    TestGrade,
)
from fsp_contracts.enums import ConsentType, Grade
from fsp_contracts.events import EVENT_PRODUCERS, EVENTS
from fsp_contracts.hiring import HIRING_EVENTS
from pydantic import ValidationError


def test_grades_match_enums_grade():
    assert [g.value for g in TEST_GRADE_ORDER] == ["junior", "middle", "senior"]
    assert {g.value for g in TestGrade} <= {g.value for g in Grade}
    assert len(SkillType) == 6


def test_category_changed_via_registry():
    cid = uuid4()
    payload = CategoryChanged(
        candidate_id=cid,
        categories=[CategoryRef(profession="backend", grade=TestGrade.middle)],
        profile_version=3,
    )
    env = new_event("candidate.category.changed", "core", payload)
    parsed = parse_payload(type(env).model_validate_json(env.model_dump_json()))
    assert parsed == payload
    assert EVENT_PRODUCERS["candidate.category.changed"] == "core"


def test_attempt_finished_and_family_alias():
    now = datetime.now(UTC)
    ev = AttemptFinished(
        candidate_id=uuid4(),
        attempt_id=uuid4(),
        profession="ml",
        declared_grade="senior",
        stage="main",
        result="passed",
        grade="senior",
        theta=1.2,
        se=0.3,
        integrity=1.0,
        needs_confirmation=False,
        low_confidence=False,
        finished_at=now,
        profile_version=1,
    )
    assert new_event("assessment.attempt.finished", "core", ev)
    fam = FamilyStatusChanged.model_validate(
        {"family_id": str(uuid4()), "from": None, "to": "live"}
    )
    assert fam.from_ is None
    assert fam.model_dump(by_alias=True)["from"] is None


def test_bad_profession_slug_rejected():
    with pytest.raises(ValidationError):
        CategoryRef(profession="Back-End", grade="junior")


def test_candidate_grade_and_dto_defaults():
    now = datetime.now(UTC)
    g = CandidateGrade(
        candidate_id=uuid4(),
        profession="qa",
        grade="junior",
        theta=-1.0,
        band_position=0.5,
        source="seed",
        confirmed_at=now,
        valid_until=now + timedelta(days=365),
        next_change_at=now + timedelta(days=30),
    )
    assert g.integrity == 1.0 and g.theta_by_type == {} and not g.needs_confirmation
    assert ClaimedVsConfirmed(profession="qa", status="unconfirmed").confirmed_grade is None
    assert ProfessionInfo(slug="qa", title="QA", skill_weights={"pytest": 0.5}).skill_types == {}


def test_registries_wired():
    assert set(ASSESSMENT_EVENTS) <= set(EVENTS)
    assert set(HIRING_EVENTS) <= set(EVENTS)
    assert set(ASSESSMENT_ANALYTICS_EVENTS) <= set(ANALYTICS_EVENTS)
    assert set(HIRING_ANALYTICS_EVENTS) <= set(ANALYTICS_EVENTS)
    assert ConsentType.profile_publication == "profile_publication"


def test_family_key_draft_contract():
    """E30-1: core ↔ ml-api `POST /v1/families/key-draft`."""
    from fsp_contracts.ml import FamilyKeyDraft, FamilyKeyDraftRequest

    req = FamilyKeyDraftRequest.model_validate(
        {"kind": "sjt", "stem": "PR на 3000 строк", "actions": ["Разбить", "Одобрить", "Обсудить"]}
    )
    assert req.options == [] and req.rubric == []
    with pytest.raises(ValidationError):
        FamilyKeyDraftRequest.model_validate({"kind": "essay", "stem": "x"})
    d = FamilyKeyDraft.model_validate({"scores": [3, 1, 2], "model": "qwen3-vl-4b"})
    assert d.correct is None and d.scores == [3.0, 1.0, 2.0]
    assert FamilyKeyDraft.model_validate(d.model_dump(mode="json")) == d


def test_answer_explain_contract():
    """E24-2: core ↔ ml-api `POST /v1/assessment/explain`."""
    from fsp_contracts.ml import AnswerExplain, AnswerExplainRequest

    req = AnswerExplainRequest.model_validate(
        {
            "kind": "chain",
            "skill": "python",
            "stem": "x",
            "reason_code": "chain_step",
            "reason_label": "Ошибка на одном из шагов",
        }
    )
    assert req.misconception is None and req.truth is None
    with pytest.raises(ValidationError):
        AnswerExplainRequest.model_validate({**req.model_dump(), "kind": "essay"})
    a = AnswerExplain.model_validate({"text": "Проверьте второй шаг", "model": "qwen"})
    assert AnswerExplain.model_validate(a.model_dump(mode="json")) == a


def test_family_llm_bank_contracts():
    from fsp_contracts.ml import (
        FamilyGenerateRequest,
        FamilyGenerateResponse,
        FamilySolveAnswer,
        FamilySolveRequest,
    )

    g = FamilyGenerateRequest.model_validate({"skill": "python", "kind": "choice", "level": 3})
    assert g.n == 1 and g.domain is None
    with pytest.raises(ValidationError):
        FamilyGenerateRequest.model_validate({"skill": "python", "kind": "choice", "level": 6})
    r = FamilyGenerateResponse.model_validate({"specs": [{"title": "x"}], "model": "m"})
    assert FamilyGenerateResponse.model_validate(r.model_dump(mode="json")) == r
    s = FamilySolveRequest.model_validate({"kind": "order", "stem": "x", "options": ["a", "b"]})
    assert s.options == ["a", "b"]
    for v in (2, 2.5, "42", [1, 0]):
        a = FamilySolveAnswer.model_validate({"answer": v})
        assert a.answer == v and type(a.answer) is type(v)


def test_regular_task_published_contract():
    """E25-1: событие рассылки регулярного задания (E9-6 у блока 2 читает его)."""
    from fsp_contracts.assessment import RegularTaskPublished

    assert ASSESSMENT_EVENTS["regular_task.published"] is RegularTaskPublished
    payload = {
        "task_id": str(uuid4()),
        "company_id": str(uuid4()),
        "profession": "backend",
        "grade": "middle",
        "round": 1,
        "period_days": 14,
        "recipients": [str(uuid4())],
        "published_at": datetime.now(UTC).isoformat(),
    }
    ev = RegularTaskPublished.model_validate(payload)
    assert RegularTaskPublished.model_validate(ev.model_dump(mode="json")) == ev
    assert RegularTaskPublished.model_validate({**payload, "recipients": []}).recipients == []
    with pytest.raises(ValidationError):
        RegularTaskPublished.model_validate({**payload, "round": 0})


def test_assessment_analytics_props_strict():
    from fsp_contracts.analytics import AnalyticsEvent, UnknownAnalyticsEvent, validate_event
    from pydantic import ValidationError

    def ev(name, props):
        return AnalyticsEvent(event=name, ts=datetime.now(UTC), props=props)

    ok = validate_event(
        ev(
            "assessment_answered",
            {
                "attempt_id": str(uuid4()),
                "seq": 3,
                "stage": "main",
                "is_pilot": False,
                "score": 0.5,
                "rt_ms": 1200,
            },
        )
    )
    assert ok.props["score"] == 0.5
    with pytest.raises(ValidationError):  # текст ответа в props запрещён
        validate_event(
            ev(
                "assessment_answered",
                {
                    "attempt_id": "a",
                    "seq": 1,
                    "stage": "main",
                    "is_pilot": False,
                    "score": 1,
                    "answer": "def f(): pass",
                },
            )
        )
    with pytest.raises(ValidationError):  # свободный текст не проходит как slug
        validate_event(ev("survey_saved", {"profession": "Backend Dev text"}))
    with pytest.raises(ValidationError):
        validate_event(
            ev(
                "family_status_changed",
                {"family": "f", "from_status": "draft", "to_status": "bogus"},
            )
        )
    with pytest.raises(UnknownAnalyticsEvent):  # веб не шлёт серверные события
        validate_event(
            ev(
                "assessment_started",
                {"attempt_id": "a", "profession": "backend", "declared_grade": "middle"},
            ),
            "web",
        )
    assert set(ASSESSMENT_ANALYTICS_EVENTS) <= set(ANALYTICS_EVENTS)
    assert all(
        n.split("_")[0] in ("survey", "assessment", "family", "regular")
        for n in ASSESSMENT_ANALYTICS_EVENTS
    )


def test_hiring_analytics_events_validate_and_reject_pii():
    from datetime import UTC, datetime
    from uuid import uuid4

    import pytest
    from fsp_contracts.analytics import AnalyticsEvent, validate_event
    from pydantic import ValidationError

    def ev(name, props):
        return AnalyticsEvent(
            event=name, ts=datetime(2026, 10, 6, 12, tzinfo=UTC), props=props, role="employer"
        )

    assert HIRING_ANALYTICS_EVENTS
    assert set(HIRING_ANALYTICS_EVENTS) <= set(ANALYTICS_EVENTS)
    ok = validate_event(ev("invite_sent", {"invite_id": str(uuid4()), "with_vacancy": False}))
    assert ok.props["with_vacancy"] is False
    # свободный текст и ПДн отклоняются
    with pytest.raises(ValidationError):
        validate_event(ev("need_created", {"need_id": str(uuid4()), "skills": 3, "text": "Вася"}))
    with pytest.raises(ValidationError):
        validate_event(
            ev("category_viewed", {"profession": "Иван", "grade": "mid", "candidates": 1})
        )
