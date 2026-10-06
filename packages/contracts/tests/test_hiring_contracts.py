"""Контракты блока 2: `offer.interest.*` (ADR-026, E33-1)."""

from uuid import uuid4

import pytest
from fsp_contracts import new_envelope, parse_payload
from fsp_contracts.enums import DeclineReason, OfferStatus
from fsp_contracts.events import EVENT_PRODUCERS, EVENTS
from fsp_contracts.hiring import (
    HIRING_EVENTS,
    INTEREST_SCHEMA_VERSION,
    OFFER_SCHEMA_VERSION,
    OfferInterestEvent,
)
from pydantic import ValidationError

NAMES = {f"offer.interest.{n}" for n in ("sent", "opened", "declined", "expired", "withdrawn")}


def test_interest_events_registered():
    assert NAMES <= set(HIRING_EVENTS) <= set(EVENTS)
    assert all(EVENT_PRODUCERS[n] == "core" for n in NAMES)
    assert INTEREST_SCHEMA_VERSION > OFFER_SCHEMA_VERSION


def test_interest_payload_roundtrip():
    payload = {
        "offer_id": str(uuid4()), "candidate_id": str(uuid4()), "company_id": str(uuid4()),
        "status": "declined", "prev_status": "interest_opened", "actor": "candidate",
        "decline_reason": "wrong_company", "salary_from": 200000, "salary_to": 260000,
    }  # fmt: skip
    ev = OfferInterestEvent.model_validate(payload)
    assert ev.status == OfferStatus.declined and ev.prev_status == OfferStatus.interest_opened
    assert ev.decline_reason == DeclineReason.wrong_company and ev.vacancy_id is None
    env = new_envelope(
        "offer.interest.declined", "core", ev, schema_version=INTEREST_SCHEMA_VERSION
    )
    assert env.schema_version == 3
    assert parse_payload(env) == ev


def test_interest_payload_requires_salary():
    with pytest.raises(ValidationError):
        OfferInterestEvent(
            offer_id=uuid4(), candidate_id=uuid4(), company_id=uuid4(), status="interest"
        )
