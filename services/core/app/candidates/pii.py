"""Шифрование ПДн анкеты (contacts_enc): Fernet, ключ `PII_KEY` (security.md §3)."""

from __future__ import annotations

import json

from cryptography.fernet import Fernet, InvalidToken


def encrypt_contacts(key: str, contacts: dict[str, str]) -> bytes:
    return Fernet(key.encode()).encrypt(json.dumps(contacts, ensure_ascii=False).encode())


def decrypt_contacts(key: str, blob: bytes | None) -> dict[str, str]:
    """Нечитаемое (ключ сменили) отдаём как пустые контакты, а не 500."""
    if not blob:
        return {}
    try:
        return json.loads(Fernet(key.encode()).decrypt(bytes(blob)))
    except (InvalidToken, ValueError):
        return {}
