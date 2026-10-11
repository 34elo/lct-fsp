"""Доменное событие → продуктовые события трекинг-плана.

Чистые функции без БД: бизнес-модули об аналитике не знают. Свободного текста и ПДн в `props`
нет: только счётчики, перечисления и id оффера/вакансии. События, которых нет в таблице
`MAPPERS`, аналитика игнорирует.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fsp_contracts import Envelope, parse_payload
from fsp_contracts.analytics import AnalyticsEvent, Channel, Role
from fsp_contracts.events import (
    CandidateRegistered,
    FspLinked,
    MatchesReady,
    MlCodeResult,
    MlInterviewGraded,
    MlResumeResult,
    OfferEvent,
    ResumeEvent,
    SkillsProfileUpdated,
    VacancyEvent,
)
from fsp_contracts.hiring import OfferInitiator

from app.analytics import hiring
from app.analytics.service import pseudonym

Mapped = list[AnalyticsEvent]


class _Ctx:
    def __init__(self, envelope: Envelope, salt: str):
        self.envelope = envelope
        self.salt = salt

    def ev(self, name: str, subject: Any, role: Role, props: dict[str, Any]) -> AnalyticsEvent:
        channel: Channel = "system"
        return AnalyticsEvent(
            event=name,
            ts=self.envelope.occurred_at,
            actor=pseudonym(self.salt, subject),
            role=role,
            channel=channel,
            props=props,
        )


def _candidate_registered(c: _Ctx, p: CandidateRegistered) -> Mapped:
    return [c.ev("signup_completed", p.candidate_id, "candidate", {"channel": p.channel})]


def _resume_confirmed(c: _Ctx, p: ResumeEvent) -> Mapped:
    return [c.ev("resume_confirmed", p.candidate_id, "candidate", {})]


def _resume_parsed(c: _Ctx, p: MlResumeResult) -> Mapped:
    parsed = p.parsed
    props = {
        "skills_found": len(parsed.skills) if parsed else 0,
        "new_skills": len(parsed.unknown_skills) if parsed else 0,
        "ok": parsed is not None and p.error is None,
    }
    return [c.ev("resume_parsed", p.candidate_id, "candidate", props)]


def _fsp_linked(c: _Ctx, p: FspLinked) -> Mapped:
    props = {"method": p.method, "verified": p.verified}
    return [c.ev("fsp_link_completed", p.candidate_id, "candidate", props)]


def _github(c: _Ctx, p: MlCodeResult) -> Mapped:
    res = p.result
    repos = res.repos if res else []
    props = {
        "repos": len(repos),
        "deep_repos": sum(r.deep for r in repos),
        "flags": len(res.flags) if res else 0,
        "ok": res is not None and p.error is None,
    }
    return [c.ev("github_analysis_completed", p.candidate_id, "candidate", props)]


def _profile(c: _Ctx, p: SkillsProfileUpdated) -> Mapped:
    d = p.diff
    props: dict[str, Any] = {
        "profile_version": p.profile_version,
        "skills_up": len(d.skills_up),
        "skills_new": len(d.skills_new),
    }
    if d.grade:
        props["grade_to"] = d.grade.to.value
        if d.grade.from_:
            props["grade_from"] = d.grade.from_.value
    return [c.ev("profile_updated", p.candidate_id, "candidate", props)]


def _interview(c: _Ctx, p: MlInterviewGraded) -> Mapped:
    if p.error:
        return []
    avg = sum(g.score for g in p.grades) / len(p.grades) if p.grades else None
    props = {"questions": len(p.grades), "avg_score": avg}
    return [c.ev("interview_completed", p.candidate_id, "candidate", props)]


def _offer(c: _Ctx, p: OfferEvent) -> Mapped:
    if p.initiator == OfferInitiator.candidate:  # отклики в метрики офферов не входят
        return hiring.offer_events(c, p)
    return [*_offer_legacy(c, p), *hiring.offer_events(c, p)]


def _offer_legacy(c: _Ctx, p: OfferEvent) -> Mapped:
    oid = str(p.offer_id)
    cand = p.candidate_id
    match c.envelope.type:
        case "offer.sent":
            return [
                c.ev("offer_sent", p.company_id, "employer", {"offer_id": oid}),
                c.ev("offer_received", cand, "candidate", {"offer_id": oid}),
            ]
        case "offer.viewed":
            return [c.ev("offer_opened", cand, "candidate", {"offer_id": oid})]
        case "offer.accepted":
            return [c.ev("offer_accepted", cand, "candidate", {"offer_id": oid})]
        case "offer.declined":
            props: dict[str, Any] = {"offer_id": oid}
            if p.decline_reason:
                props["reason"] = p.decline_reason.value
            return [c.ev("offer_declined", cand, "candidate", props)]
        case "offer.message" if p.actor == "candidate":
            return [c.ev("offer_question_asked", cand, "candidate", {"offer_id": oid})]
    return []


def _vacancy_published(c: _Ctx, p: VacancyEvent) -> Mapped:
    # актор — сама вакансия: компания в событии не указана, а свой псевдоним у неё стабилен
    return [c.ev("vacancy_published", p.vacancy_id, "employer", {"version": p.version})]


def _matches(c: _Ctx, p: MatchesReady) -> Mapped:
    props = {"vacancy_id": str(p.vacancy_id), "candidates": p.count}
    return [c.ev("matches_computed", p.vacancy_id, "employer", props)]


MAPPERS: dict[str, Callable[[_Ctx, Any], Mapped]] = {
    "candidate.registered": _candidate_registered,
    "resume.confirmed": _resume_confirmed,
    "ml.resume.completed": _resume_parsed,
    "ml.resume.failed": _resume_parsed,
    "fsp.linked": _fsp_linked,
    "ml.code.completed": _github,
    "ml.code.failed": _github,
    "skills.profile.updated": _profile,
    "ml.interview.graded": _interview,
    "offer.sent": _offer,
    "offer.viewed": _offer,
    "offer.accepted": _offer,
    "offer.declined": _offer,
    "offer.message": _offer,
    "offer.expired": _offer,
    "offer.withdrawn": _offer,
    "offer.status_changed": _offer,
    "offer.interest.sent": hiring.interest_events,
    "offer.interest.opened": hiring.interest_events,
    "offer.interest.declined": hiring.interest_events,
    "offer.interest.expired": hiring.interest_events,
    "offer.interest.withdrawn": hiring.interest_events,
    "candidate.category.changed": hiring.category_events,
    "vacancy.published": _vacancy_published,
    "matches.ready": _matches,
}


def map_event(envelope: Envelope, salt: str) -> Mapped:
    mapper = MAPPERS.get(envelope.type)
    if mapper is None:
        return []
    return mapper(_Ctx(envelope, salt), parse_payload(envelope))
