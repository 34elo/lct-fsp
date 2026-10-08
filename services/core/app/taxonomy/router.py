"""`GET /taxonomy` (публичный, ETag) и `GET /internal/taxonomy/snapshot` (для ml)."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fsp_contracts.assessment import (
    ProfessionInfo,
    ProfessionSuggestion,
    SkillSuggestion,
    SkillType,
    TestGrade,
)
from fsp_contracts.enums import EmploymentType, Grade, WorkFormat
from fsp_platform.app import ProblemError
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_redis, get_session
from app.openapi_errors import problem_responses
from app.taxonomy import service, suggest
from app.taxonomy.loader import load_grade_cuts

DEFAULT_SCORING_PATH = Path(__file__).resolve().parents[4] / "data" / "scoring.yaml"

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


@router.get("/taxonomy", responses=problem_responses(503))
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


@router.get(
    "/internal/taxonomy/snapshot",
    dependencies=[Depends(require_ml)],
    responses=problem_responses(401, 503),
)
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


class GradeCut(BaseModel):
    grade: TestGrade
    cut: float  # минимальный θ грейда


class ProfessionsOut(BaseModel):
    professions: list[ProfessionInfo]
    skill_types: list[SkillType]
    grades: list[GradeCut]


@router.get(
    "/taxonomy/professions", response_model=ProfessionsOut, responses=problem_responses(503)
)
async def get_professions(
    request: Request, session: AsyncSession = Depends(get_session)
) -> ProfessionsOut:
    """Профессии теста, веса и типы навыков, грейды с порогами θ (assessment.md §10).

    `beta` — тонкий банк семейств (E39-6): профессия открыта, в опросе помечена «бета».
    """
    from app.assessment import service as assessment  # публичное API модуля, без цикла импорта

    path = Path(request.app.state.settings.scoring_config_path or DEFAULT_SCORING_PATH)
    cuts = load_grade_cuts(path)
    profs = await service.list_professions(session)
    beta = assessment.thin_professions(profs)
    return ProfessionsOut(
        professions=[p.model_copy(update={"beta": p.slug in beta}) for p in profs],
        skill_types=list(SkillType),
        grades=[GradeCut(grade=TestGrade(g), cut=c) for g, c in cuts.items()],
    )


SUGGEST_TTL = 600  # частоты навыков меняются без новой версии справочника: кеш короткий


async def _suggest_cached(redis: Redis, key: str, build) -> list[dict[str, Any]]:
    try:
        if (hit := await redis.get(key)) is not None:
            return json.loads(hit)
    except Exception:
        log.warning("taxonomy_suggest_cache_read_failed")
    items = [i.model_dump() for i in await build()]
    try:
        await redis.set(key, json.dumps(items, ensure_ascii=False), ex=SUGGEST_TTL)
    except Exception:
        log.warning("taxonomy_suggest_cache_write_failed")
    return items


def _sha(*parts: str) -> str:
    return hashlib.sha1("".join(parts).encode()).hexdigest()[:16]


@router.get(
    "/taxonomy/skills/suggest",
    response_model=list[SkillSuggestion],
    responses=problem_responses(422, 503),
)
async def suggest_skills(
    q: str = Query(default="", max_length=100),
    limit: int = Query(default=10, ge=1, le=50),
    profession: str | None = Query(default=None, max_length=32),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> list[dict[str, Any]]:
    """Подсказки навыков: синонимы, префикс, опечатки; частые выше, `provisional` помечен."""
    version = await service.get_version(session)
    key = f"c:tax:suggest:s:{version}:{_sha(suggest.norm_alias(q), str(limit), profession or '')}"
    return await _suggest_cached(
        redis, key, lambda: suggest.suggest_skills(session, q, limit, profession)
    )


@router.get(
    "/taxonomy/professions/suggest",
    response_model=list[ProfessionSuggestion],
    responses=problem_responses(422, 503),
)
async def suggest_professions(
    q: str = Query(default="", max_length=100),
    limit: int = Query(default=10, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> list[dict[str, Any]]:
    """Подсказки профессий: все видимые роли системы, включая добавленные админом (E39-3)."""
    version = await service.get_version(session)
    key = f"c:tax:suggest:p:{version}:{_sha(suggest.norm_alias(q), str(limit))}"
    return await _suggest_cached(redis, key, lambda: suggest.suggest_professions(session, q, limit))
