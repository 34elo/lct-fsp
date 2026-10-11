"""Песочница жюри: у каждого входа «Демо для жюри» свои кандидат и работодатель.

Пара аккаунтов `jury-<pair>-c@` / `jury-<pair>-e@demo.fsp.test` (`is_demo`): кандидат без грейда
(как `jury-candidate@`), работодатель с проверенной компанией «Жюри Демо · <pair>». Ключ пары
браузер хранит у себя: повторный вход той же ролью возвращает в ту же песочницу, другой ролью —
во вторую половину пары (работодатель видит своего кандидата и наоборот). Два члена жюри с
разными ключами действий друг друга не видят. Сбрасываются `demo-reset` (в снапшот не входят).
"""

from __future__ import annotations

import re
import secrets
from typing import Any, Literal

import structlog
from fsp_contracts.enums import ConsentType
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates import service as candidates
from app.companies import service as companies
from app.consents import service as consents
from app.identity import service as identity
from app.identity.models import User

log = structlog.get_logger()

Who = Literal["candidate", "employer"]
PAIR_RE = re.compile(r"^[0-9a-f]{12}$")
SANDBOX_EMAIL_RE = re.compile(r"^jury-([0-9a-f]{12})-([ce])@demo\.fsp\.test$")
BASE_JURY_CANDIDATE = "jury-candidate@demo.fsp.test"  # участник демо-реестра ФСП (r-jury)
JURY_PREFERENCES: dict[str, Any] = {
    "city": "Москва",
    "relocation": False,
    "salary_min": 100000,
    "formats": ["remote"],
    "employment_types": ["full"],
    "search_status": "active",
}


def sandbox_email(pair: str, who: Who) -> str:
    return f"jury-{pair}-{'c' if who == 'candidate' else 'e'}{identity.DEMO_EMAIL_DOMAIN}"


def new_pair() -> str:
    return secrets.token_hex(6)


async def enter(
    session: AsyncSession, who: Who, pair: str | None, *, pseudo_secret: str
) -> tuple[User, str, bool]:
    """Вход жюри: `(пользователь, ключ пары, создан ли сейчас)`. Неверный ключ — новая пара."""
    pair = pair if pair and PAIR_RE.fullmatch(pair) else new_pair()
    email = sandbox_email(pair, who)
    user = await session.scalar(select(User).where(User.email == email))
    if user is not None:
        return user, pair, False
    role = "candidate" if who == "candidate" else "employer"
    user = await identity.register(session, email, secrets.token_urlsafe(24), role)
    if who == "candidate":
        cand = await candidates.get_or_create(session, user.id, pseudo_secret)
        await candidates.update_preferences(session, cand, dict(JURY_PREFERENCES))
        await consents.set_consents(
            session,
            user.id,
            [(ConsentType(t), True, None) for t in ("pd_processing", "profile_publication")],
        )
    else:
        company = await companies.create_company(
            session,
            user,
            {
                "name": f"Жюри Демо · {pair[:4]}",
                "site": "https://jury-demo.example.test",
                "description": "Вымышленная компания для показа жюри.",
            },
        )
        await companies.verify(session, company.id)
    return user, pair, True


async def copy_fsp_registry(connector: Any, email: str) -> bool:
    """Свой участник демо-реестра ФСП с результатами `jury-candidate@` — чтобы «Привязать ФСП»
    сработала в каждой песочнице (участник привязывается только к одному аккаунту).
    Без коннектора или при ошибке — тихо `False`: вход жюри от ФСП не зависит."""
    try:
        found = await connector.registry(
            "GET", "/participants", params={"q": BASE_JURY_CANDIDATE, "limit": 5}
        )
        base = next((p for p in found or [] if p.get("email") == BASE_JURY_CANDIDATE), None)
        if base is None:
            return False
        results = await connector.registry("GET", "/results", params={"participant_id": base["id"]})
        new = await connector.registry(
            "POST", "/participants", json={"full_name": base["full_name"], "email": email}
        )
        for r in results or []:
            await connector.registry(
                "PUT",
                "/results",
                json={
                    "participant_id": new["id"],
                    "event_id": r["event_id"],
                    "place": r.get("place"),
                    "team": r.get("team"),
                },
            )
        return True
    except Exception as exc:  # noqa: BLE001 — реестр необязателен для входа
        log.warning("jury_fsp_copy_failed", error=type(exc).__name__)
        return False
