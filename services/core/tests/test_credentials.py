"""Open Badge 3.0: подпись eddsa-jcs-2022, did.json, проверка, видимость, чужое → 404."""

from __future__ import annotations

import copy
import uuid
from datetime import UTC, datetime

from app.candidates.models import Candidate
from app.consents.models import Consent
from app.credentials import signing
from app.credentials.models import IssuedCredential
from core_helpers import assert_foreign_is_404, register
from factories.base import make_grade
from fsp_contracts.enums import ConsentType
from fsp_platform.db import session_scope
from sqlalchemy import select


async def _setup(api, factory, *, public=True, consent=True, grade=True, profession="backend"):
    """Кандидат через API (токен) + условия публикации через БД. Возвращает `(headers, uid)`."""
    h = register(api)
    uid = uuid.UUID(api.get("/me", headers=h).json()["id"])
    assert api.get("/candidates/me/profile", headers=h).status_code == 200
    async with session_scope(factory) as s:
        cand = await s.get(Candidate, uid)
        cand.visibility = {**cand.visibility, "public_profile": public}
        if consent:
            s.add(
                Consent(
                    user_id=uid,
                    type=ConsentType.profile_publication,
                    version="2025-09-01",
                    granted_at=datetime.now(UTC),
                )
            )
        if grade:
            await make_grade(s, uid, profession, "middle")
    return h, uid


async def _issue(api, factory, **kw):
    h, uid = await _setup(api, factory, **kw)
    r = api.post("/me/credentials", json={}, headers=h)
    assert r.status_code == 201, r.text
    return h, uid, r.json()


# --- подпись ---


def test_sign_verify_roundtrip_and_tamper():
    key = signing.load_private_key("")
    pub = key.public_key()
    doc = {
        "@context": ["https://www.w3.org/ns/credentials/v2"],
        "id": "urn:x",
        "credentialSubject": {"grade": "middle"},
    }
    signed = signing.sign_document(
        doc, key, verification_method="did:web:x#key-1", created=datetime.now(UTC)
    )
    assert signed["proof"]["cryptosuite"] == "eddsa-jcs-2022"
    assert signed["proof"]["proofValue"].startswith("z")
    assert signing.verify_document(signed, pub)

    forged = copy.deepcopy(signed)
    forged["credentialSubject"]["grade"] = "senior"
    assert not signing.verify_document(forged, pub)

    other = signing.Ed25519PrivateKey.generate().public_key()
    assert not signing.verify_document(signed, other)

    no_proof = {k: v for k, v in signed.items() if k != "proof"}
    assert not signing.verify_document(no_proof, pub)
    broken = copy.deepcopy(signed)
    broken["proof"]["proofValue"] = "zOOO"  # символ вне алфавита base58
    assert not signing.verify_document(broken, pub)


def test_base58_and_multibase_roundtrip():
    for raw in (b"\x00\x00ab", b"hello world", bytes(range(40))):
        assert signing.b58decode(signing.b58encode(raw)) == raw
    key = signing.load_private_key("")
    mb = signing.public_multibase(key)
    assert mb.startswith("z6Mk")  # префикс ключей Ed25519 в multibase
    pub = signing.public_from_multibase(mb)
    assert signing.public_multibase(pub) == mb


# --- выпуск ---


async def test_issue_ok_and_shape(api, factory):
    h, uid, body = await _issue(api, factory)
    vc = body["credential"]
    assert vc["type"] == ["VerifiableCredential", "OpenBadgeCredential"]
    assert vc["issuer"]["id"] == "did:web:fsp.patissons.tech"
    assert "https://purl.imsglobal.org/spec/ob/v3p0/context-3.0.3.json" in vc["@context"]
    assert vc["credentialSubject"]["achievement"]["type"] == ["Achievement"]
    assert vc["proof"]["verificationMethod"] == "did:web:fsp.patissons.tech#key-1"
    assert body["profession"] == "backend" and body["grade"] == "middle"
    text = str(vc)
    assert "@" not in vc["credentialSubject"]["identifier"][0]["identityHash"]
    assert str(uid) not in text  # внутренний id кандидата не светим


async def test_issue_is_idempotent_for_same_grade(api, factory):
    h, _, first = await _issue(api, factory)
    second = api.post("/me/credentials", json={}, headers=h).json()
    assert second["id"] == first["id"]
    assert len(api.get("/me/credentials", headers=h).json()) == 1


async def test_issue_conditions(api, factory):
    h, _ = await _setup(api, factory, public=False)
    assert api.post("/me/credentials", json={}, headers=h).status_code == 409
    h, _ = await _setup(api, factory, consent=False)
    r = api.post("/me/credentials", json={}, headers=h)
    assert r.status_code == 409 and r.json()["code"] == "publication_required"
    h, _ = await _setup(api, factory, grade=False)
    r = api.post("/me/credentials", json={}, headers=h)
    assert r.status_code == 404 and r.json()["code"] == "grade_not_found"
    h, _ = await _setup(api, factory)
    assert api.post("/me/credentials", json={"profession": "qa"}, headers=h).status_code == 404


def test_issue_requires_candidate_role(api):
    assert api.post("/me/credentials", json={}).status_code == 401
    employer = register(api, role="employer")
    assert api.post("/me/credentials", json={}, headers=employer).status_code == 403


# --- публичные эндпоинты ---


async def test_did_json_matches_signing_key(api, factory):
    r = api.get("/.well-known/did.json")
    assert r.status_code == 200
    doc = r.json()
    assert doc["id"] == "did:web:fsp.patissons.tech"
    vm = doc["verificationMethod"][0]
    assert vm["id"] == "did:web:fsp.patissons.tech#key-1" and vm["type"] == "Multikey"
    assert doc["assertionMethod"] == [vm["id"]]
    # внешняя проверка: подпись выданного бейджа сходится с ключом из did.json
    _, _, body = await _issue(api, factory)
    pub = signing.public_from_multibase(vm["publicKeyMultibase"])
    fetched = api.get(f"/public/credentials/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.headers["content-type"].startswith("application/ld+json")
    assert signing.verify_document(fetched.json(), pub)


async def test_get_public_credential_and_verify(api, factory):
    _, _, body = await _issue(api, factory)
    cid = body["id"]
    assert api.get(f"/public/credentials/{cid}").json() == body["credential"]
    v = api.get(f"/public/credentials/{cid}/verify")
    assert v.status_code == 200
    out = v.json()
    assert out["valid"] is True and out["signature_valid"] is True
    assert out["revoked"] is False and out["expired"] is False
    assert out["issuer"] == "did:web:fsp.patissons.tech"


def test_unknown_credential_404(api):
    nope = uuid.uuid4()
    for url in (f"/public/credentials/{nope}", f"/public/credentials/{nope}/verify"):
        r = api.get(url)
        assert r.status_code == 404 and r.json()["code"] == "credential_not_found"
    assert api.get("/public/credentials/not-a-uuid").status_code == 422


async def test_verify_presented_document_forgery_rejected(api, factory):
    _, _, body = await _issue(api, factory)
    vc = body["credential"]
    ok = api.post("/public/credentials/verify", json=vc).json()
    assert ok["valid"] is True

    forged = copy.deepcopy(vc)
    forged["credentialSubject"]["achievement"]["name"] = "Подтверждено ФСП: Backend · Senior"
    bad = api.post("/public/credentials/verify", json=forged).json()
    assert bad["valid"] is False and bad["signature_valid"] is False

    # подпись чужого ключа с нашим verificationMethod
    stranger = signing.Ed25519PrivateKey.generate()
    unsigned = {k: v for k, v in vc.items() if k != "proof"}
    fake = signing.sign_document(
        unsigned,
        stranger,
        verification_method=vc["proof"]["verificationMethod"],
        created=datetime.now(UTC),
    )
    assert api.post("/public/credentials/verify", json=fake).json()["valid"] is False

    # подпись снята
    assert api.post("/public/credentials/verify", json=unsigned).json()["valid"] is False
    # мусор вместо документа
    assert api.post("/public/credentials/verify", json={"x": 1}).json()["valid"] is False


async def test_tampered_row_in_db_fails_verification(api, factory):
    _, _, body = await _issue(api, factory)
    async with session_scope(factory) as s:
        row = await s.get(IssuedCredential, uuid.UUID(body["id"]))
        vc = copy.deepcopy(row.credential)
        vc["credentialSubject"]["result"][0]["value"] = "senior"
        row.credential = vc
    out = api.get(f"/public/credentials/{body['id']}/verify").json()
    assert out["valid"] is False and out["signature_valid"] is False


# --- видимость и согласие ---


async def test_visibility_withdrawn_hides_credential(api, factory):
    h, uid, body = await _issue(api, factory)
    cid = body["id"]
    async with session_scope(factory) as s:
        cand = await s.get(Candidate, uid)
        cand.visibility = {**cand.visibility, "public_profile": False}
    assert api.get(f"/public/credentials/{cid}").status_code == 404
    assert api.get(f"/public/credentials/{cid}/verify").status_code == 404
    # предъявленный документ тоже не раскрывает статус
    r = api.post("/public/credentials/verify", json=body["credential"]).json()
    assert r["valid"] is False and r["known"] is False and r["id"] is None


async def test_consent_revoked_hides_credential(api, factory):
    h, uid, body = await _issue(api, factory)
    async with session_scope(factory) as s:
        rows = (await s.scalars(select(Consent).where(Consent.user_id == uid))).all()
        for c in rows:
            c.revoked_at = datetime.now(UTC)
    assert api.get(f"/public/credentials/{body['id']}").status_code == 404


# --- отзыв ---


async def test_revoke_own_then_verify_shows_revoked(api, factory):
    h, _, body = await _issue(api, factory)
    cid = body["id"]
    r = api.post(f"/me/credentials/{cid}/revoke", headers=h)
    assert r.status_code == 200 and r.json()["revoked_at"] is not None
    assert api.post(f"/me/credentials/{cid}/revoke", headers=h).status_code == 200  # идемпотентно
    assert api.get(f"/public/credentials/{cid}").status_code == 404
    v = api.get(f"/public/credentials/{cid}/verify").json()
    assert v["valid"] is False and v["revoked"] is True and v["signature_valid"] is True
    # после отзыва можно выпустить новый
    again = api.post("/me/credentials", json={}, headers=h)
    assert again.status_code == 201 and again.json()["id"] != cid


async def test_foreign_credential_is_404(api, factory):
    _, _, body = await _issue(api, factory)
    intruder = register(api)
    assert_foreign_is_404(api, "POST", f"/me/credentials/{body['id']}/revoke", intruder)
    assert_foreign_is_404(api, "POST", f"/me/credentials/{uuid.uuid4()}/revoke", intruder)
    assert api.get("/me/credentials", headers=intruder).json() == []
    # чужой бейдж не отозвался
    assert api.get(f"/public/credentials/{body['id']}/verify").json()["valid"] is True


async def test_grade_change_supersedes_old_credential(api, factory):
    h, uid, first = await _issue(api, factory)
    async with session_scope(factory) as s:
        from app.assessment.models import Grade

        g = await s.scalar(select(Grade).where(Grade.candidate_id == uid))
        g.grade = "senior"
        g.confirmed_at = datetime.now(UTC)
    second = api.post("/me/credentials", json={}, headers=h).json()
    assert second["id"] != first["id"] and second["grade"] == "senior"
    old = api.get(f"/public/credentials/{first['id']}/verify").json()
    assert old["revoked"] is True and old["valid"] is False
    assert api.get(f"/public/credentials/{second['id']}/verify").json()["valid"] is True
