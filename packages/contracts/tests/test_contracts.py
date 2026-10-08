from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from fsp_contracts import Envelope, UnknownMessageType, new_command, new_event, parse_payload
from fsp_contracts.asyncapi import build_asyncapi
from fsp_contracts.commands import COMMANDS, CoreRecompute, MlResumeParse
from fsp_contracts.enums import EvidenceSource, Grade, OfferStatus, TrustLevel
from fsp_contracts.events import (
    EVENT_PRODUCERS,
    EVENTS,
    FspResultsImported,
    MlResumeResult,
    OfferEvent,
    ProfileDiff,
    SkillsProfileUpdated,
)
from fsp_contracts.fsp import FspResult
from fsp_contracts.ml import ParsedResume, ResumeSkill
from fsp_contracts.notify import NotifyTelegram, TgButton, TgTemplate
from fsp_contracts.ui import JobProgress, OfferCreated, new_ui_message, ui_routing_key
from pydantic import ValidationError


def test_enums_match_data_model():
    assert [g.order for g in Grade] == list(range(7))
    assert Grade.middle.order > Grade.junior_plus.order
    assert EvidenceSource.self_ == "self"
    assert [int(t) for t in TrustLevel] == [0, 1, 2, 3, 4]
    assert len(OfferStatus) == 11  # + interest, interest_opened (ADR-026)


def test_event_roundtrip_typed():
    cid = uuid4()
    payload = FspResultsImported(
        candidate_id=cid,
        participant_id="p-1",
        results=[
            FspResult(
                competition_id="c-1",
                discipline="product",
                stage="final",
                team_role="captain",
                place=2,
                participants_total=120,
                date=date(2025, 11, 15),
            )
        ],
        new=True,
    )
    env = new_event("fsp.results.imported", "fsp-connector", payload, correlation_id="rid")
    again = Envelope.model_validate_json(env.model_dump_json())
    parsed = parse_payload(again)
    assert isinstance(parsed, FspResultsImported)
    assert parsed == payload


def test_profile_diff_serializes_from():
    diff = ProfileDiff.model_validate(
        {"skills_up": [{"slug": "algorithms", "from": 3, "to": 4}], "grade": {"to": "middle"}}
    )
    ev = SkillsProfileUpdated(candidate_id=uuid4(), profile_version=7, diff=diff)
    dumped = ev.model_dump(mode="json")
    assert dumped["diff"]["skills_up"][0]["from"] == 3
    assert SkillsProfileUpdated.model_validate(dumped) == ev


def test_wrong_payload_model_rejected():
    with pytest.raises(TypeError):
        new_event("offer.sent", "core", CoreRecompute(candidate_id=uuid4(), requested_at=_now()))
    with pytest.raises(UnknownMessageType):
        new_event("offer.unknown", "core", OfferEvent.model_construct())
    with pytest.raises(UnknownMessageType):
        new_command("offer.sent", "core", OfferEvent.model_construct())


def test_parse_payload_validates():
    env = Envelope(type="offer.sent", producer="core", payload={"offer_id": "nope"})
    with pytest.raises(ValidationError):
        parse_payload(env)


def test_command_spec_and_llm_priorities():
    cmd = MlResumeParse(
        resume_id=uuid4(),
        candidate_id=uuid4(),
        object_key="resumes/x.pdf",
        mime="application/pdf",
        sha256="0" * 64,
        taxonomy_version=1,
    )
    env, spec = new_command("ml.resume.parse", "core", cmd)
    assert spec.queue == "ml.llm" and spec.priority == 9
    assert parse_payload(env) == cmd
    # messaging.md §2.2: порядок приоритетов в ml.llm
    llm = {t: s.priority for t, s in COMMANDS.items() if s.queue == "ml.llm"}
    assert llm == {
        "ml.resume.parse": 9,
        "ml.interview.grade": 8,
        "ml.interview.generate": 7,
        "ml.interview_kit.generate": 5,
        "ml.skills.resolve": 3,
        "ml.matches.explain": 2,
        "ml.questions.generate": 1,
    }
    assert COMMANDS["notify.telegram"].queue == "bot.telegram"
    assert COMMANDS["fsp.sync"].queue == "fsp.sync"


def test_ml_resume_result_keeps_quotes():
    parsed = ParsedResume(
        parser_version="1",
        skills=[
            ResumeSkill(
                raw="FastAPI", slug="fastapi", quote="FastAPI", method="alias", confidence=0.9
            )
        ],
    )
    ev = MlResumeResult(resume_id=uuid4(), candidate_id=uuid4(), parsed=parsed)
    assert MlResumeResult.model_validate_json(ev.model_dump_json()) == ev
    with pytest.raises(ValidationError):
        ResumeSkill.model_validate({"raw": "Go", "method": "alias", "confidence": 0.5})


def test_notify_telegram_buttons():
    oid = uuid4()
    msg = NotifyTelegram(
        chat_id=42,
        template=TgTemplate.offer_new,
        data={"offer_id": str(oid)},
        buttons=[[TgButton(text="✅ Принять", callback_data=f"o:a:{oid}")]],
        edit_of=f"offer:{oid}",
    )
    assert NotifyTelegram.model_validate_json(msg.model_dump_json()) == msg
    with pytest.raises(ValidationError):
        TgButton(text="x", callback_data="t:a:" + "x" * 61)
    with pytest.raises(ValidationError):
        TgButton(text="x")


def test_ui_message():
    uid = uuid4()
    m = new_ui_message(uid, "offer.created", OfferCreated(offer_id=uuid4()))
    assert m.data["offer_id"]
    assert ui_routing_key(uid) == f"ui.user.{uid}"
    with pytest.raises(TypeError):
        new_ui_message(uid, "job.progress", OfferCreated(offer_id=uuid4()))
    with pytest.raises(ValidationError):
        JobProgress(job_id=uuid4(), kind="resume", stage="x", pct=101, message="")


def test_producers():
    assert EVENT_PRODUCERS["fsp.linked"] == "fsp-connector"
    assert EVENT_PRODUCERS["ml.code.completed"] == "ml"
    assert EVENT_PRODUCERS["offer.sent"] == "core"


def _refs(node):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "$ref":
                yield v
            else:
                yield from _refs(v)
    elif isinstance(node, list):
        for v in node:
            yield from _refs(v)


def test_asyncapi_complete_and_refs_resolve():
    doc = build_asyncapi()
    assert doc["asyncapi"] == "3.0.0"
    titles = {m["name"] for m in doc["components"]["messages"].values()}
    assert set(EVENTS) <= titles
    assert set(COMMANDS) <= titles
    for ref in _refs(doc):
        node = doc
        for part in ref.removeprefix("#/").split("/"):
            node = node[part]


def _now():
    return datetime.now(UTC)


def test_analytics_events_validate_and_reject_pii():
    from fsp_contracts.analytics import (
        ANALYTICS_EVENTS,
        AnalyticsEvent,
        UnknownAnalyticsEvent,
        validate_event,
    )

    def ev(name, props, **kw):
        return AnalyticsEvent(
            event=name, ts=datetime(2026, 10, 5, 12, tzinfo=UTC), props=props, **kw
        )

    ok = validate_event(
        ev("search_submitted", {"query_len": 54, "chips": 4, "parse_source": "llm"})
    )
    assert ok.props["refining"] is False
    # лишнее поле (в т.ч. свободный текст) отклоняется
    with pytest.raises(ValidationError):
        validate_event(
            ev(
                "search_submitted",
                {"query_len": 5, "chips": 1, "parse_source": "rule", "query": "ищу Васю"},
            )
        )
    # свободный текст в slug-поле отклоняется
    with pytest.raises(ValidationError):
        validate_event(ev("uplift_shown", {"skill": "Иван Петров"}), source="web")
    # неизвестное событие и чужой источник
    with pytest.raises(UnknownAnalyticsEvent):
        validate_event(ev("hack", {}))
    with pytest.raises(UnknownAnalyticsEvent):
        validate_event(ev("offer_accepted", {"offer_id": str(uuid4())}), source="web")
    # actor только псевдоним, не email/uuid
    with pytest.raises(ValidationError):
        ev("signup_completed", {"channel": "web"}, actor="user@example.com")
    with pytest.raises(ValidationError):
        AnalyticsEvent(event="x", ts=datetime(2026, 1, 1), props={})  # naive ts
    # alias `from` у graph_opened
    g = validate_event(ev("graph_opened", {"nodes": 12, "from": "card"}), source="web")
    assert g.props == {"nodes": 12, "from": "card"}
    assert len(ANALYTICS_EVENTS) >= 45


def test_skill_card_draft_roundtrip():
    """E16-4: черновик карточки от ml совпадает по форме с карточкой core (`SkillCard`)."""
    from fsp_contracts.ml import SkillCardDraft, SkillCardDraftRequest

    assert SkillCardDraftRequest(slug="helm", name="Helm").kind == "hard"
    raw = {
        "skill": "helm",
        "type": "hard",
        "summary": "Описывает приложения чартами.",
        "levels": {
            "junior": ["а а а", "б б б"],
            "middle": ["в в в", "г г г"],
            "senior": ["д д д", "е е е"],
        },
        "concepts": [{"term": t, "note": "поясняющая фраза"} for t in "abc"],
        "misconceptions": [{"claim": f"claim {i}", "truth": "truth"} for i in range(2)],
        "model": "rules-template",
    }
    d = SkillCardDraft.model_validate(raw)
    assert d.draft is True and d.schema_version == 1


def test_offer_event_v2_without_vacancy():
    """ADR-022 (E20-2): `vacancy_id` пуст, `initiator`; старый payload без поля — `employer`."""
    from fsp_contracts import new_envelope
    from fsp_contracts.hiring import OFFER_SCHEMA_VERSION, OfferInitiator

    ids = {"offer_id": str(uuid4()), "candidate_id": str(uuid4()), "company_id": str(uuid4())}
    env = new_envelope(
        "offer.sent", "core", OfferEvent(**ids, status=OfferStatus.sent, actor="company"),
        schema_version=OFFER_SCHEMA_VERSION,
    )  # fmt: skip
    again = Envelope.model_validate_json(env.model_dump_json())
    assert again.schema_version == 2
    parsed = parse_payload(again)
    assert parsed.vacancy_id is None and parsed.initiator is OfferInitiator.employer
    v1 = OfferEvent.model_validate({**ids, "vacancy_id": str(uuid4()), "status": "sent"})
    assert v1.initiator == "employer"
    resp = OfferEvent.model_validate({**ids, "status": "sent", "initiator": "candidate"})
    assert resp.initiator is OfferInitiator.candidate
    with pytest.raises(ValidationError):
        OfferEvent.model_validate({**ids, "status": "sent", "initiator": "admin"})
