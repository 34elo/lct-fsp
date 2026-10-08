"""Подпись Data Integrity `eddsa-jcs-2022` (W3C VC Data Integrity EdDSA Cryptosuites v1.0).

Каноникализация — JCS (RFC 8785), подпись Ed25519, `proofValue` — multibase base58btc.
Для наших документов (только строки, целые, булевы, массивы, объекты) JCS совпадает с
`json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`; числа с плавающей
точкой в кредитах не используем.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import secrets
from datetime import datetime
from typing import Any

import structlog
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

log = structlog.get_logger()

CRYPTOSUITE = "eddsa-jcs-2022"
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_ED25519_MULTICODEC = b"\xed\x01"
_EPHEMERAL: dict[str, Ed25519PrivateKey] = {}


def jcs(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def b58encode(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = _B58[r] + out
    return "1" * (len(data) - len(data.lstrip(b"\0"))) + out


def b58decode(text: str) -> bytes:
    n = 0
    for ch in text:
        n = n * 58 + _B58.index(ch)  # ValueError на чужом символе
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return b"\0" * (len(text) - len(text.lstrip("1"))) + raw


def load_private_key(seed_b64: str) -> Ed25519PrivateKey:
    """Ключ из `OB_SIGNING_KEY` (seed 32 байта, base64url). Пусто: временный ключ процесса."""
    if not seed_b64:
        if "k" not in _EPHEMERAL:
            log.warning("ob_signing_key_missing_using_ephemeral")
            _EPHEMERAL["k"] = Ed25519PrivateKey.from_private_bytes(secrets.token_bytes(32))
        return _EPHEMERAL["k"]
    raw = base64.urlsafe_b64decode(seed_b64 + "=" * (-len(seed_b64) % 4))
    return Ed25519PrivateKey.from_private_bytes(raw)


def public_multibase(key: Ed25519PrivateKey | Ed25519PublicKey) -> str:
    pub = key.public_key() if isinstance(key, Ed25519PrivateKey) else key
    raw = pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return "z" + b58encode(_ED25519_MULTICODEC + raw)


def public_from_multibase(value: str) -> Ed25519PublicKey:
    raw = b58decode(value[1:])
    if not value.startswith("z") or not raw.startswith(_ED25519_MULTICODEC):
        raise ValueError("not an ed25519 multibase key")
    return Ed25519PublicKey.from_public_bytes(raw[2:])


def _hash_data(document: dict, proof_config: dict) -> bytes:
    return hashlib.sha256(jcs(proof_config)).digest() + hashlib.sha256(jcs(document)).digest()


def sign_document(
    document: dict, key: Ed25519PrivateKey, *, verification_method: str, created: datetime
) -> dict:
    """Возвращает копию документа с `proof` (`DataIntegrityProof`)."""
    unsecured = {k: v for k, v in document.items() if k != "proof"}
    config = {
        "type": "DataIntegrityProof",
        "cryptosuite": CRYPTOSUITE,
        "created": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "verificationMethod": verification_method,
        "proofPurpose": "assertionMethod",
        "@context": unsecured["@context"],
    }
    signature = key.sign(_hash_data(unsecured, config))
    proof = {k: v for k, v in config.items() if k != "@context"}
    proof["proofValue"] = "z" + b58encode(signature)
    return {**copy.deepcopy(unsecured), "proof": proof}


def verify_document(document: dict, public_key: Ed25519PublicKey) -> bool:
    """Проверка подписи. Любой дефект структуры — `False`, без исключений наружу."""
    try:
        proof = document["proof"]
        if proof["type"] != "DataIntegrityProof" or proof["cryptosuite"] != CRYPTOSUITE:
            return False
        value = proof["proofValue"]
        if not value.startswith("z"):
            return False
        unsecured = {k: v for k, v in document.items() if k != "proof"}
        config = {k: v for k, v in proof.items() if k != "proofValue"}
        config["@context"] = unsecured["@context"]
        public_key.verify(b58decode(value[1:]), _hash_data(unsecured, config))
        return True
    except (InvalidSignature, KeyError, TypeError, ValueError, AttributeError):
        return False
