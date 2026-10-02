"""`GET /taxonomy` (публичный, ETag) и `GET /internal/taxonomy/snapshot` (для ml)."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Header, Request, Response
from fsp_contracts.enums import EmploymentType, Grade, WorkFormat
from fsp_platform.app import ProblemError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_redis, get_session
from app.taxonomy import service

log = structlog.get_logger()
router = APIRouter(tags=["taxonomy"])
CACHE_TTL = 24 * 3600  # messaging.md: c:tax:{version}, версия в ключе — инвалидация не нужна


def _static_part() -> dict[str, list[str]]:
    return {
        "grades": [g.value for g in Grade],
        "formats": [f.value for f in WorkFormat],
        "employment_types": [e.value for e in EmploymentType],
    }


def _public(snap: dict[str, Any], version: int) -> dict[str, Any]:
    return {
        "version": version,
        "skills": [
            {k: s[k] for k in ("slug", "name", "kind", "group", "testable")}
            for s in snap["skills"]
            if s["status"] == "active"
        ],
        "roles": [{"slug": r["slug"], "name": r["name"]} for r in snap["roles"]],
        "disciplines": [{"slug": d["slug"], "name": d["name"]} for d in snap["disciplines"]],
        **_static_part(),
    }


async def _cached(redis: Redis, key: str, session: AsyncSession, build) -> bytes:
    try:
        if (hit := await redis.get(key)) is not None:
            return hit
    except Exception:  # Redis лежит: отдаём из БД
        log.warning("taxonomy_cache_read_failed")
    body = json.dumps(build(await service.build_snapshot(session)), ensure_ascii=False).encode()
    try:
        await redis.set(key, body, ex=CACHE_TTL)
    except Exception:
        log.warning("taxonomy_cache_write_failed")
    return body


@router.get("/taxonomy")
async def get_taxonomy(
    request: Request,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
    if_none_match: str | None = Header(default=None),
) -> Response:
    version = await service.get_version(session)
    static = hashlib.sha1(json.dumps(_static_part()).encode()).hexdigest()[:8]
    etag = f'W/"tax-{version}-{static}"'
    headers = {"ETag": etag, "Cache-Control": "public, max-age=300"}
    if if_none_match and etag in {t.strip() for t in if_none_match.split(",")}:
        return Response(status_code=304, headers=headers)
    body = await _cached(
        redis,
        f"c:tax:public:{version}:{static}",
        session,
        lambda snap: _public(snap, version),
    )
    return Response(body, media_type="application/json", headers=headers)


async def require_ml(request: Request, authorization: str | None = Header(default=None)) -> None:
    """`Authorization: Service <token>` (security.md §1); пустой токен в настройках = закрыто."""
    expected = request.app.state.settings.service_token_ml
    scheme, _, token = (authorization or "").partition(" ")
    if not (expected and scheme == "Service" and hmac.compare_digest(token, expected)):
        raise ProblemError(401, "unauthorized", "Нужен сервисный токен")


@router.get("/internal/taxonomy/snapshot", dependencies=[Depends(require_ml)])
async def internal_snapshot(
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> Response:
    version = await service.get_version(session)
    body = await _cached(
        redis,
        f"c:tax:{version}",
        session,
        lambda snap: {"version": version, **snap},
    )
    return Response(body, media_type="application/json")
