"""Выпуск, отзыв и проверка Open Badge 3.0.

Выпуск возможен только для того, что и так публично (как бейдж SVG): включена видимость
`public_profile`, выдано согласие `profile_publication`, есть действующий грейд. Пока условия
не выполняются, публичные эндпоинты отвечают 404; отозванный бейдж проверка показывает как
отозванный, но тело кредита больше не отдаётся.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fsp_contracts.enums import ConsentType
from fsp_platform.app import ProblemError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import service as assessment
from app.candidates import service as candidates
from app.candidates.models import Candidate
from app.consents import service as consents
from app.credentials import signing
from app.credentials.models import IssuedCredential
from app.identity.models import utcnow

OB_CONTEXT = [
    "https://www.w3.org/ns/credentials/v2",
    "https://purl.imsglobal.org/spec/ob/v3p0/context-3.0.3.json",
]
KEY_FRAGMENT = "key-1"


@dataclass(frozen=True)
class Issuer:
    domain: str
    key: Ed25519PrivateKey

    @property
    def did(self) -> str:
        return f"did:web:{self.domain}"

    @property
    def key_id(self) -> str:
        return f"{self.did}#{KEY_FRAGMENT}"

    @property
    def api_base(self) -> str:
        return f"https://api.{self.domain}/api/v1"

    @classmethod
    def from_settings(cls, settings) -> Issuer:
        return cls(settings.ob_issuer_domain, signing.load_private_key(settings.ob_signing_key))

    def did_document(self) -> dict:
        key = signing.public_multibase(self.key)
        return {
            "@context": ["https://www.w3.org/ns/did/v1", "https://w3id.org/security/multikey/v1"],
            "id": self.did,
            "verificationMethod": [
                {
                    "id": self.key_id,
                    "type": "Multikey",
                    "controller": self.did,
                    "publicKeyMultibase": key,
                }
            ],
            "authentication": [self.key_id],
            "assertionMethod": [self.key_id],
        }


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _iso(dt: datetime) -> str:
    return _aware(dt).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dots(integrity: float) -> str:
    n = max(0, min(4, round(integrity * 4)))
    return "●" * n + "○" * (4 - n)


def credential_url(issuer: Issuer, cid: uuid.UUID) -> str:
    return f"{issuer.api_base}/public/credentials/{cid}"


def build_credential(
    issuer: Issuer, cid: uuid.UUID, candidate: Candidate, grade, now: datetime
) -> dict:
    """Неподписанный OpenBadgeCredential. ПДн нет: только псевдоним."""
    prof = grade.profession.replace("_", " ").title()
    title = f"{prof} · {str(grade.grade).title()}"
    return {
        "@context": list(OB_CONTEXT),
        "id": credential_url(issuer, cid),
        "type": ["VerifiableCredential", "OpenBadgeCredential"],
        "name": f"Подтверждено ФСП: {title}",
        "issuer": {
            "id": issuer.did,
            "type": ["Profile"],
            "name": "ФСП Карьера",
            "url": f"https://{issuer.domain}",
        },
        "validFrom": _iso(now),
        "validUntil": _iso(grade.valid_until),
        "credentialSubject": {
            "type": ["AchievementSubject"],
            "identifier": [
                {
                    "type": "IdentityObject",
                    "identityType": "name",
                    "hashed": False,
                    "identityHash": candidate.pseudonym,
                }
            ],
            "achievement": {
                "id": f"{issuer.api_base}/public/achievements/{grade.profession}-{grade.grade}",
                "type": ["Achievement"],
                "achievementType": "Certification",
                "name": f"Подтверждено ФСП: {title}",
                "description": (
                    "Категория подтверждена тестом на платформе ФСП Карьера: "
                    f"{grade.profession} · {grade.grade}, доверие {_dots(grade.integrity)}."
                ),
                "criteria": {
                    "narrative": "Адаптивный тест по профессии с контролем добросовестности; "
                    "результат действует 12 месяцев."
                },
            },
            "result": [
                {
                    "type": "Result",
                    "resultDescription": f"{issuer.api_base}/public/achievements/grade",
                    "value": str(grade.grade),
                    "status": "Completed",
                },
                {
                    "type": "Result",
                    "resultDescription": f"{issuer.api_base}/public/achievements/trust",
                    "value": _dots(grade.integrity),
                    "status": "Completed",
                },
            ],
        },
    }


async def _publishable(session: AsyncSession, cand: Candidate) -> bool:
    return bool(
        cand.visibility.get("public_profile")
        and await consents.has_consent(session, cand.user_id, ConsentType.profile_publication)
    )


async def _active_for(session: AsyncSession, candidate_id: uuid.UUID, profession: str):
    return list(
        await session.scalars(
            select(IssuedCredential).where(
                IssuedCredential.candidate_id == candidate_id,
                IssuedCredential.profession == profession,
                IssuedCredential.revoked_at.is_(None),
            )
        )
    )


async def issue(
    session: AsyncSession, issuer: Issuer, candidate_id: uuid.UUID, profession: str | None
) -> IssuedCredential:
    cand = await candidates.get(session, candidate_id)
    if cand is None:
        raise ProblemError(404, "candidate_not_found", "Кандидат не найден")
    grades = await assessment.get_grades(session, candidate_id)
    if profession:
        grades = [g for g in grades if g.profession == profession]
    if not grades:
        raise ProblemError(404, "grade_not_found", "Нет подтверждённой категории")
    if not await _publishable(session, cand):
        raise ProblemError(
            409, "publication_required", "Включите публичный профиль и согласие на публикацию"
        )
    grade = grades[0]
    now = utcnow()
    for old in await _active_for(session, candidate_id, grade.profession):
        if old.grade == str(grade.grade) and _aware(old.issued_at) >= _aware(grade.confirmed_at):
            return old  # тот же грейд, ничего не менялось: идемпотентно
        old.revoked_at, old.revoke_reason = now, "superseded"
    cid = uuid.uuid4()
    signed = signing.sign_document(
        build_credential(issuer, cid, cand, grade, now),
        issuer.key,
        verification_method=issuer.key_id,
        created=now,
    )
    row = IssuedCredential(
        id=cid,
        candidate_id=candidate_id,
        profession=grade.profession,
        grade=str(grade.grade),
        profile_version=cand.profile_version,
        credential=signed,
        issued_at=now,
    )
    session.add(row)
    await session.flush()
    return row


async def list_own(session: AsyncSession, candidate_id: uuid.UUID) -> list[IssuedCredential]:
    return list(
        await session.scalars(
            select(IssuedCredential)
            .where(IssuedCredential.candidate_id == candidate_id)
            .order_by(IssuedCredential.issued_at.desc())
        )
    )


async def revoke_own(
    session: AsyncSession, candidate_id: uuid.UUID, cid: uuid.UUID, reason: str = "holder_request"
) -> IssuedCredential:
    row = await session.get(IssuedCredential, cid)
    if row is None or row.candidate_id != candidate_id:
        raise ProblemError(404, "credential_not_found", "Бейдж не найден")
    if row.revoked_at is None:
        row.revoked_at, row.revoke_reason = utcnow(), reason
        await session.flush()
    return row


async def revoke_all(session: AsyncSession, candidate_id: uuid.UUID, reason: str) -> int:
    """Отзыв при удалении профиля или падении грейда: зовут владельцы событий."""
    now, n = utcnow(), 0
    for row in await list_own(session, candidate_id):
        if row.revoked_at is None:
            row.revoked_at, row.revoke_reason = now, reason
            n += 1
    await session.flush()
    return n


async def get_public(session: AsyncSession, cid: uuid.UUID) -> IssuedCredential | None:
    """Кредит, который можно показывать посторонним: не отозван и владелец публикует профиль."""
    row = await session.get(IssuedCredential, cid)
    if row is None or row.revoked_at is not None:
        return None
    cand = await candidates.get(session, row.candidate_id)
    if cand is None or not await _publishable(session, cand):
        return None
    return row


async def verify(session: AsyncSession, issuer: Issuer, cid: uuid.UUID) -> dict | None:
    """Результат проверки или `None` (нет такого или владелец скрыл публикацию, 404)."""
    row = await session.get(IssuedCredential, cid)
    if row is None:
        return None
    cand = await candidates.get(session, row.candidate_id)
    if cand is None or not await _publishable(session, cand):
        return None
    return check(issuer, row.credential, row)


async def verify_document(session: AsyncSession, issuer: Issuer, credential: dict) -> dict:
    """Проверка предъявленного документа: подпись по ключу издателя + статус в нашей базе."""
    row = None
    try:
        cid = uuid.UUID(str(credential.get("id", "")).rsplit("/", 1)[-1])
        row = await session.get(IssuedCredential, cid)
    except (ValueError, AttributeError):
        pass
    if row is not None:
        cand = await candidates.get(session, row.candidate_id)
        if cand is None or not await _publishable(session, cand):
            row = None  # владелец скрыл публикацию: наружу не раскрываем
    return check(issuer, credential, row)


def check(issuer: Issuer, credential: dict, row: IssuedCredential | None) -> dict:
    """Подпись + отзыв + срок. `row=None`: кредит неизвестен платформе."""
    proof = credential.get("proof") if isinstance(credential, dict) else None
    method = proof.get("verificationMethod") if isinstance(proof, dict) else None
    signature_ok = (
        method == issuer.key_id
        and isinstance(credential.get("issuer"), dict)
        and credential["issuer"].get("id") == issuer.did
        and signing.verify_document(credential, issuer.key.public_key())
    )
    revoked = row is not None and row.revoked_at is not None
    expired = True
    try:
        expired = _aware(datetime.fromisoformat(credential["validUntil"])) <= datetime.now(UTC)
    except (KeyError, TypeError, ValueError):
        pass
    known = row is not None and row.credential.get("id") == credential.get("id")
    return {
        "id": str(row.id) if row else None,
        "valid": bool(signature_ok and known and not revoked and not expired),
        "signature_valid": bool(signature_ok),
        "known": known,
        "revoked": revoked,
        "expired": expired,
        "issuer": issuer.did,
        "checked_at": _iso(utcnow()),
    }
