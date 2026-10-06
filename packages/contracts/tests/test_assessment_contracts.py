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
